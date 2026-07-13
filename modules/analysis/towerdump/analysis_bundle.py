from __future__ import annotations

import time
import traceback
from collections import OrderedDict
from typing import Any, Callable

import pandas as pd

from .common_entities import (
    common_subscriber_matrix,
    subscribers_across_cells_from_summary,
    subscribers_across_operators_from_summary,
)
from .devices import (
    imei_summary,
    imsi_summary,
    shared_imei_from_summary,
    shared_imsi_from_summary,
)
from .movement import subscriber_movements
from .subscribers import (
    frequent_visitors_from_summary,
    repeat_visitors_from_summary,
    subscriber_summary,
)
from .summary import call_type_summary, cell_summary, operator_summary, tower_dump_summary
from .time_analysis import daily_activity, hourly_activity, night_activity


ANALYSIS_NAMES = [
    "tower_dump_summary",
    "operator_summary",
    "cell_summary",
    "call_type_summary",
    "subscriber_summary",
    "repeat_visitors",
    "frequent_visitors",
    "imei_summary",
    "imsi_summary",
    "shared_imei",
    "shared_imsi",
    "subscribers_across_cells",
    "subscribers_across_operators",
    "common_subscriber_matrix",
    "hourly_activity",
    "daily_activity",
    "night_activity",
    "subscriber_movements",
    "cell_transition_summary",
    "investigative_indicators",
]

# Kept for discoverability/status documentation.
ANALYSIS_FUNCTIONS = OrderedDict((name, None) for name in ANALYSIS_NAMES)


def _transition_summary_from_movements(movements: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(movements, pd.DataFrame) or movements.empty:
        return pd.DataFrame(
            columns=[
                "from_cell_id",
                "to_cell_id",
                "transition_events",
                "unique_subscribers",
                "minimum_gap_seconds",
                "median_gap_seconds",
            ]
        )
    return (
        movements.groupby(["from_cell_id", "to_cell_id"], dropna=False)
        .agg(
            transition_events=("subscriber_number", "size"),
            unique_subscribers=("subscriber_number", "nunique"),
            minimum_gap_seconds=("time_gap_seconds", "min"),
            median_gap_seconds=("time_gap_seconds", "median"),
        )
        .reset_index()
        .sort_values(
            ["unique_subscribers", "transition_events"],
            ascending=False,
            ignore_index=True,
        )
    )


def _indicators_from_cached(results: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for _, row in results["shared_imei"].iterrows():
        rows.append(
            {
                "indicator": "SHARED_IMEI",
                "entity": row.get("imei", ""),
                "severity": "HIGH",
                "details": (
                    f"IMEI linked with {row.get('unique_subscribers', 0)} subscribers; "
                    f"cells={row.get('unique_cells', 0)}"
                ),
                "caution": "Possible explanations include a shared, family or corporate handset, identifier recycling, or source-data issues; corroborate before interpretation.",
            }
        )

    for _, row in results["shared_imsi"].iterrows():
        rows.append(
            {
                "indicator": "SHARED_IMSI",
                "entity": row.get("imsi", ""),
                "severity": "HIGH",
                "details": f"IMSI linked with {row.get('unique_subscribers', 0)} subscriber numbers.",
                "caution": "Verify operator export semantics and normalization before treating the identifiers as linked.",
            }
        )

    for _, row in results["subscribers_across_cells"].iterrows():
        rows.append(
            {
                "indicator": "MULTI_CELL_PRESENCE",
                "entity": row.get("subscriber_number", ""),
                "severity": "MEDIUM",
                "details": (
                    f"Subscriber found in {row.get('unique_cells', 0)} searched cells; "
                    f"events={row.get('total_events', 0)}"
                ),
                "caution": "Consider overlapping coverage, sector reach and events spanning multiple cells.",
            }
        )

    for _, row in results["subscribers_across_operators"].iterrows():
        rows.append(
            {
                "indicator": "MULTI_OPERATOR_IDENTITY",
                "entity": row.get("subscriber_number", ""),
                "severity": "MEDIUM",
                "details": f"Same normalized number appeared in {row.get('unique_operators', 0)} operators.",
                "caution": "Verify porting, number formatting and subscriber inference.",
            }
        )

    summary = results["subscriber_summary"]
    if isinstance(summary, pd.DataFrame) and not summary.empty:
        threshold = max(float(summary["total_events"].quantile(0.99)), 25.0)
        for _, row in summary.loc[summary["total_events"] >= threshold].iterrows():
            rows.append(
                {
                    "indicator": "HIGH_EVENT_VOLUME",
                    "entity": row.get("subscriber_number", ""),
                    "severity": "LOW",
                    "details": (
                        f"Subscriber has {row.get('total_events', 0)} events "
                        f"(dynamic threshold={threshold:.0f})."
                    ),
                    "caution": "High event volume alone does not establish suspicious activity, identity, intent or participation.",
                }
            )

    if not rows:
        return pd.DataFrame(columns=["indicator", "entity", "severity", "details", "caution"])

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    output = pd.DataFrame(rows)
    output["_order"] = output["severity"].map(order).fillna(9)
    return output.sort_values(["_order", "indicator", "entity"]).drop(
        columns="_order"
    ).reset_index(drop=True)


def build_tower_dump_analysis_bundle(df: pd.DataFrame) -> dict[str, Any]:
    results: dict[str, Any] = {}
    status: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    def execute(name: str, function: Callable[[], Any]) -> None:
        started = time.perf_counter()
        try:
            result = function()
            results[name] = result
            row_count = len(result) if hasattr(result, "__len__") else 1
            status.append(
                {
                    "analysis": name,
                    "status": "COMPLETED",
                    "rows": row_count,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "error": "",
                }
            )
        except Exception as exc:
            results[name] = pd.DataFrame()
            message = f"{type(exc).__name__}: {exc}"
            status.append(
                {
                    "analysis": name,
                    "status": "FAILED",
                    "rows": 0,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "error": message,
                }
            )
            errors.append(
                {
                    "analysis": name,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(limit=8),
                }
            )

    execute("tower_dump_summary", lambda: tower_dump_summary(df))
    execute("operator_summary", lambda: operator_summary(df))
    execute("cell_summary", lambda: cell_summary(df))
    execute("call_type_summary", lambda: call_type_summary(df))

    execute("subscriber_summary", lambda: subscriber_summary(df))
    execute("repeat_visitors", lambda: repeat_visitors_from_summary(results["subscriber_summary"]))
    execute("frequent_visitors", lambda: frequent_visitors_from_summary(results["subscriber_summary"]))

    execute("imei_summary", lambda: imei_summary(df))
    execute("imsi_summary", lambda: imsi_summary(df))
    execute("shared_imei", lambda: shared_imei_from_summary(results["imei_summary"], df))
    execute("shared_imsi", lambda: shared_imsi_from_summary(results["imsi_summary"], df))

    execute(
        "subscribers_across_cells",
        lambda: subscribers_across_cells_from_summary(results["subscriber_summary"], df),
    )
    execute(
        "subscribers_across_operators",
        lambda: subscribers_across_operators_from_summary(results["subscriber_summary"], df),
    )
    execute("common_subscriber_matrix", lambda: common_subscriber_matrix(df))

    execute("hourly_activity", lambda: hourly_activity(df))
    execute("daily_activity", lambda: daily_activity(df))
    execute("night_activity", lambda: night_activity(df))

    execute("subscriber_movements", lambda: subscriber_movements(df))
    execute(
        "cell_transition_summary",
        lambda: _transition_summary_from_movements(results["subscriber_movements"]),
    )
    execute("investigative_indicators", lambda: _indicators_from_cached(results))

    return {
        "results": results,
        "status": pd.DataFrame(status),
        "errors": pd.DataFrame(errors),
        "function_count": len(ANALYSIS_NAMES),
        "completed_count": sum(item["status"] == "COMPLETED" for item in status),
        "failed_count": sum(item["status"] == "FAILED" for item in status),
    }
