"""Versioned database schema, migrations, backup and integrity utilities."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from modules.core.time_utils import new_run_id, utc_now_iso

from .connection import database_connection, ensure_database_folders, get_db_path

SCHEMA_VERSION = 2

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cgi_towers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cgi TEXT NOT NULL,
    cgi_key TEXT NOT NULL UNIQUE,
    mcc TEXT, mnc TEXT, lac TEXT, tac TEXT, cell_id TEXT,
    enodeb_id TEXT, local_cell_id TEXT, technology TEXT,
    site_id TEXT, site_name TEXT, cell_name TEXT,
    latitude REAL, longitude REAL, azimuth REAL,
    address TEXT, town TEXT, block TEXT, district TEXT, state TEXT,
    circle TEXT, ssa TEXT, pin_code TEXT, operator TEXT, vendor TEXT,
    source_file TEXT, source_sheet TEXT, source_row INTEGER,
    first_imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cgi_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias_key TEXT NOT NULL,
    tower_id INTEGER NOT NULL,
    alias_type TEXT NOT NULL,
    FOREIGN KEY (tower_id) REFERENCES cgi_towers(id) ON DELETE CASCADE,
    UNIQUE(alias_key, tower_id, alias_type)
);

CREATE TABLE IF NOT EXISTS cgi_import_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    files_found INTEGER NOT NULL DEFAULT 0,
    files_completed INTEGER NOT NULL DEFAULT 0,
    sheets_completed INTEGER NOT NULL DEFAULT 0,
    rows_read INTEGER NOT NULL DEFAULT 0,
    inserted INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    rejected INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    message TEXT
);

CREATE TABLE IF NOT EXISTS cgi_import_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    source_file TEXT, source_sheet TEXT, source_row INTEGER,
    error_type TEXT, error_message TEXT, raw_data TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES cgi_import_runs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS cgi_source_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tower_id INTEGER NOT NULL,
    import_run_id INTEGER,
    source_file TEXT NOT NULL,
    source_sheet TEXT,
    source_row INTEGER,
    source_record_sha256 TEXT NOT NULL,
    normalized_record_json TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    FOREIGN KEY (tower_id) REFERENCES cgi_towers(id) ON DELETE CASCADE,
    FOREIGN KEY (import_run_id) REFERENCES cgi_import_runs(id) ON DELETE SET NULL,
    UNIQUE(tower_id, source_file, source_sheet, source_row, source_record_sha256)
);

CREATE INDEX IF NOT EXISTS idx_cgi_towers_cgi_key ON cgi_towers(cgi_key);
CREATE INDEX IF NOT EXISTS idx_cgi_towers_lac_cell ON cgi_towers(lac, cell_id);
CREATE INDEX IF NOT EXISTS idx_cgi_towers_tac_cell ON cgi_towers(tac, cell_id);
CREATE INDEX IF NOT EXISTS idx_cgi_towers_cell_id ON cgi_towers(cell_id);
CREATE INDEX IF NOT EXISTS idx_cgi_towers_enodeb ON cgi_towers(enodeb_id, local_cell_id);
CREATE INDEX IF NOT EXISTS idx_cgi_towers_location ON cgi_towers(district, state, circle);
CREATE INDEX IF NOT EXISTS idx_cgi_aliases_key ON cgi_aliases(alias_key);
CREATE INDEX IF NOT EXISTS idx_cgi_import_errors_run ON cgi_import_errors(run_id);
CREATE INDEX IF NOT EXISTS idx_cgi_source_tower ON cgi_source_records(tower_id);
CREATE INDEX IF NOT EXISTS idx_cgi_source_run ON cgi_source_records(import_run_id);
"""


def _read_existing_version(path: Path) -> int:
    if not path.is_file() or path.stat().st_size == 0:
        return 0
    try:
        conn = sqlite3.connect(path)
        try:
            pragma_version = int(conn.execute("PRAGMA user_version").fetchone()[0] or 0)
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'"
            ).fetchone()
            if table:
                row = conn.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()
                if row:
                    return int(row[0])
            return pragma_version
        finally:
            conn.close()
    except (sqlite3.DatabaseError, ValueError, TypeError):
        return 0


def backup_database(label: str = "manual", *, initialize: bool = True) -> Path | None:
    if initialize:
        initialize_database(create_migration_backup=False)
    source = get_db_path()
    if not source.exists() or source.stat().st_size == 0:
        return None
    destination = (
        source.parent
        / "backups"
        / f"{source.stem}_{label}_{new_run_id('backup')}.db"
    )
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    source_conn = sqlite3.connect(source)
    destination_conn = sqlite3.connect(destination)
    try:
        source_conn.backup(destination_conn)
        destination_conn.commit()
    finally:
        destination_conn.close()
        source_conn.close()
    try:
        os.chmod(destination, 0o600)
    except OSError:
        pass
    return destination


def initialize_database(*, create_migration_backup: bool = True) -> Path:
    ensure_database_folders()
    path = get_db_path()
    existing_database = path.is_file() and path.stat().st_size > 0
    current = _read_existing_version(path)
    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema v{current} is newer than supported v{SCHEMA_VERSION}."
        )
    if existing_database and current < SCHEMA_VERSION and create_migration_backup:
        backup_database(f"pre_migration_v{current}", initialize=False)

    with database_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),),
        )
        conn.execute(
            "INSERT INTO schema_meta(key, value) VALUES('last_migrated_at', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (utc_now_iso(timespec="microseconds"),),
        )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return path


def quick_integrity_check() -> tuple[bool, str]:
    try:
        initialize_database()
        with database_connection(read_only=True) as conn:
            result = conn.execute("PRAGMA quick_check").fetchone()
        message = str(result[0]) if result else "No result"
        return message.lower() == "ok", message
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
