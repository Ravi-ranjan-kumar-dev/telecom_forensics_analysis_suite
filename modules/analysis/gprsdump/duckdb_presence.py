"""
DuckDB SQL based Tower GPRS presence intelligence.

Purpose:
- Calculate Tower GPRS investigation leads from staged DuckDB data.
- Keep pandas only for final small result tables.
- Prepare Tower GPRS for large datasets and future GUI use.

Expected staged table:
cases/active/<case_id>/staging/tower_gprs_dump/tower_gprs_dump.duckdb
table: tower_gprs_sessions
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd

from modules.staging.scalable_store import query_database
from modules.staging.tower_gprs_staging import (
    TOWER_GPRS_TABLE,
    tower_gprs_duckdb_path,
)


NEXT_ACTION = (
    "Verify with CDR/SDR/CAF, device identifiers, tower location, "
    "data session timing and field/local input."
)


def _table_columns(case_id: str) -> set[str]:
    """Return available columns in staged Tower GPRS DuckDB table."""

    db_path = tower_gprs_duckdb_path(case_id)

    info = query_database(
        db_path,
        f"PRAGMA table_info('{TOWER_GPRS_TABLE}')",
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


def _timestamp_expr(columns: set[str], preferred: list[str]) -> str:
    """Return SQL timestamp expression for first available column."""

    for column in preferred:
        if column in columns:
            return f"TRY_CAST({_quoted(column)} AS TIMESTAMP)"

    return "NULL"


def _total_volume_expr(columns: set[str]) -> str:
    """Return SQL expression for total data volume."""

    for column in (
        "total_volume",
        "total_volume_bytes",
        "data_volume",
        "volume",
    ):
        if column in columns:
            return f"COALESCE(TRY_CAST({_quoted(column)} AS DOUBLE), 0)"

    upload = None
    download = None

    for column in ("upload_volume", "uplink_volume", "upload_bytes", "uplink_bytes"):
        if column in columns:
            upload = f"COALESCE(TRY_CAST({_quoted(column)} AS DOUBLE), 0)"
            break

    for column in (
        "download_volume",
        "downlink_volume",
        "download_bytes",
        "downlink_bytes",
    ):
        if column in columns:
            download = f"COALESCE(TRY_CAST({_quoted(column)} AS DOUBLE), 0)"
            break

    if upload and download:
        return f"({upload} + {download})"

    if upload:
        return upload

    if download:
        return download

    return "0"


def _priority_label(score: float) -> str:
    """Convert score to simple priority."""

    if score >= 85:
        return "High"

    if score >= 55:
        return "Medium"

    return "Low"


def _confidence_label(row: pd.Series) -> str:
    """Convert evidence strength to confidence label."""

    evidence_points = 0

    if int(row.get("session_count", 0) or 0) >= 3:
        evidence_points += 1

    if int(row.get("cells_seen", 0) or 0) >= 2:
        evidence_points += 1

    if int(row.get("imei_count", 0) or 0) >= 2:
        evidence_points += 1

    if int(row.get("imsi_count", 0) or 0) >= 2:
        evidence_points += 1

    if int(row.get("night_session_count", 0) or 0) > 0:
        evidence_points += 1

    if evidence_points >= 3:
        return "High"

    if evidence_points >= 2:
        return "Medium"

    return "Low"


def _why_important(row: pd.Series) -> str:
    """Build simple investigation reason."""

    reasons: list[str] = []

    if int(row.get("cells_seen", 0) or 0) >= 2:
        reasons.append("multi-cell presence")

    if int(row.get("session_count", 0) or 0) >= 2:
        reasons.append("repeat/high data-session activity")

    if int(row.get("session_count", 0) or 0) == 1:
        reasons.append("single-session/rare presence")

    if int(row.get("imei_count", 0) or 0) >= 2:
        reasons.append("multiple IMEI")

    if int(row.get("imsi_count", 0) or 0) >= 2:
        reasons.append("multiple IMSI")

    if int(row.get("night_session_count", 0) or 0) > 0:
        reasons.append("night-time data activity")

    if float(row.get("total_volume", 0) or 0) > 0:
        reasons.append("data usage observed")

    return ", ".join(reasons) if reasons else "review recommended"


def _prepare_rollup(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Add priority/confidence/reason columns."""

    if dataframe.empty:
        return dataframe

    output = dataframe.copy()
    output["priority_score"] = output["priority_score"].fillna(0).astype(int)
    output["priority"] = output["priority_score"].apply(_priority_label)
    output["confidence"] = output.apply(_confidence_label, axis=1)
    output["why_important"] = output.apply(_why_important, axis=1)
    output["next_action"] = NEXT_ACTION

    return output


def _subscriber_rollup(case_id: str) -> pd.DataFrame:
    """Build subscriber-level GPRS rollup using DuckDB SQL."""

    columns = _table_columns(case_id)

    if "subscriber_number" not in columns:
        raise ValueError("subscriber_number column missing in Tower GPRS staged table.")

    subscriber = _text_expr(columns, ["subscriber_number", "msisdn"])
    searched_cell = _text_expr(columns, ["searched_cell_id", "cell_id", "cgi"])
    imei = _text_expr(columns, ["imei"])
    imsi = _text_expr(columns, ["imsi"])
    ipv4 = _text_expr(columns, ["ipv4_address", "ip_address", "private_ip"])
    ipv6 = _text_expr(columns, ["ipv6_address"])
    technology = _text_expr(columns, ["technology", "rat_type"])
    operator = _text_expr(columns, ["operator"])
    session_start = _timestamp_expr(
        columns,
        ["session_start", "start_time", "event_time", "start_datetime"],
    )
    session_end = _timestamp_expr(
        columns,
        ["session_end", "end_time", "end_datetime"],
    )
    total_volume = _total_volume_expr(columns)

    db_path = tower_gprs_duckdb_path(case_id)

    sql = f"""
    WITH normalized AS (
        SELECT
            {subscriber} AS subscriber_number,
            {searched_cell} AS searched_cell_id,
            {imei} AS imei,
            {imsi} AS imsi,
            {ipv4} AS ipv4_address,
            {ipv6} AS ipv6_address,
            {technology} AS technology,
            {operator} AS operator,
            {session_start} AS session_start,
            {session_end} AS session_end,
            {total_volume} AS total_volume
        FROM {TOWER_GPRS_TABLE}
        WHERE {subscriber} IS NOT NULL
    ),
    rollup AS (
        SELECT
            subscriber_number,
            COUNT(*) AS session_count,
            MIN(session_start) AS first_seen,
            MAX(session_end) AS last_seen,
            SUM(total_volume) AS total_volume,
            SUM(
                CASE
                    WHEN session_start IS NOT NULL
                     AND (
                        EXTRACT(HOUR FROM session_start) >= 22
                        OR EXTRACT(HOUR FROM session_start) <= 5
                     )
                    THEN 1
                    ELSE 0
                END
            ) AS night_session_count,
            COUNT(DISTINCT searched_cell_id) AS cells_seen,
            COUNT(DISTINCT imei) AS imei_count,
            COUNT(DISTINCT imsi) AS imsi_count,
            COUNT(DISTINCT ipv4_address) AS ipv4_count,
            COUNT(DISTINCT ipv6_address) AS ipv6_count,
            LEFT(STRING_AGG(DISTINCT searched_cell_id, ', '), 700) AS searched_cells,
            LEFT(STRING_AGG(DISTINCT technology, ', '), 300) AS technologies,
            LEFT(STRING_AGG(DISTINCT operator, ', '), 300) AS operators
        FROM normalized
        GROUP BY subscriber_number
    )
    SELECT
        *,
        (
            LEAST(session_count, 50)
            + cells_seen * 10
            + CASE WHEN imei_count > 1 THEN 25 ELSE 0 END
            + CASE WHEN imsi_count > 1 THEN 25 ELSE 0 END
            + CASE WHEN night_session_count > 0 THEN 15 ELSE 0 END
            + CASE WHEN total_volume > 0 THEN 5 ELSE 0 END
        ) AS priority_score
    FROM rollup
    """

    result = query_database(db_path, sql)
    return _prepare_rollup(result)


def _select_columns(dataframe: pd.DataFrame, preferred_columns: list[str]) -> pd.DataFrame:
    """Return dataframe with available preferred columns only."""

    if dataframe.empty:
        return dataframe

    columns = [column for column in preferred_columns if column in dataframe.columns]
    return dataframe[columns].copy()


def build_tower_gprs_duckdb_presence(
    case_id: str,
    top_limit: int = 200,
) -> dict[str, pd.DataFrame]:
    """Build Tower GPRS presence intelligence using DuckDB SQL."""

    rollup = _subscriber_rollup(case_id)

    if rollup.empty:
        empty = pd.DataFrame()
        return {
            "gprs_common_numbers": empty,
            "gprs_uncommon_numbers": empty,
            "gprs_multi_cell_presence": empty,
            "gprs_device_consistency": empty,
            "gprs_suspicious_timing": empty,
            "gprs_priority_leads": empty,
            "subscriber_rollup": empty,
        }

    base_columns = [
        "subscriber_number",
        "priority",
        "confidence",
        "priority_score",
        "session_count",
        "first_seen",
        "last_seen",
        "total_volume",
        "night_session_count",
        "cells_seen",
        "imei_count",
        "imsi_count",
        "ipv4_count",
        "ipv6_count",
        "searched_cells",
        "technologies",
        "operators",
        "why_important",
        "next_action",
    ]

    common_numbers = (
        rollup[rollup["session_count"] >= 2]
        .sort_values(
            ["session_count", "cells_seen", "priority_score"],
            ascending=[False, False, False],
        )
        .head(top_limit)
    )

    uncommon_numbers = (
        rollup[rollup["session_count"] == 1]
        .sort_values(
            ["night_session_count", "first_seen", "subscriber_number"],
            ascending=[False, True, True],
        )
        .head(top_limit)
    )

    multi_cell_presence = (
        rollup[rollup["cells_seen"] >= 2]
        .sort_values(
            ["cells_seen", "session_count", "priority_score"],
            ascending=[False, False, False],
        )
        .head(top_limit)
    )

    device_consistency = (
        rollup[(rollup["imei_count"] >= 2) | (rollup["imsi_count"] >= 2)]
        .sort_values(
            ["imei_count", "imsi_count", "session_count", "cells_seen"],
            ascending=[False, False, False, False],
        )
        .head(top_limit)
    )

    suspicious_timing = (
        rollup[rollup["night_session_count"] > 0]
        .sort_values(
            ["night_session_count", "session_count", "cells_seen"],
            ascending=[False, False, False],
        )
        .head(top_limit)
    )

    priority_leads = (
        rollup.sort_values(
            ["priority_score", "cells_seen", "session_count"],
            ascending=[False, False, False],
        )
        .head(top_limit)
    )

    return {
        "gprs_common_numbers": _select_columns(common_numbers, base_columns),
        "gprs_uncommon_numbers": _select_columns(uncommon_numbers, base_columns),
        "gprs_multi_cell_presence": _select_columns(multi_cell_presence, base_columns),
        "gprs_device_consistency": _select_columns(device_consistency, base_columns),
        "gprs_suspicious_timing": _select_columns(suspicious_timing, base_columns),
        "gprs_priority_leads": _select_columns(priority_leads, base_columns),
        "subscriber_rollup": _select_columns(rollup, base_columns),
    }


def benchmark_tower_gprs_duckdb_presence(
    case_id: str,
    top_limit: int = 200,
) -> dict[str, Any]:
    """Run GPRS DuckDB presence engine and return timing summary."""

    started = time.perf_counter()
    results = build_tower_gprs_duckdb_presence(case_id, top_limit=top_limit)
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


def print_tower_gprs_duckdb_benchmark(benchmark: dict[str, Any]) -> None:
    """Print simple GPRS benchmark summary."""

    print()
    print("TOWER GPRS DUCKDB SQL PRESENCE ENGINE")
    print("-" * 78)
    print(f"Case ID     : {benchmark.get('case_id')}")
    print(f"Duration ms : {benchmark.get('duration_ms')}")
    print()

    rows = benchmark.get("rows", {}) or {}

    for key, value in rows.items():
        print(f"{key:<34}: {value:,}")

    print("-" * 78)
