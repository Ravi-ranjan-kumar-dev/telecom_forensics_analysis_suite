"""
Tower CDR scalable staging helpers.

Purpose:
- Store normalized Tower CDR Dump data as Parquet.
- Register the same data as a DuckDB table.
- Save input fingerprint and latest stage metadata.

This module prepares Tower CDR for heavy-data analysis and future GUI reuse.
Existing Tower CDR analysis/reporting can continue while this backend matures.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from modules.staging.scalable_store import (
    case_staging_root,
    duckdb_database_path,
    parquet_dataset_path,
    query_database,
    stage_dataframe_to_parquet_and_duckdb,
)


TOWER_CDR_WORKFLOW = "tower_cdr_dump"
TOWER_CDR_TABLE = "tower_cdr_events"
TOWER_CDR_DATASET = "normalized"

SUPPORTED_SUFFIXES = {".csv", ".txt", ".tsv", ".xlsx", ".xls"}


def tower_cdr_staging_root(case_id: str) -> Path:
    """Return Tower CDR staging root for a case."""

    return case_staging_root(case_id, TOWER_CDR_WORKFLOW)


def tower_cdr_parquet_path(case_id: str) -> Path:
    """Return Tower CDR normalized Parquet path."""

    return parquet_dataset_path(
        case_id,
        TOWER_CDR_WORKFLOW,
        TOWER_CDR_DATASET,
    )


def tower_cdr_duckdb_path(case_id: str) -> Path:
    """Return Tower CDR DuckDB database path."""

    return duckdb_database_path(case_id, TOWER_CDR_WORKFLOW)


def tower_cdr_latest_stage_path(case_id: str) -> Path:
    """Return latest Tower CDR staging metadata path."""

    return tower_cdr_staging_root(case_id) / "latest_stage.json"


def tower_cdr_input_fingerprint(input_folder: str | Path) -> dict[str, Any]:
    """
    Build a simple fingerprint for Tower CDR input files.

    It records relative path, file size and modified-time nanoseconds.
    Later this helps decide whether staged backend data is still fresh.
    """

    root = Path(input_folder)
    files: list[dict[str, Any]] = []

    if root.exists():
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue

            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue

            stat = path.stat()
            try:
                relative_path = str(path.relative_to(root))
            except ValueError:
                relative_path = str(path)

            files.append(
                {
                    "path": relative_path,
                    "size": int(stat.st_size),
                    "mtime_ns": int(stat.st_mtime_ns),
                }
            )

    return {
        "input_folder": str(root),
        "file_count": len(files),
        "total_size": sum(item["size"] for item in files),
        "files": files,
    }


def stage_tower_cdr_dataframe(
    case_id: str,
    dataframe: pd.DataFrame,
    input_folder: str | Path,
    stage_reason: str = "tower_cdr_analysis",
) -> dict[str, Any]:
    """
    Stage normalized Tower CDR dataframe to Parquet and DuckDB.

    Main output:
    - cases/active/<case_id>/staging/tower_cdr_dump/parquet/normalized.parquet
    - cases/active/<case_id>/staging/tower_cdr_dump/tower_cdr_dump.duckdb
    - cases/active/<case_id>/staging/tower_cdr_dump/latest_stage.json
    """

    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("Tower CDR staging requires a pandas DataFrame.")

    stage_result = stage_dataframe_to_parquet_and_duckdb(
        case_id=case_id,
        workflow=TOWER_CDR_WORKFLOW,
        dataframe=dataframe,
        table_name=TOWER_CDR_TABLE,
        dataset_name=TOWER_CDR_DATASET,
    )

    payload = {
        **asdict(stage_result),
        "stage_reason": stage_reason,
        "input_fingerprint": tower_cdr_input_fingerprint(input_folder),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }

    latest_path = tower_cdr_latest_stage_path(case_id)
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return payload


def load_latest_tower_cdr_stage(case_id: str) -> dict[str, Any] | None:
    """Read latest Tower CDR staging metadata if available."""

    path = tower_cdr_latest_stage_path(case_id)

    if not path.exists():
        return None

    return json.loads(path.read_text(encoding="utf-8"))


def count_tower_cdr_events(case_id: str) -> int:
    """Return count of staged Tower CDR events from DuckDB."""

    db_path = tower_cdr_duckdb_path(case_id)

    if not db_path.exists():
        return 0

    result = query_database(
        db_path,
        f"SELECT COUNT(*) AS total_records FROM {TOWER_CDR_TABLE}",
    )

    if result.empty:
        return 0

    return int(result.iloc[0]["total_records"])


def print_tower_cdr_stage_summary(payload: dict[str, Any]) -> None:
    """Print user-friendly Tower CDR scalable backend status.

    Normal users should not see backend file paths such as DuckDB, Parquet,
    or JSON manifest files. Those are internal software cache files.
    """

    import os

    fingerprint = payload.get("input_fingerprint", {}) or {}
    debug_backend = os.environ.get("TELECOM_DEBUG_BACKEND") == "1"

    print()
    print("TOWER CDR FAST ANALYSIS BACKEND READY")
    print("-" * 78)
    print(f"Records indexed : {int(payload.get('record_count', 0)):,}")
    print(f"Columns indexed : {int(payload.get('column_count', 0)):,}")
    print(f"Input files     : {int(fingerprint.get('file_count', 0)):,}")
    print("Speed mode      : DuckDB SQL + Parquet internal backend")
    print("User output     : Excel report only")
    print("-" * 78)

    if debug_backend:
        print("DEBUG BACKEND FILES")
        print("-" * 78)
        print(f"Parquet file    : {payload.get('parquet_path', '')}")
        print(f"DuckDB file     : {payload.get('duckdb_path', '')}")
        print(f"Manifest        : {payload.get('manifest_path', '')}")
        print("-" * 78)
