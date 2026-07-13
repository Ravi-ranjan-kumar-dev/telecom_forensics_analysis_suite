from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class UncommonNumberConfig:
    entity_col: str = "subscriber_number"
    time_col: str | None = None
    cell_col: str | None = None
    imei_col: str | None = None
    imsi_col: str | None = None
    source_module: str = "common"

    def to_dict(self) -> dict:
        return asdict(self)


def _clean_text_series(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .replace(
            {
                "": pd.NA,
                "nan": pd.NA,
                "NaN": pd.NA,
                "None": pd.NA,
                "NONE": pd.NA,
            }
        )
    )


def _safe_datetime_series(series: pd.Series) -> pd.Series:
    """Parse datetime safely.

    First try normal/ISO parsing because many telecom-normalized fields are
    stored as YYYY-MM-DD HH:MM:SS. If some values fail, retry those values with
    dayfirst=True for Indian DD/MM/YYYY style data.
    """

    parsed = pd.to_datetime(
        series,
        errors="coerce",
    )

    missing_mask = parsed.isna() & series.notna()

    if missing_mask.any():
        retry = pd.to_datetime(
            series[missing_mask],
            errors="coerce",
            dayfirst=True,
        )
        parsed.loc[missing_mask] = retry

    return parsed


def _safe_nunique(
    dataframe: pd.DataFrame,
    column: str | None,
) -> pd.Series:
    if not column or column not in dataframe.columns:
        return pd.Series(dtype="int64")

    return dataframe.groupby("_entity")[column].nunique(dropna=True)


def _safe_first(
    dataframe: pd.DataFrame,
    column: str | None,
) -> pd.Series:
    if not column or column not in dataframe.columns:
        return pd.Series(dtype="object")

    return dataframe.groupby("_entity")[column].first()


def _prepare_entity_frame(
    dataframe: pd.DataFrame,
    config: UncommonNumberConfig,
) -> pd.DataFrame:
    if dataframe is None or dataframe.empty:
        return pd.DataFrame()

    if config.entity_col not in dataframe.columns:
        raise ValueError(
            f"Required entity column missing: {config.entity_col}"
        )

    prepared = dataframe.copy()
    prepared["_entity"] = _clean_text_series(
        prepared[config.entity_col]
    )

    prepared = prepared.dropna(
        subset=["_entity"]
    )

    if prepared.empty:
        return prepared

    if config.time_col and config.time_col in prepared.columns:
        prepared["_event_time"] = _safe_datetime_series(
            prepared[config.time_col]
        )
    else:
        prepared["_event_time"] = pd.NaT

    return prepared


def _summarise_presence(
    dataframe: pd.DataFrame,
    config: UncommonNumberConfig,
    *,
    count_column_name: str,
) -> pd.DataFrame:
    if dataframe is None or dataframe.empty:
        return pd.DataFrame(
            columns=[
                "entity",
                count_column_name,
                "first_seen",
                "last_seen",
                "cells_seen",
                "imei_count",
                "imsi_count",
            ]
        )

    grouped = dataframe.groupby("_entity")

    summary = grouped.size().reset_index(
        name=count_column_name
    )

    summary = summary.rename(
        columns={"_entity": "entity"}
    )

    if "_event_time" in dataframe.columns:
        time_summary = grouped["_event_time"].agg(
            first_seen="min",
            last_seen="max",
        ).reset_index().rename(
            columns={"_entity": "entity"}
        )

        summary = summary.merge(
            time_summary,
            on="entity",
            how="left",
        )
    else:
        summary["first_seen"] = pd.NaT
        summary["last_seen"] = pd.NaT

    cell_counts = _safe_nunique(
        dataframe,
        config.cell_col,
    )

    imei_counts = _safe_nunique(
        dataframe,
        config.imei_col,
    )

    imsi_counts = _safe_nunique(
        dataframe,
        config.imsi_col,
    )

    for column_name, series in [
        ("cells_seen", cell_counts),
        ("imei_count", imei_counts),
        ("imsi_count", imsi_counts),
    ]:
        if series.empty:
            summary[column_name] = 0
        else:
            summary = summary.merge(
                series.rename(column_name).reset_index().rename(
                    columns={"_entity": "entity"}
                ),
                on="entity",
                how="left",
            )
            summary[column_name] = summary[column_name].fillna(0).astype(int)

    return summary


def _score_row(row: pd.Series) -> tuple[int, str]:
    baseline_count = int(row.get("baseline_seen_count", 0) or 0)
    current_count = int(row.get("current_seen_count", 0) or 0)
    cells_seen = int(row.get("cells_seen", 0) or 0)
    imei_count = int(row.get("imei_count", 0) or 0)
    imsi_count = int(row.get("imsi_count", 0) or 0)

    if baseline_count == 0:
        return 100, "Not seen in baseline"

    if baseline_count <= 2:
        return 85, "Very rare in baseline"

    if current_count >= 5 and baseline_count <= 5:
        return 75, "Low baseline presence but repeated in current window"

    if cells_seen >= 3:
        return 70, "Seen across multiple cells"

    if imei_count >= 2:
        return 65, "Multiple IMEI observed"

    if imsi_count >= 2:
        return 60, "Multiple IMSI observed"

    if current_count == 1:
        return 50, "Single current appearance"

    return 30, "Common or low-priority presence"


def find_uncommon_numbers(
    current_dataframe: pd.DataFrame,
    baseline_dataframe: pd.DataFrame | None = None,
    *,
    config: UncommonNumberConfig | None = None,
    min_score: int = 50,
) -> pd.DataFrame:
    """Find uncommon/rare entities in current data compared to baseline.

    current_dataframe:
        Incident window / selected period / candidate set.

    baseline_dataframe:
        Previous history, outside-window data, earlier days, or known local data.
        If baseline is missing, every current entity is treated as not seen in
        baseline, so score will be high. In real investigation, baseline is
        recommended for better accuracy.
    """

    config = config or UncommonNumberConfig()

    current = _prepare_entity_frame(
        current_dataframe,
        config,
    )

    if current.empty:
        return pd.DataFrame(
            columns=[
                "entity",
                "current_seen_count",
                "baseline_seen_count",
                "first_seen",
                "last_seen",
                "cells_seen",
                "imei_count",
                "imsi_count",
                "rarity_score",
                "reason",
                "source_module",
            ]
        )

    baseline = _prepare_entity_frame(
        baseline_dataframe,
        config,
    ) if baseline_dataframe is not None else pd.DataFrame()

    current_summary = _summarise_presence(
        current,
        config,
        count_column_name="current_seen_count",
    )

    baseline_summary = _summarise_presence(
        baseline,
        config,
        count_column_name="baseline_seen_count",
    )

    baseline_counts = baseline_summary[
        ["entity", "baseline_seen_count"]
    ] if not baseline_summary.empty else pd.DataFrame(
        columns=["entity", "baseline_seen_count"]
    )

    result = current_summary.merge(
        baseline_counts,
        on="entity",
        how="left",
    )

    result["baseline_seen_count"] = (
        result["baseline_seen_count"]
        .fillna(0)
        .astype(int)
    )

    scores = result.apply(
        _score_row,
        axis=1,
    )

    result["rarity_score"] = [
        score
        for score, _reason in scores
    ]

    result["reason"] = [
        reason
        for _score, reason in scores
    ]

    result["source_module"] = config.source_module

    result = result[
        result["rarity_score"] >= min_score
    ].copy()

    result = result.sort_values(
        by=[
            "rarity_score",
            "current_seen_count",
            "baseline_seen_count",
        ],
        ascending=[
            False,
            False,
            True,
        ],
    ).reset_index(drop=True)

    return result


def split_current_and_baseline_by_window(
    dataframe: pd.DataFrame,
    *,
    time_col: str,
    window_start,
    window_end,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split one DataFrame into current-window and outside-window baseline."""

    if dataframe is None or dataframe.empty:
        return pd.DataFrame(), pd.DataFrame()

    if time_col not in dataframe.columns:
        raise ValueError(
            f"Required time column missing: {time_col}"
        )

    prepared = dataframe.copy()
    event_time = _safe_datetime_series(
        prepared[time_col]
    )

    start = pd.to_datetime(
        window_start,
        errors="coerce",
    )

    end = pd.to_datetime(
        window_end,
        errors="coerce",
    )

    if pd.isna(start) or pd.isna(end):
        raise ValueError(
            "Invalid window_start or window_end"
        )

    current_mask = (
        event_time.ge(start)
        & event_time.le(end)
    )

    current = prepared.loc[current_mask].copy()
    baseline = prepared.loc[~current_mask].copy()

    return current, baseline


def print_uncommon_summary(
    uncommon_dataframe: pd.DataFrame,
    *,
    max_rows: int = 20,
) -> None:
    print("\nUNCOMMON NUMBER SUMMARY")
    print("-" * 70)

    if uncommon_dataframe is None or uncommon_dataframe.empty:
        print("No uncommon numbers found.")
        return

    display_columns = [
        column
        for column in [
            "entity",
            "rarity_score",
            "reason",
            "current_seen_count",
            "baseline_seen_count",
            "first_seen",
            "last_seen",
            "cells_seen",
            "imei_count",
            "imsi_count",
            "source_module",
        ]
        if column in uncommon_dataframe.columns
    ]

    print(
        uncommon_dataframe[display_columns]
        .head(max_rows)
        .to_string(index=False)
    )

    remaining = len(uncommon_dataframe) - max_rows

    if remaining > 0:
        print(f"... {remaining} more uncommon number(s)")