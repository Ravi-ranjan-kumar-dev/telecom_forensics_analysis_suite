"""Fingerprint-verified reuse of normalized Parquet and DuckDB stages.

The cache stores only derived normalized data and loader diagnostics. Raw
evidence remains unchanged. A file, timestamp, size, Spot selection or cache
contract change makes the caller fall back to the normal loader.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from modules.cases.repository import normalize_case_id
from modules.staging.scalable_store import (
    case_staging_root,
    duckdb_database_path,
    manifest_path,
    parquet_dataset_path,
    query_database,
)


CACHE_SCHEMA_VERSION = 1

LOAD_CONTEXT_KEYS = (
    "files",
    "operators",
    "cell_ids",
    "metadata",
    "warnings",
    "errors",
)

LOAD_DATAFRAME_KEYS = (
    "file_summary",
    "spot_summary",
    "rejected_rows",
)

VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _json_default(value: Any) -> Any:
    """Convert common scalar objects used in loader metadata."""

    if isinstance(value, Path):
        return str(value)

    item = getattr(value, "item", None)

    if callable(item):
        try:
            return item()
        except (TypeError, ValueError):
            pass

    return str(value)


def _cache_root(case_id: str, workflow: str) -> Path:
    return case_staging_root(case_id, workflow) / "cache" / "normalized_pipeline"


def normalized_cache_manifest_path(case_id: str, workflow: str) -> Path:
    """Return the canonical normalized cache manifest path."""

    return _cache_root(case_id, workflow) / "cache_manifest.json"


def _frame_path(case_id: str, workflow: str, key: str) -> Path:
    return _cache_root(case_id, workflow) / f"{key}.parquet"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.temporary")

    try:
        temporary.write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
                default=_json_default,
            ),
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_frame(path: Path, value: Any) -> dict[str, Any]:
    frame = value.copy() if isinstance(value, pd.DataFrame) else pd.DataFrame()
    empty_without_columns = len(frame.columns) == 0
    stored = (
        pd.DataFrame({"__empty_cache_table__": pd.Series(dtype="int8")})
        if empty_without_columns
        else frame
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.stem}.temporary.parquet")

    try:
        stored.to_parquet(temporary, index=False)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)

    return {
        "rows": int(len(frame)),
        "columns": [str(column) for column in frame.columns],
        "empty_without_columns": empty_without_columns,
    }


def _read_frame(path: Path, metadata: dict[str, Any]) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Cached loader table missing: {path}")

    frame = pd.read_parquet(path)

    if bool(metadata.get("empty_without_columns", False)):
        frame = pd.DataFrame()

    expected_rows = int(metadata.get("rows", -1))
    expected_columns = [str(value) for value in metadata.get("columns", [])]

    if len(frame) != expected_rows or list(map(str, frame.columns)) != expected_columns:
        raise ValueError(f"Cached loader table validation failed: {path.name}")

    return frame


def validate_normalized_stage(
    *,
    case_id: str,
    workflow: str,
    table_name: str,
    dataset_name: str,
    dataframe: pd.DataFrame,
    required_columns: Iterable[str] = (),
) -> dict[str, Any]:
    """Verify canonical Parquet, DuckDB and manifest state for a DataFrame."""

    if not VALID_IDENTIFIER.fullmatch(str(table_name)):
        raise ValueError(f"Invalid cached table name: {table_name!r}")

    required = {str(column) for column in required_columns}
    missing = sorted(required.difference(dataframe.columns))

    if missing:
        raise ValueError(
            "Reusable normalized stage is missing required column(s): "
            + ", ".join(missing)
        )

    parquet_path = parquet_dataset_path(case_id, workflow, dataset_name)
    database_path = duckdb_database_path(case_id, workflow)
    stage_manifest_path = manifest_path(case_id, workflow, dataset_name)

    for label, path in (
        ("Parquet", parquet_path),
        ("DuckDB", database_path),
        ("stage manifest", stage_manifest_path),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"Reusable {label} file missing: {path}")

    stage = json.loads(stage_manifest_path.read_text(encoding="utf-8"))
    expected_values = {
        "case_id": normalize_case_id(case_id),
        "workflow": str(workflow),
        "dataset_name": str(dataset_name),
        "table_name": str(table_name),
    }

    for key, expected in expected_values.items():
        if str(stage.get(key, "")) != expected:
            raise ValueError(
                f"Reusable stage {key} does not match the current workflow."
            )

    record_count = int(stage.get("record_count", 0) or 0)

    if record_count <= 0 or record_count != len(dataframe):
        raise ValueError(
            "Reusable Parquet row count does not match the normalized data."
        )

    count_result = query_database(
        database_path,
        f'SELECT COUNT(*) AS total_records FROM "{table_name}"',
    )
    database_records = (
        int(count_result.iloc[0]["total_records"])
        if not count_result.empty
        else 0
    )

    if database_records != record_count:
        raise ValueError(
            "Reusable DuckDB row count does not match the Parquet stage."
        )

    return {
        **stage,
        "record_count": record_count,
        "column_count": int(len(dataframe.columns)),
        "parquet_path": str(parquet_path),
        "duckdb_path": str(database_path),
        "manifest_path": str(stage_manifest_path),
    }


def load_reusable_normalized_stage(
    *,
    case_id: str,
    workflow: str,
    table_name: str,
    dataset_name: str,
    cache_key: str,
    input_fingerprint: dict[str, Any],
    required_columns: Iterable[str],
    dataframe_key: str,
) -> dict[str, Any]:
    """Return a reusable loader result when evidence and stage match."""

    cache_path = normalized_cache_manifest_path(case_id, workflow)

    if not cache_path.is_file():
        return {"reused": False, "reason": "CACHE_MANIFEST_NOT_FOUND"}

    try:
        manifest = json.loads(cache_path.read_text(encoding="utf-8"))

        if int(manifest.get("schema_version", 0)) != CACHE_SCHEMA_VERSION:
            raise ValueError("CACHE_SCHEMA_CHANGED")

        if str(manifest.get("cache_key", "")) != str(cache_key):
            raise ValueError("CACHE_KEY_CHANGED")

        if manifest.get("input_fingerprint", {}) != input_fingerprint:
            raise ValueError("INPUT_FILES_CHANGED")

        dataframe = pd.read_parquet(
            parquet_dataset_path(case_id, workflow, dataset_name)
        )
        stage = validate_normalized_stage(
            case_id=case_id,
            workflow=workflow,
            table_name=table_name,
            dataset_name=dataset_name,
            dataframe=dataframe,
            required_columns=required_columns,
        )
        context = manifest.get("load_context", {})
        frame_metadata = manifest.get("load_dataframes", {})
        load_result: dict[str, Any] = {
            "ok": True,
            dataframe_key: dataframe,
            "file_results": [],
            "cache_reused": True,
            "cache_reason": "INPUT_UNCHANGED",
            "scalable_stage": stage,
        }

        for key in LOAD_CONTEXT_KEYS:
            if key in context:
                load_result[key] = context[key]

        for key in LOAD_DATAFRAME_KEYS:
            metadata = frame_metadata.get(key)

            if not isinstance(metadata, dict):
                raise ValueError(f"Cached loader context missing: {key}")

            load_result[key] = _read_frame(
                _frame_path(case_id, workflow, key),
                metadata,
            )

        metadata = dict(load_result.get("metadata", {}) or {})
        metadata.update(
            cache_reused=True,
            cache_source="normalized.parquet",
        )
        load_result["metadata"] = metadata

        warnings = list(load_result.get("warnings", []) or [])
        cache_message = "Raw input files unchanged; verified normalized stage reused."

        if cache_message not in warnings:
            warnings.append(cache_message)

        load_result["warnings"] = warnings

        return {
            "reused": True,
            "reason": "INPUT_UNCHANGED",
            "load_result": load_result,
            "dataframe": dataframe,
            "stage": stage,
        }
    except Exception as error:
        reason = str(error).strip()

        if reason not in {
            "CACHE_SCHEMA_CHANGED",
            "CACHE_KEY_CHANGED",
            "INPUT_FILES_CHANGED",
        }:
            reason = f"{type(error).__name__}: {error}"

        return {"reused": False, "reason": reason}


def save_reusable_normalized_stage(
    *,
    case_id: str,
    workflow: str,
    cache_key: str,
    input_fingerprint: dict[str, Any],
    load_result: Any,
) -> Path:
    """Persist loader diagnostics needed to reuse one normalized stage."""

    if not isinstance(load_result, dict):
        raise TypeError(
            "Reusable normalized cache requires a loader result dictionary."
        )

    context = {
        key: load_result[key]
        for key in LOAD_CONTEXT_KEYS
        if key in load_result
    }
    frame_metadata = {
        key: _write_frame(
            _frame_path(case_id, workflow, key),
            load_result.get(key),
        )
        for key in LOAD_DATAFRAME_KEYS
    }
    cache_path = normalized_cache_manifest_path(case_id, workflow)
    _atomic_write_json(
        cache_path,
        {
            "schema_version": CACHE_SCHEMA_VERSION,
            "cache_key": str(cache_key),
            "input_fingerprint": input_fingerprint,
            "load_context": context,
            "load_dataframes": frame_metadata,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    return cache_path
