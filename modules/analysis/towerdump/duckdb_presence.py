"""
DuckDB SQL based Tower CDR presence intelligence.

Purpose:
- Calculate heavy Tower CDR investigation leads from DuckDB.
- Keep pandas only for final small result formatting.
- Prepare the Tower CDR workflow for large datasets and future GUI use.

This module reads the staged table:
cases/active/<case_id>/staging/tower_cdr_dump/tower_cdr_dump.duckdb
table: tower_cdr_events
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pandas as pd

from modules.staging.scalable_store import query_database
from modules.staging.tower_cdr_staging import (
    TOWER_CDR_TABLE,
    tower_cdr_duckdb_path,
)


NEXT_ACTION = (
    "Verify with CDR/SDR/CAF, IMEI/IMSI, tower location, "
    "call context and field/local input."
)


def _table_columns(case_id: str) -> set[str]:
    """Return available columns in the staged Tower CDR DuckDB table."""

    db_path = tower_cdr_duckdb_path(case_id)

    info = query_database(
        db_path,
        f"PRAGMA table_info('{TOWER_CDR_TABLE}')",
    )

    if info.empty or "name" not in info.columns:
        return set()

    return {str(value) for value in info["name"].tolist()}


def _quoted(column: str) -> str:
    """Safely quote a known column name for DuckDB SQL."""

    return '"' + column.replace('"', '""') + '"'


def _text_expr(columns: set[str], preferred: list[str], fallback: str = "NULL") -> str:
    """Return SQL text expression for first available column."""

    for column in preferred:
        if column in columns:
            return f"NULLIF(TRIM(CAST({_quoted(column)} AS VARCHAR)), '')"

    return fallback


def _numeric_expr(columns: set[str], preferred: list[str]) -> str:
    """Return SQL numeric expression for first available column."""

    for column in preferred:
        if column in columns:
            return f"COALESCE(TRY_CAST({_quoted(column)} AS DOUBLE), 0)"

    return "0"


def _event_time_expr(columns: set[str]) -> str:
    """Return SQL timestamp expression for Tower CDR event time."""

    for column in ("call_datetime", "event_time", "datetime"):
        if column in columns:
            return f"TRY_CAST({_quoted(column)} AS TIMESTAMP)"

    if "call_date" in columns and "call_time" in columns:
        return (
            "TRY_CAST("
            f"CAST({_quoted('call_date')} AS VARCHAR) || ' ' || "
            f"CAST({_quoted('call_time')} AS VARCHAR) "
            "AS TIMESTAMP)"
        )

    if "call_date" in columns:
        return f"TRY_CAST({_quoted('call_date')} AS TIMESTAMP)"

    return "NULL"


def _priority_label(score: float) -> str:
    """Convert numeric priority score to simple investigation priority."""

    if score >= 85:
        return "High"

    if score >= 55:
        return "Medium"

    return "Low"


def _confidence_label(row: pd.Series) -> str:
    """Convert row evidence into simple confidence label."""

    evidence_points = 0

    if int(row.get("event_count", 0) or 0) >= 3:
        evidence_points += 1

    if int(row.get("cells_seen", 0) or 0) >= 2:
        evidence_points += 1

    if int(row.get("imei_count", 0) or 0) >= 2:
        evidence_points += 1

    if int(row.get("imsi_count", 0) or 0) >= 2:
        evidence_points += 1

    if int(row.get("night_event_count", 0) or 0) > 0:
        evidence_points += 1

    if evidence_points >= 3:
        return "High"

    if evidence_points >= 2:
        return "Medium"

    return "Low"


def _why_important(row: pd.Series) -> str:
    """Build plain-language reason for investigator."""

    reasons: list[str] = []

    if int(row.get("cells_seen", 0) or 0) >= 2:
        reasons.append("multi-cell presence")

    if int(row.get("event_count", 0) or 0) >= 2:
        reasons.append("repeat/high activity")

    if int(row.get("event_count", 0) or 0) == 1:
        reasons.append("single-event/rare presence")

    if int(row.get("imei_count", 0) or 0) >= 2:
        reasons.append("multiple IMEI")

    if int(row.get("imsi_count", 0) or 0) >= 2:
        reasons.append("multiple IMSI")

    if int(row.get("night_event_count", 0) or 0) > 0:
        reasons.append("night-time activity")

    return ", ".join(reasons) if reasons else "review recommended"


def _prepare_rollup(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Add priority, confidence, and investigator-friendly explanation."""

    if dataframe.empty:
        return dataframe

    output = dataframe.copy()

    if "searched_cells_seen" in output.columns and "cells_seen" not in output.columns:
        output["cells_seen"] = output["searched_cells_seen"]

    output["priority_score"] = output["priority_score"].fillna(0).astype(int)
    output["priority"] = output["priority_score"].apply(_priority_label)
    output["confidence"] = output.apply(_confidence_label, axis=1)
    output["why_important"] = output.apply(_why_important, axis=1)
    output["next_action"] = NEXT_ACTION

    return output


def _subscriber_rollup(case_id: str) -> pd.DataFrame:
    """
    Build subscriber-level rollup from DuckDB.

    Heavy work happens inside DuckDB:
    COUNT, COUNT DISTINCT, MIN/MAX timestamp, SUM duration, STRING_AGG.
    """

    columns = _table_columns(case_id)

    if "subscriber_number" not in columns:
        raise ValueError("subscriber_number column missing in Tower CDR staged table.")

    subscriber = _text_expr(columns, ["subscriber_number"])
    searched_cell = _text_expr(columns, ["searched_cell_id"])
    first_cell = _text_expr(columns, ["first_cell_id"])
    other_party = _text_expr(columns, ["other_party", "b_party"])
    imei = _text_expr(columns, ["imei"])
    imsi = _text_expr(columns, ["imsi"])
    operator = _text_expr(columns, ["operator"])
    call_type = _text_expr(columns, ["call_type", "service_type"])
    duration = _numeric_expr(columns, ["call_duration", "call_duration_seconds", "duration"])
    event_time = _event_time_expr(columns)

    db_path = tower_cdr_duckdb_path(case_id)

    sql = f"""
    WITH normalized AS (
        SELECT
            {subscriber} AS subscriber_number,
            {searched_cell} AS searched_cell_id,
            {first_cell} AS first_cell_id,
            {other_party} AS other_party,
            {imei} AS imei,
            {imsi} AS imsi,
            {operator} AS operator,
            {call_type} AS call_type,
            {duration} AS call_duration_seconds,
            {event_time} AS event_time
        FROM {TOWER_CDR_TABLE}
        WHERE {subscriber} IS NOT NULL
    ),
    rollup AS (
        SELECT
            subscriber_number,
            COUNT(*) AS event_count,
            MIN(event_time) AS first_seen,
            MAX(event_time) AS last_seen,
            SUM(call_duration_seconds) AS total_duration_seconds,
            SUM(
                CASE
                    WHEN event_time IS NOT NULL
                     AND (
                        EXTRACT(HOUR FROM event_time) >= 22
                        OR EXTRACT(HOUR FROM event_time) <= 5
                     )
                    THEN 1
                    ELSE 0
                END
            ) AS night_event_count,
            COUNT(DISTINCT searched_cell_id) AS searched_cells_seen,
            COUNT(DISTINCT first_cell_id) AS first_cells_seen,
            COUNT(DISTINCT imei) AS imei_count,
            COUNT(DISTINCT imsi) AS imsi_count,
            COUNT(DISTINCT other_party) AS other_party_count,
            LEFT(STRING_AGG(DISTINCT operator, ', '), 500) AS operators,
            LEFT(STRING_AGG(DISTINCT call_type, ', '), 500) AS call_types,
            LEFT(STRING_AGG(DISTINCT searched_cell_id, ', '), 700) AS searched_cells,
            LEFT(STRING_AGG(DISTINCT first_cell_id, ', '), 700) AS first_cells
        FROM normalized
        GROUP BY subscriber_number
    )
    SELECT
        *,
        searched_cells_seen AS cells_seen,
        (
            LEAST(event_count, 50)
            + searched_cells_seen * 10
            + CASE WHEN imei_count > 1 THEN 25 ELSE 0 END
            + CASE WHEN imsi_count > 1 THEN 25 ELSE 0 END
            + CASE WHEN night_event_count > 0 THEN 15 ELSE 0 END
        ) AS priority_score
    FROM rollup
    """

    result = query_database(db_path, sql)

    return _prepare_rollup(result)


def _select_columns(dataframe: pd.DataFrame, preferred_columns: list[str]) -> pd.DataFrame:
    """Return dataframe with only available preferred columns."""

    if dataframe.empty:
        return dataframe

    columns = [column for column in preferred_columns if column in dataframe.columns]
    return dataframe[columns].copy()


def build_tower_cdr_duckdb_presence(
    case_id: str,
    top_limit: int = 200,
) -> dict[str, pd.DataFrame]:
    """
    Build Tower CDR presence intelligence using DuckDB SQL.

    Returns same investigation buckets used by the current pandas workflow.
    """

    rollup = _subscriber_rollup(case_id)

    if rollup.empty:
        empty = pd.DataFrame()
        return {
            "tower_cdr_common_numbers": empty,
            "tower_cdr_uncommon_numbers": empty,
            "tower_cdr_multi_cell_presence": empty,
            "tower_cdr_device_consistency": empty,
            "tower_cdr_suspicious_timing": empty,
            "tower_cdr_priority_leads": empty,
            "subscriber_rollup": empty,
        }

    base_columns = [
        "subscriber_number",
        "priority",
        "confidence",
        "priority_score",
        "event_count",
        "first_seen",
        "last_seen",
        "total_duration_seconds",
        "night_event_count",
        "searched_cells_seen",
        "first_cells_seen",
        "imei_count",
        "imsi_count",
        "other_party_count",
        "operators",
        "call_types",
        "searched_cells",
        "first_cells",
        "cells_seen",
        "why_important",
        "next_action",
    ]

    common_numbers = (
        rollup[rollup["event_count"] >= 2]
        .sort_values(
            ["event_count", "cells_seen", "priority_score"],
            ascending=[False, False, False],
        )
        .head(top_limit)
    )

    uncommon_numbers = (
        rollup[rollup["event_count"] == 1]
        .sort_values(
            ["night_event_count", "first_seen", "subscriber_number"],
            ascending=[False, True, True],
        )
        .head(top_limit)
    )

    multi_cell_presence = (
        rollup[rollup["cells_seen"] >= 2]
        .sort_values(
            ["cells_seen", "event_count", "priority_score"],
            ascending=[False, False, False],
        )
        .head(top_limit)
    )

    device_consistency = (
        rollup[(rollup["imei_count"] >= 2) | (rollup["imsi_count"] >= 2)]
        .sort_values(
            ["imei_count", "imsi_count", "event_count", "cells_seen"],
            ascending=[False, False, False, False],
        )
        .head(top_limit)
    )

    suspicious_timing = (
        rollup[rollup["night_event_count"] > 0]
        .sort_values(
            ["night_event_count", "event_count", "cells_seen"],
            ascending=[False, False, False],
        )
        .head(top_limit)
    )

    priority_leads = (
        rollup.sort_values(
            ["priority_score", "cells_seen", "event_count"],
            ascending=[False, False, False],
        )
        .head(top_limit)
    )

    return {
        "tower_cdr_common_numbers": _select_columns(common_numbers, base_columns),
        "tower_cdr_uncommon_numbers": _select_columns(uncommon_numbers, base_columns),
        "tower_cdr_multi_cell_presence": _select_columns(multi_cell_presence, base_columns),
        "tower_cdr_device_consistency": _select_columns(device_consistency, base_columns),
        "tower_cdr_suspicious_timing": _select_columns(suspicious_timing, base_columns),
        "tower_cdr_priority_leads": _select_columns(priority_leads, base_columns),
        "subscriber_rollup": _select_columns(rollup, base_columns),
    }


def benchmark_tower_cdr_duckdb_presence(
    case_id: str,
    top_limit: int = 200,
) -> dict[str, Any]:
    """Run DuckDB presence engine and return timing summary."""

    started = time.perf_counter()
    results = build_tower_cdr_duckdb_presence(case_id, top_limit=top_limit)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)

    return {
        "case_id": case_id,
        "duration_ms": duration_ms,
        "rows": {
            key: len(value)
            for key, value in results.items()
            if isinstance(value, pd.DataFrame)
        },
        "results": results,
    }


def print_tower_cdr_duckdb_benchmark(
    benchmark: dict[str, Any],
) -> None:
    """Print simple benchmark summary."""

    print()
    print("TOWER CDR DUCKDB SQL PRESENCE ENGINE")
    print("-" * 78)
    print(f"Case ID     : {benchmark.get('case_id')}")
    print(f"Duration ms : {benchmark.get('duration_ms')}")
    print()

    rows = benchmark.get("rows", {}) or {}

    for key, value in rows.items():
        print(f"{key:<34}: {value:,}")

    print("-" * 78)
