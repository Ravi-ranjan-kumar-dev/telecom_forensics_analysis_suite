from __future__ import annotations

import pandas as pd

from .utils import datetime_series, numeric_series, text_series


def subscriber_summary(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    for column in (
        "subscriber_number",
        "searched_cell_id",
        "operator",
        "imei",
        "imsi",
        "other_party",
        "call_type",
    ):
        work[column] = text_series(work, column)

    work = work.loc[work["subscriber_number"].ne("")].copy()
    if work.empty:
        return pd.DataFrame()

    work["_dt"] = datetime_series(work)
    work["_date"] = work["_dt"].dt.date
    work["_duration"] = numeric_series(work, "call_duration")

    result = (
        work.groupby("subscriber_number", sort=False, dropna=False)
        .agg(
            total_events=("subscriber_number", "size"),
            first_seen=("_dt", "min"),
            last_seen=("_dt", "max"),
            active_days=("_date", "nunique"),
            unique_cells=("searched_cell_id", "nunique"),
            unique_operators=("operator", "nunique"),
            unique_imei=("imei", "nunique"),
            unique_imsi=("imsi", "nunique"),
            unique_other_parties=("other_party", "nunique"),
            total_duration_seconds=("_duration", "sum"),
        )
        .reset_index()
    )

    type_counts = pd.crosstab(work["subscriber_number"], work["call_type"])
    for source, target in (
        ("incoming", "incoming_calls"),
        ("outgoing", "outgoing_calls"),
        ("smsin", "incoming_sms"),
        ("smsout", "outgoing_sms"),
    ):
        if source in type_counts.columns:
            mapping = type_counts[source]
            result[target] = result["subscriber_number"].map(mapping).fillna(0).astype(int)
        else:
            result[target] = 0

    result["total_duration_seconds"] = (
        pd.to_numeric(result["total_duration_seconds"], errors="coerce")
        .fillna(0)
        .round()
        .astype("int64")
    )

    return result.sort_values(
        ["total_events", "unique_cells", "active_days"],
        ascending=[False, False, False],
        ignore_index=True,
    )


def repeat_visitors_from_summary(
    summary: pd.DataFrame,
    minimum_events: int = 2,
) -> pd.DataFrame:
    if not isinstance(summary, pd.DataFrame) or summary.empty:
        return pd.DataFrame()
    return summary.loc[
        summary["total_events"] >= max(int(minimum_events), 2)
    ].reset_index(drop=True)


def frequent_visitors_from_summary(
    summary: pd.DataFrame,
    top_n: int = 100,
) -> pd.DataFrame:
    if not isinstance(summary, pd.DataFrame) or summary.empty:
        return pd.DataFrame()
    return summary.head(max(int(top_n), 1)).reset_index(drop=True)


def repeat_visitors(df: pd.DataFrame, minimum_events: int = 2) -> pd.DataFrame:
    return repeat_visitors_from_summary(
        subscriber_summary(df),
        minimum_events=minimum_events,
    )


def frequent_visitors(df: pd.DataFrame, top_n: int = 100) -> pd.DataFrame:
    return frequent_visitors_from_summary(
        subscriber_summary(df),
        top_n=top_n,
    )
