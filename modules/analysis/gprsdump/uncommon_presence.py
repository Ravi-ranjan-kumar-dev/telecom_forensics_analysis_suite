"""Tower GPRS uncommon/common presence helpers.

GPRS sessions are duration-based, so selected-period matching must use
session overlap:

    session_start <= window_end
    session_end >= window_start

The reusable ranking/scoring logic lives in:

    modules.analysis.common.uncommon_numbers
"""

from __future__ import annotations

import pandas as pd

from modules.analysis.common.uncommon_numbers import (
    UncommonNumberConfig,
    find_uncommon_numbers,
)


TOWER_GPRS_UNCOMMON_CONFIG = UncommonNumberConfig(
    entity_col="subscriber_number",
    time_col="session_start",
    cell_col="searched_cell_id",
    imei_col="imei",
    imsi_col="imsi",
    source_module="tower_gprs",
)


def split_gprs_current_and_baseline_by_overlap(
    dataframe: pd.DataFrame,
    *,
    window_start,
    window_end,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split GPRS sessions into selected-period and outside-period baseline."""

    if dataframe is None or dataframe.empty:
        return pd.DataFrame(), pd.DataFrame()

    required_columns = ["session_start", "session_end"]

    for column in required_columns:
        if column not in dataframe.columns:
            raise ValueError(f"Required GPRS session column missing: {column}")

    start = pd.to_datetime(window_start, errors="coerce")
    end = pd.to_datetime(window_end, errors="coerce")

    if pd.isna(start) or pd.isna(end):
        raise ValueError("Invalid window_start or window_end")

    if start >= end:
        raise ValueError("window_start must be before window_end")

    session_start = pd.to_datetime(
        dataframe["session_start"],
        errors="coerce",
    )
    session_end = pd.to_datetime(
        dataframe["session_end"],
        errors="coerce",
    )

    current_mask = (
        session_start.le(end)
        & session_end.ge(start)
    )

    current = dataframe.loc[current_mask].copy()
    baseline = dataframe.loc[~current_mask].copy()

    return current, baseline


def find_tower_gprs_uncommon_numbers(
    dataframe: pd.DataFrame,
    *,
    window_start,
    window_end,
    min_score: int = 50,
) -> pd.DataFrame:
    """Find Tower GPRS uncommon/new visitor numbers for selected period."""

    current, baseline = split_gprs_current_and_baseline_by_overlap(
        dataframe,
        window_start=window_start,
        window_end=window_end,
    )

    return find_uncommon_numbers(
        current,
        baseline,
        config=TOWER_GPRS_UNCOMMON_CONFIG,
        min_score=min_score,
    )
