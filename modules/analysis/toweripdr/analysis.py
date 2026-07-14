"""Analytical engine for multi-cell Tower IPDR/NAT dumps."""

from __future__ import annotations

from typing import Any

import pandas as pd
from modules.analysis.common.uncommon_numbers import (
    UncommonNumberConfig,
    find_uncommon_numbers,
    split_current_and_baseline_by_window,
)

from modules.analysis.partition_scope import (
    cell_mask,
    loaded_cell_map,
    resolve_sighting_scope,
)


def _clean_text(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .replace({"nan": "", "None": "", "<NA>": ""})
    )


def _joined_unique(series: pd.Series, limit: int = 10) -> str:
    """Return a small, readable list of unique values.

    Large Tower IPDR dumps can contain thousands of values per group.
    Sorting and joining all values makes subscriber summary very slow.
    For console/Excel summary, keep only first few unique values and mark
    overflow with "...".
    """

    values: list[str] = []
    seen: set[str] = set()
    max_values = max(1, int(limit))

    for value in _clean_text(series):
        if not value or value in seen:
            continue

        seen.add(value)

        if len(values) < max_values:
            values.append(value)
        else:
            values.append("...")
            break

    return ", ".join(values)


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _metric_rows(df: pd.DataFrame, allocations: pd.DataFrame) -> pd.DataFrame:
    event_time = pd.to_datetime(df["event_time"], errors="coerce")
    allocation_start = pd.to_datetime(df["allocation_start"], errors="coerce")
    allocation_end = pd.to_datetime(df["allocation_end"], errors="coerce")

    return pd.DataFrame(
        [
            ("Total IPDR/NAT Events", len(df)),
            ("Source Files", _clean_text(df["source_file"]).replace("", pd.NA).nunique()),
            ("Searched Cell IDs", _clean_text(df["searched_cell_id"]).replace("", pd.NA).nunique()),
            ("Unique Subscribers", _clean_text(df["subscriber_number"]).replace("", pd.NA).nunique()),
            ("Unique IMEI", _clean_text(df["imei"]).replace("", pd.NA).nunique()),
            ("Unique IMSI", _clean_text(df["imsi"]).replace("", pd.NA).nunique()),
            ("Unique Allocation Keys", _clean_text(df["allocation_key"]).replace("", pd.NA).nunique()),
            ("Observed Allocation-Volume Records", len(allocations)),
            ("Unique Source IP", _clean_text(df["source_ip"]).replace("", pd.NA).nunique()),
            ("Unique Translated/NAT IP", _clean_text(df["translated_ip"]).replace("", pd.NA).nunique()),
            ("Unique Destination IP", _clean_text(df["destination_ip"]).replace("", pd.NA).nunique()),
            ("Unique Destination Ports", _numeric(df["destination_port"]).dropna().nunique()),
            ("First Event Time", event_time.min()),
            ("Last Event Time", event_time.max()),
            ("Earliest Allocation Start", allocation_start.min()),
            ("Latest Allocation End", allocation_end.max()),
            ("Negative Duration Rows", int(df["event_duration_negative"].fillna(False).sum())),
            ("Zero Duration Rows", int(df["event_zero_duration"].fillna(False).sum())),
            ("Events Outside Allocation", int((~df["event_within_allocation"].fillna(False)).sum())),
            ("Exact Duplicate Rows Flagged", int(df["exact_duplicate_flag"].fillna(False).sum())),
        ],
        columns=["Metric", "Value"],
    )


def _allocation_records(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["allocation_volume_key"] = _clean_text(work["allocation_volume_key"])
    work = work.loc[work["allocation_volume_key"].ne("")].copy()

    if work.empty:
        return pd.DataFrame()

    group = work.groupby("allocation_volume_key", sort=False, dropna=False)
    records = group.agg(
        subscriber_number=("subscriber_number", "first"),
        subscriber_number_raw=("subscriber_number_raw", "first"),
        source_ip=("source_ip", "first"),
        source_ip_version=("source_ip_version", "first"),
        allocation_start=("allocation_start", "first"),
        allocation_end=("allocation_end", "first"),
        allocation_duration_seconds=("allocation_duration_seconds", "first"),
        imei=("imei", "first"),
        imsi=("imsi", "first"),
        pgw_ip=("pgw_ip", "first"),
        apn=("apn", "first"),
        searched_cell_id=("searched_cell_id", "first"),
        first_cell_id=("first_cell_id", "first"),
        uplink_volume=("uplink_volume", "first"),
        downlink_volume=("downlink_volume", "first"),
        total_volume=("total_volume", "first"),
        event_count=("event_time", "size"),
        first_event_time=("event_time", "min"),
        last_event_time=("event_time", "max"),
        destination_ip_count=(
            "destination_ip",
            lambda values: _clean_text(values).replace("", pd.NA).nunique(),
        ),
        destination_port_count=(
            "destination_port",
            lambda values: _numeric(values).dropna().nunique(),
        ),
        last_cell_count=(
            "last_cell_id",
            lambda values: _clean_text(values).replace("", pd.NA).nunique(),
        ),
        last_cells=("last_cell_id", _joined_unique),
        source_files=("source_file", _joined_unique),
    ).reset_index()

    return records.sort_values(
        ["event_count", "total_volume", "subscriber_number"],
        ascending=[False, False, True],
        na_position="last",
        ignore_index=True,
    )


def _cell_summary(df: pd.DataFrame) -> pd.DataFrame:
    group = df.groupby("searched_cell_id", sort=True, dropna=False)
    result = group.agg(
        Events=("event_time", "size"),
        Unique_Subscribers=(
            "subscriber_number",
            lambda values: _clean_text(values).replace("", pd.NA).nunique(),
        ),
        Unique_IMEI=("imei", lambda values: _clean_text(values).replace("", pd.NA).nunique()),
        Unique_IMSI=("imsi", lambda values: _clean_text(values).replace("", pd.NA).nunique()),
        Allocation_Keys=("allocation_key", "nunique"),
        Allocation_Volume_Records=("allocation_volume_key", "nunique"),
        Unique_Last_Cells=(
            "last_cell_id",
            lambda values: _clean_text(values).replace("", pd.NA).nunique(),
        ),
        First_Event=("event_time", "min"),
        Last_Event=("event_time", "max"),
        Source_Files=("source_file", _joined_unique),
    ).reset_index()

    same = (
        df.groupby("searched_cell_id", dropna=False)["last_cell_matches_searched"]
        .sum()
        .rename("Events_Last_Cell_Same")
        .reset_index()
    )
    result = result.merge(same, on="searched_cell_id", how="left")
    result["Events_Last_Cell_Changed"] = (
        result["Events"] - result["Events_Last_Cell_Same"].fillna(0)
    )
    return result.sort_values("Events", ascending=False, ignore_index=True)


def _subscriber_summary(df: pd.DataFrame, allocations: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["_subscriber"] = _clean_text(work["subscriber_number"])
    work = work.loc[work["_subscriber"].ne("")].copy()

    if work.empty:
        return pd.DataFrame()

    grouped = work.groupby("_subscriber", sort=False)
    result = grouped.agg(
        Events=("event_time", "size"),
        Searched_Cell_Count=(
            "searched_cell_id",
            lambda values: _clean_text(values).replace("", pd.NA).nunique(),
        ),
        Searched_Cells=("searched_cell_id", _joined_unique),
        Allocation_Count=("allocation_key", "nunique"),
        Allocation_Volume_Record_Count=("allocation_volume_key", "nunique"),
        Source_IP_Count=("source_ip", lambda values: _clean_text(values).replace("", pd.NA).nunique()),
        Destination_IP_Count=("destination_ip", lambda values: _clean_text(values).replace("", pd.NA).nunique()),
        Destination_Port_Count=("destination_port", lambda values: _numeric(values).dropna().nunique()),
        First_Event=("event_time", "min"),
        Last_Event=("event_time", "max"),
        IMEI=("imei", _joined_unique),
        IMSI=("imsi", _joined_unique),
        APN=("apn", _joined_unique),
        Roaming=("roaming_indicator", _joined_unique),
        Last_Cell_Count=("last_cell_id", lambda values: _clean_text(values).replace("", pd.NA).nunique()),
        Last_Cells=("last_cell_id", _joined_unique),
    ).reset_index().rename(columns={"_subscriber": "subscriber_number"})

    if not allocations.empty:
        volume = allocations.groupby("subscriber_number", sort=False).agg(
            Deduplicated_Uplink=("uplink_volume", "sum"),
            Deduplicated_Downlink=("downlink_volume", "sum"),
            Deduplicated_Total_Volume=("total_volume", "sum"),
        ).reset_index()
        result = result.merge(volume, on="subscriber_number", how="left")

    return result.sort_values(
        ["Searched_Cell_Count", "Events", "subscriber_number"],
        ascending=[False, False, True],
        ignore_index=True,
    )


def _identity_summary(df: pd.DataFrame, identity: str) -> pd.DataFrame:
    work = df.copy()
    work["_identity"] = _clean_text(work[identity])
    work = work.loc[work["_identity"].ne("")].copy()

    if work.empty:
        return pd.DataFrame()

    result = work.groupby("_identity", sort=False).agg(
        Events=("event_time", "size"),
        Subscriber_Count=(
            "subscriber_number",
            lambda values: _clean_text(values).replace("", pd.NA).nunique(),
        ),
        Subscribers=("subscriber_number", _joined_unique),
        Cell_Count=(
            "searched_cell_id",
            lambda values: _clean_text(values).replace("", pd.NA).nunique(),
        ),
        Cells=("searched_cell_id", _joined_unique),
        Allocation_Count=("allocation_key", "nunique"),
        First_Event=("event_time", "min"),
        Last_Event=("event_time", "max"),
    ).reset_index().rename(columns={"_identity": identity})

    return result.sort_values(
        ["Cell_Count", "Subscriber_Count", "Events", identity],
        ascending=[False, False, False, True],
        ignore_index=True,
    )


def _cell_presence(df: pd.DataFrame, identity_column: str) -> pd.DataFrame:
    cells = sorted(
        value
        for value in _clean_text(df["searched_cell_id"]).unique()
        if value
    )
    work = df.copy()
    work["_identity"] = _clean_text(work[identity_column])
    work = work.loc[work["_identity"].ne("")].copy()

    if work.empty:
        return pd.DataFrame(
            columns=[
                identity_column,
                "cell_count",
                "total_cells",
                "match_ratio",
                "matched_cells",
                "record_count",
                "allocation_count",
                *cells,
            ]
        )

    rows: list[dict[str, Any]] = []

    for identity, group in work.groupby("_identity", sort=False):
        matched = sorted(
            value
            for value in _clean_text(group["searched_cell_id"]).unique()
            if value
        )
        row: dict[str, Any] = {
            identity_column: identity,
            "cell_count": len(matched),
            "total_cells": len(cells),
            "match_ratio": f"{len(matched)}/{len(cells)}",
            "matched_cells": ", ".join(matched),
            "event_count": len(group),
            "allocation_count": group["allocation_key"].nunique(),
            "first_event": pd.to_datetime(group["event_time"], errors="coerce").min(),
            "last_event": pd.to_datetime(group["event_time"], errors="coerce").max(),
        }

        for cell in cells:
            cell_group = group.loc[_clean_text(group["searched_cell_id"]).eq(cell)]
            row[cell] = len(cell_group)

        rows.append(row)

    return pd.DataFrame(rows).sort_values(
        ["cell_count", "event_count", identity_column],
        ascending=[False, False, True],
        ignore_index=True,
    )


def _ip_summary(df: pd.DataFrame, column: str, version_column: str) -> pd.DataFrame:
    work = df.copy()
    work["_ip"] = _clean_text(work[column])
    work = work.loc[work["_ip"].ne("")].copy()

    if work.empty:
        return pd.DataFrame()

    result = work.groupby("_ip", sort=False).agg(
        IP_Version=(version_column, "first"),
        Events=("event_time", "size"),
        Subscriber_Count=("subscriber_number", lambda values: _clean_text(values).replace("", pd.NA).nunique()),
        Subscribers=("subscriber_number", _joined_unique),
        Cell_Count=("searched_cell_id", lambda values: _clean_text(values).replace("", pd.NA).nunique()),
        Cells=("searched_cell_id", _joined_unique),
        First_Event=("event_time", "min"),
        Last_Event=("event_time", "max"),
    ).reset_index().rename(columns={"_ip": column})

    return result.sort_values(
        ["Subscriber_Count", "Cell_Count", "Events", column],
        ascending=[False, False, False, True],
        ignore_index=True,
    )


def _destination_ip_summary(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["_destination"] = _clean_text(work["destination_ip"])
    work = work.loc[work["_destination"].ne("")].copy()

    if work.empty:
        return pd.DataFrame()

    result = work.groupby("_destination", sort=False).agg(
        IP_Version=("destination_ip_version", "first"),
        Events=("event_time", "size"),
        Subscriber_Count=("subscriber_number", lambda values: _clean_text(values).replace("", pd.NA).nunique()),
        Cell_Count=("searched_cell_id", lambda values: _clean_text(values).replace("", pd.NA).nunique()),
        Destination_Port_Count=("destination_port", lambda values: _numeric(values).dropna().nunique()),
        Destination_Ports=("destination_port", _joined_unique),
        First_Event=("event_time", "min"),
        Last_Event=("event_time", "max"),
    ).reset_index().rename(columns={"_destination": "destination_ip"})

    return result.sort_values(
        ["Subscriber_Count", "Cell_Count", "Events", "destination_ip"],
        ascending=[False, False, False, True],
        ignore_index=True,
    )


def _destination_port_summary(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["_port"] = _numeric(work["destination_port"])
    work = work.loc[work["_port"].notna()].copy()

    if work.empty:
        return pd.DataFrame()

    result = work.groupby("_port", sort=True).agg(
        Events=("event_time", "size"),
        Subscriber_Count=("subscriber_number", lambda values: _clean_text(values).replace("", pd.NA).nunique()),
        Destination_IP_Count=("destination_ip", lambda values: _clean_text(values).replace("", pd.NA).nunique()),
        Cell_Count=("searched_cell_id", lambda values: _clean_text(values).replace("", pd.NA).nunique()),
        First_Event=("event_time", "min"),
        Last_Event=("event_time", "max"),
    ).reset_index().rename(columns={"_port": "destination_port"})
    result["destination_port"] = result["destination_port"].astype("Int64")
    return result.sort_values("Events", ascending=False, ignore_index=True)


def _destination_endpoint_summary(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["destination_endpoint"] = (
        _clean_text(work["destination_ip"])
        + ":"
        + _clean_text(work["destination_port"])
    )
    work = work.loc[_clean_text(work["destination_ip"]).ne("")].copy()

    if work.empty:
        return pd.DataFrame()

    return work.groupby("destination_endpoint", sort=False).agg(
        Events=("event_time", "size"),
        Subscriber_Count=("subscriber_number", lambda values: _clean_text(values).replace("", pd.NA).nunique()),
        Cell_Count=("searched_cell_id", lambda values: _clean_text(values).replace("", pd.NA).nunique()),
        First_Event=("event_time", "min"),
        Last_Event=("event_time", "max"),
    ).reset_index().sort_values(
        ["Subscriber_Count", "Events", "destination_endpoint"],
        ascending=[False, False, True],
        ignore_index=True,
    )


def _simple_count(df: pd.DataFrame, column: str, name: str) -> pd.DataFrame:
    values = _clean_text(df[column]).replace("", "UNKNOWN")
    return values.value_counts(dropna=False).rename_axis(name).reset_index(name="Events")


def _movement_summary(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["first_cell_id"] = _clean_text(work["first_cell_id"])
    work["last_cell_id"] = _clean_text(work["last_cell_id"])

    return work.groupby(
        ["searched_cell_id", "first_cell_id", "last_cell_id", "cell_transition_type"],
        dropna=False,
        sort=False,
    ).agg(
        Events=("event_time", "size"),
        Subscriber_Count=("subscriber_number", lambda values: _clean_text(values).replace("", pd.NA).nunique()),
        Subscribers=("subscriber_number", _joined_unique),
        First_Event=("event_time", "min"),
        Last_Event=("event_time", "max"),
    ).reset_index().sort_values(
        ["Subscriber_Count", "Events"],
        ascending=[False, False],
        ignore_index=True,
    )


def _hourly_activity(df: pd.DataFrame) -> pd.DataFrame:
    events = pd.to_datetime(df["event_time"], errors="coerce")
    work = pd.DataFrame({
        "Date": events.dt.date,
        "Hour": events.dt.hour,
        "subscriber_number": df["subscriber_number"],
        "searched_cell_id": df["searched_cell_id"],
    }).dropna(subset=["Date", "Hour"])

    if work.empty:
        return pd.DataFrame()

    return work.groupby(["Date", "Hour"], dropna=False).agg(
        Events=("subscriber_number", "size"),
        Unique_Subscribers=("subscriber_number", lambda values: _clean_text(values).replace("", pd.NA).nunique()),
        Cell_Count=("searched_cell_id", lambda values: _clean_text(values).replace("", pd.NA).nunique()),
    ).reset_index()


def _quality_table(df: pd.DataFrame) -> pd.DataFrame:
    checks = [
        ("Invalid allocation timestamp/range", ~df["allocation_time_valid"].fillna(False)),
        ("Invalid/missing event timestamp", pd.to_datetime(df["event_time"], errors="coerce").isna()),
        ("Negative event duration", df["event_duration_negative"].fillna(False)),
        ("Zero event duration", df["event_zero_duration"].fillna(False)),
        ("Event outside allocation interval", ~df["event_within_allocation"].fillna(False)),
        ("Missing translated/NAT IP", _clean_text(df["translated_ip"]).eq("")),
        ("Missing IMEI", _clean_text(df["imei"]).eq("")),
        ("Missing IMSI", _clean_text(df["imsi"]).eq("")),
        ("First Cell differs from searched Cell", ~df["first_cell_matches_searched"].fillna(False)),
        ("Last Cell differs from searched Cell", ~df["last_cell_matches_searched"].fillna(False)),
        ("Missing volume fields", ~df["volume_fields_present"].fillna(False)),
        ("Exact duplicate event flag", df["exact_duplicate_flag"].fillna(False)),
    ]

    return pd.DataFrame(
        [
            {
                "Check": label,
                "Rows": int(mask.sum()),
                "Percentage": round((int(mask.sum()) / len(df) * 100) if len(df) else 0, 4),
            }
            for label, mask in checks
        ]
    )


def _empty_uncommon_numbers() -> pd.DataFrame:
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
            "priority_level",
            "rank_reason",
            "reason",
            "investigation_hint",
            "source_module",
        ]
    )


def _uncommon_priority_summary(uncommon: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(uncommon, pd.DataFrame) or uncommon.empty:
        return pd.DataFrame(
            columns=[
                "priority_level",
                "candidate_count",
            ]
        )

    if "priority_level" not in uncommon.columns:
        return pd.DataFrame(
            columns=[
                "priority_level",
                "candidate_count",
            ]
        )

    priority_order = {
        "HIGH": 1,
        "MEDIUM_HIGH": 2,
        "MEDIUM": 3,
        "LOW": 4,
    }

    summary = (
        uncommon.groupby("priority_level")
        .size()
        .reset_index(name="candidate_count")
    )

    summary["_sort"] = (
        summary["priority_level"]
        .map(priority_order)
        .fillna(99)
        .astype(int)
    )

    return (
        summary.sort_values("_sort")
        .drop(columns=["_sort"])
        .reset_index(drop=True)
    )


def _tower_ipdr_uncommon_numbers(
    df: pd.DataFrame,
    *,
    window_start: str | None = None,
    window_end: str | None = None,
) -> pd.DataFrame:
    """Build uncommon subscriber leads for a CCTV/incident window.

    Without a window, this returns an empty table because uncommon presence
    needs a current-window vs baseline comparison.
    """

    required_columns = {
        "subscriber_number",
        "event_time",
    }

    if (
        not isinstance(df, pd.DataFrame)
        or df.empty
        or not required_columns.issubset(df.columns)
        or not window_start
        or not window_end
    ):
        return _empty_uncommon_numbers()

    current, baseline = split_current_and_baseline_by_window(
        df,
        time_col="event_time",
        window_start=window_start,
        window_end=window_end,
    )

    config = UncommonNumberConfig(
        entity_col="subscriber_number",
        time_col="event_time",
        cell_col="searched_cell_id" if "searched_cell_id" in df.columns else None,
        imei_col="imei" if "imei" in df.columns else None,
        imsi_col="imsi" if "imsi" in df.columns else None,
        source_module="tower_ipdr",
    )

    return find_uncommon_numbers(
        current,
        baseline,
        config=config,
        min_score=50,
    )

def _normalise_identity_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Keep telecom identifiers as strings for safe grouping/merge.

    CSV/DuckDB/Excel can infer subscriber numbers or ports as numeric values.
    For forensic analysis these are identifiers, not mathematical numbers.
    """

    if not isinstance(df, pd.DataFrame) or df.empty:
        return df

    identity_columns = [
        "subscriber_number",
        "subscriber_number_raw",
        "identifier_type",
        "user_id",
        "imei",
        "imei_raw",
        "imsi",
        "imsi_raw",
        "searched_cell_id",
        "first_cell_id",
        "last_cell_id",
        "source_ip",
        "source_ip_raw",
        "translated_ip",
        "translated_ip_raw",
        "destination_ip",
        "destination_ip_raw",
        "source_port",
        "translated_port",
        "destination_port",
        "operator",
        "source_format",
        "allocation_key",
        "allocation_volume_key",
    ]

    output = df.copy()

    for column in identity_columns:
        if column in output.columns:
            output[column] = (
                output[column]
                .astype("string")
                .fillna("")
                .str.strip()
            )

    return output


def run_tower_ipdr_analysis(
    df: pd.DataFrame,
    *,
    file_summary: pd.DataFrame | None = None,
    uncommon_window_start: str | None = None,
    uncommon_window_end: str | None = None,
) -> dict[str, Any]:
    if not isinstance(df, pd.DataFrame):
        raise TypeError("Tower IPDR pandas DataFrame required hai.")

    if df.empty:
        raise ValueError("Tower IPDR DataFrame empty hai.")
    df = _normalise_identity_columns(df)
    allocations = _allocation_records(df)
    subscriber_summary = _subscriber_summary(df, allocations)
    subscriber_cell_presence = _cell_presence(df, "subscriber_number")
    imei_cell_presence = _cell_presence(df, "imei")
    imsi_cell_presence = _cell_presence(df, "imsi")
    total_cells = int(_clean_text(df["searched_cell_id"]).replace("", pd.NA).nunique())
    uncommon_numbers = _tower_ipdr_uncommon_numbers(
        df,
        window_start=uncommon_window_start,
        window_end=uncommon_window_end,
    )

    uncommon_priority_summary = _uncommon_priority_summary(
        uncommon_numbers
    )

    return {
        "summary": _metric_rows(df, allocations),
        "file_summary": file_summary.copy() if isinstance(file_summary, pd.DataFrame) else pd.DataFrame(),
        "cell_summary": _cell_summary(df),
        "allocation_records": allocations,
        "subscriber_summary": subscriber_summary,
        "subscriber_cell_presence": subscriber_cell_presence,
        "subscriber_multi_cell_candidates": subscriber_cell_presence.loc[
            subscriber_cell_presence["cell_count"] >= 2
        ].reset_index(drop=True) if not subscriber_cell_presence.empty else subscriber_cell_presence,
        "subscriber_all_cell_candidates": subscriber_cell_presence.loc[
            subscriber_cell_presence["cell_count"] == total_cells
        ].reset_index(drop=True) if total_cells and not subscriber_cell_presence.empty else subscriber_cell_presence.iloc[0:0],
        "imei_summary": _identity_summary(df, "imei"),
        "imei_cell_presence": imei_cell_presence,
        "imsi_summary": _identity_summary(df, "imsi"),
        "imsi_cell_presence": imsi_cell_presence,
        "source_ip_summary": _ip_summary(df, "source_ip", "source_ip_version"),
        "translated_ip_summary": _ip_summary(df, "translated_ip", "translated_ip_version"),
        "destination_ip_summary": _destination_ip_summary(df),
        "destination_port_summary": _destination_port_summary(df),
        "destination_endpoint_summary": _destination_endpoint_summary(df),
        "apn_summary": _simple_count(df, "apn", "APN"),
        "roaming_summary": _simple_count(df, "roaming_indicator", "Roaming_Status"),
        "cell_movement_summary": _movement_summary(df),
        "hourly_activity": _hourly_activity(df),
        "data_quality": _quality_table(df),
        "normalized_events": df.copy(),
        "record_count": len(df),
        "total_cells": total_cells,
        "uncommon_numbers": uncommon_numbers,
        "uncommon_priority_summary": uncommon_priority_summary,
    }


def _partition_presence(
    partitions: dict[str, pd.DataFrame],
    identity_column: str,
) -> pd.DataFrame:
    partition_ids = list(partitions)
    aggregate: dict[str, dict[str, Any]] = {}

    for partition_id, dataframe in partitions.items():
        if dataframe.empty or identity_column not in dataframe.columns:
            continue

        work = dataframe.copy()
        work["_identity"] = _clean_text(work[identity_column])
        work = work.loc[work["_identity"].ne("")].copy()

        for identity, group in work.groupby("_identity", sort=False):
            item = aggregate.setdefault(
                identity,
                {
                    identity_column: identity,
                    "matched_partitions": [],
                    "record_count": 0,
                    "allocation_count": set(),
                    "cells": set(),
                    "first_event": pd.NaT,
                    "last_event": pd.NaT,
                },
            )
            item["matched_partitions"].append(partition_id)
            item["record_count"] += len(group)
            item["allocation_count"].update(_clean_text(group["allocation_key"]))
            item["cells"].update(value for value in _clean_text(group["searched_cell_id"]) if value)
            group_times = pd.to_datetime(group["event_time"], errors="coerce")
            first = group_times.min()
            last = group_times.max()

            if pd.isna(item["first_event"]) or (pd.notna(first) and first < item["first_event"]):
                item["first_event"] = first
            if pd.isna(item["last_event"]) or (pd.notna(last) and last > item["last_event"]):
                item["last_event"] = last

    rows: list[dict[str, Any]] = []

    for item in aggregate.values():
        matched = set(item["matched_partitions"])
        row: dict[str, Any] = {
            identity_column: item[identity_column],
            "match_count": len(matched),
            "total_partitions": len(partition_ids),
            "match_ratio": f"{len(matched)}/{len(partition_ids)}",
            "matched_partitions": ", ".join(sorted(matched)),
            "record_count": item["record_count"],
            "allocation_count": len({value for value in item["allocation_count"] if value}),
            "cell_count": len(item["cells"]),
            "cells": ", ".join(sorted(item["cells"])),
            "first_event": item["first_event"],
            "last_event": item["last_event"],
        }

        for partition_id in partition_ids:
            row[partition_id] = 1 if partition_id in matched else 0

        rows.append(row)

    if not rows:
        return pd.DataFrame(
            columns=[
                identity_column,
                "match_count",
                "total_partitions",
                "match_ratio",
                "matched_partitions",
                "record_count",
                "allocation_count",
                "cell_count",
                "cells",
                "first_event",
                "last_event",
                *partition_ids,
            ]
        )

    return pd.DataFrame(rows).sort_values(
        ["match_count", "cell_count", "record_count", identity_column],
        ascending=[False, False, False, True],
        ignore_index=True,
    )


def create_tower_ipdr_partitions(
    df: pd.DataFrame,
    *,
    sightings: list[dict[str, Any]],
    cgi_groups: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create location-aware actual-event and allocation-overlap partitions."""

    if not isinstance(df, pd.DataFrame) or df.empty:
        raise ValueError("Valid Tower IPDR DataFrame required hai.")

    ordered = sorted(
        [item for item in sightings if isinstance(item, dict)],
        key=lambda item: (
            str(item.get("cctv_timestamp", "")),
            str(item.get("sighting_id", "")),
        ),
    )

    event_time = pd.to_datetime(df["event_time"], errors="coerce")
    allocation_start = pd.to_datetime(df["allocation_start"], errors="coerce")
    allocation_end = pd.to_datetime(df["allocation_end"], errors="coerce")
    loaded_cells = loaded_cell_map(df)

    actual_partitions: dict[str, pd.DataFrame] = {}
    allocation_partitions: dict[str, pd.DataFrame] = {}
    window_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    actual_hits: list[pd.DataFrame] = []
    allocation_hits: list[pd.DataFrame] = []
    actual_excluded: list[pd.DataFrame] = []
    allocation_excluded: list[pd.DataFrame] = []
    warnings: list[str] = []

    for index, sighting in enumerate(ordered, start=1):
        partition_id = f"P{index}"
        sighting_id = str(sighting.get("sighting_id", "")).strip()
        cctv_timestamp = pd.to_datetime(sighting.get("cctv_timestamp"), errors="coerce")
        window_start = pd.to_datetime(sighting.get("window_start"), errors="coerce")
        window_end = pd.to_datetime(sighting.get("window_end"), errors="coerce")

        status: dict[str, Any] = {
            "partition_id": partition_id,
            "sighting_id": sighting_id,
            "location_name": sighting.get("location_name", ""),
            "cctv_timestamp": cctv_timestamp,
            "window_start": window_start,
            "window_end": window_end,
            "cgi_group_id": str(sighting.get("cgi_group_id", "")),
        }

        if not sighting_id:
            status.update(status="INVALID_SIGHTING_ID", scope_mode="INVALID", message="Sighting ID missing hai.", included=False)
            status_rows.append(status)
            continue
        if pd.isna(window_start) or pd.isna(window_end) or window_start > window_end:
            status.update(status="INVALID_TIME_WINDOW", scope_mode="INVALID", message="Window start/end invalid hai.", included=False)
            status_rows.append(status)
            continue

        scope = resolve_sighting_scope(
            sighting,
            cgi_groups=cgi_groups,
            loaded_cells=loaded_cells,
            source_type="IPDR",
        )
        status.update(
            status=scope["status"],
            scope_mode=scope["scope_mode"],
            cgi_group_id=scope["group_id"],
            resolved_cgi_count=len(scope["cell_keys"]),
            resolved_cgi_values=", ".join(scope["cell_values"]),
            message=scope["message"],
            included=bool(scope["valid"]),
        )
        status_rows.append(status)
        if not scope["valid"]:
            continue

        if scope["scope_mode"] == "TIME_ONLY_ALL_CELLS":
            location_mask = pd.Series(True, index=df.index)
            warnings.append(f"{partition_id}: {scope['message']}")
        else:
            location_mask = cell_mask(df, scope["cell_keys"])

        actual_time_mask = event_time.between(window_start, window_end, inclusive="both")
        allocation_time_mask = (
            allocation_start.le(window_end)
            & allocation_end.ge(window_start)
            & allocation_start.notna()
            & allocation_end.notna()
        )
        actual_mask = actual_time_mask & location_mask
        allocation_mask = allocation_time_mask & location_mask

        actual = df.loc[actual_mask].copy()
        allocation = df.loc[allocation_mask].copy()
        deduplicated_allocation = (
            allocation.sort_values("event_time").drop_duplicates(
                subset=["allocation_volume_key"], keep="first"
            ).copy()
            if not allocation.empty
            else allocation.copy()
        )

        excluded_actual = df.loc[actual_time_mask & ~location_mask].copy()
        if not excluded_actual.empty:
            excluded_actual.insert(0, "partition_id", partition_id)
            excluded_actual.insert(1, "sighting_id", sighting_id)
            excluded_actual.insert(2, "exclusion_reason", "TIME_MATCH_LOCATION_MISMATCH")
            actual_excluded.append(excluded_actual)

        excluded_allocation = df.loc[allocation_time_mask & ~location_mask].copy()
        if not excluded_allocation.empty:
            excluded_allocation.insert(0, "partition_id", partition_id)
            excluded_allocation.insert(1, "sighting_id", sighting_id)
            excluded_allocation.insert(2, "exclusion_reason", "ALLOCATION_TIME_MATCH_LOCATION_MISMATCH")
            allocation_excluded.append(excluded_allocation)

        for table in (actual, deduplicated_allocation):
            if not table.empty:
                table.insert(0, "partition_id", partition_id)
                table.insert(1, "partition_sighting_id", sighting_id)
                table.insert(2, "partition_location", sighting.get("location_name", ""))
                table.insert(3, "partition_cgi_group_id", scope["group_id"])
                table.insert(4, "partition_scope_mode", scope["scope_mode"])

        actual_partitions[partition_id] = actual
        allocation_partitions[partition_id] = deduplicated_allocation
        if not actual.empty:
            actual_hits.append(actual)
        if not deduplicated_allocation.empty:
            allocation_hits.append(deduplicated_allocation)

        window_rows.append(
            {
                "partition_id": partition_id,
                "sighting_id": sighting_id,
                "location_name": sighting.get("location_name", ""),
                "cctv_timestamp": cctv_timestamp,
                "window_start": window_start,
                "window_end": window_end,
                "minutes_before": sighting.get("minutes_before", 10),
                "minutes_after": sighting.get("minutes_after", 10),
                "cgi_group_id": scope["group_id"],
                "scope_mode": scope["scope_mode"],
                "resolved_cgi_values": ", ".join(scope["cell_values"]),
            }
        )
        summary_rows.append(
            {
                "partition_id": partition_id,
                "sighting_id": sighting_id,
                "location_name": sighting.get("location_name", ""),
                "cctv_timestamp": cctv_timestamp,
                "window_start": window_start,
                "window_end": window_end,
                "cgi_group_id": scope["group_id"],
                "scope_mode": scope["scope_mode"],
                "resolved_cgi_count": len(scope["cell_keys"]),
                "actual_event_rows": len(actual),
                "actual_event_subscribers": _clean_text(actual.get("subscriber_number", pd.Series(dtype=str))).replace("", pd.NA).nunique(),
                "actual_event_cells": _clean_text(actual.get("searched_cell_id", pd.Series(dtype=str))).replace("", pd.NA).nunique(),
                "actual_event_allocations": actual.get("allocation_key", pd.Series(dtype=str)).nunique(),
                "actual_time_only_location_exclusions": int((actual_time_mask & ~location_mask).sum()),
                "allocation_overlap_rows": len(allocation),
                "allocation_overlap_records": len(deduplicated_allocation),
                "allocation_overlap_subscribers": _clean_text(allocation.get("subscriber_number", pd.Series(dtype=str))).replace("", pd.NA).nunique(),
                "allocation_overlap_cells": _clean_text(allocation.get("searched_cell_id", pd.Series(dtype=str))).replace("", pd.NA).nunique(),
                "allocation_overlap_keys": allocation.get("allocation_key", pd.Series(dtype=str)).nunique(),
                "allocation_time_only_location_exclusions": int((allocation_time_mask & ~location_mask).sum()),
            }
        )

    total_partitions = len(actual_partitions)
    event_presence = _partition_presence(actual_partitions, "subscriber_number")
    allocation_presence = _partition_presence(allocation_partitions, "subscriber_number")
    imei_presence = _partition_presence(actual_partitions, "imei")
    imsi_presence = _partition_presence(actual_partitions, "imsi")

    def candidates(table: pd.DataFrame, minimum: int) -> pd.DataFrame:
        if table.empty:
            return table.copy()
        return table.loc[table["match_count"] >= minimum].reset_index(drop=True)

    minimum = 1 if total_partitions <= 1 else 2
    return {
        "partition_windows": pd.DataFrame(window_rows),
        "partition_summary": pd.DataFrame(summary_rows),
        "partition_status": pd.DataFrame(status_rows),
        "actual_event_hits": pd.concat(actual_hits, ignore_index=True) if actual_hits else pd.DataFrame(),
        "allocation_overlap_hits": pd.concat(allocation_hits, ignore_index=True) if allocation_hits else pd.DataFrame(),
        "actual_time_only_excluded_by_location": pd.concat(actual_excluded, ignore_index=True) if actual_excluded else pd.DataFrame(),
        "allocation_time_only_excluded_by_location": pd.concat(allocation_excluded, ignore_index=True) if allocation_excluded else pd.DataFrame(),
        "event_subscriber_presence": event_presence,
        "event_n_of_m_candidates": candidates(event_presence, minimum),
        "event_strict_common_candidates": candidates(event_presence, total_partitions) if total_partitions else event_presence.iloc[0:0],
        "allocation_subscriber_presence": allocation_presence,
        "allocation_n_of_m_candidates": candidates(allocation_presence, minimum),
        "allocation_strict_common_candidates": candidates(allocation_presence, total_partitions) if total_partitions else allocation_presence.iloc[0:0],
        "imei_event_presence": imei_presence,
        "imsi_event_presence": imsi_presence,
        "total_partitions": total_partitions,
        "total_configured_sightings": len(ordered),
        "warnings": list(dict.fromkeys(warnings)),
        "actual_event_rule": "window_start <= event_time <= window_end",
        "allocation_overlap_rule": "allocation_start <= window_end AND allocation_end >= window_start",
        "location_rule": "searched_cell_id matches resolved sighting CGI group",
    }
