"""Tower GPRS common/uncommon presence helpers.

GPRS sessions are duration-based. For selected-period matching, use:

    session_start <= window_end
    session_end >= window_start

For full-dump reporting, this module also creates simple investigator-friendly
presence intelligence:
- common/repeat numbers
- uncommon/new visitor style rare numbers
- multi-cell presence
- device/SIM consistency
- suspicious timing/high activity
- priority leads
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


def split_gprs_current_and_baseline_by_overlap(
    dataframe: pd.DataFrame,
    *,
    window_start,
    window_end,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split GPRS sessions into selected-period and outside-period baseline."""

    if dataframe is None or dataframe.empty:
        return pd.DataFrame(), pd.DataFrame()

    for column in ["session_start", "session_end"]:
        if column not in dataframe.columns:
            raise ValueError(f"Required GPRS session column missing: {column}")

    start = pd.to_datetime(window_start, errors="coerce")
    end = pd.to_datetime(window_end, errors="coerce")

    if pd.isna(start) or pd.isna(end):
        raise ValueError("Invalid window_start or window_end")

    if start >= end:
        raise ValueError("window_start must be before window_end")

    session_start = pd.to_datetime(dataframe["session_start"], errors="coerce")
    session_end = pd.to_datetime(dataframe["session_end"], errors="coerce")

    current_mask = session_start.le(end) & session_end.ge(start)

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


def build_tower_gprs_presence_intelligence(
    dataframe: pd.DataFrame,
    *,
    top_limit: int = 200,
) -> dict[str, pd.DataFrame]:
    """Build full-dump GPRS presence intelligence tables.

    This is not final proof. It creates lead tables for investigator review.
    """

    if dataframe is None or dataframe.empty:
        empty = pd.DataFrame()
        return {
            "common_numbers": empty,
            "uncommon_numbers": empty,
            "multi_cell_presence": empty,
            "device_consistency": empty,
            "suspicious_timing": empty,
            "priority_leads": empty,
        }

    if "subscriber_number" not in dataframe.columns:
        raise ValueError("subscriber_number column missing in GPRS data.")

    work = dataframe.copy()
    work["_subscriber"] = _clean_text(work["subscriber_number"])
    work = work.loc[work["_subscriber"].ne("")].copy()

    if work.empty:
        empty = pd.DataFrame()
        return {
            "common_numbers": empty,
            "uncommon_numbers": empty,
            "multi_cell_presence": empty,
            "device_consistency": empty,
            "suspicious_timing": empty,
            "priority_leads": empty,
        }

    work["_session_start"] = pd.to_datetime(
        work.get("session_start"),
        errors="coerce",
    )
    work["_session_end"] = pd.to_datetime(
        work.get("session_end"),
        errors="coerce",
    )

    duration = pd.to_numeric(
        work.get("session_duration_seconds"),
        errors="coerce",
    ).fillna(0)

    volume = pd.to_numeric(
        work.get("total_volume"),
        errors="coerce",
    ).fillna(0)

    work["_duration_seconds"] = duration
    work["_total_volume"] = volume

    grouped = work.groupby("_subscriber", dropna=True)

    summary = grouped.agg(
        session_count=("subscriber_number", "size"),
        first_seen=("_session_start", "min"),
        last_seen=("_session_end", "max"),
        total_duration_seconds=("_duration_seconds", "sum"),
        total_volume=("_total_volume", "sum"),
    ).reset_index().rename(columns={"_subscriber": "subscriber_number"})

    for source_col, output_col in [
        ("searched_cell_id", "cells_seen"),
        ("imei", "imei_count"),
        ("imsi", "imsi_count"),
        ("ipv4_address", "ipv4_count"),
        ("ipv6_address", "ipv6_count"),
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
        ("technology", "technology"),
        ("operator", "operators"),
        ("searched_cell_id", "searched_cells"),
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
        "cells_seen",
        "imei_count",
        "imsi_count",
        "ipv4_count",
        "ipv6_count",
    ]:
        summary[col] = summary[col].fillna(0).astype(int)

    summary["priority_score"] = 0
    summary.loc[summary["session_count"].eq(1), "priority_score"] += 25
    summary.loc[summary["cells_seen"].ge(2), "priority_score"] += 35
    summary.loc[summary["session_count"].ge(5), "priority_score"] += 25
    summary.loc[summary["imei_count"].ge(2), "priority_score"] += 20
    summary.loc[summary["imsi_count"].ge(2), "priority_score"] += 20

    high_volume_threshold = summary["total_volume"].quantile(0.90)
    if pd.notna(high_volume_threshold) and high_volume_threshold > 0:
        summary.loc[
            summary["total_volume"].ge(high_volume_threshold),
            "priority_score",
        ] += 15

    def _priority(score: int) -> str:
        if score >= 70:
            return "High"
        if score >= 45:
            return "Medium"
        return "Low"

    def _confidence(row: pd.Series) -> str:
        if int(row.get("cells_seen", 0) or 0) >= 2 and int(row.get("session_count", 0) or 0) >= 2:
            return "High"
        if int(row.get("session_count", 0) or 0) >= 2:
            return "Medium"
        return "Low"

    def _reason(row: pd.Series) -> str:
        reasons: list[str] = []

        if int(row.get("session_count", 0) or 0) == 1:
            reasons.append("single-session/rare presence")

        if int(row.get("cells_seen", 0) or 0) >= 2:
            reasons.append("multi-cell presence")

        if int(row.get("session_count", 0) or 0) >= 5:
            reasons.append("repeat/high activity")

        if int(row.get("imei_count", 0) or 0) >= 2:
            reasons.append("multiple IMEI")

        if int(row.get("imsi_count", 0) or 0) >= 2:
            reasons.append("multiple IMSI")

        return ", ".join(reasons) if reasons else "low-priority presence"

    summary["priority"] = summary["priority_score"].apply(_priority)
    summary["confidence"] = summary.apply(_confidence, axis=1)
    summary["why_important"] = summary.apply(_reason, axis=1)
    summary["next_action"] = (
        "Verify with CDR/SDR/CAF, IMEI/IMSI, IP details, tower location and field/local input."
    )

    common_numbers = summary.loc[
        summary["session_count"].ge(2)
    ].sort_values(
        ["session_count", "cells_seen", "total_volume"],
        ascending=[False, False, False],
    ).head(top_limit).reset_index(drop=True)

    uncommon_numbers = summary.loc[
        summary["session_count"].eq(1)
    ].sort_values(
        ["cells_seen", "total_volume", "first_seen"],
        ascending=[False, False, True],
    ).head(top_limit).reset_index(drop=True)

    multi_cell_presence = summary.loc[
        summary["cells_seen"].ge(2)
    ].sort_values(
        ["cells_seen", "session_count", "total_volume"],
        ascending=[False, False, False],
    ).head(top_limit).reset_index(drop=True)

    device_consistency = summary.sort_values(
        ["imei_count", "imsi_count", "session_count"],
        ascending=[False, False, False],
    ).head(top_limit).reset_index(drop=True)

    suspicious_timing = summary.sort_values(
        ["session_count", "total_volume", "cells_seen"],
        ascending=[False, False, False],
    ).head(top_limit).reset_index(drop=True)

    priority_leads = summary.sort_values(
        ["priority_score", "cells_seen", "session_count", "total_volume"],
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
