"""Tower CDR common/uncommon presence helpers.

This module builds investigator-friendly lead tables:
- common/repeat numbers
- uncommon/new visitor style rare numbers
- multi-cell presence
- device/SIM consistency
- suspicious timing/high activity
- priority leads

The selected-period uncommon wrapper reuses:

    modules.analysis.common.uncommon_numbers
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


def _clean_text(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .replace({"nan": "", "None": "", "<NA>": ""})
    )


def _joined_unique(series: pd.Series) -> str:
    values = sorted({value for value in _clean_text(series) if value})
    return ", ".join(values)


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


def _empty_presence_tables() -> dict[str, pd.DataFrame]:
    empty = pd.DataFrame()
    return {
        "common_numbers": empty,
        "uncommon_numbers": empty,
        "multi_cell_presence": empty,
        "device_consistency": empty,
        "suspicious_timing": empty,
        "priority_leads": empty,
    }


def build_tower_cdr_presence_intelligence(
    dataframe: pd.DataFrame,
    *,
    top_limit: int = 200,
) -> dict[str, pd.DataFrame]:
    """Build full-dump Tower CDR presence intelligence tables.

    These are investigation leads, not final proof.
    """

    if dataframe is None or dataframe.empty:
        return _empty_presence_tables()

    if "subscriber_number" not in dataframe.columns:
        raise ValueError("subscriber_number column missing in Tower CDR data.")

    work = dataframe.copy()
    work["_subscriber"] = _clean_text(work["subscriber_number"])
    work = work.loc[work["_subscriber"].ne("")].copy()

    if work.empty:
        return _empty_presence_tables()

    if "call_datetime" in work.columns:
        work["_event_time"] = pd.to_datetime(
            work["call_datetime"],
            errors="coerce",
        )
    else:
        work["_event_time"] = pd.NaT

    if "call_duration" in work.columns:
        work["_duration_seconds"] = pd.to_numeric(
            work["call_duration"],
            errors="coerce",
        ).fillna(0)
    else:
        work["_duration_seconds"] = 0

    hour = work["_event_time"].dt.hour
    work["_night_event"] = hour.ge(22) | hour.lt(5)

    grouped = work.groupby("_subscriber", dropna=True)

    summary = grouped.agg(
        event_count=("subscriber_number", "size"),
        first_seen=("_event_time", "min"),
        last_seen=("_event_time", "max"),
        total_duration_seconds=("_duration_seconds", "sum"),
        night_event_count=("_night_event", "sum"),
    ).reset_index().rename(columns={"_subscriber": "subscriber_number"})

    for source_col, output_col in [
        ("searched_cell_id", "searched_cells_seen"),
        ("first_cell_id", "first_cells_seen"),
        ("imei", "imei_count"),
        ("imsi", "imsi_count"),
        ("other_party", "other_party_count"),
    ]:
        if source_col in work.columns:
            counts = grouped[source_col].nunique(dropna=True).reset_index()
            counts = counts.rename(
                columns={
                    "_subscriber": "subscriber_number",
                    source_col: output_col,
                }
            )
            summary = summary.merge(counts, on="subscriber_number", how="left")
        else:
            summary[output_col] = 0

    for source_col, output_col in [
        ("operator", "operators"),
        ("call_type", "call_types"),
        ("searched_cell_id", "searched_cells"),
        ("first_cell_id", "first_cells"),
    ]:
        if source_col in work.columns:
            joined = grouped[source_col].apply(_joined_unique).reset_index()
            joined = joined.rename(
                columns={
                    "_subscriber": "subscriber_number",
                    source_col: output_col,
                }
            )
            summary = summary.merge(joined, on="subscriber_number", how="left")
        else:
            summary[output_col] = ""

    for col in [
        "searched_cells_seen",
        "first_cells_seen",
        "imei_count",
        "imsi_count",
        "other_party_count",
        "night_event_count",
    ]:
        summary[col] = summary[col].fillna(0).astype(int)

    summary["cells_seen"] = summary[
        ["searched_cells_seen", "first_cells_seen"]
    ].max(axis=1)

    summary["priority_score"] = 0
    summary.loc[summary["event_count"].eq(1), "priority_score"] += 25
    summary.loc[summary["cells_seen"].ge(2), "priority_score"] += 35
    summary.loc[summary["event_count"].ge(5), "priority_score"] += 25
    summary.loc[summary["imei_count"].ge(2), "priority_score"] += 20
    summary.loc[summary["imsi_count"].ge(2), "priority_score"] += 20
    summary.loc[summary["other_party_count"].ge(5), "priority_score"] += 15
    summary.loc[summary["night_event_count"].ge(1), "priority_score"] += 15

    def _priority(score: int) -> str:
        if score >= 70:
            return "High"
        if score >= 45:
            return "Medium"
        return "Low"

    def _confidence(row: pd.Series) -> str:
        if int(row.get("cells_seen", 0) or 0) >= 2 and int(row.get("event_count", 0) or 0) >= 2:
            return "High"
        if int(row.get("event_count", 0) or 0) >= 2:
            return "Medium"
        return "Low"

    def _reason(row: pd.Series) -> str:
        reasons: list[str] = []

        if int(row.get("event_count", 0) or 0) == 1:
            reasons.append("single-event/rare presence")

        if int(row.get("cells_seen", 0) or 0) >= 2:
            reasons.append("multi-cell presence")

        if int(row.get("event_count", 0) or 0) >= 5:
            reasons.append("repeat/high activity")

        if int(row.get("imei_count", 0) or 0) >= 2:
            reasons.append("multiple IMEI")

        if int(row.get("imsi_count", 0) or 0) >= 2:
            reasons.append("multiple IMSI")

        if int(row.get("night_event_count", 0) or 0) >= 1:
            reasons.append("night-time activity")

        return ", ".join(reasons) if reasons else "low-priority presence"

    summary["priority"] = summary["priority_score"].apply(_priority)
    summary["confidence"] = summary.apply(_confidence, axis=1)
    summary["why_important"] = summary.apply(_reason, axis=1)
    summary["next_action"] = (
        "Verify with CDR/SDR/CAF, IMEI/IMSI, tower location, call context and field/local input."
    )

    common_numbers = summary.loc[
        summary["event_count"].ge(2)
    ].sort_values(
        ["event_count", "cells_seen", "other_party_count"],
        ascending=[False, False, False],
    ).head(top_limit).reset_index(drop=True)

    uncommon_numbers = summary.loc[
        summary["event_count"].eq(1)
    ].sort_values(
        ["cells_seen", "night_event_count", "first_seen"],
        ascending=[False, False, True],
    ).head(top_limit).reset_index(drop=True)

    multi_cell_presence = summary.loc[
        summary["cells_seen"].ge(2)
    ].sort_values(
        ["cells_seen", "event_count", "other_party_count"],
        ascending=[False, False, False],
    ).head(top_limit).reset_index(drop=True)

    device_consistency = summary.sort_values(
        ["imei_count", "imsi_count", "event_count"],
        ascending=[False, False, False],
    ).head(top_limit).reset_index(drop=True)

    suspicious_timing = summary.sort_values(
        ["night_event_count", "event_count", "cells_seen"],
        ascending=[False, False, False],
    ).head(top_limit).reset_index(drop=True)

    priority_leads = summary.sort_values(
        ["priority_score", "cells_seen", "event_count", "night_event_count"],
        ascending=[False, False, False, False],
    ).head(top_limit).reset_index(drop=True)

    return {
        "common_numbers": common_numbers,
        "uncommon_numbers": uncommon_numbers,
        "multi_cell_presence": multi_cell_presence,
        "device_consistency": device_consistency,
        "suspicious_timing": suspicious_timing,
        "priority_leads": priority_leads,
    }
