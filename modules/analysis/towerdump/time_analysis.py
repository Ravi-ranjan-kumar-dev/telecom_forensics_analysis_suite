from __future__ import annotations

import pandas as pd

from .utils import datetime_series, safe_nunique


def hourly_activity(df: pd.DataFrame) -> pd.DataFrame:
    dt = datetime_series(df)
    valid = df.loc[dt.notna()].copy()
    if valid.empty:
        return pd.DataFrame(columns=["hour", "records", "unique_subscribers"])
    valid["_hour"] = dt.loc[dt.notna()].dt.hour
    rows = []
    for hour, group in valid.groupby("_hour"):
        rows.append(
            {
                "hour": int(hour),
                "records": len(group),
                "unique_subscribers": safe_nunique(group, "subscriber_number"),
            }
        )
    base = pd.DataFrame({"hour": range(24)})
    return base.merge(pd.DataFrame(rows), on="hour", how="left").fillna(0)


def daily_activity(df: pd.DataFrame) -> pd.DataFrame:
    dt = datetime_series(df)
    valid = df.loc[dt.notna()].copy()
    if valid.empty:
        return pd.DataFrame(columns=["date", "records", "unique_subscribers"])
    valid["_date"] = dt.loc[dt.notna()].dt.date
    rows = []
    for date, group in valid.groupby("_date"):
        rows.append(
            {
                "date": date,
                "records": len(group),
                "unique_subscribers": safe_nunique(group, "subscriber_number"),
            }
        )
    return pd.DataFrame(rows).sort_values("date", ignore_index=True)


def night_activity(
    df: pd.DataFrame,
    start_hour: int = 22,
    end_hour: int = 6,
) -> pd.DataFrame:
    dt = datetime_series(df)
    valid = df.loc[dt.notna()].copy()
    if valid.empty:
        return pd.DataFrame()
    valid["_dt"] = dt.loc[dt.notna()]
    hours = valid["_dt"].dt.hour
    mask = (hours >= start_hour) | (hours < end_hour)
    result = valid.loc[mask].copy()
    result = result.sort_values("_dt", kind="stable")
    columns = [
        column
        for column in (
            "subscriber_number",
            "other_party",
            "call_type",
            "call_datetime",
            "imei",
            "imsi",
            "searched_cell_id",
            "operator",
            "source_file",
        )
        if column in result.columns
    ]
    return result[columns].reset_index(drop=True)
