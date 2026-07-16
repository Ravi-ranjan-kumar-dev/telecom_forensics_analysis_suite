"""
Common scalable storage helpers for Telecom Forensics Analysis Suite.

Purpose:
- Save normalized telecom data as Parquet.
- Register Parquet data inside DuckDB.
- Query staged data using DuckDB.
- Save a small manifest JSON for traceability.

This file is a foundation layer. Existing workflows do not change automatically
until their controllers/loaders start using these helpers.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import duckdb
import pandas as pd


_VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class ScalableStageResult:
    """Result returned after a DataFrame is staged to Parquet and DuckDB."""

    case_id: str
    workflow: str
    dataset_name: str
    table_name: str
    record_count: int
    column_count: int
    parquet_path: str
    duckdb_path: str
    manifest_path: str
    generated_at: str


def _safe_identifier(value: str, label: str) -> str:
    """Validate table/workflow-like names used inside SQL identifiers."""

    value = str(value or "").strip()

    if not _VALID_IDENTIFIER.match(value):
        raise ValueError(
            f"Invalid {label}: {value!r}. "
            "Use only letters, numbers and underscore. "
            "First character must be a letter or underscore."
        )

    return value


def _quote_identifier(value: str) -> str:
    """Return a safely quoted DuckDB identifier."""

    value = _safe_identifier(value, "SQL identifier")
    return f'"{value}"'


def _sql_string(value: str | Path) -> str:
    """Return a safely quoted SQL string literal for file paths."""

    text = str(value)
    return "'" + text.replace("'", "''") + "'"


def case_staging_root(case_id: str, workflow: str) -> Path:
    """Return staging root for a case workflow."""

    workflow = _safe_identifier(workflow, "workflow")
    return Path("cases") / "active" / str(case_id) / "staging" / workflow


def parquet_dataset_path(
    case_id: str,
    workflow: str,
    dataset_name: str = "normalized",
) -> Path:
    """Return default Parquet path for a staged dataset."""

    workflow = _safe_identifier(workflow, "workflow")
    dataset_name = _safe_identifier(dataset_name, "dataset_name")

    return case_staging_root(case_id, workflow) / "parquet" / f"{dataset_name}.parquet"


def duckdb_database_path(case_id: str, workflow: str) -> Path:
    """Return default DuckDB database path for a workflow."""

    workflow = _safe_identifier(workflow, "workflow")
    return case_staging_root(case_id, workflow) / f"{workflow}.duckdb"


def manifest_path(case_id: str, workflow: str, dataset_name: str = "normalized") -> Path:
    """Return manifest path for a staged dataset."""

    workflow = _safe_identifier(workflow, "workflow")
    dataset_name = _safe_identifier(dataset_name, "dataset_name")

    return case_staging_root(case_id, workflow) / "manifest" / f"{dataset_name}.json"


def write_dataframe_to_parquet_with_duckdb(
    dataframe: pd.DataFrame,
    parquet_path: str | Path,
    compression: str = "SNAPPY",
) -> Path:
    """
    Save a pandas DataFrame as Parquet using DuckDB.

    DuckDB is used here so this helper does not depend on pandas pyarrow setup.
    """

    if dataframe is None:
        dataframe = pd.DataFrame()

    parquet_path = Path(parquet_path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    connection = duckdb.connect(database=":memory:")
    try:
        connection.register("source_dataframe", dataframe)
        connection.execute(
            "COPY source_dataframe TO "
            f"{_sql_string(parquet_path)} "
            f"(FORMAT PARQUET, COMPRESSION {compression})"
        )
    finally:
        connection.close()

    return parquet_path


def read_parquet_to_dataframe(parquet_path: str | Path) -> pd.DataFrame:
    """Read Parquet file into a pandas DataFrame using DuckDB."""

    parquet_path = Path(parquet_path)

    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet file not found: {parquet_path}")

    connection = duckdb.connect(database=":memory:")
    try:
        return connection.execute(
            "SELECT * FROM read_parquet(?)",
            [str(parquet_path)],
        ).fetchdf()
    finally:
        connection.close()


def create_or_replace_table_from_parquet(
    duckdb_path: str | Path,
    table_name: str,
    parquet_path: str | Path,
) -> None:
    """Create or replace a DuckDB table from a Parquet file."""

    table_name = _safe_identifier(table_name, "table_name")
    duckdb_path = Path(duckdb_path)
    parquet_path = Path(parquet_path)

    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet file not found: {parquet_path}")

    duckdb_path.parent.mkdir(parents=True, exist_ok=True)

    connection = duckdb.connect(str(duckdb_path), read_only=False)
    try:
        connection.execute(
            f"CREATE OR REPLACE TABLE {_quote_identifier(table_name)} AS "
            "SELECT * FROM read_parquet(?)",
            [str(parquet_path)],
        )
    finally:
        connection.close()


def query_database(
    duckdb_path: str | Path,
    sql: str,
    parameters: Iterable[Any] | None = None,
) -> pd.DataFrame:
    """Run a SQL query against a DuckDB database and return a DataFrame."""

    duckdb_path = Path(duckdb_path)

    if not duckdb_path.exists():
        raise FileNotFoundError(f"DuckDB database not found: {duckdb_path}")

    connection = duckdb.connect(str(duckdb_path), read_only=False)
    try:
        return connection.execute(sql, list(parameters or [])).fetchdf()
    finally:
        connection.close()


def write_manifest(payload: dict[str, Any], output_path: str | Path) -> Path:
    """Write a manifest JSON file."""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path


def read_manifest(input_path: str | Path) -> dict[str, Any]:
    """Read a manifest JSON file."""

    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Manifest not found: {input_path}")

    return json.loads(input_path.read_text(encoding="utf-8"))


def stage_dataframe_to_parquet_and_duckdb(
    case_id: str,
    workflow: str,
    dataframe: pd.DataFrame,
    table_name: str,
    dataset_name: str = "normalized",
    compression: str = "SNAPPY",
) -> ScalableStageResult:
    """
    Stage a normalized DataFrame as Parquet and DuckDB table.

    This is the main helper future workflows should call after normalization.
    """

    workflow = _safe_identifier(workflow, "workflow")
    table_name = _safe_identifier(table_name, "table_name")
    dataset_name = _safe_identifier(dataset_name, "dataset_name")

    if dataframe is None:
        dataframe = pd.DataFrame()

    parquet_path = parquet_dataset_path(case_id, workflow, dataset_name)
    db_path = duckdb_database_path(case_id, workflow)
    manifest = manifest_path(case_id, workflow, dataset_name)

    write_dataframe_to_parquet_with_duckdb(
        dataframe=dataframe,
        parquet_path=parquet_path,
        compression=compression,
    )

    create_or_replace_table_from_parquet(
        duckdb_path=db_path,
        table_name=table_name,
        parquet_path=parquet_path,
    )

    generated_at = datetime.now().isoformat(timespec="seconds")

    result = ScalableStageResult(
        case_id=str(case_id),
        workflow=workflow,
        dataset_name=dataset_name,
        table_name=table_name,
        record_count=int(len(dataframe)),
        column_count=int(len(dataframe.columns)),
        parquet_path=str(parquet_path),
        duckdb_path=str(db_path),
        manifest_path=str(manifest),
        generated_at=generated_at,
    )

    write_manifest(asdict(result), manifest)

    return result
