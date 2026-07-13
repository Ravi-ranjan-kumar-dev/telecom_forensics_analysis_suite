from __future__ import annotations

import pandas as pd

from .subscribers import subscriber_summary
from .utils import join_unique, text_series


def _subscriber_details(
    df: pd.DataFrame,
    candidates: pd.DataFrame,
) -> pd.DataFrame:
    if not isinstance(candidates, pd.DataFrame) or candidates.empty:
        return pd.DataFrame()

    work = df.copy()
    for column in ("subscriber_number", "searched_cell_id", "operator"):
        work[column] = text_series(work, column)

    wanted = set(candidates["subscriber_number"])
    work = work.loc[work["subscriber_number"].isin(wanted)].copy()

    details = (
        work.groupby("subscriber_number", sort=False)
        .agg(
            searched_cells=("searched_cell_id", join_unique),
            operators=("operator", join_unique),
        )
        .reset_index()
    )
    return candidates.merge(details, on="subscriber_number", how="left").reset_index(drop=True)


def subscribers_across_cells_from_summary(
    summary: pd.DataFrame,
    df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if not isinstance(summary, pd.DataFrame) or summary.empty:
        return pd.DataFrame()
    candidates = summary.loc[summary["unique_cells"] >= 2].reset_index(drop=True)
    return _subscriber_details(df, candidates) if df is not None else candidates


def subscribers_across_operators_from_summary(
    summary: pd.DataFrame,
    df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if not isinstance(summary, pd.DataFrame) or summary.empty:
        return pd.DataFrame()
    candidates = summary.loc[summary["unique_operators"] >= 2].reset_index(drop=True)
    return _subscriber_details(df, candidates) if df is not None else candidates


def subscribers_across_cells(df: pd.DataFrame) -> pd.DataFrame:
    return subscribers_across_cells_from_summary(subscriber_summary(df), df)


def subscribers_across_operators(df: pd.DataFrame) -> pd.DataFrame:
    return subscribers_across_operators_from_summary(subscriber_summary(df), df)


def common_subscriber_matrix(df: pd.DataFrame) -> pd.DataFrame:
    required = {"subscriber_number", "searched_cell_id"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    work = df[["subscriber_number", "searched_cell_id"]].copy()
    work["subscriber_number"] = work["subscriber_number"].fillna("").astype(str).str.strip()
    work["searched_cell_id"] = work["searched_cell_id"].fillna("").astype(str).str.strip()
    work = work.loc[
        work["subscriber_number"].ne("") & work["searched_cell_id"].ne("")
    ]

    if work.empty:
        return pd.DataFrame()

    matrix = pd.crosstab(work["subscriber_number"], work["searched_cell_id"])
    matrix.insert(0, "cell_count", (matrix > 0).sum(axis=1))
    event_columns = [column for column in matrix.columns if column != "cell_count"]
    matrix.insert(1, "total_events", matrix[event_columns].sum(axis=1))
    return matrix.sort_values(
        ["cell_count", "total_events"],
        ascending=False,
    ).reset_index()
