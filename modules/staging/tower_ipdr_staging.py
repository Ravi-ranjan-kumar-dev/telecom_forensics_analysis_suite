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
