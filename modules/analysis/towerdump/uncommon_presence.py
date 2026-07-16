"""Tower CDR uncommon/common presence helpers.

This module is intentionally thin. The reusable investigation logic lives in:

    modules.analysis.common.uncommon_numbers

Tower CDR-specific integration should import the common engine and pass
Tower CDR column mapping such as subscriber_number, call_datetime,
searched_cell_id/first_cell_id, imei and imsi.
"""

from __future__ import annotations

import pandas as pd

from modules.analysis.common.uncommon_numbers import (
    UncommonNumberConfig,
    find_uncommon_numbers,
    split_current_and_baseline_by_window,
)


TOWER_CDR_UNCOMMON_CONFIG = UncommonNumberConfig(
    entity_col="subscriber_number",
    time_col="call_datetime",
    cell_col="searched_cell_id",
    imei_col="imei",
    imsi_col="imsi",
    source_module="tower_cdr",
)


def find_tower_cdr_uncommon_numbers(
    dataframe: pd.DataFrame,
    *,
    window_start,
    window_end,
    min_score: int = 50,
) -> pd.DataFrame:
    """Find Tower CDR uncommon/new visitor numbers for selected period."""

    current, baseline = split_current_and_baseline_by_window(
        dataframe,
        time_col="call_datetime",
        window_start=window_start,
        window_end=window_end,
    )

    return find_uncommon_numbers(
        current,
        baseline,
        config=TOWER_CDR_UNCOMMON_CONFIG,
        min_score=min_score,
    )
