from __future__ import annotations

import pandas as pd

from .utils import datetime_series, text_series


def subscriber_movements(df: pd.DataFrame) -> pd.DataFrame:
    required = {"subscriber_number", "searched_cell_id", "call_datetime"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    work = df.copy()
    work["subscriber_number"] = text_series(work, "subscriber_number")
    work["searched_cell_id"] = text_series(work, "searched_cell_id")
    work["_dt"] = datetime_series(work)
    work = work.loc[
        work["subscriber_number"].ne("")
        & work["searched_cell_id"].ne("")
        & work["_dt"].notna()
    ].copy()

    if work.empty:
        return pd.DataFrame()

    work = work.sort_values(
        ["subscriber_number", "_dt", "searched_cell_id"],
        kind="stable",
    )
    work["previous_cell_id"] = work.groupby("subscriber_number")["searched_cell_id"].shift()
    work["previous_datetime"] = work.groupby("subscriber_number")["_dt"].shift()
    work["time_gap_seconds"] = (
        work["_dt"] - work["previous_datetime"]
    ).dt.total_seconds()

    moved = work.loc[
        work["previous_cell_id"].notna()
        & work["previous_cell_id"].ne(work["searched_cell_id"])
    ].copy()

    if moved.empty:
        return pd.DataFrame(
            columns=[
                "subscriber_number",
                "from_cell_id",
                "to_cell_id",
                "from_datetime",
                "to_datetime",
                "time_gap_seconds",
                "operator",
                "source_file",
            ]
        )

    result = pd.DataFrame(
        {
            "subscriber_number": moved["subscriber_number"],
            "from_cell_id": moved["previous_cell_id"],
            "to_cell_id": moved["searched_cell_id"],
            "from_datetime": moved["previous_datetime"],
            "to_datetime": moved["_dt"],
            "time_gap_seconds": moved["time_gap_seconds"],
            "operator": text_series(moved, "operator"),
            "source_file": text_series(moved, "source_file"),
        }
    )
    return result.reset_index(drop=True)


def cell_transition_summary(df: pd.DataFrame) -> pd.DataFrame:
    movements = subscriber_movements(df)
    if movements.empty:
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

    result = (
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
    return result
