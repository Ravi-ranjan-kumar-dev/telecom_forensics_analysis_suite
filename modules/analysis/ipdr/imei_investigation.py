"""Exact IMEI investigation for normalized IPDR records.

The module searches one canonical 15- or 16-digit IMEI across an already
loaded IPDR DataFrame. Source rows are copied and never modified.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from modules.loader.telecom_identifiers import (
    normalize_imei,
    normalize_imsi,
)


def _series(
    dataframe: pd.DataFrame,
    names: tuple[str, ...],
    default: Any = "",
) -> pd.Series:
    for name in names:
        if name in dataframe.columns:
            return dataframe[name]

    return pd.Series(
        default,
        index=dataframe.index,
        dtype="object",
    )


def _text(
    dataframe: pd.DataFrame,
    names: tuple[str, ...],
) -> pd.Series:
    return (
        _series(dataframe, names)
        .astype("string")
        .fillna("")
        .str.strip()
    )


def _datetime(
    dataframe: pd.DataFrame,
    names: tuple[str, ...],
) -> pd.Series:
    for name in names:
        if name not in dataframe.columns:
            continue

        parsed = pd.to_datetime(
            dataframe[name],
            errors="coerce",
            dayfirst=True,
        )

        if parsed.notna().any():
            return parsed

    return pd.Series(
        pd.NaT,
        index=dataframe.index,
        dtype="datetime64[ns]",
    )


def _join_unique(
    values: pd.Series,
) -> str:
    return ", ".join(
        sorted(
            {
                str(value).strip()
                for value in values.dropna()
                if str(value).strip()
            }
        )
    )


def _unique_count(
    values: pd.Series,
) -> int:
    return int(
        values.astype("string")
        .fillna("")
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .nunique()
    )


def _empty_bundle(
    requested_imei: str,
    *,
    status: str,
    message: str,
) -> dict[str, Any]:
    return {
        "requested_imei": requested_imei,
        "status": status,
        "message": message,
        "record_count": 0,
        "summary": pd.DataFrame(
            columns=["Metric", "Value"]
        ),
        "associated_subscribers": pd.DataFrame(),
        "associated_sims": pd.DataFrame(),
        "destination_endpoints": pd.DataFrame(),
        "cells": pd.DataFrame(),
        "timeline": pd.DataFrame(),
        "review_indicators": pd.DataFrame(
            columns=[
                "Indicator",
                "Observation",
                "Caution",
            ]
        ),
        "data_quality": pd.DataFrame(
            columns=[
                "Check",
                "Count",
                "Meaning",
            ]
        ),
    }


def _prepare_matches(
    dataframe: pd.DataFrame,
    requested_imei: str,
) -> pd.DataFrame:
    if (
        not isinstance(dataframe, pd.DataFrame)
        or dataframe.empty
        or "imei" not in dataframe.columns
    ):
        return pd.DataFrame()

    raw_imei = (
        dataframe["imei"]
        .astype("string")
        .fillna("")
        .str.strip()
    )

    normalized_imei = raw_imei.map(
        normalize_imei
    )

    query_identifier = _text(
        dataframe,
        (
            "query_identifier_normalized",
            "query_identifier_raw",
        ),
    ).map(
        normalize_imei
    )

    recorded_relation = (
        _text(
            dataframe,
            (
                "match_relation",
            ),
        )
        .astype("string")
        .fillna("")
        .str.strip()
        .str.upper()
    )

    exact_observed_match = normalized_imei.eq(
        requested_imei
    )

    exact_query_scope = query_identifier.eq(
        requested_imei
    )

    match_mask = (
        exact_observed_match
        | exact_query_scope
    )

    if not match_mask.any():
        return pd.DataFrame()

    match_basis = pd.Series(
        "",
        index=dataframe.index,
        dtype="string",
    )

    match_basis.loc[
        exact_query_scope
    ] = "QUERY_SCOPE"

    # Exact observed matching takes precedence when both conditions apply.
    match_basis.loc[
        exact_observed_match
    ] = "EXACT_OBSERVED"

    fallback_relation = pd.Series(
        "UNAVAILABLE",
        index=dataframe.index,
        dtype="string",
    )

    fallback_relation.loc[
        exact_query_scope
    ] = "REPORT_SCOPE"

    fallback_relation.loc[
        exact_observed_match
    ] = "EXACT"

    effective_relation = recorded_relation.where(
        recorded_relation.ne(""),
        fallback_relation,
    )

    data = dataframe.loc[
        match_mask
    ].copy()

    # Do not carry source DataFrame metadata into internal calculations.
    data.attrs = {}

    data["_raw_imei"] = raw_imei.loc[
        match_mask
    ].astype(str)

    data["_imei"] = normalized_imei.loc[
        match_mask
    ].astype(str)

    data["_query_identifier"] = query_identifier.loc[
        match_mask
    ].astype(str)

    data["_match_basis"] = match_basis.loc[
        match_mask
    ].astype(str)

    data["_match_relation"] = effective_relation.loc[
        match_mask
    ].astype(str)

    data["_subscriber"] = _text(
        data,
        (
            "subscriber_number",
            "subscriber_id",
            "user_id",
        ),
    )

    data["_subscriber_type"] = _text(
        data,
        (
            "subscriber_identifier_type",
            "identifier_type",
        ),
    )

    data["_imsi"] = _text(
        data,
        ("imsi",),
    ).map(
        normalize_imsi
    )

    data["_event_time"] = _datetime(
        data,
        (
            "event_time",
            "allocation_start",
            "session_start",
            "start_time",
        ),
    )

    data["_end_time"] = _datetime(
        data,
        (
            "allocation_end",
            "session_end",
            "end_time",
        ),
    )

    data["_duration"] = (
        pd.to_numeric(
            _series(
                data,
                (
                    "session_duration_seconds",
                    "duration_seconds",
                    "duration",
                ),
                0,
            ),
            errors="coerce",
        )
        .fillna(0)
        .clip(lower=0)
    )

    text_columns = {
        "_source_ip": ("source_ip",),
        "_source_port": ("source_port",),
        "_translated_ip": ("translated_ip",),
        "_translated_port": ("translated_port",),
        "_destination_ip": ("destination_ip",),
        "_destination_port": ("destination_port",),
        "_protocol": (
            "protocol",
            "ip_protocol",
            "transport_protocol",
        ),
        "_apn": ("apn",),
        "_technology": ("technology",),
        "_cgi": (
            "cgi",
            "cell_id",
        ),
        "_first_cell": ("first_cell_id",),
        "_last_cell": ("last_cell_id",),
        "_charging_id": ("charging_id",),
        "_source_file": (
            "source_file",
            "file_name",
            "filename",
        ),
    }

    for output_column, source_columns in text_columns.items():
        data[output_column] = _text(
            data,
            source_columns,
        )

    data["_source_row"] = _series(
        data,
        (
            "source_row_number",
            "raw_row_number",
            "row_number",
        ),
        pd.NA,
    )

    return data


def _build_summary(
    data: pd.DataFrame,
    requested_imei: str,
    cells: pd.DataFrame,
) -> pd.DataFrame:
    event_times = data[
        "_event_time"
    ].dropna()

    rows = [
        (
            "Requested IMEI / IMEISV",
            requested_imei,
        ),
        (
            "Identifier Length",
            len(requested_imei),
        ),
        (
            "Matched IPDR Records",
            len(data),
        ),
        (
            "Associated Subscribers / User IDs",
            _unique_count(data["_subscriber"]),
        ),
        (
            "Associated IMSIs",
            _unique_count(data["_imsi"]),
        ),
        (
            "Source Files",
            _unique_count(data["_source_file"]),
        ),
        (
            "Unique Source IPs",
            _unique_count(data["_source_ip"]),
        ),
        (
            "Unique Destination IPs",
            _unique_count(data["_destination_ip"]),
        ),
        (
            "Unique Cell IDs",
            (
                _unique_count(cells["_cell"])
                if not cells.empty
                else 0
            ),
        ),
        (
            "First Seen",
            (
                event_times.min()
                if not event_times.empty
                else pd.NaT
            ),
        ),
        (
            "Last Seen",
            (
                event_times.max()
                if not event_times.empty
                else pd.NaT
            ),
        ),
        (
            "Total Duration (Sec)",
            int(data["_duration"].sum()),
        ),
    ]

    return pd.DataFrame(
        rows,
        columns=["Metric", "Value"],
    )


def _build_subscribers(
    data: pd.DataFrame,
) -> pd.DataFrame:
    work = data.loc[
        data["_subscriber"].ne("")
    ].copy()

    columns = [
        "Subscriber / User ID",
        "Identifier Type",
        "Source Files",
        "File Count",
        "Total Records",
        "First Seen",
        "Last Seen",
        "Unique IMSIs",
        "Unique Source IPs",
        "Unique Destination IPs",
        "Total Duration (Sec)",
    ]

    if work.empty:
        return pd.DataFrame(
            columns=columns
        )

    result = (
        work.groupby(
            [
                "_subscriber",
                "_subscriber_type",
            ],
            dropna=False,
        )
        .agg(
            **{
                "Source Files": (
                    "_source_file",
                    _join_unique,
                ),
                "File Count": (
                    "_source_file",
                    _unique_count,
                ),
                "Total Records": (
                    "_imei",
                    "size",
                ),
                "First Seen": (
                    "_event_time",
                    "min",
                ),
                "Last Seen": (
                    "_event_time",
                    "max",
                ),
                "Unique IMSIs": (
                    "_imsi",
                    _unique_count,
                ),
                "Unique Source IPs": (
                    "_source_ip",
                    _unique_count,
                ),
                "Unique Destination IPs": (
                    "_destination_ip",
                    _unique_count,
                ),
                "Total Duration (Sec)": (
                    "_duration",
                    "sum",
                ),
            }
        )
        .reset_index()
        .rename(
            columns={
                "_subscriber": "Subscriber / User ID",
                "_subscriber_type": "Identifier Type",
            }
        )
    )

    result["Total Duration (Sec)"] = (
        result["Total Duration (Sec)"]
        .fillna(0)
        .astype(int)
    )

    return (
        result[columns]
        .sort_values(
            [
                "Total Records",
                "Subscriber / User ID",
            ],
            ascending=[
                False,
                True,
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _build_sims(
    data: pd.DataFrame,
) -> pd.DataFrame:
    work = data.loc[
        data["_imsi"].ne("")
    ].copy()

    columns = [
        "IMSI",
        "Subscribers / User IDs",
        "Subscriber Count",
        "Source Files",
        "File Count",
        "Total Records",
        "First Seen",
        "Last Seen",
    ]

    if work.empty:
        return pd.DataFrame(
            columns=columns
        )

    result = (
        work.groupby(
            "_imsi",
            dropna=False,
        )
        .agg(
            **{
                "Subscribers / User IDs": (
                    "_subscriber",
                    _join_unique,
                ),
                "Subscriber Count": (
                    "_subscriber",
                    _unique_count,
                ),
                "Source Files": (
                    "_source_file",
                    _join_unique,
                ),
                "File Count": (
                    "_source_file",
                    _unique_count,
                ),
                "Total Records": (
                    "_imei",
                    "size",
                ),
                "First Seen": (
                    "_event_time",
                    "min",
                ),
                "Last Seen": (
                    "_event_time",
                    "max",
                ),
            }
        )
        .reset_index()
        .rename(
            columns={
                "_imsi": "IMSI",
            }
        )
    )

    return (
        result[columns]
        .sort_values(
            [
                "Total Records",
                "IMSI",
            ],
            ascending=[
                False,
                True,
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _build_endpoints(
    data: pd.DataFrame,
) -> pd.DataFrame:
    work = data.loc[
        data["_destination_ip"].ne("")
    ].copy()

    columns = [
        "Destination IP",
        "Destination Port",
        "Protocol",
        "Subscribers / User IDs",
        "Subscriber Count",
        "Source Files",
        "Total Records",
        "First Seen",
        "Last Seen",
    ]

    if work.empty:
        return pd.DataFrame(
            columns=columns
        )

    result = (
        work.groupby(
            [
                "_destination_ip",
                "_destination_port",
                "_protocol",
            ],
            dropna=False,
        )
        .agg(
            **{
                "Subscribers / User IDs": (
                    "_subscriber",
                    _join_unique,
                ),
                "Subscriber Count": (
                    "_subscriber",
                    _unique_count,
                ),
                "Source Files": (
                    "_source_file",
                    _join_unique,
                ),
                "Total Records": (
                    "_imei",
                    "size",
                ),
                "First Seen": (
                    "_event_time",
                    "min",
                ),
                "Last Seen": (
                    "_event_time",
                    "max",
                ),
            }
        )
        .reset_index()
        .rename(
            columns={
                "_destination_ip": "Destination IP",
                "_destination_port": "Destination Port",
                "_protocol": "Protocol",
            }
        )
    )

    return (
        result[columns]
        .sort_values(
            [
                "Total Records",
                "Destination IP",
                "Destination Port",
            ],
            ascending=[
                False,
                True,
                True,
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _collect_cells(
    data: pd.DataFrame,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for column in (
        "_cgi",
        "_first_cell",
        "_last_cell",
    ):
        subset = data.loc[
            data[column].ne("")
        ].copy()

        if subset.empty:
            continue

        subset["_cell"] = subset[column]
        frames.append(subset)

    if not frames:
        return pd.DataFrame()

    cells = pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )

    return cells.drop_duplicates(
        subset=[
            "_cell",
            "_source_file",
            "_source_row",
            "_event_time",
        ],
        keep="first",
    )


def _build_cells(
    cells: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "Cell ID",
        "Subscribers / User IDs",
        "Subscriber Count",
        "Source Files",
        "Total Records",
        "First Seen",
        "Last Seen",
    ]

    if cells.empty:
        return pd.DataFrame(
            columns=columns
        )

    result = (
        cells.groupby(
            "_cell",
            dropna=False,
        )
        .agg(
            **{
                "Subscribers / User IDs": (
                    "_subscriber",
                    _join_unique,
                ),
                "Subscriber Count": (
                    "_subscriber",
                    _unique_count,
                ),
                "Source Files": (
                    "_source_file",
                    _join_unique,
                ),
                "Total Records": (
                    "_imei",
                    "size",
                ),
                "First Seen": (
                    "_event_time",
                    "min",
                ),
                "Last Seen": (
                    "_event_time",
                    "max",
                ),
            }
        )
        .reset_index()
        .rename(
            columns={
                "_cell": "Cell ID",
            }
        )
    )

    return (
        result[columns]
        .sort_values(
            [
                "Total Records",
                "Cell ID",
            ],
            ascending=[
                False,
                True,
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _build_timeline(
    data: pd.DataFrame,
) -> pd.DataFrame:
    timeline = pd.DataFrame(
        {
            "Event Time": data["_event_time"],
            "Allocation End": data["_end_time"],
            "Subscriber / User ID": data["_subscriber"],
            "Identifier Type": data["_subscriber_type"],
            "IMSI": data["_imsi"],
            "Source IP": data["_source_ip"],
            "Source Port": data["_source_port"],
            "Translated IP": data["_translated_ip"],
            "Translated Port": data["_translated_port"],
            "Destination IP": data["_destination_ip"],
            "Destination Port": data["_destination_port"],
            "Protocol": data["_protocol"],
            "APN": data["_apn"],
            "Technology": data["_technology"],
            "Cell ID": data["_cgi"],
            "First Cell ID": data["_first_cell"],
            "Last Cell ID": data["_last_cell"],
            "Duration (Sec)": data["_duration"].astype(int),
            "Charging ID": data["_charging_id"],
            "Source File": data["_source_file"],
            "Source Row Number": data["_source_row"],
            "Query Identifier": data["_query_identifier"],
            "Raw IMEI": data["_raw_imei"],
            "Normalized IMEI": data["_imei"],
            "Match Basis": data["_match_basis"],
            "Match Relation": data["_match_relation"],
        }
    )

    return (
        timeline.sort_values(
            [
                "Event Time",
                "Source File",
                "Source Row Number",
            ],
            ascending=[
                True,
                True,
                True,
            ],
            kind="stable",
            na_position="last",
        )
        .reset_index(drop=True)
    )


def _build_review_indicators(
    data: pd.DataFrame,
    requested_imei: str,
) -> pd.DataFrame:
    rows: list[dict[str, str]] = []

    subscriber_count = _unique_count(
        data["_subscriber"]
    )

    imsi_count = _unique_count(
        data["_imsi"]
    )

    file_count = _unique_count(
        data["_source_file"]
    )

    if subscriber_count > 1:
        rows.append(
            {
                "Indicator": (
                    "Device identifier linked to multiple subscribers"
                ),
                "Observation": (
                    f"The exact identifier appears with "
                    f"{subscriber_count} subscriber or user identifiers."
                ),
                "Caution": (
                    "Verify ownership periods, SIM changes, "
                    "shared-device use and source duplication."
                ),
            }
        )

    if imsi_count > 1:
        rows.append(
            {
                "Indicator": (
                    "Multiple SIM identities observed"
                ),
                "Observation": (
                    f"The exact identifier appears with "
                    f"{imsi_count} IMSIs."
                ),
                "Caution": (
                    "This may reflect SIM changes, dual-SIM handling, "
                    "different usage periods or source-data quality."
                ),
            }
        )

    if file_count > 1:
        rows.append(
            {
                "Indicator": (
                    "Evidence appears in multiple IPDR files"
                ),
                "Observation": (
                    f"Matching records occur in "
                    f"{file_count} source files."
                ),
                "Caution": (
                    "Check overlapping request periods and exact "
                    "duplicates before summing records."
                ),
            }
        )

    if len(requested_imei) == 16:
        rows.append(
            {
                "Indicator": (
                    "Exact 16-digit identifier retained"
                ),
                "Observation": (
                    "The complete normalized 16-digit value was searched."
                ),
                "Caution": (
                    "It was not silently truncated or merged "
                    "with a 15-digit IMEI."
                ),
            }
        )

    query_scope_mask = data[
        "_match_basis"
    ].eq(
        "QUERY_SCOPE"
    )

    query_scope_count = int(
        query_scope_mask.sum()
    )

    if query_scope_count:
        relation_values = _join_unique(
            data.loc[
                query_scope_mask,
                "_match_relation",
            ]
        )

        rows.append(
            {
                "Indicator": (
                    "Dedicated report query matched"
                ),
                "Observation": (
                    f"{query_scope_count} IPDR record(s) were included "
                    "because the entered identifier exactly matched "
                    "the dedicated report query. Observed relation(s): "
                    f"{relation_values or 'UNAVAILABLE'}."
                ),
                "Caution": (
                    "The report query and the identifier observed in "
                    "individual records remain separate. Verify the "
                    "recorded relation against the original evidence."
                ),
            }
        )

    if not rows:
        rows.append(
            {
                "Indicator": (
                    "No automatic review indicator"
                ),
                "Observation": (
                    "No configured multi-subscriber, multi-SIM "
                    "or multi-file condition was found."
                ),
                "Caution": (
                    "Absence of an indicator does not establish "
                    "ownership or normality."
                ),
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "Indicator",
            "Observation",
            "Caution",
        ],
    )


def _build_data_quality(
    data: pd.DataFrame,
) -> pd.DataFrame:
    rows = [
        (
            "Matched IPDR records",
            len(data),
            "Rows matching the exact canonical identifier.",
        ),
        (
            "Missing event time",
            int(data["_event_time"].isna().sum()),
            "Rows not reliably placeable on the timeline.",
        ),
        (
            "Missing subscriber / user ID",
            int(data["_subscriber"].eq("").sum()),
            "Rows without a subscriber identity.",
        ),
        (
            "Missing or invalid IMSI",
            int(data["_imsi"].eq("").sum()),
            "Rows without a valid normalized SIM identity.",
        ),
        (
            "Missing source IP",
            int(data["_source_ip"].eq("").sum()),
            "Rows without a source IP.",
        ),
        (
            "Missing destination IP",
            int(data["_destination_ip"].eq("").sum()),
            "Rows without a destination IP.",
        ),
        (
            "Exact observed identifier matches",
            int(
                data[
                    "_match_basis"
                ]
                .eq(
                    "EXACT_OBSERVED"
                )
                .sum()
            ),
            (
                "Rows where the entered identifier exactly equals "
                "the identifier observed in the IPDR record."
            ),
        ),
        (
            "Dedicated report-query matches",
            int(
                data[
                    "_match_basis"
                ]
                .eq(
                    "QUERY_SCOPE"
                )
                .sum()
            ),
            (
                "Rows included through an exact dedicated-report "
                "query match. The observed identifier remains separate."
            ),
        ),
        (
            "16-digit observed records",
            int(data["_imei"].str.len().eq(16).sum()),
            "Complete 16-digit observed identifiers retained.",
        ),
    ]

    return pd.DataFrame(
        rows,
        columns=[
            "Check",
            "Count",
            "Meaning",
        ],
    )


def build_ipdr_imei_investigation(
    dataframe: pd.DataFrame,
    requested_imei: Any,
) -> dict[str, Any]:
    """Search one exact IMEI or IMEISV in normalized IPDR records."""

    normalized_requested = normalize_imei(
        requested_imei
    )

    if not normalized_requested:
        return _empty_bundle(
            "",
            status="INVALID_IMEI",
            message=(
                "Enter a valid 15- or 16-digit IMEI/IMEISV."
            ),
        )

    if not isinstance(
        dataframe,
        pd.DataFrame,
    ):
        return _empty_bundle(
            normalized_requested,
            status="NO_INPUT",
            message=(
                "No normalized IPDR DataFrame was provided."
            ),
        )

    matches = _prepare_matches(
        dataframe,
        normalized_requested,
    )

    if matches.empty:
        return _empty_bundle(
            normalized_requested,
            status="NOT_FOUND",
            message=(
                "The exact normalized IMEI/IMEISV was not found "
                "in the loaded IPDR records."
            ),
        )

    cell_events = _collect_cells(
        matches
    )

    timeline = _build_timeline(
        matches
    )

    return {
        "requested_imei": normalized_requested,
        "status": "FOUND",
        "message": (
            f"Found {len(matches)} matching IPDR record(s)."
        ),
        "record_count": len(matches),
        "summary": _build_summary(
            matches,
            normalized_requested,
            cell_events,
        ),
        "associated_subscribers": _build_subscribers(
            matches
        ),
        "associated_sims": _build_sims(
            matches
        ),
        "destination_endpoints": _build_endpoints(
            matches
        ),
        "cells": _build_cells(
            cell_events
        ),
        "timeline": timeline,
        "review_indicators": _build_review_indicators(
            matches,
            normalized_requested,
        ),
        "data_quality": _build_data_quality(
            matches
        ),
    }
