"""DuckDB staging importer for Tower IPDR/NAT dumps.

Production goal:
- Do not concatenate all Tower IPDR files into one huge pandas DataFrame.
- Load one source file at a time.
- Normalize with the existing verified loader.
- Append normalized events into DuckDB.
- Save a resumable manifest.
- Run later analysis using SQL instead of full pandas memory.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from modules.loader.tower_ipdr_loader import (
    NORMALIZED_COLUMNS,
    SUPPORTED_SUFFIXES,
    load_tower_ipdr_file,
)
from modules.staging.duckdb_store import DuckDBStore
from modules.staging.manifest import calculate_sha256


TABLE_EVENTS = "tower_ipdr_events"
TABLE_FILE_SUMMARY = "tower_ipdr_file_summary"


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _json_safe(value: Any) -> Any:
    """Convert pandas/path/datetime values into JSON-safe values."""

    if value is None:
        return None

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, (pd.Timestamp, datetime)):
        if pd.isna(value):
            return ""
        return value.isoformat(sep=" ")

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            _json_safe(item)
            for item in value
        ]

    if isinstance(value, tuple):
        return [
            _json_safe(item)
            for item in value
        ]

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    return value


def tower_ipdr_staging_root(case_id: str) -> Path:
    return (
        Path("cases")
        / "active"
        / str(case_id)
        / "staging"
        / "tower_ipdr"
    )


def tower_ipdr_database_path(case_id: str) -> Path:
    return tower_ipdr_staging_root(case_id) / "tower_ipdr.duckdb"


def tower_ipdr_manifest_path(case_id: str) -> Path:
    return tower_ipdr_staging_root(case_id) / "manifest.json"


def _read_manifest(case_id: str) -> dict[str, Any]:
    path = tower_ipdr_manifest_path(case_id)

    if not path.exists():
        return {
            "case_id": str(case_id),
            "staging_type": "TOWER_IPDR_DUCKDB",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "files": [],
        }

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "case_id": str(case_id),
            "staging_type": "TOWER_IPDR_DUCKDB",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "files": [],
            "manifest_warning": "Previous manifest could not be read.",
        }


def _write_manifest(case_id: str, manifest: dict[str, Any]) -> None:
    root = tower_ipdr_staging_root(case_id)
    root.mkdir(parents=True, exist_ok=True)

    manifest["updated_at"] = _now_iso()

    path = tower_ipdr_manifest_path(case_id)
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    tmp_path.write_text(
        json.dumps(
            _json_safe(manifest),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    tmp_path.replace(path)


def _manifest_file_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = manifest.get("files", [])

    if not isinstance(records, list):
        return {}

    result: dict[str, dict[str, Any]] = {}

    for item in records:
        if not isinstance(item, dict):
            continue

        sha256 = str(item.get("sha256", "")).strip()
        source_path = str(item.get("source_path", "")).strip()

        key = sha256 or source_path

        if key:
            result[key] = item

    return result


def _upsert_manifest_file(
    manifest: dict[str, Any],
    record: dict[str, Any],
) -> None:
    files = manifest.setdefault("files", [])

    if not isinstance(files, list):
        manifest["files"] = []
        files = manifest["files"]

    record_key = str(record.get("sha256") or record.get("source_path") or "")

    for index, existing in enumerate(files):
        if not isinstance(existing, dict):
            continue

        existing_key = str(
            existing.get("sha256")
            or existing.get("source_path")
            or ""
        )

        if existing_key == record_key:
            files[index] = record
            return

    files.append(record)


def _candidate_files(input_folder: str | Path, recursive: bool = True) -> list[Path]:
    folder = Path(input_folder).expanduser().resolve()

    if not folder.is_dir():
        raise FileNotFoundError(f"Input folder not found: {folder}")

    iterator = folder.rglob("*") if recursive else folder.glob("*")

    return sorted(
        path
        for path in iterator
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_SUFFIXES
    )


def _file_summary_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for record in records:
        metadata = record.get("metadata", {})

        if not isinstance(metadata, dict):
            metadata = {}

        rows.append(
            {
                "file_name": record.get("file_name", ""),
                "source_path": record.get("source_path", ""),
                "sha256": record.get("sha256", ""),
                "status": record.get("status", ""),
                "rows_loaded": record.get("rows_loaded", 0),
                "searched_cell_id": metadata.get("searched_cell_id", ""),
                "event_time_min": metadata.get("event_time_min", ""),
                "event_time_max": metadata.get("event_time_max", ""),
                "unique_subscribers": metadata.get("unique_subscribers", 0),
                "warnings": " | ".join(record.get("warnings", []) or []),
                "errors": " | ".join(record.get("errors", []) or []),
                "loaded_at": record.get("loaded_at", ""),
            }
        )

    return pd.DataFrame(rows)


def import_tower_ipdr_folder_to_duckdb(
    case_id: str,
    input_folder: str | Path,
    *,
    recursive: bool = True,
    force_rebuild: bool = False,
    max_files: int | None = None,
) -> dict[str, Any]:
    """Import Tower IPDR files into case DuckDB staging.

    This is intentionally file-by-file, not folder-concat.
    """

    root = tower_ipdr_staging_root(case_id)
    root.mkdir(parents=True, exist_ok=True)

    database_path = tower_ipdr_database_path(case_id)
    manifest = _read_manifest(case_id)
    manifest_map = _manifest_file_map(manifest)

    store = DuckDBStore(database_path)

    if force_rebuild:
        store.drop_table(TABLE_EVENTS)
        store.drop_table(TABLE_FILE_SUMMARY)
        manifest = {
            "case_id": str(case_id),
            "staging_type": "TOWER_IPDR_DUCKDB",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "files": [],
        }
        manifest_map = {}

    files = _candidate_files(input_folder, recursive=recursive)

    if max_files is not None:
        files = files[: int(max_files)]

    loaded_files = 0
    skipped_files = 0
    failed_files = 0
    total_rows = 0

    print(f"[+] Tower IPDR staging database: {database_path}")
    print(f"[+] Candidate files: {len(files)}")

    for index, path in enumerate(files, start=1):
        sha256 = calculate_sha256(path)
        existing = manifest_map.get(sha256)

        if (
            existing
            and existing.get("status") == "LOADED"
            and not force_rebuild
        ):
            skipped_files += 1
            print(f"[SKIP] {index}/{len(files)} already loaded: {path.name}")
            continue

        started_at = _now_iso()
        print(f"[LOAD] {index}/{len(files)} {path.name}")

        record: dict[str, Any] = {
            "file_name": path.name,
            "source_path": str(path),
            "sha256": sha256,
            "status": "LOADING",
            "rows_loaded": 0,
            "started_at": started_at,
            "loaded_at": "",
            "metadata": {},
            "warnings": [],
            "errors": [],
        }

        _upsert_manifest_file(manifest, record)
        _write_manifest(case_id, manifest)

        try:
            result = load_tower_ipdr_file(path)

            record["warnings"] = list(result.get("warnings", []) or [])
            record["errors"] = list(result.get("errors", []) or [])
            record["metadata"] = _json_safe(result.get("metadata", {}) or {})

            if not result.get("ok"):
                failed_files += 1
                record["status"] = "FAILED"
                record["loaded_at"] = _now_iso()
                _upsert_manifest_file(manifest, record)
                _write_manifest(case_id, manifest)
                print(f"[FAIL] {path.name}: {record['errors']}")
                continue

            dataframe = result.get("df")

            if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
                failed_files += 1
                record["status"] = "FAILED"
                record["errors"].append("Normalized DataFrame empty.")
                record["loaded_at"] = _now_iso()
                _upsert_manifest_file(manifest, record)
                _write_manifest(case_id, manifest)
                print(f"[FAIL] {path.name}: empty normalized data")
                continue

            for column in NORMALIZED_COLUMNS:
                if column not in dataframe.columns:
                    dataframe[column] = pd.NA

            dataframe = dataframe[NORMALIZED_COLUMNS].copy()

            rows_written = store.write_dataframe(
                dataframe,
                TABLE_EVENTS,
                mode="append",
            )

            rows_loaded = int(rows_written or len(dataframe))

            record["status"] = "LOADED"
            record["rows_loaded"] = rows_loaded
            record["loaded_at"] = _now_iso()

            loaded_files += 1
            total_rows += rows_loaded

            _upsert_manifest_file(manifest, record)
            _write_manifest(case_id, manifest)

            print(f"[OK] {path.name}: {rows_loaded:,} row(s)")

            del dataframe

        except Exception as error:
            failed_files += 1
            record["status"] = "FAILED"
            record["errors"].append(
                f"{type(error).__name__}: {error}"
            )
            record["loaded_at"] = _now_iso()
            _upsert_manifest_file(manifest, record)
            _write_manifest(case_id, manifest)
            print(f"[ERROR] {path.name}: {type(error).__name__}: {error}")

    records = [
        item
        for item in manifest.get("files", [])
        if isinstance(item, dict)
    ]

    summary_frame = _file_summary_frame(records)

    if not summary_frame.empty:
        store.drop_table(TABLE_FILE_SUMMARY)
        store.write_dataframe(
            summary_frame,
            TABLE_FILE_SUMMARY,
            mode="append",
        )

    summary = {
        "case_id": str(case_id),
        "database_path": str(database_path),
        "manifest_path": str(tower_ipdr_manifest_path(case_id)),
        "candidate_files": len(files),
        "loaded_files": loaded_files,
        "skipped_files": skipped_files,
        "failed_files": failed_files,
        "rows_loaded_this_run": total_rows,
        "total_rows_in_database": count_tower_ipdr_events(case_id),
    }

    manifest["summary"] = summary
    _write_manifest(case_id, manifest)

    return summary


def count_tower_ipdr_events(case_id: str) -> int:
    database_path = tower_ipdr_database_path(case_id)
    store = DuckDBStore(database_path)

    if not store.table_exists(TABLE_EVENTS):
        return 0

    return int(store.row_count(TABLE_EVENTS))


def tower_ipdr_cell_counts(case_id: str) -> pd.DataFrame:
    database_path = tower_ipdr_database_path(case_id)
    store = DuckDBStore(database_path)

    if not store.table_exists(TABLE_EVENTS):
        return pd.DataFrame(
            columns=[
                "searched_cell_id",
                "event_count",
                "subscriber_count",
            ]
        )

    return store.query_df(
        f"""
        SELECT
            searched_cell_id,
            COUNT(*) AS event_count,
            COUNT(DISTINCT subscriber_number) AS subscriber_count
        FROM {TABLE_EVENTS}
        GROUP BY searched_cell_id
        ORDER BY event_count DESC
        """
    )


def tower_ipdr_time_count(
    case_id: str,
    partition_time: str,
) -> pd.DataFrame:
    database_path = tower_ipdr_database_path(case_id)
    store = DuckDBStore(database_path)

    if not store.table_exists(TABLE_EVENTS):
        return pd.DataFrame(
            columns=[
                "partition_time",
                "event_count",
                "subscriber_count",
            ]
        )

    return store.query_df(
        f"""
        SELECT
            CAST(? AS TIMESTAMP) AS partition_time,
            COUNT(*) AS event_count,
            COUNT(DISTINCT subscriber_number) AS subscriber_count
        FROM {TABLE_EVENTS}
        WHERE TRY_CAST(event_time AS TIMESTAMP) = CAST(? AS TIMESTAMP)
        """,
        [partition_time, partition_time],
    )


def tower_ipdr_uncommon_at_time(
    case_id: str,
    partition_time: str,
    *,
    limit: int = 50,
) -> pd.DataFrame:
    database_path = tower_ipdr_database_path(case_id)
    store = DuckDBStore(database_path)

    if not store.table_exists(TABLE_EVENTS):
        return pd.DataFrame()

    return store.query_df(
        f"""
        WITH current_part AS (
            SELECT
                subscriber_number,
                COUNT(*) AS current_seen_count,
                COUNT(DISTINCT searched_cell_id) AS cells_seen,
                MIN(TRY_CAST(event_time AS TIMESTAMP)) AS first_seen,
                MAX(TRY_CAST(event_time AS TIMESTAMP)) AS last_seen
            FROM {TABLE_EVENTS}
            WHERE TRY_CAST(event_time AS TIMESTAMP) = CAST(? AS TIMESTAMP)
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
            GROUP BY subscriber_number
        ),
        baseline AS (
            SELECT DISTINCT subscriber_number
            FROM {TABLE_EVENTS}
            WHERE TRY_CAST(event_time AS TIMESTAMP) <> CAST(? AS TIMESTAMP)
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
        )
        SELECT
            current_part.subscriber_number,
            current_part.current_seen_count,
            0 AS baseline_seen_count,
            current_part.first_seen,
            current_part.last_seen,
            current_part.cells_seen,
            100 AS rarity_score,
            CASE
                WHEN current_part.cells_seen >= 3 THEN 'HIGH'
                WHEN current_part.current_seen_count >= 100 THEN 'HIGH'
                WHEN current_part.cells_seen >= 2 THEN 'MEDIUM_HIGH'
                ELSE 'MEDIUM'
            END AS priority_level,
            CASE
                WHEN current_part.cells_seen >= 3 THEN 'Multi-cell exact date-time presence'
                WHEN current_part.current_seen_count >= 100 THEN 'High activity at exact date-time'
                WHEN current_part.cells_seen >= 2 THEN 'Seen on multiple cells at exact date-time'
                ELSE 'Exact date-time only presence'
            END AS rank_reason
        FROM current_part
        LEFT JOIN baseline
          ON current_part.subscriber_number = baseline.subscriber_number
        WHERE baseline.subscriber_number IS NULL
        ORDER BY
            CASE priority_level
                WHEN 'HIGH' THEN 1
                WHEN 'MEDIUM_HIGH' THEN 2
                WHEN 'MEDIUM' THEN 3
                ELSE 9
            END,
            current_seen_count DESC
        LIMIT ?
        """,
        [partition_time, partition_time, int(limit)],
    )


def tower_ipdr_minute_count(
    case_id: str,
    partition_time: str,
) -> pd.DataFrame:
    """Count events in the same minute as the entered partition time."""

    database_path = tower_ipdr_database_path(case_id)
    store = DuckDBStore(database_path)

    if not store.table_exists(TABLE_EVENTS):
        return pd.DataFrame(
            columns=[
                "partition_minute",
                "event_count",
                "subscriber_count",
            ]
        )

    return store.query_df(
        f"""
        SELECT
            DATE_TRUNC('minute', CAST(? AS TIMESTAMP)) AS partition_minute,
            COUNT(*) AS event_count,
            COUNT(DISTINCT subscriber_number) AS subscriber_count
        FROM {TABLE_EVENTS}
        WHERE DATE_TRUNC('minute', TRY_CAST(event_time AS TIMESTAMP))
              = DATE_TRUNC('minute', CAST(? AS TIMESTAMP))
        """,
        [partition_time, partition_time],
    )


def tower_ipdr_uncommon_in_minute(
    case_id: str,
    partition_time: str,
    *,
    limit: int = 50,
) -> pd.DataFrame:
    """Find uncommon subscribers in the same minute as the entered time."""

    database_path = tower_ipdr_database_path(case_id)
    store = DuckDBStore(database_path)

    if not store.table_exists(TABLE_EVENTS):
        return pd.DataFrame()

    return store.query_df(
        f"""
        WITH current_part AS (
            SELECT
                subscriber_number,
                COUNT(*) AS current_seen_count,
                COUNT(DISTINCT searched_cell_id) AS cells_seen,
                MIN(TRY_CAST(event_time AS TIMESTAMP)) AS first_seen,
                MAX(TRY_CAST(event_time AS TIMESTAMP)) AS last_seen
            FROM {TABLE_EVENTS}
            WHERE DATE_TRUNC('minute', TRY_CAST(event_time AS TIMESTAMP))
                  = DATE_TRUNC('minute', CAST(? AS TIMESTAMP))
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
            GROUP BY subscriber_number
        ),
        baseline AS (
            SELECT DISTINCT subscriber_number
            FROM {TABLE_EVENTS}
            WHERE DATE_TRUNC('minute', TRY_CAST(event_time AS TIMESTAMP))
                  <> DATE_TRUNC('minute', CAST(? AS TIMESTAMP))
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
        )
        SELECT
            current_part.subscriber_number,
            current_part.current_seen_count,
            0 AS baseline_seen_count,
            current_part.first_seen,
            current_part.last_seen,
            current_part.cells_seen,
            100 AS rarity_score,
            CASE
                WHEN current_part.cells_seen >= 3 THEN 'HIGH'
                WHEN current_part.current_seen_count >= 100 THEN 'HIGH'
                WHEN current_part.cells_seen >= 2 THEN 'MEDIUM_HIGH'
                ELSE 'MEDIUM'
            END AS priority_level,
            CASE
                WHEN current_part.cells_seen >= 3 THEN 'Multi-cell same-minute presence'
                WHEN current_part.current_seen_count >= 100 THEN 'High activity in same minute'
                WHEN current_part.cells_seen >= 2 THEN 'Seen on multiple cells in same minute'
                ELSE 'Same-minute only presence'
            END AS rank_reason
        FROM current_part
        LEFT JOIN baseline
          ON current_part.subscriber_number = baseline.subscriber_number
        WHERE baseline.subscriber_number IS NULL
        ORDER BY
            CASE priority_level
                WHEN 'HIGH' THEN 1
                WHEN 'MEDIUM_HIGH' THEN 2
                WHEN 'MEDIUM' THEN 3
                ELSE 9
            END,
            current_seen_count DESC
        LIMIT ?
        """,
        [partition_time, partition_time, int(limit)],
    )


def tower_ipdr_investigation_summary(
    case_id: str,
    partition_time: str,
    *,
    mode: str = "same_minute",
    lead_limit: int = 50,
) -> dict[str, pd.DataFrame]:
    """Simple investigation-friendly Tower IPDR partition summary.

    mode:
    - exact_second: only exact timestamp match
    - same_minute: all events in same minute as partition_time

    This function is designed for non-technical investigation output.
    """

    database_path = tower_ipdr_database_path(case_id)
    store = DuckDBStore(database_path)

    empty = {
        "summary": pd.DataFrame(),
        "lead_summary": pd.DataFrame(),
        "common_numbers": pd.DataFrame(),
        "uncommon_numbers": pd.DataFrame(),
        "multi_cell_presence": pd.DataFrame(),
        "repeat_presence": pd.DataFrame(),
        "device_consistency": pd.DataFrame(),
        "priority_leads": pd.DataFrame(),
    }

    if not store.table_exists(TABLE_EVENTS):
        return empty

    mode_value = str(mode).strip().lower()

    if mode_value not in {"exact_second", "same_minute"}:
        mode_value = "same_minute"

    if mode_value == "exact_second":
        current_filter = "TRY_CAST(event_time AS TIMESTAMP) = CAST(? AS TIMESTAMP)"
        baseline_filter = "TRY_CAST(event_time AS TIMESTAMP) <> CAST(? AS TIMESTAMP)"
        mode_label = "Exact second"
    else:
        current_filter = (
            "DATE_TRUNC('minute', TRY_CAST(event_time AS TIMESTAMP)) "
            "= DATE_TRUNC('minute', CAST(? AS TIMESTAMP))"
        )
        baseline_filter = (
            "DATE_TRUNC('minute', TRY_CAST(event_time AS TIMESTAMP)) "
            "<> DATE_TRUNC('minute', CAST(? AS TIMESTAMP))"
        )
        mode_label = "Same minute"

    summary = store.query_df(
        f"""
        WITH current_part AS (
            SELECT *
            FROM {TABLE_EVENTS}
            WHERE {current_filter}
        )
        SELECT
            CAST(? AS TIMESTAMP) AS partition_time,
            ? AS analysis_mode,
            COUNT(*) AS records_found,
            COUNT(DISTINCT subscriber_number) AS numbers_found,
            COUNT(DISTINCT searched_cell_id) AS cells_involved,
            COUNT(DISTINCT imei) AS imei_found,
            COUNT(DISTINCT imsi) AS imsi_found,
            MIN(TRY_CAST(event_time AS TIMESTAMP)) AS first_activity,
            MAX(TRY_CAST(event_time AS TIMESTAMP)) AS last_activity
        FROM current_part
        """,
        [partition_time, partition_time, mode_label],
    )

    common_numbers = store.query_df(
        f"""
        WITH current_part AS (
            SELECT
                subscriber_number,
                COUNT(*) AS selected_time_records,
                COUNT(DISTINCT searched_cell_id) AS selected_time_cells,
                COUNT(DISTINCT imei) AS selected_time_imei,
                COUNT(DISTINCT imsi) AS selected_time_imsi,
                MIN(TRY_CAST(event_time AS TIMESTAMP)) AS first_seen_selected,
                MAX(TRY_CAST(event_time AS TIMESTAMP)) AS last_seen_selected
            FROM {TABLE_EVENTS}
            WHERE {current_filter}
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
            GROUP BY subscriber_number
        ),
        baseline AS (
            SELECT
                subscriber_number,
                COUNT(*) AS other_time_records,
                COUNT(DISTINCT searched_cell_id) AS other_time_cells,
                MIN(TRY_CAST(event_time AS TIMESTAMP)) AS first_seen_other,
                MAX(TRY_CAST(event_time AS TIMESTAMP)) AS last_seen_other
            FROM {TABLE_EVENTS}
            WHERE {baseline_filter}
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
            GROUP BY subscriber_number
        )
        SELECT
            current_part.subscriber_number AS mobile_number,
            current_part.selected_time_records,
            baseline.other_time_records,
            current_part.selected_time_cells,
            baseline.other_time_cells,
            'Common Number' AS finding_type,
            'This number is present in selected time and also seen in other loaded data.' AS meaning,
            'May be a local/repeated number or linked person. Verify before conclusion.' AS why_it_matters,
            'Medium' AS priority,
            CASE
                WHEN current_part.selected_time_cells >= 2 OR baseline.other_time_cells >= 2 THEN 'Medium'
                ELSE 'Low'
            END AS confidence_level,
            'Verify with CDR, SDR/CAF, IMEI/IMSI and field information.' AS suggested_action
        FROM current_part
        INNER JOIN baseline
          ON current_part.subscriber_number = baseline.subscriber_number
        ORDER BY
            current_part.selected_time_cells DESC,
            current_part.selected_time_records DESC,
            baseline.other_time_records DESC
        LIMIT ?
        """,
        [partition_time, partition_time, int(lead_limit)],
    )

    uncommon_numbers = store.query_df(
        f"""
        WITH current_part AS (
            SELECT
                subscriber_number,
                COUNT(*) AS selected_time_records,
                COUNT(DISTINCT searched_cell_id) AS selected_time_cells,
                COUNT(DISTINCT imei) AS selected_time_imei,
                COUNT(DISTINCT imsi) AS selected_time_imsi,
                MIN(TRY_CAST(event_time AS TIMESTAMP)) AS first_seen_selected,
                MAX(TRY_CAST(event_time AS TIMESTAMP)) AS last_seen_selected
            FROM {TABLE_EVENTS}
            WHERE {current_filter}
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
            GROUP BY subscriber_number
        ),
        baseline AS (
            SELECT DISTINCT subscriber_number
            FROM {TABLE_EVENTS}
            WHERE {baseline_filter}
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
        )
        SELECT
            current_part.subscriber_number AS mobile_number,
            current_part.selected_time_records,
            0 AS other_time_records,
            current_part.selected_time_cells,
            current_part.selected_time_imei,
            current_part.selected_time_imsi,
            current_part.first_seen_selected,
            current_part.last_seen_selected,
            'Uncommon / New Visitor' AS finding_type,
            'This number is present in selected time but not found in other loaded data.' AS meaning,
            'May indicate a new visitor, rare presence, or incident-time lead.' AS why_it_matters,
            CASE
                WHEN current_part.selected_time_cells >= 3 THEN 'High'
                WHEN current_part.selected_time_cells >= 2 THEN 'Medium-High'
                WHEN current_part.selected_time_records >= 10 THEN 'Medium'
                ELSE 'Low'
            END AS priority,
            CASE
                WHEN current_part.selected_time_cells >= 2 AND current_part.selected_time_records >= 5 THEN 'High'
                WHEN current_part.selected_time_records >= 3 THEN 'Medium'
                ELSE 'Low'
            END AS confidence_level,
            'Verify this number first with CDR/SDR/CAF, IMEI/IMSI continuity, and CCTV/field input.' AS suggested_action
        FROM current_part
        LEFT JOIN baseline
          ON current_part.subscriber_number = baseline.subscriber_number
        WHERE baseline.subscriber_number IS NULL
        ORDER BY
            CASE
                WHEN current_part.selected_time_cells >= 3 THEN 1
                WHEN current_part.selected_time_cells >= 2 THEN 2
                WHEN current_part.selected_time_records >= 10 THEN 3
                ELSE 4
            END,
            current_part.selected_time_records DESC
        LIMIT ?
        """,
        [partition_time, partition_time, int(lead_limit)],
    )

    multi_cell_presence = store.query_df(
        f"""
        SELECT
            subscriber_number AS mobile_number,
            COUNT(*) AS records_found,
            COUNT(DISTINCT searched_cell_id) AS cells_seen,
            COUNT(DISTINCT imei) AS imei_count,
            COUNT(DISTINCT imsi) AS imsi_count,
            MIN(TRY_CAST(event_time AS TIMESTAMP)) AS first_seen,
            MAX(TRY_CAST(event_time AS TIMESTAMP)) AS last_seen,
            'Multi-Cell Presence' AS finding_type,
            'This number appeared in more than one searched cell during selected time.' AS meaning,
            'Multi-cell presence can be a stronger area-presence or movement lead.' AS why_it_matters,
            CASE
                WHEN COUNT(DISTINCT searched_cell_id) >= 3 THEN 'High'
                ELSE 'Medium-High'
            END AS priority,
            CASE
                WHEN COUNT(*) >= 5 THEN 'High'
                ELSE 'Medium'
            END AS confidence_level,
            'Verify movement feasibility, tower locations, CDR location and field/CCTV information.' AS suggested_action
        FROM {TABLE_EVENTS}
        WHERE {current_filter}
          AND subscriber_number IS NOT NULL
          AND subscriber_number <> ''
        GROUP BY subscriber_number
        HAVING COUNT(DISTINCT searched_cell_id) >= 2
        ORDER BY cells_seen DESC, records_found DESC
        LIMIT ?
        """,
        [partition_time, int(lead_limit)],
    )

    repeat_presence = store.query_df(
        f"""
        WITH current_part AS (
            SELECT DISTINCT subscriber_number
            FROM {TABLE_EVENTS}
            WHERE {current_filter}
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
        ),
        baseline AS (
            SELECT
                subscriber_number,
                COUNT(*) AS other_time_records,
                COUNT(DISTINCT DATE_TRUNC('minute', TRY_CAST(event_time AS TIMESTAMP))) AS other_minutes_seen,
                COUNT(DISTINCT searched_cell_id) AS other_cells_seen
            FROM {TABLE_EVENTS}
            WHERE {baseline_filter}
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
            GROUP BY subscriber_number
        )
        SELECT
            current_part.subscriber_number AS mobile_number,
            baseline.other_time_records,
            baseline.other_minutes_seen,
            baseline.other_cells_seen,
            'Repeat Presence' AS finding_type,
            'This number is seen at selected time and repeatedly in other loaded data.' AS meaning,
            'May be local, regular visitor, or associated number depending on case context.' AS why_it_matters,
            CASE
                WHEN baseline.other_minutes_seen >= 10 OR baseline.other_cells_seen >= 3 THEN 'Medium'
                ELSE 'Low'
            END AS priority,
            CASE
                WHEN baseline.other_time_records >= 20 THEN 'Medium'
                ELSE 'Low'
            END AS confidence_level,
            'Do not treat as suspect only because it is repeated. Verify role and location context.' AS suggested_action
        FROM current_part
        INNER JOIN baseline
          ON current_part.subscriber_number = baseline.subscriber_number
        ORDER BY
            baseline.other_minutes_seen DESC,
            baseline.other_time_records DESC
        LIMIT ?
        """,
        [partition_time, partition_time, int(lead_limit)],
    )

    device_consistency = store.query_df(
        f"""
        SELECT
            subscriber_number AS mobile_number,
            COUNT(*) AS records_found,
            COUNT(DISTINCT imei) AS imei_count,
            COUNT(DISTINCT imsi) AS imsi_count,
            COUNT(DISTINCT searched_cell_id) AS cells_seen,
            'IMEI/IMSI Consistency' AS finding_type,
            CASE
                WHEN COUNT(DISTINCT imei) > 1 AND COUNT(DISTINCT imsi) > 1
                    THEN 'Multiple device and SIM identifiers seen.'
                WHEN COUNT(DISTINCT imei) > 1
                    THEN 'Multiple device identifiers seen.'
                WHEN COUNT(DISTINCT imsi) > 1
                    THEN 'Multiple SIM identifiers seen.'
                ELSE 'Device and SIM identifiers appear consistent in selected time.'
            END AS meaning,
            CASE
                WHEN COUNT(DISTINCT imei) > 1 OR COUNT(DISTINCT imsi) > 1
                    THEN 'May indicate SIM/device change, shared handset, data issue, or multiple records.'
                ELSE 'Consistent identifiers increase confidence but still need verification.'
            END AS why_it_matters,
            CASE
                WHEN COUNT(DISTINCT imei) > 1 OR COUNT(DISTINCT imsi) > 1
                    THEN 'Medium'
                ELSE 'Low'
            END AS priority,
            CASE
                WHEN COUNT(*) >= 3 THEN 'Medium'
                ELSE 'Low'
            END AS confidence_level,
            'Verify IMEI/IMSI with CDR, SDR/CAF and operator records before conclusion.' AS suggested_action
        FROM {TABLE_EVENTS}
        WHERE {current_filter}
          AND subscriber_number IS NOT NULL
          AND subscriber_number <> ''
        GROUP BY subscriber_number
        ORDER BY
            imei_count DESC,
            imsi_count DESC,
            records_found DESC
        LIMIT ?
        """,
        [partition_time, int(lead_limit)],
    )

    priority_leads = store.query_df(
        f"""
        WITH current_part AS (
            SELECT
                subscriber_number,
                COUNT(*) AS selected_time_records,
                COUNT(DISTINCT searched_cell_id) AS selected_time_cells,
                COUNT(DISTINCT imei) AS imei_count,
                COUNT(DISTINCT imsi) AS imsi_count,
                MIN(TRY_CAST(event_time AS TIMESTAMP)) AS first_seen,
                MAX(TRY_CAST(event_time AS TIMESTAMP)) AS last_seen
            FROM {TABLE_EVENTS}
            WHERE {current_filter}
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
            GROUP BY subscriber_number
        ),
        baseline AS (
            SELECT
                subscriber_number,
                COUNT(*) AS baseline_records
            FROM {TABLE_EVENTS}
            WHERE {baseline_filter}
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
            GROUP BY subscriber_number
        )
        SELECT
            current_part.subscriber_number AS mobile_number,
            current_part.selected_time_records,
            COALESCE(baseline.baseline_records, 0) AS baseline_records,
            current_part.selected_time_cells,
            current_part.imei_count,
            current_part.imsi_count,
            current_part.first_seen,
            current_part.last_seen,
            CASE
                WHEN baseline.subscriber_number IS NULL AND current_part.selected_time_cells >= 2
                    THEN 'High'
                WHEN baseline.subscriber_number IS NULL
                    THEN 'Medium'
                WHEN current_part.selected_time_cells >= 2
                    THEN 'Medium-High'
                WHEN current_part.selected_time_records >= 10
                    THEN 'Medium'
                ELSE 'Low'
            END AS priority,
            CASE
                WHEN current_part.selected_time_cells >= 2 AND current_part.selected_time_records >= 5
                    THEN 'High'
                WHEN current_part.selected_time_records >= 3
                    THEN 'Medium'
                ELSE 'Low'
            END AS confidence_level,
            CASE
                WHEN baseline.subscriber_number IS NULL AND current_part.selected_time_cells >= 2
                    THEN 'New/rare number with multi-cell presence'
                WHEN baseline.subscriber_number IS NULL
                    THEN 'New/rare number in selected time'
                WHEN current_part.selected_time_cells >= 2
                    THEN 'Common number with multi-cell presence'
                WHEN current_part.selected_time_records >= 10
                    THEN 'High activity in selected time'
                ELSE 'Low-volume presence'
            END AS simple_reason,
            'Verify priority leads with CDR/SDR/CAF, IMEI/IMSI and field/CCTV information.' AS suggested_action
        FROM current_part
        LEFT JOIN baseline
          ON current_part.subscriber_number = baseline.subscriber_number
        ORDER BY
            CASE
                WHEN baseline.subscriber_number IS NULL AND current_part.selected_time_cells >= 2 THEN 1
                WHEN baseline.subscriber_number IS NULL THEN 2
                WHEN current_part.selected_time_cells >= 2 THEN 3
                WHEN current_part.selected_time_records >= 10 THEN 4
                ELSE 9
            END,
            current_part.selected_time_records DESC
        LIMIT ?
        """,
        [partition_time, partition_time, int(lead_limit)],
    )

    lead_summary = pd.DataFrame(
        [
            {
                "finding": "Common Numbers",
                "records": len(common_numbers),
                "meaning": "Numbers seen in selected time and also elsewhere in loaded data.",
            },
            {
                "finding": "Uncommon / New Visitor",
                "records": len(uncommon_numbers),
                "meaning": "Numbers seen in selected time but not seen elsewhere in loaded data.",
            },
            {
                "finding": "Multi-Cell Presence",
                "records": len(multi_cell_presence),
                "meaning": "Numbers seen in more than one searched cell.",
            },
            {
                "finding": "Repeat Presence",
                "records": len(repeat_presence),
                "meaning": "Numbers repeatedly seen in other loaded data also.",
            },
            {
                "finding": "IMEI/IMSI Consistency",
                "records": len(device_consistency),
                "meaning": "Device/SIM consistency or possible change indicators.",
            },
            {
                "finding": "Priority Leads",
                "records": len(priority_leads),
                "meaning": "Combined ranking based on rarity, cells, activity and confidence.",
            },
        ]
    )

    return {
        "summary": summary,
        "lead_summary": lead_summary,
        "common_numbers": common_numbers,
        "uncommon_numbers": uncommon_numbers,
        "multi_cell_presence": multi_cell_presence,
        "repeat_presence": repeat_presence,
        "device_consistency": device_consistency,
        "priority_leads": priority_leads,
    }


def _safe_first_value(dataframe: pd.DataFrame, column: str, default: Any = "") -> Any:
    if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
        return default

    if column not in dataframe.columns:
        return default

    value = dataframe.iloc[0].get(column, default)

    try:
        if pd.isna(value):
            return default
    except Exception:
        pass

    return value


def _print_simple_leads(
    dataframe: pd.DataFrame,
    *,
    number_col: str = "mobile_number",
    max_rows: int = 10,
) -> None:
    if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
        print("   No important lead found in this section.")
        return

    for index, row in dataframe.head(max_rows).reset_index(drop=True).iterrows():
        number = row.get(number_col, "")
        priority = row.get("priority", "")
        confidence = row.get("confidence_level", "")
        reason = (
            row.get("simple_reason", "")
            or row.get("meaning", "")
            or row.get("finding_type", "")
        )
        action = row.get("suggested_action", "")

        print(f"   {index + 1}. Mobile Number : {number}")
        print(f"      Priority      : {priority or 'Not specified'}")
        print(f"      Confidence    : {confidence or 'Not specified'}")
        print(f"      Why important : {reason or 'Needs verification'}")

        if action:
            print(f"      Next Action   : {action}")

        print()


def print_tower_ipdr_investigation_summary(
    result: dict[str, pd.DataFrame],
    *,
    max_leads: int = 10,
) -> None:
    """Print Tower IPDR partition analysis in simple investigation language."""

    summary = result.get("summary", pd.DataFrame())
    lead_summary = result.get("lead_summary", pd.DataFrame())
    common_numbers = result.get("common_numbers", pd.DataFrame())
    uncommon_numbers = result.get("uncommon_numbers", pd.DataFrame())
    multi_cell_presence = result.get("multi_cell_presence", pd.DataFrame())
    repeat_presence = result.get("repeat_presence", pd.DataFrame())
    device_consistency = result.get("device_consistency", pd.DataFrame())
    priority_leads = result.get("priority_leads", pd.DataFrame())

    partition_time = _safe_first_value(summary, "partition_time", "")
    partition_start = _safe_first_value(summary, "partition_start", "")
    partition_end = _safe_first_value(summary, "partition_end", "")
    analysis_mode = _safe_first_value(summary, "analysis_mode", "")
    records_found = _safe_first_value(summary, "records_found", 0)
    numbers_found = _safe_first_value(summary, "numbers_found", 0)
    cells_involved = _safe_first_value(summary, "cells_involved", 0)
    first_activity = _safe_first_value(summary, "first_activity", "")
    last_activity = _safe_first_value(summary, "last_activity", "")

    print("\n" + "=" * 78)
    print("TOWER IPDR INVESTIGATION SUMMARY")
    print("=" * 78)

    if partition_start and partition_end:
        print(f"Selected Period    : {partition_start} to {partition_end}")
    else:
        print(f"Selected Date-Time : {partition_time}")

    print(f"Analysis Mode      : {analysis_mode}")
    print(f"Records Found      : {records_found:,}")
    print(f"Numbers Found      : {numbers_found:,}")
    print(f"Searched Cells     : {cells_involved:,}")
    print(f"First Activity     : {first_activity}")
    print(f"Last Activity      : {last_activity}")

    print("\n" + "-" * 78)
    print("IMPORTANT FINDINGS")
    print("-" * 78)

    if isinstance(lead_summary, pd.DataFrame) and not lead_summary.empty:
        for _, row in lead_summary.iterrows():
            print(
                f"- {row.get('finding', '')}: "
                f"{row.get('records', 0)} lead(s)"
            )
            print(f"  Meaning: {row.get('meaning', '')}")
    else:
        print("- No finding summary available.")

    print("\n" + "-" * 78)
    print("TOP PRIORITY LEADS")
    print("-" * 78)
    _print_simple_leads(priority_leads, max_rows=max_leads)

    print("\n" + "-" * 78)
    print("COMMON NUMBERS")
    print("-" * 78)
    print("Meaning: Numbers seen in selected period and also seen elsewhere in loaded data.")
    print("Use: Check whether these are local, repeated visitor, associate, or linked person.")
    _print_simple_leads(common_numbers, max_rows=max_leads)

    print("\n" + "-" * 78)
    print("UNCOMMON / NEW VISITOR NUMBERS")
    print("-" * 78)
    print("Meaning: Numbers seen in selected period but not found elsewhere in loaded data.")
    print("Use: These may be new visitor, rare presence, or incident-period leads.")
    _print_simple_leads(uncommon_numbers, max_rows=max_leads)

    print("\n" + "-" * 78)
    print("MULTI-CELL PRESENCE")
    print("-" * 78)
    print("Meaning: Numbers seen on more than one searched cell during selected period.")
    print("Use: This may indicate stronger area presence or movement.")
    _print_simple_leads(multi_cell_presence, max_rows=max_leads)

    print("\n" + "-" * 78)
    print("REPEAT PRESENCE")
    print("-" * 78)
    print("Meaning: Numbers repeatedly seen in other loaded data also.")
    print("Use: Could be local/repeated visitor; do not treat as suspect without verification.")
    _print_simple_leads(repeat_presence, max_rows=max_leads)

    print("\n" + "-" * 78)
    print("IMEI / IMSI CONSISTENCY")
    print("-" * 78)
    print("Meaning: Checks whether same number shows same or multiple device/SIM identifiers.")
    print("Use: Helps verify SIM/device continuity or possible device/SIM change.")
    _print_simple_leads(device_consistency, max_rows=max_leads)

    suspicious_timing = result.get("suspicious_timing", pd.DataFrame())

    print("\n" + "-" * 78)
    print("SUSPICIOUS TIMING / HIGH ACTIVITY")
    print("-" * 78)
    print("Meaning: Numbers with notable activity during the selected period.")
    print("Use: Compare timing with incident time, CCTV/field input and route.")
    _print_simple_leads(suspicious_timing, max_rows=max_leads)

    print("\n" + "-" * 78)
    print("SUGGESTED VERIFICATION")
    print("-" * 78)
    print("1. Verify high-priority and medium-priority numbers first.")
    print("2. Check CDR/SDR/CAF details for identity and ownership.")
    print("3. Verify IMEI/IMSI continuity with operator records.")
    print("4. Compare with CCTV, field input, suspect route and tower location.")
    print("5. Do not conclude only from tower/IPDR presence; corroboration is required.")
    print("=" * 78)


def _safe_report_name(value: str) -> str:
    import re

    text = str(value).strip()
    text = text.replace(":", "-").replace(" ", "_")
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.strip("_") or "partition"


def tower_ipdr_fast_report_root(case_id: str) -> Path:
    return (
        Path("cases")
        / "active"
        / str(case_id)
        / "reports"
        / "tower_dump"
        / "ipdr"
        / "fast_partition"
    )


def export_tower_ipdr_investigation_summary(
    case_id: str,
    partition_time: str,
    *,
    mode: str = "same_minute",
    lead_limit: int = 50,
    max_leads_in_text: int = 20,
) -> dict[str, Any]:
    """Export fast Tower IPDR partition result for case record.

    Exports:
    - simple officer-friendly TXT summary
    - detailed CSV tables
    - manifest.json
    """

    import io
    from contextlib import redirect_stdout

    result = tower_ipdr_investigation_summary(
        case_id,
        partition_time,
        mode=mode,
        lead_limit=lead_limit,
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_partition = _safe_report_name(partition_time)
    run_id = f"tower_ipdr_fast_partition_{safe_partition}_{timestamp}"

    output_dir = tower_ipdr_fast_report_root(case_id) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_files: dict[str, str] = {}

    for name, dataframe in result.items():
        if not isinstance(dataframe, pd.DataFrame):
            continue

        csv_path = output_dir / f"{name}.csv"
        dataframe.to_csv(csv_path, index=False)
        saved_files[name] = str(csv_path)

    buffer = io.StringIO()

    with redirect_stdout(buffer):
        print_tower_ipdr_investigation_summary(
            result,
            max_leads=max_leads_in_text,
        )

    text_path = output_dir / "investigation_summary.txt"
    text_path.write_text(buffer.getvalue(), encoding="utf-8")
    saved_files["investigation_summary_text"] = str(text_path)

    manifest = {
        "case_id": str(case_id),
        "run_id": run_id,
        "created_at": _now_iso(),
        "partition_time": str(partition_time),
        "analysis_mode": str(mode),
        "lead_limit": int(lead_limit),
        "max_leads_in_text": int(max_leads_in_text),
        "output_dir": str(output_dir),
        "saved_files": saved_files,
        "note": (
            "Fast Tower IPDR partition report generated from DuckDB staging. "
            "Results are investigation leads and require verification."
        ),
    }

    manifest_path.write_text(
        json.dumps(
            _json_safe(manifest),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return manifest


def tower_ipdr_range_investigation_summary(
    case_id: str,
    start_time: str,
    end_time: str,
    *,
    lead_limit: int = 50,
) -> dict[str, pd.DataFrame]:
    """Investigation-friendly Tower IPDR summary for a Date-Time range.

    Rule:
    start_time <= event_time < end_time

    This is the main production workflow for Date-Time Parts.
    """

    database_path = tower_ipdr_database_path(case_id)
    store = DuckDBStore(database_path)

    empty = {
        "summary": pd.DataFrame(),
        "lead_summary": pd.DataFrame(),
        "common_numbers": pd.DataFrame(),
        "uncommon_numbers": pd.DataFrame(),
        "multi_cell_presence": pd.DataFrame(),
        "repeat_presence": pd.DataFrame(),
        "device_consistency": pd.DataFrame(),
        "suspicious_timing": pd.DataFrame(),
        "priority_leads": pd.DataFrame(),
    }

    if not store.table_exists(TABLE_EVENTS):
        return empty

    current_filter = (
        "TRY_CAST(event_time AS TIMESTAMP) >= CAST(? AS TIMESTAMP) "
        "AND TRY_CAST(event_time AS TIMESTAMP) < CAST(? AS TIMESTAMP)"
    )

    baseline_filter = (
        "NOT (TRY_CAST(event_time AS TIMESTAMP) >= CAST(? AS TIMESTAMP) "
        "AND TRY_CAST(event_time AS TIMESTAMP) < CAST(? AS TIMESTAMP))"
    )

    summary = store.query_df(
        f"""
        WITH current_part AS (
            SELECT *
            FROM {TABLE_EVENTS}
            WHERE {current_filter}
        )
        SELECT
            CAST(? AS TIMESTAMP) AS partition_start,
            CAST(? AS TIMESTAMP) AS partition_end,
            CONCAT(CAST(? AS VARCHAR), ' to ', CAST(? AS VARCHAR)) AS partition_time,
            'Date-Time Range' AS analysis_mode,
            COUNT(*) AS records_found,
            COUNT(DISTINCT subscriber_number) AS numbers_found,
            COUNT(DISTINCT searched_cell_id) AS cells_involved,
            COUNT(DISTINCT imei) AS imei_found,
            COUNT(DISTINCT imsi) AS imsi_found,
            MIN(TRY_CAST(event_time AS TIMESTAMP)) AS first_activity,
            MAX(TRY_CAST(event_time AS TIMESTAMP)) AS last_activity
        FROM current_part
        """,
        [start_time, end_time, start_time, end_time, start_time, end_time],
    )

    common_numbers = store.query_df(
        f"""
        WITH current_part AS (
            SELECT
                subscriber_number,
                COUNT(*) AS selected_period_records,
                COUNT(DISTINCT searched_cell_id) AS selected_period_cells,
                COUNT(DISTINCT imei) AS selected_period_imei,
                COUNT(DISTINCT imsi) AS selected_period_imsi,
                MIN(TRY_CAST(event_time AS TIMESTAMP)) AS first_seen_selected,
                MAX(TRY_CAST(event_time AS TIMESTAMP)) AS last_seen_selected
            FROM {TABLE_EVENTS}
            WHERE {current_filter}
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
            GROUP BY subscriber_number
        ),
        baseline AS (
            SELECT
                subscriber_number,
                COUNT(*) AS other_period_records,
                COUNT(DISTINCT searched_cell_id) AS other_period_cells,
                MIN(TRY_CAST(event_time AS TIMESTAMP)) AS first_seen_other,
                MAX(TRY_CAST(event_time AS TIMESTAMP)) AS last_seen_other
            FROM {TABLE_EVENTS}
            WHERE {baseline_filter}
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
            GROUP BY subscriber_number
        )
        SELECT
            current_part.subscriber_number AS mobile_number,
            current_part.selected_period_records,
            baseline.other_period_records,
            current_part.selected_period_cells,
            baseline.other_period_cells,
            current_part.first_seen_selected,
            current_part.last_seen_selected,
            'Common Number' AS finding_type,
            'This number is present in selected period and also seen in other loaded data.' AS meaning,
            'May be a local/repeated number, associate, or linked person. Verify before conclusion.' AS why_it_matters,
            CASE
                WHEN current_part.selected_period_cells >= 2 OR baseline.other_period_cells >= 2 THEN 'Medium'
                ELSE 'Low'
            END AS priority,
            CASE
                WHEN current_part.selected_period_cells >= 2 THEN 'Medium'
                ELSE 'Low'
            END AS confidence_level,
            'Verify with CDR, SDR/CAF, IMEI/IMSI and field information.' AS suggested_action
        FROM current_part
        INNER JOIN baseline
          ON current_part.subscriber_number = baseline.subscriber_number
        ORDER BY
            current_part.selected_period_cells DESC,
            current_part.selected_period_records DESC,
            baseline.other_period_records DESC
        LIMIT ?
        """,
        [start_time, end_time, start_time, end_time, int(lead_limit)],
    )

    uncommon_numbers = store.query_df(
        f"""
        WITH current_part AS (
            SELECT
                subscriber_number,
                COUNT(*) AS selected_period_records,
                COUNT(DISTINCT searched_cell_id) AS selected_period_cells,
                COUNT(DISTINCT imei) AS selected_period_imei,
                COUNT(DISTINCT imsi) AS selected_period_imsi,
                MIN(TRY_CAST(event_time AS TIMESTAMP)) AS first_seen_selected,
                MAX(TRY_CAST(event_time AS TIMESTAMP)) AS last_seen_selected
            FROM {TABLE_EVENTS}
            WHERE {current_filter}
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
            GROUP BY subscriber_number
        ),
        baseline AS (
            SELECT DISTINCT subscriber_number
            FROM {TABLE_EVENTS}
            WHERE {baseline_filter}
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
        )
        SELECT
            current_part.subscriber_number AS mobile_number,
            current_part.selected_period_records,
            0 AS other_period_records,
            current_part.selected_period_cells,
            current_part.selected_period_imei,
            current_part.selected_period_imsi,
            current_part.first_seen_selected,
            current_part.last_seen_selected,
            'Uncommon / New Visitor' AS finding_type,
            'This number is present in selected period but not found in other loaded data.' AS meaning,
            'May indicate a new visitor, rare presence, or incident-period lead.' AS why_it_matters,
            CASE
                WHEN current_part.selected_period_cells >= 3 THEN 'High'
                WHEN current_part.selected_period_cells >= 2 THEN 'Medium-High'
                WHEN current_part.selected_period_records >= 10 THEN 'Medium'
                ELSE 'Low'
            END AS priority,
            CASE
                WHEN current_part.selected_period_cells >= 2 AND current_part.selected_period_records >= 5 THEN 'High'
                WHEN current_part.selected_period_records >= 3 THEN 'Medium'
                ELSE 'Low'
            END AS confidence_level,
            'Verify this number with CDR/SDR/CAF, IMEI/IMSI continuity, and CCTV/field input.' AS suggested_action
        FROM current_part
        LEFT JOIN baseline
          ON current_part.subscriber_number = baseline.subscriber_number
        WHERE baseline.subscriber_number IS NULL
        ORDER BY
            CASE
                WHEN current_part.selected_period_cells >= 3 THEN 1
                WHEN current_part.selected_period_cells >= 2 THEN 2
                WHEN current_part.selected_period_records >= 10 THEN 3
                ELSE 4
            END,
            current_part.selected_period_records DESC
        LIMIT ?
        """,
        [start_time, end_time, start_time, end_time, int(lead_limit)],
    )

    multi_cell_presence = store.query_df(
        f"""
        SELECT
            subscriber_number AS mobile_number,
            COUNT(*) AS records_found,
            COUNT(DISTINCT searched_cell_id) AS cells_seen,
            COUNT(DISTINCT imei) AS imei_count,
            COUNT(DISTINCT imsi) AS imsi_count,
            MIN(TRY_CAST(event_time AS TIMESTAMP)) AS first_seen,
            MAX(TRY_CAST(event_time AS TIMESTAMP)) AS last_seen,
            'Multi-Cell Presence' AS finding_type,
            'This number appeared in more than one searched cell during selected period.' AS meaning,
            'Multi-cell presence can be a stronger area-presence or movement lead.' AS why_it_matters,
            CASE
                WHEN COUNT(DISTINCT searched_cell_id) >= 3 THEN 'High'
                ELSE 'Medium-High'
            END AS priority,
            CASE
                WHEN COUNT(*) >= 5 THEN 'High'
                ELSE 'Medium'
            END AS confidence_level,
            'Verify tower route, movement feasibility, CDR location and field/CCTV information.' AS suggested_action
        FROM {TABLE_EVENTS}
        WHERE {current_filter}
          AND subscriber_number IS NOT NULL
          AND subscriber_number <> ''
        GROUP BY subscriber_number
        HAVING COUNT(DISTINCT searched_cell_id) >= 2
        ORDER BY cells_seen DESC, records_found DESC
        LIMIT ?
        """,
        [start_time, end_time, int(lead_limit)],
    )

    repeat_presence = store.query_df(
        f"""
        WITH current_part AS (
            SELECT DISTINCT subscriber_number
            FROM {TABLE_EVENTS}
            WHERE {current_filter}
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
        ),
        baseline AS (
            SELECT
                subscriber_number,
                COUNT(*) AS other_period_records,
                COUNT(DISTINCT DATE_TRUNC('minute', TRY_CAST(event_time AS TIMESTAMP))) AS other_minutes_seen,
                COUNT(DISTINCT searched_cell_id) AS other_cells_seen
            FROM {TABLE_EVENTS}
            WHERE {baseline_filter}
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
            GROUP BY subscriber_number
        )
        SELECT
            current_part.subscriber_number AS mobile_number,
            baseline.other_period_records,
            baseline.other_minutes_seen,
            baseline.other_cells_seen,
            'Repeat Presence' AS finding_type,
            'This number is seen in selected period and repeatedly in other loaded data.' AS meaning,
            'May be local, regular visitor, or associated number depending on case context.' AS why_it_matters,
            CASE
                WHEN baseline.other_minutes_seen >= 10 OR baseline.other_cells_seen >= 3 THEN 'Medium'
                ELSE 'Low'
            END AS priority,
            CASE
                WHEN baseline.other_period_records >= 20 THEN 'Medium'
                ELSE 'Low'
            END AS confidence_level,
            'Do not treat as suspect only because it is repeated. Verify role and location context.' AS suggested_action
        FROM current_part
        INNER JOIN baseline
          ON current_part.subscriber_number = baseline.subscriber_number
        ORDER BY
            baseline.other_minutes_seen DESC,
            baseline.other_period_records DESC
        LIMIT ?
        """,
        [start_time, end_time, start_time, end_time, int(lead_limit)],
    )

    device_consistency = store.query_df(
        f"""
        SELECT
            subscriber_number AS mobile_number,
            COUNT(*) AS records_found,
            COUNT(DISTINCT imei) AS imei_count,
            COUNT(DISTINCT imsi) AS imsi_count,
            COUNT(DISTINCT searched_cell_id) AS cells_seen,
            MIN(TRY_CAST(event_time AS TIMESTAMP)) AS first_seen,
            MAX(TRY_CAST(event_time AS TIMESTAMP)) AS last_seen,
            'IMEI/IMSI Consistency' AS finding_type,
            CASE
                WHEN COUNT(DISTINCT imei) > 1 AND COUNT(DISTINCT imsi) > 1
                    THEN 'Multiple device and SIM identifiers seen.'
                WHEN COUNT(DISTINCT imei) > 1
                    THEN 'Multiple device identifiers seen.'
                WHEN COUNT(DISTINCT imsi) > 1
                    THEN 'Multiple SIM identifiers seen.'
                ELSE 'Device and SIM identifiers appear consistent in selected period.'
            END AS meaning,
            CASE
                WHEN COUNT(DISTINCT imei) > 1 OR COUNT(DISTINCT imsi) > 1
                    THEN 'May indicate SIM/device change, shared handset, data issue, or multiple records.'
                ELSE 'Consistent identifiers increase confidence but still need verification.'
            END AS why_it_matters,
            CASE
                WHEN COUNT(DISTINCT imei) > 1 OR COUNT(DISTINCT imsi) > 1
                    THEN 'Medium'
                ELSE 'Low'
            END AS priority,
            CASE
                WHEN COUNT(*) >= 3 THEN 'Medium'
                ELSE 'Low'
            END AS confidence_level,
            'Verify IMEI/IMSI with CDR, SDR/CAF and operator records before conclusion.' AS suggested_action
        FROM {TABLE_EVENTS}
        WHERE {current_filter}
          AND subscriber_number IS NOT NULL
          AND subscriber_number <> ''
        GROUP BY subscriber_number
        ORDER BY
            imei_count DESC,
            imsi_count DESC,
            records_found DESC
        LIMIT ?
        """,
        [start_time, end_time, int(lead_limit)],
    )

    suspicious_timing = store.query_df(
        f"""
        SELECT
            subscriber_number AS mobile_number,
            COUNT(*) AS records_found,
            COUNT(DISTINCT searched_cell_id) AS cells_seen,
            COUNT(DISTINCT imei) AS imei_count,
            COUNT(DISTINCT imsi) AS imsi_count,
            MIN(TRY_CAST(event_time AS TIMESTAMP)) AS first_seen,
            MAX(TRY_CAST(event_time AS TIMESTAMP)) AS last_seen,
            'Suspicious Timing / High Activity' AS finding_type,
            'This number has notable activity during the selected period.' AS meaning,
            'High activity during an important period may be useful for investigation, but needs verification.' AS why_it_matters,
            CASE
                WHEN COUNT(DISTINCT searched_cell_id) >= 2 AND COUNT(*) >= 10 THEN 'High'
                WHEN COUNT(*) >= 10 THEN 'Medium'
                ELSE 'Low'
            END AS priority,
            CASE
                WHEN COUNT(*) >= 10 OR COUNT(DISTINCT searched_cell_id) >= 2 THEN 'Medium'
                ELSE 'Low'
            END AS confidence_level,
            'Compare timing with incident time, CCTV/field input, route and CDR location.' AS suggested_action
        FROM {TABLE_EVENTS}
        WHERE {current_filter}
          AND subscriber_number IS NOT NULL
          AND subscriber_number <> ''
        GROUP BY subscriber_number
        HAVING COUNT(*) >= 5 OR COUNT(DISTINCT searched_cell_id) >= 2
        ORDER BY
            cells_seen DESC,
            records_found DESC
        LIMIT ?
        """,
        [start_time, end_time, int(lead_limit)],
    )

    priority_leads = store.query_df(
        f"""
        WITH current_part AS (
            SELECT
                subscriber_number,
                COUNT(*) AS selected_period_records,
                COUNT(DISTINCT searched_cell_id) AS selected_period_cells,
                COUNT(DISTINCT imei) AS imei_count,
                COUNT(DISTINCT imsi) AS imsi_count,
                MIN(TRY_CAST(event_time AS TIMESTAMP)) AS first_seen,
                MAX(TRY_CAST(event_time AS TIMESTAMP)) AS last_seen
            FROM {TABLE_EVENTS}
            WHERE {current_filter}
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
            GROUP BY subscriber_number
        ),
        baseline AS (
            SELECT
                subscriber_number,
                COUNT(*) AS baseline_records
            FROM {TABLE_EVENTS}
            WHERE {baseline_filter}
              AND subscriber_number IS NOT NULL
              AND subscriber_number <> ''
            GROUP BY subscriber_number
        )
        SELECT
            current_part.subscriber_number AS mobile_number,
            current_part.selected_period_records,
            COALESCE(baseline.baseline_records, 0) AS baseline_records,
            current_part.selected_period_cells,
            current_part.imei_count,
            current_part.imsi_count,
            current_part.first_seen,
            current_part.last_seen,
            CASE
                WHEN baseline.subscriber_number IS NULL AND current_part.selected_period_cells >= 2
                    THEN 'High'
                WHEN baseline.subscriber_number IS NULL AND current_part.selected_period_records >= 5
                    THEN 'Medium'
                WHEN current_part.selected_period_cells >= 2
                    THEN 'Medium-High'
                WHEN current_part.selected_period_records >= 10
                    THEN 'Medium'
                ELSE 'Low'
            END AS priority,
            CASE
                WHEN current_part.selected_period_cells >= 2 AND current_part.selected_period_records >= 5
                    THEN 'High'
                WHEN current_part.selected_period_records >= 3
                    THEN 'Medium'
                ELSE 'Low'
            END AS confidence_level,
            CASE
                WHEN baseline.subscriber_number IS NULL AND current_part.selected_period_cells >= 2
                    THEN 'New/rare number with multi-cell presence'
                WHEN baseline.subscriber_number IS NULL
                    THEN 'New/rare number in selected period'
                WHEN current_part.selected_period_cells >= 2
                    THEN 'Common number with multi-cell presence'
                WHEN current_part.selected_period_records >= 10
                    THEN 'High activity in selected period'
                ELSE 'Low-volume presence'
            END AS simple_reason,
            'Verify priority leads with CDR/SDR/CAF, IMEI/IMSI and field/CCTV information.' AS suggested_action
        FROM current_part
        LEFT JOIN baseline
          ON current_part.subscriber_number = baseline.subscriber_number
        ORDER BY
            CASE
                WHEN baseline.subscriber_number IS NULL AND current_part.selected_period_cells >= 2 THEN 1
                WHEN baseline.subscriber_number IS NULL AND current_part.selected_period_records >= 5 THEN 2
                WHEN current_part.selected_period_cells >= 2 THEN 3
                WHEN current_part.selected_period_records >= 10 THEN 4
                ELSE 9
            END,
            current_part.selected_period_records DESC
        LIMIT ?
        """,
        [start_time, end_time, start_time, end_time, int(lead_limit)],
    )

    lead_summary = pd.DataFrame(
        [
            {
                "finding": "Common Numbers",
                "records": len(common_numbers),
                "meaning": "Numbers seen in selected period and also elsewhere in loaded data.",
            },
            {
                "finding": "Uncommon / New Visitor",
                "records": len(uncommon_numbers),
                "meaning": "Numbers seen in selected period but not seen elsewhere in loaded data.",
            },
            {
                "finding": "Multi-Cell Presence",
                "records": len(multi_cell_presence),
                "meaning": "Numbers seen in more than one searched cell.",
            },
            {
                "finding": "Repeat Presence",
                "records": len(repeat_presence),
                "meaning": "Numbers repeatedly seen in other loaded data also.",
            },
            {
                "finding": "IMEI/IMSI Consistency",
                "records": len(device_consistency),
                "meaning": "Device/SIM consistency or possible change indicators.",
            },
            {
                "finding": "Suspicious Timing",
                "records": len(suspicious_timing),
                "meaning": "Numbers with notable activity during the selected period.",
            },
            {
                "finding": "Priority Leads",
                "records": len(priority_leads),
                "meaning": "Combined ranking based on rarity, cells, activity and confidence.",
            },
        ]
    )

    return {
        "summary": summary,
        "lead_summary": lead_summary,
        "common_numbers": common_numbers,
        "uncommon_numbers": uncommon_numbers,
        "multi_cell_presence": multi_cell_presence,
        "repeat_presence": repeat_presence,
        "device_consistency": device_consistency,
        "suspicious_timing": suspicious_timing,
        "priority_leads": priority_leads,
    }


def tower_ipdr_partwise_range_report_root(case_id: str) -> Path:
    return (
        Path("cases")
        / "active"
        / str(case_id)
        / "reports"
        / "tower_dump"
        / "ipdr"
        / "partwise_range"
    )


def _report_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _report_json_safe(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_report_json_safe(item) for item in value]

    if isinstance(value, tuple):
        return [_report_json_safe(item) for item in value]

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)

    return value


def export_tower_ipdr_partwise_range_report(
    case_id: str,
    parts: list[dict[str, Any]],
    *,
    lead_limit: int = 50,
    max_leads_in_text: int = 20,
) -> dict[str, Any]:
    """Export Tower IPDR report for saved Date-Time Parts.

    Main production export:
    - Each saved Date-Time Part is analyzed by range:
      start_time <= event_time < end_time
    - Officer-friendly TXT report is saved.
    - Detailed CSV tables are saved for every part.
    - manifest.json records the export details.
    """

    import io
    from contextlib import redirect_stdout

    if not parts:
        raise ValueError("Date-Time Parts available nahi hain.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"tower_ipdr_partwise_range_{timestamp}"

    output_dir = tower_ipdr_partwise_range_report_root(case_id) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_files: dict[str, str] = {}
    part_summaries: list[dict[str, Any]] = []
    part_manifests: list[dict[str, Any]] = []

    text_buffer = io.StringIO()

    print("=" * 78, file=text_buffer)
    print("TOWER IPDR PART-WISE INVESTIGATION REPORT", file=text_buffer)
    print("=" * 78, file=text_buffer)
    print(f"Case ID     : {case_id}", file=text_buffer)
    print(f"Report Run  : {run_id}", file=text_buffer)
    print(f"Total Parts : {len(parts)}", file=text_buffer)
    print("", file=text_buffer)
    print("Important Note:", file=text_buffer)
    print(
        "This report gives investigation leads. "
        "Every lead must be verified with CDR, SDR/CAF, IMEI/IMSI, "
        "operator records and field information before conclusion.",
        file=text_buffer,
    )
    print("", file=text_buffer)

    try:
        from modules.cases.date_time_partitions import find_overlapping_date_time_parts

        overlap_warnings = find_overlapping_date_time_parts(parts)
    except Exception:
        overlap_warnings = []

    if overlap_warnings:
        print("-" * 78, file=text_buffer)
        print("DATE-TIME PART WARNING", file=text_buffer)
        print("-" * 78, file=text_buffer)

        for warning in overlap_warnings:
            print(f"[!] {warning.get('message')}", file=text_buffer)
            print(f"    {warning.get('left_part')} : {warning.get('left_range')}", file=text_buffer)
            print(f"    {warning.get('right_part')}: {warning.get('right_range')}", file=text_buffer)

        print(
            "Meaning: Overlap intentional ho sakta hai, lekin comparison karte time "
            "dhyan rakhein ki same records multiple parts me aa sakte hain.",
            file=text_buffer,
        )
        print("", file=text_buffer)

    for part in parts:
        part_no = int(part.get("part_no", 0))
        part_name = str(part.get("part_name") or f"Part {part_no}")
        start_time = str(part.get("start_time"))
        end_time = str(part.get("end_time"))

        print("\n" + "#" * 78, file=text_buffer)
        print(f"{part_name.upper()} REPORT", file=text_buffer)
        print("#" * 78, file=text_buffer)
        print(f"Period: {start_time} to {end_time}", file=text_buffer)

        result = tower_ipdr_range_investigation_summary(
            case_id,
            start_time,
            end_time,
            lead_limit=lead_limit,
        )

        part_prefix = f"part_{part_no:02d}"

        for table_name, dataframe in result.items():
            if not isinstance(dataframe, pd.DataFrame):
                continue

            csv_path = output_dir / f"{part_prefix}_{table_name}.csv"
            dataframe.to_csv(csv_path, index=False)
            saved_files[f"{part_prefix}_{table_name}"] = str(csv_path)

        summary_df = result.get("summary", pd.DataFrame())

        if isinstance(summary_df, pd.DataFrame) and not summary_df.empty:
            summary_row = summary_df.iloc[0].to_dict()
        else:
            summary_row = {}

        part_summary = {
            "part_no": part_no,
            "part_name": part_name,
            "start_time": start_time,
            "end_time": end_time,
            "records_found": summary_row.get("records_found", 0),
            "numbers_found": summary_row.get("numbers_found", 0),
            "cells_involved": summary_row.get("cells_involved", 0),
            "first_activity": summary_row.get("first_activity", ""),
            "last_activity": summary_row.get("last_activity", ""),
        }
        part_summaries.append(part_summary)

        with redirect_stdout(text_buffer):
            print_tower_ipdr_investigation_summary(
                result,
                max_leads=max_leads_in_text,
            )

        part_manifests.append(
            {
                "part_no": part_no,
                "part_name": part_name,
                "start_time": start_time,
                "end_time": end_time,
                "saved_tables_prefix": part_prefix,
                "summary": _report_json_safe(part_summary),
            }
        )

    all_parts_summary = pd.DataFrame(part_summaries)
    all_parts_summary_path = output_dir / "all_parts_summary.csv"
    all_parts_summary.to_csv(all_parts_summary_path, index=False)
    saved_files["all_parts_summary"] = str(all_parts_summary_path)

    text_path = output_dir / "investigation_summary_all_parts.txt"
    text_path.write_text(text_buffer.getvalue(), encoding="utf-8")
    saved_files["investigation_summary_all_parts"] = str(text_path)

    manifest_path = output_dir / "manifest.json"
    saved_files["manifest"] = str(manifest_path)

    manifest = {
        "case_id": str(case_id),
        "run_id": run_id,
        "created_at": _now_iso(),
        "analysis_type": "Tower IPDR Part-wise Date-Time Range Analysis",
        "range_rule": "start_time <= event_time < end_time",
        "display_rule": "Start aur End Date-Time ke beech ka data",
        "parts_count": len(parts),
        "lead_limit": int(lead_limit),
        "max_leads_in_text": int(max_leads_in_text),
        "output_dir": str(output_dir),
        "overlap_warnings": _report_json_safe(overlap_warnings),
        "parts": _report_json_safe(part_manifests),
        "saved_files": _report_json_safe(saved_files),
        "note": (
            "This report provides investigation leads. "
            "Final conclusion requires verification from independent sources."
        ),
    }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            _report_json_safe(manifest),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    saved_files["manifest"] = str(manifest_path)

    return manifest
