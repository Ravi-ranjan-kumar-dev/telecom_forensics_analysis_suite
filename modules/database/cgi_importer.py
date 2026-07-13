"""Crash-resistant, streaming and batch-optimized CGI Excel/CSV importer."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tempfile
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from modules.core.time_utils import new_run_id, utc_now_iso

from .cgi_repository import clear_lookup_cache
from .connection import database_connection, get_db_path
from .normalization import build_column_map, detect_header_row, normalize_record
from .schema import backup_database, initialize_database

SUPPORTED_EXTENSIONS = {".xlsx", ".csv", ".tsv"}
SKIP_SHEET_WORDS = {"deleted", "obsolete", "old", "backup", "archive"}
BATCH_SIZE = 5000

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

DB_COLUMNS = [
    "cgi", "cgi_key", "mcc", "mnc", "lac", "tac", "cell_id", "enodeb_id",
    "local_cell_id", "technology", "site_id", "site_name", "cell_name", "latitude",
    "longitude", "azimuth", "address", "town", "block", "district", "state",
    "circle", "ssa", "pin_code", "operator", "vendor", "source_file",
    "source_sheet", "source_row",
]
UPDATE_COLUMNS = [column for column in DB_COLUMNS if column != "cgi_key"]
UPSERT_SQL = (
    f"INSERT INTO cgi_towers({','.join(DB_COLUMNS)}) "
    f"VALUES({','.join('?' for _ in DB_COLUMNS)}) "
    "ON CONFLICT(cgi_key) DO UPDATE SET "
    + ",".join(
        f"{column}=COALESCE(NULLIF(excluded.{column}, ''), cgi_towers.{column})"
        for column in UPDATE_COLUMNS
    )
    + ",updated_at=CURRENT_TIMESTAMP"
)


@dataclass
class ImportStats:
    source: str
    run_id: int | None = None
    files_found: int = 0
    files_completed: int = 0
    sheets_completed: int = 0
    rows_read: int = 0
    inserted: int = 0
    updated: int = 0
    rejected: int = 0
    skipped: int = 0
    status: str = "STARTED"
    message: str = ""
    backup_path: str = ""
    log_path: str = ""


def discover_files(source: str | Path) -> list[Path]:
    source_path = Path(source).expanduser().resolve()
    if source_path.is_file():
        return [source_path] if source_path.suffix.lower() in SUPPORTED_EXTENSIONS else []
    if source_path.is_dir():
        return sorted(
            path for path in source_path.rglob("*")
            if path.is_file()
            and path.suffix.lower() in SUPPORTED_EXTENSIONS
            and not path.name.startswith("~$")
        )
    return []


def _xlsx_target_path(target: str) -> str:
    target = target.replace("\\", "/")
    if target.startswith("/"):
        return target.lstrip("/")
    if target.startswith("xl/"):
        return target
    return f"xl/{target}"


def _load_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    strings: list[str] = []
    with archive.open("xl/sharedStrings.xml") as stream:
        for event, element in ET.iterparse(stream, events=("end",)):
            if element.tag == f"{{{MAIN_NS}}}si":
                strings.append("".join(node.text or "" for node in element.iter(f"{{{MAIN_NS}}}t")))
                element.clear()
    return strings


def _xlsx_sheet_targets(archive: ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in relationships.findall(f"{{{PKG_REL_NS}}}Relationship")
    }
    result: list[tuple[str, str]] = []
    sheets = workbook.find(f"{{{MAIN_NS}}}sheets")
    if sheets is None:
        return result
    for sheet in sheets:
        name = sheet.attrib.get("name", "Sheet")
        rel_id = sheet.attrib.get(f"{{{DOC_REL_NS}}}id", "")
        target = rel_map.get(rel_id)
        if target:
            result.append((name, _xlsx_target_path(target)))
    return result


def _column_index(cell_reference: str) -> int:
    letters = re.match(r"([A-Z]+)", cell_reference.upper())
    if not letters:
        return 0
    number = 0
    for char in letters.group(1):
        number = number * 26 + ord(char) - 64
    return number - 1


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> Any:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t"))
    value_node = cell.find(f"{{{MAIN_NS}}}v")
    if value_node is None:
        return ""
    raw = value_node.text or ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError):
            return raw
    if cell_type == "b":
        return "1" if raw == "1" else "0"
    return raw


def _iter_xlsx_rows(
    archive: ZipFile,
    sheet_target: str,
    shared_strings: list[str],
    *,
    start_row: int = 1,
    max_rows: int | None = None,
) -> Iterator[tuple[int, tuple[Any, ...]]]:
    emitted = 0
    with archive.open(sheet_target) as stream:
        for event, element in ET.iterparse(stream, events=("end",)):
            if element.tag != f"{{{MAIN_NS}}}row":
                continue
            row_number = int(element.attrib.get("r", "0") or 0)
            if row_number < start_row:
                element.clear()
                continue
            values: list[Any] = []
            for cell in element.findall(f"{{{MAIN_NS}}}c"):
                index = _column_index(cell.attrib.get("r", "A1"))
                if index >= len(values):
                    values.extend([""] * (index - len(values) + 1))
                values[index] = _cell_value(cell, shared_strings)
            yield row_number, tuple(values)
            emitted += 1
            element.clear()
            if max_rows is not None and emitted >= max_rows:
                break


def _iter_xlsx_sheets(path: Path) -> Iterator[tuple[str, list[tuple[Any, ...]], Iterator[tuple[int, tuple[Any, ...]]]]]:
    with ZipFile(path) as archive:
        shared_strings = _load_shared_strings(archive)
        for sheet_name, target in _xlsx_sheet_targets(archive):
            preview_pairs = list(
                _iter_xlsx_rows(
                    archive, target, shared_strings, start_row=1, max_rows=40
                )
            )
            preview_rows = [row for _, row in preview_pairs]
            header_index = detect_header_row(preview_rows)
            if header_index is None:
                yield sheet_name, [], iter(())
                continue
            header_row_number = preview_pairs[header_index][0]
            headers = preview_rows[header_index]
            rows = _iter_xlsx_rows(
                archive,
                target,
                shared_strings,
                start_row=header_row_number + 1,
            )
            yield sheet_name, [headers], rows


def _iter_csv_sheets(path: Path) -> Iterator[tuple[str, list[tuple[Any, ...]], Iterator[tuple[int, tuple[Any, ...]]]]]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    encoding_used = "utf-8-sig"
    try:
        handle = path.open("r", encoding=encoding_used, errors="strict", newline="")
        preview_lines = [handle.readline() for _ in range(40)]
    except UnicodeDecodeError:
        encoding_used = "latin-1"
        handle = path.open("r", encoding=encoding_used, errors="replace", newline="")
        preview_lines = [handle.readline() for _ in range(40)]
    preview = [tuple(row) for row in csv.reader(preview_lines, delimiter=delimiter)]
    header_index = detect_header_row(preview)
    handle.close()
    if header_index is None:
        yield path.stem, [], iter(())
        return
    headers = preview[header_index]

    def iterator() -> Iterator[tuple[int, tuple[Any, ...]]]:
        with path.open("r", encoding=encoding_used, errors="replace", newline="") as stream:
            reader = csv.reader(stream, delimiter=delimiter)
            for row_number, row in enumerate(reader, start=1):
                if row_number <= header_index + 1:
                    continue
                yield row_number, tuple(row)

    yield path.stem, [headers], iterator()


def _sheet_iterator(path: Path):
    return _iter_xlsx_sheets(path) if path.suffix.lower() == ".xlsx" else _iter_csv_sheets(path)


def _log_error(conn, stats: ImportStats, *, path: Path, sheet: str, row_number: int | None, error: Exception | str, raw: Any = None) -> None:
    if isinstance(error, Exception):
        error_type = type(error).__name__
        message = str(error)
    else:
        error_type = "ValidationError"
        message = str(error)
    try:
        raw_json = json.dumps(raw, ensure_ascii=False, default=str)[:10000]
    except Exception:
        raw_json = str(raw)[:10000]
    conn.execute(
        "INSERT INTO cgi_import_errors(run_id, source_file, source_sheet, source_row, error_type, error_message, raw_data) "
        "VALUES(?,?,?,?,?,?,?)",
        (stats.run_id, path.name, sheet, row_number, error_type, message[:2000], raw_json),
    )


def _record_values(record: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(record.get(column) if record.get(column) != "" else None for column in DB_COLUMNS)


def _flush_batch(conn, batch: list[dict[str, Any]], import_run_id: int | None) -> None:
    if not batch:
        return
    conn.executemany(UPSERT_SQL, [_record_values(record) for record in batch])
    keys = list(dict.fromkeys(record["cgi_key"] for record in batch))
    id_map: dict[str, int] = {}
    for start in range(0, len(keys), 800):
        chunk = keys[start:start + 800]
        placeholders = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"SELECT id, cgi_key FROM cgi_towers WHERE cgi_key IN ({placeholders})",
            chunk,
        ).fetchall()
        id_map.update({str(row["cgi_key"]): int(row["id"]) for row in rows})
    alias_rows: list[tuple[str, int, str]] = []
    for record in batch:
        tower_id = id_map.get(record["cgi_key"])
        if not tower_id:
            continue
        alias_rows.append((record["cgi_key"], tower_id, "cgi"))
        for alias_key, alias_type in record.get("aliases", []):
            if alias_key:
                alias_rows.append((alias_key, tower_id, alias_type))
    if alias_rows:
        conn.executemany(
            "INSERT OR IGNORE INTO cgi_aliases(alias_key, tower_id, alias_type) VALUES(?,?,?)",
            alias_rows,
        )

    provenance_rows: list[tuple[Any, ...]] = []
    imported_at = utc_now_iso(timespec="microseconds")
    for record in batch:
        tower_id = id_map.get(record["cgi_key"])
        if not tower_id:
            continue
        normalized = {
            key: value
            for key, value in record.items()
            if key != "aliases"
        }
        normalized_json = json.dumps(
            normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        )
        provenance_rows.append(
            (
                tower_id, import_run_id, str(record.get("source_file", "")),
                str(record.get("source_sheet", "")), record.get("source_row"),
                hashlib.sha256(normalized_json.encode("utf-8")).hexdigest(),
                normalized_json, imported_at,
            )
        )
    if provenance_rows:
        conn.executemany(
            "INSERT OR IGNORE INTO cgi_source_records("
            "tower_id, import_run_id, source_file, source_sheet, source_row, "
            "source_record_sha256, normalized_record_json, imported_at"
            ") VALUES(?,?,?,?,?,?,?,?)",
            provenance_rows,
        )


def _checkpoint(conn, stats: ImportStats, status: str = "RUNNING") -> None:
    conn.execute(
        "UPDATE cgi_import_runs SET status=?, files_completed=?, sheets_completed=?, rows_read=?, "
        "inserted=?, updated=?, rejected=?, skipped=?, message=? WHERE id=?",
        (
            status, stats.files_completed, stats.sheets_completed, stats.rows_read,
            stats.inserted, stats.updated, stats.rejected, stats.skipped,
            stats.message, stats.run_id,
        ),
    )


def _write_json_log(stats: ImportStats) -> Path:
    log_dir = get_db_path().parent / "import_logs"
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_path = log_dir / f"cgi_import_{new_run_id('run')}.json"
    stats.log_path = str(log_path)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{log_path.name}.", suffix=".tmp", dir=str(log_dir)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(asdict(stats), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, log_path)
        try:
            os.chmod(log_path, 0o600)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    return log_path


def import_cgi_data(
    source: str | Path,
    *,
    include_deleted_sheets: bool = False,
    create_backup: bool = True,
    dry_run: bool = False,
) -> ImportStats:
    initialize_database()
    files = discover_files(source)
    stats = ImportStats(source=str(Path(source).expanduser()), files_found=len(files))
    if not files:
        stats.status = "FAILED"
        stats.message = "No supported .xlsx/.csv/.tsv files found"
        _write_json_log(stats)
        return stats
    if create_backup and not dry_run:
        backup = backup_database("before_cgi_import")
        stats.backup_path = str(backup) if backup else ""

    with database_connection() as conn:
        now = utc_now_iso(timespec="microseconds")
        conn.execute(
            "UPDATE cgi_import_runs SET status='INTERRUPTED', completed_at=?, "
            "message=COALESCE(message,'') || ' Previous process did not finish cleanly.' "
            "WHERE status='RUNNING'",
            (now,),
        )
        cursor = conn.execute(
            "INSERT INTO cgi_import_runs(started_at, source, status, files_found) VALUES(?,?,?,?)",
            (now, stats.source, "RUNNING", stats.files_found),
        )
        stats.run_id = int(cursor.lastrowid)
        conn.commit()

        existing_keys = {str(row[0]) for row in conn.execute("SELECT cgi_key FROM cgi_towers")}
        seen_this_run: set[str] = set()

        for path in files:
            file_ok = False
            try:
                for sheet_name, header_rows, rows in _sheet_iterator(path):
                    if not include_deleted_sheets and any(word in sheet_name.lower() for word in SKIP_SHEET_WORDS):
                        stats.skipped += 1
                        _checkpoint(conn, stats)
                        conn.commit()
                        continue
                    if not header_rows:
                        stats.skipped += 1
                        _log_error(conn, stats, path=path, sheet=sheet_name, row_number=None, error="Recognized CGI header not found")
                        _checkpoint(conn, stats)
                        conn.commit()
                        continue

                    column_map = build_column_map(header_rows[0])
                    batch: list[dict[str, Any]] = []
                    for row_number, row in rows:
                        if not any(value not in (None, "") for value in row):
                            continue
                        stats.rows_read += 1
                        try:
                            record, validation_error = normalize_record(
                                row,
                                column_map,
                                source_file=path.name,
                                source_sheet=sheet_name,
                                source_row=row_number,
                            )
                            if record is None:
                                stats.rejected += 1
                                _log_error(
                                    conn, stats, path=path, sheet=sheet_name,
                                    row_number=row_number,
                                    error=validation_error or "Invalid row", raw=row,
                                )
                                continue
                            key = record["cgi_key"]
                            if key in existing_keys or key in seen_this_run:
                                stats.updated += 1
                            else:
                                stats.inserted += 1
                                seen_this_run.add(key)
                            if not dry_run:
                                batch.append(record)
                                if len(batch) >= BATCH_SIZE:
                                    _flush_batch(conn, batch, stats.run_id)
                                    _checkpoint(conn, stats)
                                    conn.commit()
                                    batch.clear()
                        except Exception as row_error:
                            stats.rejected += 1
                            _log_error(
                                conn, stats, path=path, sheet=sheet_name,
                                row_number=row_number, error=row_error, raw=row,
                            )

                    if not dry_run and batch:
                        _flush_batch(conn, batch, stats.run_id)
                    stats.sheets_completed += 1
                    _checkpoint(conn, stats)
                    conn.commit()
                    file_ok = True
                if file_ok:
                    stats.files_completed += 1
                    _checkpoint(conn, stats)
                    conn.commit()
            except Exception as file_error:
                conn.rollback()
                _log_error(
                    conn, stats, path=path, sheet="", row_number=None,
                    error=file_error, raw=traceback.format_exc(),
                )
                stats.message = f"Some files had errors; see import log. Last: {path.name}"
                _checkpoint(conn, stats)
                conn.commit()

        stats.status = "DRY_RUN_OK" if dry_run else "COMPLETED"
        integrity_row = conn.execute("PRAGMA quick_check").fetchone()
        integrity = str(integrity_row[0]) if integrity_row else "No result"
        if integrity.lower() != "ok":
            stats.status = "COMPLETED_WITH_WARNING"
            stats.message = f"Database integrity warning: {integrity}"
        conn.execute(
            "UPDATE cgi_import_runs SET completed_at=?, status=?, files_completed=?, sheets_completed=?, "
            "rows_read=?, inserted=?, updated=?, rejected=?, skipped=?, message=? WHERE id=?",
            (
                utc_now_iso(timespec="microseconds"), stats.status,
                stats.files_completed, stats.sheets_completed, stats.rows_read,
                stats.inserted, stats.updated, stats.rejected, stats.skipped,
                stats.message, stats.run_id,
            ),
        )
        conn.commit()

    clear_lookup_cache()
    _write_json_log(stats)
    return stats
