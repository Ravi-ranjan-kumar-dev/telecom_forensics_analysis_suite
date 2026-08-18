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
from typing import Any, Iterable

import pandas as pd

from modules.loader.tower_spot_layout import (
    normalize_selected_spot_folders,
    select_tower_evidence_files,
)
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


def tower_cdr_input_fingerprint(
    input_folder: str | Path,
    *,
    selected_spot_folders: Iterable[str] | None = None,
    include_root_files: bool = True,
) -> dict[str, Any]:
    """Build a selection-aware fingerprint for Tower CDR evidence."""

    root = Path(
        input_folder
    ).expanduser().resolve(
        strict=False
    )
    files: list[dict[str, Any]] = []

    normalized_selection: tuple[str, ...] | None = None

    if root.is_dir():
        if selected_spot_folders is not None:
            normalized_selection = normalize_selected_spot_folders(
                root,
                selected_spot_folders,
            )

        candidates = [
            path
            for path in root.rglob("*")
            if (
                path.is_file()
                and path.suffix.lower()
                in SUPPORTED_SUFFIXES
            )
        ]
        selected_files = select_tower_evidence_files(
            root,
            candidates,
            selected_spot_folders=normalized_selection,
            include_root_files=include_root_files,
        )

        for path in selected_files:
            stat = path.stat()
            files.append(
                {
                    "path": str(
                        path.relative_to(
                            root
                        )
                    ),
                    "size": int(
                        stat.st_size
                    ),
                    "mtime_ns": int(
                        stat.st_mtime_ns
                    ),
                }
            )

    return {
        "input_folder": str(
            root
        ),
        "selected_spot_folders": (
            list(
                normalized_selection
            )
            if normalized_selection is not None
            else None
        ),
        "include_root_files": bool(
            include_root_files
        ),
        "file_count": len(
            files
        ),
        "total_size": sum(
            item["size"]
            for item in files
        ),
        "files": files,
    }


def stage_tower_cdr_dataframe(
    case_id: str,
    dataframe: pd.DataFrame,
    input_folder: str | Path,
    stage_reason: str = "tower_cdr_analysis",
    *,
    selected_spot_folders: Iterable[str] | None = None,
    include_root_files: bool = True,
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
        "input_fingerprint": tower_cdr_input_fingerprint(
            input_folder,
            selected_spot_folders=(
                selected_spot_folders
            ),
            include_root_files=(
                include_root_files
            ),
        ),
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



# Version 2 invalidates stages created before stable full-inventory Spot IDs.
TOWER_CDR_REUSE_SCHEMA_VERSION = 2


def tower_cdr_reuse_manifest_path(
    case_id: str,
) -> Path:
    """Return normalized Tower CDR reusable-cache manifest path."""

    return (
        tower_cdr_staging_root(case_id)
        / "cache"
        / "reuse_manifest.json"
    )


def save_tower_cdr_reuse_manifest(
    case_id: str,
    input_folder: str | Path,
    dataframe: pd.DataFrame,
    *,
    selected_spot_folders: Iterable[str] | None = None,
    include_root_files: bool = True,
) -> dict[str, Any]:
    """Save a verified reusable-stage manifest after successful staging."""

    if not isinstance(
        dataframe,
        pd.DataFrame,
    ):
        raise TypeError(
            "Tower CDR reuse manifest requires a pandas DataFrame."
        )

    parquet_path = tower_cdr_parquet_path(
        case_id
    )

    database_path = tower_cdr_duckdb_path(
        case_id
    )

    if not parquet_path.exists():
        raise FileNotFoundError(
            f"Tower CDR Parquet stage missing: {parquet_path}"
        )

    if not database_path.exists():
        raise FileNotFoundError(
            f"Tower CDR DuckDB stage missing: {database_path}"
        )

    database_rows = int(
        count_tower_cdr_events(
            case_id
        )
    )

    dataframe_rows = int(
        len(dataframe)
    )

    if (
        database_rows <= 0
        or dataframe_rows <= 0
        or database_rows != dataframe_rows
    ):
        raise ValueError(
            "Tower CDR reusable stage row-count mismatch. "
            f"DataFrame={dataframe_rows}, DuckDB={database_rows}"
        )

    parquet_stat = parquet_path.stat()
    database_stat = database_path.stat()

    payload = {
        "schema_version": (
            TOWER_CDR_REUSE_SCHEMA_VERSION
        ),
        "workflow": TOWER_CDR_WORKFLOW,
        "dataset": TOWER_CDR_DATASET,
        "table_name": TOWER_CDR_TABLE,
        "input_fingerprint": (
            tower_cdr_input_fingerprint(
                input_folder,
                selected_spot_folders=selected_spot_folders,
                include_root_files=include_root_files,
            )
        ),
        "record_count": dataframe_rows,
        "column_count": int(
            len(dataframe.columns)
        ),
        "columns": [
            str(column)
            for column in dataframe.columns
        ],
        "parquet_path": str(
            parquet_path
        ),
        "parquet_size": int(
            parquet_stat.st_size
        ),
        "parquet_mtime_ns": int(
            parquet_stat.st_mtime_ns
        ),
        "duckdb_path": str(
            database_path
        ),
        "duckdb_size": int(
            database_stat.st_size
        ),
        "duckdb_mtime_ns": int(
            database_stat.st_mtime_ns
        ),
        "created_at": datetime.now().isoformat(
            timespec="seconds"
        ),
    }

    manifest_path = (
        tower_cdr_reuse_manifest_path(
            case_id
        )
    )

    manifest_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = manifest_path.with_suffix(
        ".json.tmp"
    )

    temporary_path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(
        manifest_path
    )

    return payload


def load_reusable_tower_cdr_stage(
    case_id: str,
    input_folder: str | Path,
    *,
    selected_spot_folders: Iterable[str] | None = None,
    include_root_files: bool = True,
) -> dict[str, Any]:
    """Load normalized Parquet only when input and stage are unchanged."""

    manifest_path = (
        tower_cdr_reuse_manifest_path(
            case_id
        )
    )

    if not manifest_path.exists():
        return {
            "reused": False,
            "reason": "REUSE_MANIFEST_NOT_FOUND",
            "dataframe": None,
            "manifest": {},
        }

    try:
        manifest = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )
    except Exception as error:
        return {
            "reused": False,
            "reason": (
                "REUSE_MANIFEST_INVALID"
            ),
            "error": (
                f"{type(error).__name__}: "
                f"{error}"
            ),
            "dataframe": None,
            "manifest": {},
        }

    if int(
        manifest.get(
            "schema_version",
            0,
        )
    ) != TOWER_CDR_REUSE_SCHEMA_VERSION:
        return {
            "reused": False,
            "reason": "REUSE_SCHEMA_CHANGED",
            "dataframe": None,
            "manifest": manifest,
        }

    current_fingerprint = (
        tower_cdr_input_fingerprint(
            input_folder,
            selected_spot_folders=selected_spot_folders,
            include_root_files=include_root_files,
        )
    )

    saved_fingerprint = manifest.get(
        "input_fingerprint",
        {},
    )

    if current_fingerprint != saved_fingerprint:
        return {
            "reused": False,
            "reason": "INPUT_FILES_CHANGED",
            "dataframe": None,
            "manifest": manifest,
            "current_fingerprint": (
                current_fingerprint
            ),
        }

    parquet_path = tower_cdr_parquet_path(
        case_id
    )

    database_path = tower_cdr_duckdb_path(
        case_id
    )

    if not parquet_path.exists():
        return {
            "reused": False,
            "reason": "PARQUET_STAGE_MISSING",
            "dataframe": None,
            "manifest": manifest,
        }

    if not database_path.exists():
        return {
            "reused": False,
            "reason": "DUCKDB_STAGE_MISSING",
            "dataframe": None,
            "manifest": manifest,
        }

    expected_records = int(
        manifest.get(
            "record_count",
            0,
        )
        or 0
    )

    try:
        database_records = int(
            count_tower_cdr_events(
                case_id
            )
        )
    except Exception as error:
        return {
            "reused": False,
            "reason": "DUCKDB_COUNT_FAILED",
            "error": (
                f"{type(error).__name__}: "
                f"{error}"
            ),
            "dataframe": None,
            "manifest": manifest,
        }

    if (
        expected_records <= 0
        or database_records
        != expected_records
    ):
        return {
            "reused": False,
            "reason": (
                "DUCKDB_RECORD_COUNT_MISMATCH"
            ),
            "dataframe": None,
            "manifest": manifest,
            "database_records": (
                database_records
            ),
        }

    try:
        dataframe = pd.read_parquet(
            parquet_path
        )
    except Exception as error:
        return {
            "reused": False,
            "reason": "PARQUET_READ_FAILED",
            "error": (
                f"{type(error).__name__}: "
                f"{error}"
            ),
            "dataframe": None,
            "manifest": manifest,
        }

    if len(dataframe) != expected_records:
        return {
            "reused": False,
            "reason": (
                "PARQUET_RECORD_COUNT_MISMATCH"
            ),
            "dataframe": None,
            "manifest": manifest,
            "parquet_records": int(
                len(dataframe)
            ),
        }

    required_columns = {
        "subscriber_number",
        "call_datetime",
        "searched_cell_id",
        "source_relative_path",
        "spot_id",
        "spot_name",
    }

    missing_columns = sorted(
        required_columns.difference(
            dataframe.columns
        )
    )

    if missing_columns:
        return {
            "reused": False,
            "reason": (
                "PARQUET_REQUIRED_COLUMNS_MISSING"
            ),
            "missing_columns": (
                missing_columns
            ),
            "dataframe": None,
            "manifest": manifest,
        }

    return {
        "reused": True,
        "reason": "INPUT_UNCHANGED",
        "dataframe": dataframe,
        "manifest": manifest,
        "current_fingerprint": (
            current_fingerprint
        ),
    }

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
