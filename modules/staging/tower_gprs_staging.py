"""
Tower GPRS scalable staging constants and helpers.

Purpose:
- Provide one canonical workflow/table name for Tower GPRS scalable backend.
- Reuse the common scalable pipeline for Parquet + DuckDB storage.
- Keep backend files hidden from normal user-facing output.

User-facing result should remain Excel/GUI.
DuckDB, Parquet and JSON are internal backend/cache files.
"""

from __future__ import annotations

from pathlib import Path

from modules.staging.scalable_store import (
    case_staging_root,
    duckdb_database_path,
    parquet_dataset_path,
    query_database,
)


TOWER_GPRS_WORKFLOW = "tower_gprs_dump"
TOWER_GPRS_TABLE = "tower_gprs_sessions"
TOWER_GPRS_DATASET = "normalized"

SUPPORTED_SUFFIXES = {".csv", ".txt", ".tsv", ".xlsx", ".xls"}


def tower_gprs_staging_root(case_id: str) -> Path:
    """Return Tower GPRS staging root."""

    return case_staging_root(case_id, TOWER_GPRS_WORKFLOW)


def tower_gprs_parquet_path(case_id: str) -> Path:
    """Return Tower GPRS normalized Parquet path."""

    return parquet_dataset_path(
        case_id,
        TOWER_GPRS_WORKFLOW,
        TOWER_GPRS_DATASET,
    )


def tower_gprs_duckdb_path(case_id: str) -> Path:
    """Return Tower GPRS DuckDB path."""

    return duckdb_database_path(case_id, TOWER_GPRS_WORKFLOW)


def count_tower_gprs_sessions(case_id: str) -> int:
    """Return staged Tower GPRS session count."""

    db_path = tower_gprs_duckdb_path(case_id)

    if not db_path.exists():
        return 0

    result = query_database(
        db_path,
        f"SELECT COUNT(*) AS total_records FROM {TOWER_GPRS_TABLE}",
    )

    if result.empty:
        return 0

    return int(result.iloc[0]["total_records"])
