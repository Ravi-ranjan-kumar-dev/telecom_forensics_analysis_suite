from __future__ import annotations

import pandas as pd

from .common_entities import subscribers_across_cells, subscribers_across_operators
from .devices import shared_imei, shared_imsi
from .subscribers import subscriber_summary


def investigative_indicators(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []

    for _, row in shared_imei(df).iterrows():
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

    for _, row in shared_imsi(df).iterrows():
        rows.append(
            {
                "indicator": "SHARED_IMSI",
                "entity": row.get("imsi", ""),
                "severity": "HIGH",
                "details": (
                    f"IMSI linked with {row.get('unique_subscribers', 0)} subscriber numbers."
                ),
                "caution": "Verify operator export semantics and normalization before treating the identifiers as linked.",
            }
        )

    for _, row in subscribers_across_cells(df).iterrows():
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

    for _, row in subscribers_across_operators(df).iterrows():
        rows.append(
            {
                "indicator": "MULTI_OPERATOR_IDENTITY",
                "entity": row.get("subscriber_number", ""),
                "severity": "MEDIUM",
                "details": (
                    f"Same normalized number appeared in {row.get('unique_operators', 0)} operators."
                ),
                "caution": "Verify porting, number formatting and subscriber-versus-counterparty inference.",
            }
        )

    summary = subscriber_summary(df)
    if not summary.empty:
        threshold = max(float(summary["total_events"].quantile(0.99)), 25.0)
        high = summary.loc[summary["total_events"] >= threshold]
        for _, row in high.iterrows():
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
        return pd.DataFrame(
            columns=["indicator", "entity", "severity", "details", "caution"]
        )

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    result = pd.DataFrame(rows)
    result["_order"] = result["severity"].map(order).fillna(9)
    return result.sort_values(["_order", "indicator", "entity"]).drop(
        columns="_order"
    ).reset_index(drop=True)
