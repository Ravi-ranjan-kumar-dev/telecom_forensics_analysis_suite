from __future__ import annotations

import pandas as pd

from .utils import datetime_series, join_unique, text_series


def _identifier_summary(df: pd.DataFrame, identifier: str) -> pd.DataFrame:
    work = df.copy()
    for column in (identifier, "subscriber_number", "searched_cell_id", "operator"):
        work[column] = text_series(work, column)

    work = work.loc[work[identifier].ne("")].copy()
    if work.empty:
        return pd.DataFrame()

    work["_dt"] = datetime_series(work)

    return (
        work.groupby(identifier, sort=False, dropna=False)
        .agg(
            total_events=(identifier, "size"),
            unique_subscribers=("subscriber_number", "nunique"),
            unique_cells=("searched_cell_id", "nunique"),
            unique_operators=("operator", "nunique"),
            first_seen=("_dt", "min"),
            last_seen=("_dt", "max"),
        )
        .reset_index()
        .sort_values(
            ["unique_subscribers", "total_events"],
            ascending=[False, False],
            ignore_index=True,
        )
    )


def _shared_details(
    df: pd.DataFrame,
    identifier: str,
    summary: pd.DataFrame,
) -> pd.DataFrame:
    if not isinstance(summary, pd.DataFrame) or summary.empty:
        return pd.DataFrame()

    candidates = summary.loc[summary["unique_subscribers"] >= 2].copy()
    if candidates.empty:
        return candidates

    work = df.copy()
    for column in (identifier, "subscriber_number", "searched_cell_id", "operator"):
        work[column] = text_series(work, column)
    work = work.loc[work[identifier].isin(set(candidates[identifier]))].copy()

    details = (
        work.groupby(identifier, sort=False)
        .agg(
            subscribers=("subscriber_number", join_unique),
            searched_cells=("searched_cell_id", join_unique),
            operators=("operator", join_unique),
        )
        .reset_index()
    )
    return candidates.merge(details, on=identifier, how="left").reset_index(drop=True)


def imei_summary(df: pd.DataFrame) -> pd.DataFrame:
    return _identifier_summary(df, "imei")


def imsi_summary(df: pd.DataFrame) -> pd.DataFrame:
    return _identifier_summary(df, "imsi")


def shared_imei_from_summary(
    summary: pd.DataFrame,
    df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if df is None:
        if not isinstance(summary, pd.DataFrame) or summary.empty:
            return pd.DataFrame()
        return summary.loc[summary["unique_subscribers"] >= 2].reset_index(drop=True)
    return _shared_details(df, "imei", summary)


def shared_imsi_from_summary(
    summary: pd.DataFrame,
    df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if df is None:
        if not isinstance(summary, pd.DataFrame) or summary.empty:
            return pd.DataFrame()
        return summary.loc[summary["unique_subscribers"] >= 2].reset_index(drop=True)
    return _shared_details(df, "imsi", summary)


def shared_imei(df: pd.DataFrame) -> pd.DataFrame:
    return shared_imei_from_summary(imei_summary(df), df)


def shared_imsi(df: pd.DataFrame) -> pd.DataFrame:
    return shared_imsi_from_summary(imsi_summary(df), df)
