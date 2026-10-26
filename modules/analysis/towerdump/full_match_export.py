"""Export all matches from verified Tower CDR/GPRS/IPDR stages without pandas loading.

The export is a fresh, exact-match, selection-verified SQL query. The GUI preview
and any cached preview DataFrame are never used to populate this export.
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


class SearchExportError(RuntimeError):
    pass


def _ident(s: str) -> str:
    return '"' + str(s).replace('"', '""') + '"'


def _digits(col: str) -> str:
    raw = f"TRIM(COALESCE(CAST(e.{_ident(col)} AS VARCHAR), ''))"
    stripped = (f"CASE WHEN regexp_matches({raw}, '^[0-9]+[.]0+$') "
                f"THEN split_part({raw}, '.', 1) ELSE {raw} END")
    return f"regexp_replace(({stripped}), '[^0-9]', '', 'g')"


def _mobile(col: str) -> str:
    value = _digits(col)
    return (f"CASE WHEN length({value}) = 12 AND starts_with({value}, '91') "
            f"THEN right({value},10) WHEN length({value}) = 11 "
            f"AND starts_with({value}, '0') THEN right({value},10) ELSE {value} END")


COMPACT_COLUMNS = {
    "cdr": (
        "subscriber_number", "other_party", "b_party", "call_datetime", "call_date",
        "call_type", "call_duration", "imei", "imsi", "searched_cell_id",
        "cgi", "spot_name", "spot_id", "source_file", "source_relative_path",
        "source_row_number",
    ),
    "gprs": (
        "subscriber_number", "imei", "imsi", "session_start", "session_end",
        "session_duration_seconds", "ipv4_address", "ipv6_address",
        "uplink_volume", "downlink_volume", "total_volume", "searched_cell_id",
        "spot_name", "spot_id", "source_file", "source_relative_path",
        "source_row_number",
    ),
    "ipdr": (
        "subscriber_number", "imei", "imsi", "event_time", "event_duration_seconds",
        "source_ip", "source_port", "translated_ip", "translated_port",
        "destination_ip", "destination_port", "allocation_start", "allocation_end",
        "searched_cell_id", "spot_name", "spot_id", "source_file",
        "source_relative_path", "source_row_number",
    ),
}
INVALID_EXCEL = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]")


def _targets(query: object) -> tuple[list[str], list[str], list[str]]:
    from modules.analysis.towerdump.full_dump_search import parse_target_numbers
    items = parse_target_numbers(query)
    if not 1 <= len(items) <= 100:
        raise ValueError("Enter 1–100 unique mobile numbers, IMEIs or IMSIs.")
    bad = [x for x in items if not (len(x) == 10 or 14 <= len(x) <= 16)]
    if bad:
        raise ValueError("Only exact 10-digit mobile and 14–16 digit device/SIM IDs are supported.")
    return items, [x for x in items if len(x) == 10], [x for x in items if len(x) >= 14]


def _stage(request: dict[str, Any]):
    """Return mode, source SQL, expected row count, file db path (or None)."""
    mode = str(request["source_type"]).strip().lower()
    if mode not in COMPACT_COLUMNS:
        raise SearchExportError("Unsupported Tower Dump source type.")
    case = str(request["case_id"])
    folder = Path(request["input_folder"]).expanduser().resolve()
    if not folder.is_dir():
        raise SearchExportError("Selected evidence folder no longer exists.")
    selection = request.get("selected_spot_folders")
    include_root = bool(request.get("include_root_files", True))
    if mode == "cdr":
        from modules.staging.tower_cdr_staging import (
            tower_cdr_input_fingerprint, load_latest_tower_cdr_stage, tower_cdr_parquet_path,
        )
        stage = load_latest_tower_cdr_stage(case)
        if not isinstance(stage, dict) or not isinstance(stage.get("input_fingerprint"), dict):
            raise SearchExportError("No verified CDR stage. Run Complete Analysis first.")
        current = tower_cdr_input_fingerprint(
            folder, selected_spot_folders=selection, include_root_files=include_root,
        )
        if not current.get("file_count") or current != stage["input_fingerprint"]:
            raise SearchExportError("CDR evidence or Spots changed. Rerun Complete Analysis before export.")
        path = tower_cdr_parquet_path(case)
        if not path.is_file():
            raise SearchExportError("Verified CDR Parquet stage is missing.")
        expected = int(stage.get("record_count", 0) or 0)
        if expected <= 0:
            raise SearchExportError("CDR stage record count is invalid.")
        return mode, "read_parquet(?)", [str(path.resolve())], None, expected
    if mode == "gprs":
        from modules.analysis.towerdump.verified_session_search import _verified_gprs
        path_sql, expected = _verified_gprs(case, folder, selection, include_root)
        # _verified_gprs constructs the SQL from a verified canonical Parquet path.
        return mode, path_sql, [], None, expected
    from modules.analysis.towerdump.verified_session_search import _verified_ipdr
    db_path, table, expected = _verified_ipdr(case, folder, selection, include_root)
    return mode, table, [], str(db_path), expected


def _filter_sql(mode: str, columns: set[str], mobiles: list[str], devices: list[str]):
    filters: list[str] = []
    params: list[str] = []
    for col in (("subscriber_number", "other_party", "b_party") if mode == "cdr" else ("subscriber_number",)):
        if col not in columns or not mobiles:
            continue
        filters.append(f"({_mobile(col)}) IN ({','.join('?' for _ in mobiles)})")
        params.extend(mobiles)
    for col in ("imei", "imsi"):
        if col not in columns or not devices:
            continue
        filters.append(f"({_digits(col)}) IN ({','.join('?' for _ in devices)})")
        params.extend(devices)
    if not filters:
        raise SearchExportError("The staged evidence has no columns matching the identifier types searched.")
    return " OR ".join(filters), params


def _csv_value(val: object):
    """Neutralize formula injection if CSV is later opened in a spreadsheet."""
    if val is None:
        return ""
    if isinstance(val, str):
        s = val.replace("\x00", "")
        if s.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + s
        return s
    return val


def _xlsx_text(val: object):
    if val is None:
        return None
    if isinstance(val, (bytes, bytearray)):
        val = bytes(val).hex()
    if isinstance(val, str):
        return INVALID_EXCEL.sub("", val)[:32767]
    if isinstance(val, int) and len(str(abs(val))) > 15:
        return str(val)
    if isinstance(val, datetime) and val.tzinfo is not None:
        return val.isoformat()
    return val


def _write_rows(path: Path, extension: str, header: list[str], cursor,
                *, case_id: str, source_type: str, targets: list[str],
                matched_total: int, progress: Callable[[int], None] | None):
    rows = 0
    if extension == ".csv":
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, dialect="excel")
            writer.writerow(header)
            while True:
                batch = cursor.fetchmany(2000)
                if not batch:
                    break
                writer.writerows([_csv_value(x) for x in row] for row in batch)
                rows += len(batch)
                if progress:
                    progress(rows)
    else:
        from openpyxl import Workbook
        from openpyxl.cell import WriteOnlyCell
        book = Workbook(write_only=True)
        # One header row per sheet. Do not silently truncate on Excel limit.
        sheet = None
        sheet_rows = 0
        sheet_num = 0
        def next_sheet():
            nonlocal sheet, sheet_rows, sheet_num
            sheet_num += 1
            sheet = book.create_sheet(f"Matched_{sheet_num:03d}")
            sheet.append(header)
            sheet_rows = 1
        next_sheet()
        while True:
            batch = cursor.fetchmany(2000)
            if not batch:
                break
            for row in batch:
                if sheet_rows >= 1_048_576:
                    next_sheet()
                safe = []
                for val in row:
                    transformed = _xlsx_text(val)
                    if isinstance(transformed, str):
                        c = WriteOnlyCell(sheet, value=transformed)
                        c.data_type = "s"  # Never interpret untrusted evidence as a formula.
                        safe.append(c)
                    else:
                        safe.append(transformed)
                sheet.append(safe)
                rows += 1
                sheet_rows += 1
            if progress:
                progress(rows)
        info = book.create_sheet("Export_Info")
        for pair in (("Case ID", case_id), ("Source Mode", source_type.upper()),
                     ("Targets", ", ".join(targets)), ("Full Matched Records", matched_total),
                     ("Exported Records", rows),
                     ("Exported At UTC", datetime.now(timezone.utc).isoformat()),
                     ("Columns", "Compact evidence and provenance fields"),
                     ("Notes", "All matching records, not GUI preview; raw evidence unmodified")):
            info.append(pair)
        book.save(path)
    return rows


def export_all_matches(
    request: dict[str, Any], destination: str | Path,
    *, progress: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """Stream all verified SQL matches to atomic CSV/XLSX output.

    The row count is checked before committing the output. Errors leave the
    destination untouched. Raw evidence is always read-only.
    """
    if not isinstance(request, dict) or not all(request.get(k) is not None for k in
       ("case_id", "source_type", "input_folder", "query")):
        raise SearchExportError("Search context is missing. Run Full Dump Search again.")
    dest = Path(destination).expanduser().resolve()
    extension = dest.suffix.lower()
    if extension not in {".csv", ".xlsx"}:
        raise ValueError("Choose CSV (.csv) or Excel (.xlsx).")
    if not dest.parent.is_dir():
        raise SearchExportError("Export directory does not exist.")
    folder = Path(request["input_folder"]).expanduser().resolve()
    if dest.is_relative_to(folder):
        raise SearchExportError("Choose a destination OUTSIDE the raw evidence folder.")
    targets, mobiles, devices = _targets(request["query"])
    mode, source, source_params, database_path, expected = _stage(request)
    import duckdb

    # Open the staged case database in read-only mode; in-memory connections
    # read staged Parquet files without modifying persistent database files.
    con = duckdb.connect(database=database_path, read_only=True) if database_path else duckdb.connect(database=":memory:")
    try:
        # First read columns, then construct safe, parameterized filter expressions.
        desc = con.execute(f"SELECT * FROM {source} AS e LIMIT 0", source_params).description
        all_cols = [item[0] for item in desc]
        cols = set(all_cols)
        export_cols = [x for x in COMPACT_COLUMNS[mode] if x in cols]
        if not export_cols:
            raise SearchExportError("No investigation columns found in the verified stage.")
        where, values = _filter_sql(mode, cols, mobiles, devices)
        total = int(con.execute(f"SELECT COUNT(*) FROM {source}", source_params).fetchone()[0])
        if expected is not None and total != expected:
            raise SearchExportError("Staging row count changed. Rerun Complete Analysis.")
        count_sql = f"SELECT COUNT(*) FROM {source} AS e WHERE {where}"
        matched = int(con.execute(count_sql, [*source_params, *values]).fetchone()[0])
        select_sql = (f"SELECT {', '.join('e.'+_ident(c) for c in export_cols)} "
                      f"FROM {source} AS e WHERE {where}")
        # SQL reuses the same row-filter as count, with one row per evidence record.
        cursor = con.execute(select_sql, [*source_params, *values])
        fd, temporary = tempfile.mkstemp(prefix=".ethicalarmor_export_", suffix=extension, dir=dest.parent)
        os.close(fd)
        tmp_path = Path(temporary)
        try:
            exported = _write_rows(tmp_path, extension, export_cols, cursor,
                                   case_id=str(request["case_id"]), source_type=mode,
                                   targets=targets, matched_total=matched, progress=progress)
            if exported != matched:
                raise SearchExportError(f"Export incomplete: wrote {exported:,} of {matched:,} matching records.")
            # Recheck selection against current evidence before making final output visible.
            _stage(request)
            digest = hashlib.sha256()
            with tmp_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(2 * 1024 * 1024), b""):
                    digest.update(chunk)
            os.replace(tmp_path, dest)
            return {"path": str(dest), "rows": exported, "total_records": total,
                    "sha256": digest.hexdigest(), "source_type": mode, "targets": targets,
                    "columns": len(export_cols)}
        finally:
            tmp_path.unlink(missing_ok=True)
    finally:
        con.close()
