"""Exact IMEI investigation for normalized GPRS sessions.

The module searches one canonical 15- or 16-digit IMEI across an already
loaded GPRS DataFrame. Source rows and raw evidence remain unchanged.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from modules.loader.telecom_identifiers import (
    normalize_imei,
    normalize_imsi,
)


SUMMARY_COLUMNS = [
    "Metric",
    "Value",
]

SUBSCRIBER_COLUMNS = [
    "Subscriber Number",
    "Identifier Type",
    "Linked IMSIs",
    "IMSI Count",
    "Source Files",
    "File Count",
    "Spot Count",
    "Total Sessions",
    "First Seen",
    "Last Seen",
    "Total Downlink Volume",
    "Total Uplink Volume",
    "Total Volume",
    "Unique IP Addresses",
    "Unique Cell IDs",
]

SIM_COLUMNS = [
    "IMSI",
    "Subscribers",
    "Subscriber Count",
    "Source Files",
    "File Count",
    "Spot Count",
    "Total Sessions",
    "First Seen",
    "Last Seen",
    "Total Volume",
]

IP_COLUMNS = [
    "IP Address",
    "IP Version",
    "Subscribers",
    "Subscriber Count",
    "Source Files",
    "Total Sessions",
    "First Seen",
    "Last Seen",
    "Total Volume",
]

NETWORK_COLUMNS = [
    "Technology",
    "Connection Type",
    "Roaming Circle",
    "ICR Operator",
    "Home Circle",
    "Subscribers",
    "Subscriber Count",
    "Total Sessions",
    "First Seen",
    "Last Seen",
    "Total Volume",
]

CELL_COLUMNS = [
    "Cell ID",
    "Latitude",
    "Longitude",
    "Subscribers",
    "Subscriber Count",
    "Source Files",
    "Spot Names",
    "Spot Count",
    "Total Sessions",
    "First Seen",
    "Last Seen",
    "Total Volume",
]

TIMELINE_COLUMNS = [
    "Session Start",
    "Session End",
    "Duration (Sec)",
    "Subscriber Number",
    "Raw Subscriber",
    "Identifier Type",
    "IMSI",
    "Raw IMSI",
    "IPv4 Address",
    "Raw IPv4",
    "IPv6 Address",
    "Raw IPv6",
    "Downlink Volume",
    "Uplink Volume",
    "Total Volume",
    "Technology",
    "Connection Type",
    "Roaming Circle",
    "ICR Operator",
    "Home Circle",
    "Cell ID",
    "CGI Latitude",
    "CGI Longitude",
    "Operator",
    "Source Format",
    "Source File",
    "Source Relative Path",
    "Spot ID",
    "Spot Name",
    "Spot Folder",
    "Source Row Number",
    "Raw IMEI",
    "Normalized IMEI",
]

REVIEW_COLUMNS = [
    "Indicator",
    "Observation",
    "Caution",
]

QUALITY_COLUMNS = [
    "Check",
    "Count",
    "Meaning",
]


def _empty_frame(
    columns: list[str],
) -> pd.DataFrame:
    return pd.DataFrame(
        columns=columns
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
        "session_count": 0,
        "matched_sessions": _empty_frame(
            TIMELINE_COLUMNS
        ),
        "summary": _empty_frame(
            SUMMARY_COLUMNS
        ),
        "associated_subscribers": _empty_frame(
            SUBSCRIBER_COLUMNS
        ),
        "associated_sims": _empty_frame(
            SIM_COLUMNS
        ),
        "ip_addresses": _empty_frame(
            IP_COLUMNS
        ),
        "technology_and_roaming": _empty_frame(
            NETWORK_COLUMNS
        ),
        "cells": _empty_frame(
            CELL_COLUMNS
        ),
        "timeline": _empty_frame(
            TIMELINE_COLUMNS
        ),
        "review_indicators": _empty_frame(
            REVIEW_COLUMNS
        ),
        "data_quality": _empty_frame(
            QUALITY_COLUMNS
        ),
    }


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
        _series(
            dataframe,
            names,
        )
        .astype("string")
        .fillna("")
        .str.strip()
    )


def _number(
    dataframe: pd.DataFrame,
    names: tuple[str, ...],
) -> pd.Series:
    return (
        pd.to_numeric(
            _series(
                dataframe,
                names,
                0,
            ),
            errors="coerce",
        )
        .fillna(0)
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


def _boolean(
    dataframe: pd.DataFrame,
    names: tuple[str, ...],
) -> pd.Series:
    value = _series(
        dataframe,
        names,
        False,
    )

    if pd.api.types.is_bool_dtype(
        value.dtype
    ):
        return value.fillna(False).astype(bool)

    return (
        value.astype("string")
        .fillna("")
        .str.strip()
        .str.lower()
        .isin(
            {
                "1",
                "true",
                "yes",
                "y",
            }
        )
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


def _combined_ip_count(
    group: pd.DataFrame,
) -> int:
    values = pd.concat(
        [
            group["_ipv4"],
            group["_ipv6"],
        ],
        ignore_index=True,
    )

    return _unique_count(
        values
    )


def _prepare_matches(
    dataframe: pd.DataFrame,
    requested_imei: str,
) -> pd.DataFrame:
    if (
        not isinstance(
            dataframe,
            pd.DataFrame,
        )
        or dataframe.empty
        or "imei" not in dataframe.columns
    ):
        return pd.DataFrame()

    source_imei = (
        dataframe["imei"]
        .astype("string")
        .fillna("")
        .str.strip()
    )

    normalized_imei = source_imei.map(
        normalize_imei
    )

    match_mask = normalized_imei.eq(
        requested_imei
    )

    if not match_mask.any():
        return pd.DataFrame()

    data = dataframe.loc[
        match_mask
    ].copy()

    # Internal calculations must not carry source DataFrame metadata.
    data.attrs = {}

    raw_imei = (
        _text(
            dataframe,
            (
                "imei_raw",
                "imei",
            ),
        )
        .loc[
            match_mask
        ]
    )

    data["_imei_raw"] = raw_imei.astype(
        str
    )

    data["_imei"] = (
        normalized_imei.loc[
            match_mask
        ]
        .astype(str)
    )

    data["_subscriber_raw"] = _text(
        data,
        (
            "subscriber_number_raw",
            "subscriber_number",
        ),
    )

    data["_subscriber"] = _text(
        data,
        (
            "subscriber_number",
        ),
    )

    data["_identifier_type"] = _text(
        data,
        (
            "identifier_type",
        ),
    )

    data["_imsi_raw"] = _text(
        data,
        (
            "imsi_raw",
            "imsi",
        ),
    )

    data["_imsi"] = _text(
        data,
        (
            "imsi",
        ),
    ).map(
        normalize_imsi
    )

    data["_ipv4_raw"] = _text(
        data,
        (
            "ipv4_address_raw",
            "ipv4_address",
        ),
    )

    data["_ipv4"] = _text(
        data,
        (
            "ipv4_address",
        ),
    )

    data["_ipv6_raw"] = _text(
        data,
        (
            "ipv6_address_raw",
            "ipv6_address",
        ),
    )

    data["_ipv6"] = _text(
        data,
        (
            "ipv6_address",
        ),
    )

    data["_session_start"] = _datetime(
        data,
        (
            "session_start",
        ),
    )

    data["_session_end"] = _datetime(
        data,
        (
            "session_end",
        ),
    )

    data["_duration"] = _number(
        data,
        (
            "session_duration_seconds",
        ),
    ).clip(
        lower=0
    )

    data["_downlink"] = _number(
        data,
        (
            "downlink_volume",
        ),
    )

    data["_uplink"] = _number(
        data,
        (
            "uplink_volume",
        ),
    )

    data["_total_volume"] = _number(
        data,
        (
            "total_volume",
        ),
    )

    data["_session_time_valid"] = _boolean(
        data,
        (
            "session_time_valid",
        ),
    )

    data["_volume_fields_present"] = _boolean(
        data,
        (
            "volume_fields_present",
        ),
    )

    data["_volume_mismatch"] = _boolean(
        data,
        (
            "volume_mismatch",
        ),
    )

    data["_is_zero_volume"] = _boolean(
        data,
        (
            "is_zero_volume",
        ),
    )

    text_columns = {
        "_record_type": (
            "record_type",
        ),
        "_source_format": (
            "source_format",
        ),
        "_operator": (
            "operator",
        ),
        "_pre_post": (
            "pre_post",
        ),
        "_roaming_circle": (
            "roaming_circle",
        ),
        "_technology": (
            "technology",
        ),
        "_icr_operator": (
            "icr_operator",
        ),
        "_home_circle": (
            "home_circle",
        ),
        "_cell": (
            "searched_cell_id",
        ),
        "_source_file": (
            "source_file",
        ),
        "_source_relative_path": (
            "source_relative_path",
        ),
        "_spot_id": (
            "spot_id",
        ),
        "_spot_name": (
            "spot_name",
        ),
        "_spot_folder": (
            "spot_folder",
        ),
    }

    for output_column, input_columns in text_columns.items():
        data[output_column] = _text(
            data,
            input_columns,
        )

    data["_cgi_latitude"] = _number(
        data,
        (
            "cgi_latitude",
        ),
    )

    data["_cgi_longitude"] = _number(
        data,
        (
            "cgi_longitude",
        ),
    )

    data["_source_row"] = _series(
        data,
        (
            "source_row_number",
        ),
        pd.NA,
    )

    return data


def _build_summary(
    data: pd.DataFrame,
    requested_imei: str,
) -> pd.DataFrame:
    starts = data[
        "_session_start"
    ].dropna()

    rows = [
        (
            "Requested IMEI / IMEISV",
            requested_imei,
        ),
        (
            "Identifier Length",
            len(
                requested_imei
            ),
        ),
        (
            "Matched GPRS Sessions",
            len(
                data
            ),
        ),
        (
            "Associated Subscribers",
            _unique_count(
                data[
                    "_subscriber"
                ]
            ),
        ),
        (
            "Associated IMSIs",
            _unique_count(
                data[
                    "_imsi"
                ]
            ),
        ),
        (
            "Source Files",
            _unique_count(
                data[
                    "_source_file"
                ]
            ),
        ),
        (
            "Tower Spots",
            _unique_count(
                data[
                    "_spot_id"
                ]
            ),
        ),
        (
            "IPv4 Addresses",
            _unique_count(
                data[
                    "_ipv4"
                ]
            ),
        ),
        (
            "IPv6 Addresses",
            _unique_count(
                data[
                    "_ipv6"
                ]
            ),
        ),
        (
            "Cell IDs",
            _unique_count(
                data[
                    "_cell"
                ]
            ),
        ),
        (
            "Technologies",
            _unique_count(
                data[
                    "_technology"
                ]
            ),
        ),
        (
            "First Seen",
            (
                starts.min()
                if not starts.empty
                else pd.NaT
            ),
        ),
        (
            "Last Seen",
            (
                starts.max()
                if not starts.empty
                else pd.NaT
            ),
        ),
        (
            "Total Duration (Sec)",
            int(
                data[
                    "_duration"
                ].sum()
            ),
        ),
        (
            "Total Downlink Volume",
            float(
                data[
                    "_downlink"
                ].sum()
            ),
        ),
        (
            "Total Uplink Volume",
            float(
                data[
                    "_uplink"
                ].sum()
            ),
        ),
        (
            "Total Volume",
            float(
                data[
                    "_total_volume"
                ].sum()
            ),
        ),
    ]

    return pd.DataFrame(
        rows,
        columns=SUMMARY_COLUMNS,
    )


def _build_subscribers(
    data: pd.DataFrame,
) -> pd.DataFrame:
    work = data.loc[
        data[
            "_subscriber"
        ].ne("")
    ].copy()

    if work.empty:
        return _empty_frame(
            SUBSCRIBER_COLUMNS
        )

    rows: list[dict[str, Any]] = []

    for (
        subscriber,
        identifier_type,
    ), group in work.groupby(
        [
            "_subscriber",
            "_identifier_type",
        ],
        dropna=False,
        sort=False,
    ):
        rows.append(
            {
                "Subscriber Number": subscriber,
                "Identifier Type": identifier_type,
                "Linked IMSIs": _join_unique(
                    group[
                        "_imsi"
                    ]
                ),
                "IMSI Count": _unique_count(
                    group[
                        "_imsi"
                    ]
                ),
                "Source Files": _join_unique(
                    group[
                        "_source_file"
                    ]
                ),
                "File Count": _unique_count(
                    group[
                        "_source_file"
                    ]
                ),
                "Spot Count": _unique_count(
                    group[
                        "_spot_id"
                    ]
                ),
                "Total Sessions": len(
                    group
                ),
                "First Seen": group[
                    "_session_start"
                ].min(),
                "Last Seen": group[
                    "_session_end"
                ].max(),
                "Total Downlink Volume": float(
                    group[
                        "_downlink"
                    ].sum()
                ),
                "Total Uplink Volume": float(
                    group[
                        "_uplink"
                    ].sum()
                ),
                "Total Volume": float(
                    group[
                        "_total_volume"
                    ].sum()
                ),
                "Unique IP Addresses": _combined_ip_count(
                    group
                ),
                "Unique Cell IDs": _unique_count(
                    group[
                        "_cell"
                    ]
                ),
            }
        )

    result = pd.DataFrame(
        rows,
        columns=SUBSCRIBER_COLUMNS,
    )

    return result.sort_values(
        [
            "Total Sessions",
            "Subscriber Number",
        ],
        ascending=[
            False,
            True,
        ],
        kind="stable",
    ).reset_index(
        drop=True
    )


def _build_sims(
    data: pd.DataFrame,
) -> pd.DataFrame:
    work = data.loc[
        data[
            "_imsi"
        ].ne("")
    ].copy()

    if work.empty:
        return _empty_frame(
            SIM_COLUMNS
        )

    rows: list[dict[str, Any]] = []

    for imsi, group in work.groupby(
        "_imsi",
        dropna=False,
        sort=False,
    ):
        rows.append(
            {
                "IMSI": imsi,
                "Subscribers": _join_unique(
                    group[
                        "_subscriber"
                    ]
                ),
                "Subscriber Count": _unique_count(
                    group[
                        "_subscriber"
                    ]
                ),
                "Source Files": _join_unique(
                    group[
                        "_source_file"
                    ]
                ),
                "File Count": _unique_count(
                    group[
                        "_source_file"
                    ]
                ),
                "Spot Count": _unique_count(
                    group[
                        "_spot_id"
                    ]
                ),
                "Total Sessions": len(
                    group
                ),
                "First Seen": group[
                    "_session_start"
                ].min(),
                "Last Seen": group[
                    "_session_end"
                ].max(),
                "Total Volume": float(
                    group[
                        "_total_volume"
                    ].sum()
                ),
            }
        )

    result = pd.DataFrame(
        rows,
        columns=SIM_COLUMNS,
    )

    return result.sort_values(
        [
            "Total Sessions",
            "IMSI",
        ],
        ascending=[
            False,
            True,
        ],
        kind="stable",
    ).reset_index(
        drop=True
    )


def _build_ip_addresses(
    data: pd.DataFrame,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for column, version in (
        (
            "_ipv4",
            "IPv4",
        ),
        (
            "_ipv6",
            "IPv6",
        ),
    ):
        work = data.loc[
            data[
                column
            ].ne("")
        ].copy()

        if work.empty:
            continue

        work["_ip_address"] = work[
            column
        ]

        work["_ip_version"] = version

        frames.append(
            work
        )

    if not frames:
        return _empty_frame(
            IP_COLUMNS
        )

    combined = pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )

    rows: list[dict[str, Any]] = []

    for (
        ip_address,
        ip_version,
    ), group in combined.groupby(
        [
            "_ip_address",
            "_ip_version",
        ],
        dropna=False,
        sort=False,
    ):
        rows.append(
            {
                "IP Address": ip_address,
                "IP Version": ip_version,
                "Subscribers": _join_unique(
                    group[
                        "_subscriber"
                    ]
                ),
                "Subscriber Count": _unique_count(
                    group[
                        "_subscriber"
                    ]
                ),
                "Source Files": _join_unique(
                    group[
                        "_source_file"
                    ]
                ),
                "Total Sessions": len(
                    group
                ),
                "First Seen": group[
                    "_session_start"
                ].min(),
                "Last Seen": group[
                    "_session_end"
                ].max(),
                "Total Volume": float(
                    group[
                        "_total_volume"
                    ].sum()
                ),
            }
        )

    result = pd.DataFrame(
        rows,
        columns=IP_COLUMNS,
    )

    return result.sort_values(
        [
            "Total Sessions",
            "IP Version",
            "IP Address",
        ],
        ascending=[
            False,
            True,
            True,
        ],
        kind="stable",
    ).reset_index(
        drop=True
    )


def _build_network_summary(
    data: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    grouped = data.groupby(
        [
            "_technology",
            "_pre_post",
            "_roaming_circle",
            "_icr_operator",
            "_home_circle",
        ],
        dropna=False,
        sort=False,
    )

    for keys, group in grouped:
        (
            technology,
            pre_post,
            roaming_circle,
            icr_operator,
            home_circle,
        ) = keys

        rows.append(
            {
                "Technology": technology,
                "Connection Type": pre_post,
                "Roaming Circle": roaming_circle,
                "ICR Operator": icr_operator,
                "Home Circle": home_circle,
                "Subscribers": _join_unique(
                    group[
                        "_subscriber"
                    ]
                ),
                "Subscriber Count": _unique_count(
                    group[
                        "_subscriber"
                    ]
                ),
                "Total Sessions": len(
                    group
                ),
                "First Seen": group[
                    "_session_start"
                ].min(),
                "Last Seen": group[
                    "_session_end"
                ].max(),
                "Total Volume": float(
                    group[
                        "_total_volume"
                    ].sum()
                ),
            }
        )

    result = pd.DataFrame(
        rows,
        columns=NETWORK_COLUMNS,
    )

    return result.sort_values(
        [
            "Total Sessions",
            "Technology",
        ],
        ascending=[
            False,
            True,
        ],
        kind="stable",
    ).reset_index(
        drop=True
    )


def _build_cells(
    data: pd.DataFrame,
) -> pd.DataFrame:
    work = data.loc[
        data[
            "_cell"
        ].ne("")
    ].copy()

    if work.empty:
        return _empty_frame(
            CELL_COLUMNS
        )

    rows: list[dict[str, Any]] = []

    for cell_id, group in work.groupby(
        "_cell",
        dropna=False,
        sort=False,
    ):
        latitude_values = group.loc[
            group[
                "_cgi_latitude"
            ].ne(0),
            "_cgi_latitude",
        ]

        longitude_values = group.loc[
            group[
                "_cgi_longitude"
            ].ne(0),
            "_cgi_longitude",
        ]

        rows.append(
            {
                "Cell ID": cell_id,
                "Latitude": (
                    latitude_values.iloc[0]
                    if not latitude_values.empty
                    else pd.NA
                ),
                "Longitude": (
                    longitude_values.iloc[0]
                    if not longitude_values.empty
                    else pd.NA
                ),
                "Subscribers": _join_unique(
                    group[
                        "_subscriber"
                    ]
                ),
                "Subscriber Count": _unique_count(
                    group[
                        "_subscriber"
                    ]
                ),
                "Source Files": _join_unique(
                    group[
                        "_source_file"
                    ]
                ),
                "Spot Names": _join_unique(
                    group[
                        "_spot_name"
                    ]
                ),
                "Spot Count": _unique_count(
                    group[
                        "_spot_id"
                    ]
                ),
                "Total Sessions": len(
                    group
                ),
                "First Seen": group[
                    "_session_start"
                ].min(),
                "Last Seen": group[
                    "_session_end"
                ].max(),
                "Total Volume": float(
                    group[
                        "_total_volume"
                    ].sum()
                ),
            }
        )

    result = pd.DataFrame(
        rows,
        columns=CELL_COLUMNS,
    )

    return result.sort_values(
        [
            "Total Sessions",
            "Cell ID",
        ],
        ascending=[
            False,
            True,
        ],
        kind="stable",
    ).reset_index(
        drop=True
    )


def _build_timeline(
    data: pd.DataFrame,
) -> pd.DataFrame:
    timeline = pd.DataFrame(
        {
            "Session Start": data[
                "_session_start"
            ],
            "Session End": data[
                "_session_end"
            ],
            "Duration (Sec)": data[
                "_duration"
            ].astype(int),
            "Subscriber Number": data[
                "_subscriber"
            ],
            "Raw Subscriber": data[
                "_subscriber_raw"
            ],
            "Identifier Type": data[
                "_identifier_type"
            ],
            "IMSI": data[
                "_imsi"
            ],
            "Raw IMSI": data[
                "_imsi_raw"
            ],
            "IPv4 Address": data[
                "_ipv4"
            ],
            "Raw IPv4": data[
                "_ipv4_raw"
            ],
            "IPv6 Address": data[
                "_ipv6"
            ],
            "Raw IPv6": data[
                "_ipv6_raw"
            ],
            "Downlink Volume": data[
                "_downlink"
            ],
            "Uplink Volume": data[
                "_uplink"
            ],
            "Total Volume": data[
                "_total_volume"
            ],
            "Technology": data[
                "_technology"
            ],
            "Connection Type": data[
                "_pre_post"
            ],
            "Roaming Circle": data[
                "_roaming_circle"
            ],
            "ICR Operator": data[
                "_icr_operator"
            ],
            "Home Circle": data[
                "_home_circle"
            ],
            "Cell ID": data[
                "_cell"
            ],
            "CGI Latitude": data[
                "_cgi_latitude"
            ],
            "CGI Longitude": data[
                "_cgi_longitude"
            ],
            "Operator": data[
                "_operator"
            ],
            "Source Format": data[
                "_source_format"
            ],
            "Source File": data[
                "_source_file"
            ],
            "Source Relative Path": data[
                "_source_relative_path"
            ],
            "Spot ID": data[
                "_spot_id"
            ],
            "Spot Name": data[
                "_spot_name"
            ],
            "Spot Folder": data[
                "_spot_folder"
            ],
            "Source Row Number": data[
                "_source_row"
            ],
            "Raw IMEI": data[
                "_imei_raw"
            ],
            "Normalized IMEI": data[
                "_imei"
            ],
        }
    )

    return timeline.sort_values(
        [
            "Session Start",
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
    ).reset_index(
        drop=True
    )


def _build_review_indicators(
    data: pd.DataFrame,
    requested_imei: str,
) -> pd.DataFrame:
    rows: list[dict[str, str]] = []

    subscriber_count = _unique_count(
        data[
            "_subscriber"
        ]
    )

    imsi_count = _unique_count(
        data[
            "_imsi"
        ]
    )

    file_count = _unique_count(
        data[
            "_source_file"
        ]
    )

    spot_count = _unique_count(
        data[
            "_spot_id"
        ]
    )

    mismatch_count = int(
        data[
            "_volume_mismatch"
        ].sum()
    )

    if subscriber_count > 1:
        rows.append(
            {
                "Indicator": (
                    "Device identifier linked to multiple subscribers"
                ),
                "Observation": (
                    f"The exact identifier appears with "
                    f"{subscriber_count} subscriber identifiers."
                ),
                "Caution": (
                    "Verify ownership periods, SIM changes, shared-device "
                    "use and duplicate records."
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
                    f"{imsi_count} normalized IMSIs."
                ),
                "Caution": (
                    "This can reflect SIM changes, dual-SIM handling, "
                    "different usage periods or data quality."
                ),
            }
        )

    if file_count > 1:
        rows.append(
            {
                "Indicator": (
                    "Evidence appears in multiple GPRS files"
                ),
                "Observation": (
                    f"Matching sessions occur in "
                    f"{file_count} source files."
                ),
                "Caution": (
                    "Check overlapping request periods and exact "
                    "duplicates before summing sessions or volume."
                ),
            }
        )

    if spot_count > 1:
        rows.append(
            {
                "Indicator": (
                    "Device identifier appears at multiple tower spots"
                ),
                "Observation": (
                    f"Matching sessions occur across "
                    f"{spot_count} configured tower spots."
                ),
                "Caution": (
                    "Verify session times, Cell IDs and tower locations "
                    "before interpreting movement."
                ),
            }
        )

    if mismatch_count:
        rows.append(
            {
                "Indicator": (
                    "Volume consistency warning"
                ),
                "Observation": (
                    f"{mismatch_count} matching session(s) contain "
                    "a downlink/uplink versus total-volume mismatch."
                ),
                "Caution": (
                    "Use the preserved raw volume fields and do not "
                    "silently correct operator evidence."
                ),
            }
        )

    if len(
        requested_imei
    ) == 16:
        rows.append(
            {
                "Indicator": (
                    "Exact 16-digit identifier retained"
                ),
                "Observation": (
                    "The complete normalized 16-digit value was searched."
                ),
                "Caution": (
                    "It was not silently truncated or merged with "
                    "a 15-digit IMEI."
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
                    "No configured multi-subscriber, multi-SIM, "
                    "multi-file or multi-spot condition was found."
                ),
                "Caution": (
                    "Absence of an indicator does not establish "
                    "ownership or normality."
                ),
            }
        )

    return pd.DataFrame(
        rows,
        columns=REVIEW_COLUMNS,
    )


def _build_data_quality(
    data: pd.DataFrame,
) -> pd.DataFrame:
    missing_ip = (
        data[
            "_ipv4"
        ].eq("")
        & data[
            "_ipv6"
        ].eq("")
    )

    rows = [
        (
            "Matched GPRS sessions",
            len(
                data
            ),
            "Rows matching the exact canonical identifier.",
        ),
        (
            "Invalid or missing session time",
            int(
                (
                    ~data[
                        "_session_time_valid"
                    ]
                ).sum()
            ),
            "Sessions not reliably placeable on the timeline.",
        ),
        (
            "Missing subscriber identifier",
            int(
                data[
                    "_subscriber"
                ].eq("").sum()
            ),
            "Sessions without a subscriber or user identifier.",
        ),
        (
            "Missing or invalid IMSI",
            int(
                data[
                    "_imsi"
                ].eq("").sum()
            ),
            "Sessions without a valid normalized SIM identity.",
        ),
        (
            "Missing IPv4 and IPv6",
            int(
                missing_ip.sum()
            ),
            "Sessions without a usable normalized IP address.",
        ),
        (
            "Missing Cell ID",
            int(
                data[
                    "_cell"
                ].eq("").sum()
            ),
            "Sessions without a searched Cell ID.",
        ),
        (
            "Missing volume fields",
            int(
                (
                    ~data[
                        "_volume_fields_present"
                    ]
                ).sum()
            ),
            "Sessions where complete volume evidence is unavailable.",
        ),
        (
            "Volume mismatch rows",
            int(
                data[
                    "_volume_mismatch"
                ].sum()
            ),
            "Downlink plus uplink does not match total within tolerance.",
        ),
        (
            "Zero-volume sessions",
            int(
                data[
                    "_is_zero_volume"
                ].sum()
            ),
            "Sessions with a reported total volume of zero.",
        ),
        (
            "16-digit matched sessions",
            int(
                data[
                    "_imei"
                ].str.len().eq(
                    16
                ).sum()
            ),
            "Exact 16-digit identifiers retained.",
        ),
    ]

    return pd.DataFrame(
        rows,
        columns=QUALITY_COLUMNS,
    )


def build_gprs_imei_investigation(
    dataframe: pd.DataFrame,
    requested_imei: Any,
) -> dict[str, Any]:
    """Search one exact IMEI or IMEISV in normalized GPRS sessions."""

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
                "No normalized GPRS DataFrame was provided."
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
                "in the loaded GPRS sessions."
            ),
        )

    timeline = _build_timeline(
        matches
    )

    return {
        "requested_imei": normalized_requested,
        "status": "FOUND",
        "message": (
            f"Found {len(matches)} matching GPRS session(s)."
        ),
        "session_count": len(
            matches
        ),
        "matched_sessions": timeline.copy(),
        "summary": _build_summary(
            matches,
            normalized_requested,
        ),
        "associated_subscribers": _build_subscribers(
            matches
        ),
        "associated_sims": _build_sims(
            matches
        ),
        "ip_addresses": _build_ip_addresses(
            matches
        ),
        "technology_and_roaming": _build_network_summary(
            matches
        ),
        "cells": _build_cells(
            matches
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
