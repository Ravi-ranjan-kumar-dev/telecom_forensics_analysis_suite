"""SQLite connection management for Telecom Forensics Suite."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from modules.core.paths import CGI_DATA_DIR, DATABASE_DIR, DATABASE_FILE

DEFAULT_DB_PATH = DATABASE_FILE


def get_db_path() -> Path:
    configured = os.environ.get("TELECOM_FORENSICS_DB", "").strip()
    return Path(configured).expanduser().resolve() if configured else DEFAULT_DB_PATH


def ensure_database_folders() -> None:
    db_dir = get_db_path().parent
    db_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    (db_dir / "backups").mkdir(parents=True, exist_ok=True, mode=0o700)
    (db_dir / "import_logs").mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ("raw", "processed", "rejected"):
        (CGI_DATA_DIR / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    for directory in (db_dir, db_dir / "backups", db_dir / "import_logs", CGI_DATA_DIR):
        try:
            os.chmod(directory, 0o700)
        except OSError:
            pass


def _configure_connection(
    conn: sqlite3.Connection,
    *,
    read_only: bool,
) -> sqlite3.Connection:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA cache_size = -65536")
    if read_only:
        conn.execute("PRAGMA query_only = ON")
    else:
        conn.execute("PRAGMA journal_mode = WAL")
        sync = os.environ.get("TELECOM_FORENSICS_SQLITE_SYNC", "FULL").upper()
        if sync not in {"OFF", "NORMAL", "FULL", "EXTRA"}:
            sync = "FULL"
        conn.execute(f"PRAGMA synchronous = {sync}")
        try:
            conn.execute("PRAGMA mmap_size = 268435456")
        except sqlite3.DatabaseError:
            pass
    return conn


def open_connection(*, read_only: bool = False) -> sqlite3.Connection:
    db_path = get_db_path()
    if read_only:
        if not db_path.is_file():
            raise FileNotFoundError(f"Database not found for read-only access: {db_path}")
        uri = f"{db_path.as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=30.0)
        return _configure_connection(conn, read_only=True)

    ensure_database_folders()
    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        os.chmod(db_path, 0o600)
    except OSError:
        pass
    return _configure_connection(conn, read_only=False)


@contextmanager
def database_connection(*, read_only: bool = False) -> Iterator[sqlite3.Connection]:
    conn = open_connection(read_only=read_only)
    try:
        yield conn
        if not read_only:
            conn.commit()
    except Exception:
        if not read_only:
            conn.rollback()
        raise
    finally:
        conn.close()
