"""Unified IMEI investigation across CDR, IPDR and GPRS evidence.

Source-specific calculations remain inside their tested analysis modules.
This module only coordinates results and builds common investigator views.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

import pandas as pd

from modules.analysis.cdr.imei_investigation import (
    build_imei_investigation,
)
from modules.analysis.gprsdump.imei_investigation import (
    build_gprs_imei_investigation,
)
from modules.analysis.ipdr.imei_investigation import (
    build_ipdr_imei_investigation,
)
from modules.loader.telecom_identifiers import normalize_imei


SOURCE_SUMMARY_COLUMNS = [
    "Evidence Source",
    "Status",
    "Evidence Unit",
    "Matched Count",
    "Message",
]

IDENTITY_COLUMNS = [
    "Evidence Source",
    "Identity Type",
    "Identity Value",
    "Related Identity",
    "First Seen",
    "Last Seen",
    "Matched Count",
]

TIMELINE_COLUMNS = [
    "Evidence Source",
    "Evidence Type",
    "Start Time",
    "End Time",
    "Target / Subscriber",
    "IMSI",
    "Contact / Endpoint",
    "IP Address",
    "Cell ID",
    "Source File",
    "Source Row Number",
    "Source Detail",
]

REVIEW_COLUMNS = [
    "Evidence Source",
    "Indicator",
    "Observation",
    "Caution",
]

QUALITY_COLUMNS = [
    "Evidence Source",
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


def _empty_source_result(
    *,
    status: str,
    message: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "timeline": pd.DataFrame(),
    }


def _empty_unified_bundle(
    requested_imei: str,
    *,
    status: str,
    message: str,
) -> dict[str, Any]:
    invalid_source = _empty_source_result(
        status=status,
        message=message,
    )

    return {
        "requested_imei": requested_imei,
        "overall_status": status,
        "message": message,
        "cdr": dict(invalid_source),
        "ipdr": dict(invalid_source),
        "gprs": dict(invalid_source),
        "source_summary": _empty_frame(
            SOURCE_SUMMARY_COLUMNS
        ),
        "associated_identities": _empty_frame(
            IDENTITY_COLUMNS
        ),
        "cross_source_timeline": _empty_frame(
            TIMELINE_COLUMNS
        ),
        "review_indicators": _empty_frame(
            REVIEW_COLUMNS
        ),
        "data_quality": _empty_frame(
            QUALITY_COLUMNS
        ),
    }


def _safe_source_call(
    *,
    source_name: str,
    provided: bool,
    builder: Callable[..., dict[str, Any]],
    arguments: tuple[Any, ...],
) -> dict[str, Any]:
    if not provided:
        return _empty_source_result(
            status="NO_INPUT",
            message=(
                f"No {source_name} input was provided."
            ),
        )

    try:
        result = builder(
            *arguments
        )

        if not isinstance(
            result,
            dict,
        ):
            raise TypeError(
                f"{source_name} IMEI builder returned "
                f"{type(result).__name__}, expected dict."
            )

        return result

    except Exception as error:
        return _empty_source_result(
            status="ERROR",
            message=(
                f"{type(error).__name__}: {error}"
            ),
        )


def _timeline(
    result: dict[str, Any],
) -> pd.DataFrame:
    value = result.get(
        "timeline"
    )

    return (
        value.copy()
        if isinstance(
            value,
            pd.DataFrame,
        )
        else pd.DataFrame()
    )


def _status(
    result: dict[str, Any],
) -> str:
    return str(
        result.get(
            "status",
            "ERROR",
        )
    ).strip().upper()


def _matched_count(
    result: dict[str, Any],
) -> int:
    timeline = result.get(
        "timeline"
    )

    return (
        len(
            timeline
        )
        if isinstance(
            timeline,
            pd.DataFrame,
        )
        else 0
    )


def _build_source_summary(
    sources: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    units = {
        "CDR": "CDR records",
        "IPDR": "IPDR records",
        "GPRS": "GPRS sessions",
    }

    rows = []

    for source_name in (
        "CDR",
        "IPDR",
        "GPRS",
    ):
        result = sources[
            source_name
        ]

        rows.append(
            {
                "Evidence Source": source_name,
                "Status": _status(
                    result
                ),
                "Evidence Unit": units[
                    source_name
                ],
                "Matched Count": _matched_count(
                    result
                ),
                "Message": str(
                    result.get(
                        "message",
                        "",
                    )
                ),
            }
        )

    return pd.DataFrame(
        rows,
        columns=SOURCE_SUMMARY_COLUMNS,
    )


def _text_column(
    dataframe: pd.DataFrame,
    column: str,
) -> pd.Series:
    if column not in dataframe.columns:
        return pd.Series(
            "",
            index=dataframe.index,
            dtype="string",
        )

    return (
        dataframe[
            column
        ]
        .astype("string")
        .fillna("")
        .str.strip()
    )


def _datetime_column(
    dataframe: pd.DataFrame,
    column: str,
) -> pd.Series:
    if column not in dataframe.columns:
        return pd.Series(
            pd.NaT,
            index=dataframe.index,
            dtype="datetime64[ns]",
        )

    return pd.to_datetime(
        dataframe[
            column
        ],
        errors="coerce",
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


def _append_identity_rows(
    rows: list[dict[str, Any]],
    *,
    source_name: str,
    dataframe: pd.DataFrame,
    primary_column: str,
    primary_type: str,
    primary_type_column: str | None,
    imsi_column: str,
    start_column: str,
    end_column: str,
) -> None:
    if dataframe.empty:
        return

    work = dataframe.copy()

    work["_primary"] = _text_column(
        work,
        primary_column,
    )

    work["_imsi"] = _text_column(
        work,
        imsi_column,
    )

    work["_start"] = _datetime_column(
        work,
        start_column,
    )

    work["_end"] = _datetime_column(
        work,
        end_column,
    )

    if work["_end"].isna().all():
        work["_end"] = work[
            "_start"
        ]

    if (
        primary_type_column
        and primary_type_column in work.columns
    ):
        work["_primary_type"] = _text_column(
            work,
            primary_type_column,
        )
    else:
        work["_primary_type"] = ""

    primary_work = work.loc[
        work[
            "_primary"
        ].ne("")
    ].copy()

    if not primary_work.empty:
        group_columns = [
            "_primary",
            "_primary_type",
        ]

        for keys, group in primary_work.groupby(
            group_columns,
            dropna=False,
            sort=False,
        ):
            identity_value, detected_type = keys

            identity_type = (
                f"{primary_type}_{detected_type}"
                if str(
                    detected_type
                ).strip()
                else primary_type
            )

            rows.append(
                {
                    "Evidence Source": source_name,
                    "Identity Type": identity_type,
                    "Identity Value": identity_value,
                    "Related Identity": _join_unique(
                        group[
                            "_imsi"
                        ]
                    ),
                    "First Seen": group[
                        "_start"
                    ].min(),
                    "Last Seen": group[
                        "_end"
                    ].max(),
                    "Matched Count": len(
                        group
                    ),
                }
            )

    imsi_work = work.loc[
        work[
            "_imsi"
        ].ne("")
    ].copy()

    if not imsi_work.empty:
        for imsi, group in imsi_work.groupby(
            "_imsi",
            dropna=False,
            sort=False,
        ):
            rows.append(
                {
                    "Evidence Source": source_name,
                    "Identity Type": "IMSI",
                    "Identity Value": imsi,
                    "Related Identity": _join_unique(
                        group[
                            "_primary"
                        ]
                    ),
                    "First Seen": group[
                        "_start"
                    ].min(),
                    "Last Seen": group[
                        "_end"
                    ].max(),
                    "Matched Count": len(
                        group
                    ),
                }
            )


def _build_associated_identities(
    cdr: dict[str, Any],
    ipdr: dict[str, Any],
    gprs: dict[str, Any],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    _append_identity_rows(
        rows,
        source_name="CDR",
        dataframe=_timeline(
            cdr
        ),
        primary_column="Target Number",
        primary_type="TARGET_MSISDN",
        primary_type_column=None,
        imsi_column="IMSI",
        start_column="Date-Time",
        end_column="Date-Time",
    )

    _append_identity_rows(
        rows,
        source_name="IPDR",
        dataframe=_timeline(
            ipdr
        ),
        primary_column="Subscriber / User ID",
        primary_type="SUBSCRIBER",
        primary_type_column="Identifier Type",
        imsi_column="IMSI",
        start_column="Event Time",
        end_column="Allocation End",
    )

    _append_identity_rows(
        rows,
        source_name="GPRS",
        dataframe=_timeline(
            gprs
        ),
        primary_column="Subscriber Number",
        primary_type="SUBSCRIBER",
        primary_type_column="Identifier Type",
        imsi_column="IMSI",
        start_column="Session Start",
        end_column="Session End",
    )

    if not rows:
        return _empty_frame(
            IDENTITY_COLUMNS
        )

    return (
        pd.DataFrame(
            rows,
            columns=IDENTITY_COLUMNS,
        )
        .sort_values(
            [
                "Evidence Source",
                "Identity Type",
                "Matched Count",
                "Identity Value",
            ],
            ascending=[
                True,
                True,
                False,
                True,
            ],
            kind="stable",
        )
        .reset_index(
            drop=True
        )
    )


def _cdr_timeline(
    result: dict[str, Any],
) -> pd.DataFrame:
    frame = _timeline(
        result
    )

    if frame.empty:
        return _empty_frame(
            TIMELINE_COLUMNS
        )

    return pd.DataFrame(
        {
            "Evidence Source": "CDR",
            "Evidence Type": "CDR Event",
            "Start Time": _datetime_column(
                frame,
                "Date-Time",
            ),
            "End Time": pd.NaT,
            "Target / Subscriber": _text_column(
                frame,
                "Target Number",
            ),
            "IMSI": _text_column(
                frame,
                "IMSI",
            ),
            "Contact / Endpoint": _text_column(
                frame,
                "Other Party",
            ),
            "IP Address": "",
            "Cell ID": _text_column(
                frame,
                "First Cell ID",
            ),
            "Source File": _text_column(
                frame,
                "Source File",
            ),
            "Source Row Number": (
                frame[
                    "Source Row Number"
                ]
                if "Source Row Number" in frame.columns
                else pd.NA
            ),
            "Source Detail": _text_column(
                frame,
                "Call Type",
            ),
        }
    )


def _ipdr_timeline(
    result: dict[str, Any],
) -> pd.DataFrame:
    frame = _timeline(
        result
    )

    if frame.empty:
        return _empty_frame(
            TIMELINE_COLUMNS
        )

    destination_ip = _text_column(
        frame,
        "Destination IP",
    )

    destination_port = _text_column(
        frame,
        "Destination Port",
    )

    endpoint = destination_ip.copy()

    both_present = (
        destination_ip.ne("")
        & destination_port.ne("")
    )

    endpoint.loc[
        both_present
    ] = (
        destination_ip.loc[
            both_present
        ]
        + ":"
        + destination_port.loc[
            both_present
        ]
    )

    endpoint.loc[
        destination_ip.eq("")
        & destination_port.ne("")
    ] = destination_port

    cell_id = _text_column(
        frame,
        "Cell ID",
    )

    first_cell = _text_column(
        frame,
        "First Cell ID",
    )

    cell_id = cell_id.where(
        cell_id.ne(""),
        first_cell,
    )

    return pd.DataFrame(
        {
            "Evidence Source": "IPDR",
            "Evidence Type": "IPDR Record",
            "Start Time": _datetime_column(
                frame,
                "Event Time",
            ),
            "End Time": _datetime_column(
                frame,
                "Allocation End",
            ),
            "Target / Subscriber": _text_column(
                frame,
                "Subscriber / User ID",
            ),
            "IMSI": _text_column(
                frame,
                "IMSI",
            ),
            "Contact / Endpoint": endpoint,
            "IP Address": _text_column(
                frame,
                "Source IP",
            ),
            "Cell ID": cell_id,
            "Source File": _text_column(
                frame,
                "Source File",
            ),
            "Source Row Number": (
                frame[
                    "Source Row Number"
                ]
                if "Source Row Number" in frame.columns
                else pd.NA
            ),
            "Source Detail": _text_column(
                frame,
                "Protocol",
            ),
        }
    )


def _gprs_timeline(
    result: dict[str, Any],
) -> pd.DataFrame:
    frame = _timeline(
        result
    )

    if frame.empty:
        return _empty_frame(
            TIMELINE_COLUMNS
        )

    ipv4 = _text_column(
        frame,
        "IPv4 Address",
    )

    ipv6 = _text_column(
        frame,
        "IPv6 Address",
    )

    ip_address = ipv4.where(
        ipv4.ne(""),
        ipv6,
    )

    return pd.DataFrame(
        {
            "Evidence Source": "GPRS",
            "Evidence Type": "GPRS Session",
            "Start Time": _datetime_column(
                frame,
                "Session Start",
            ),
            "End Time": _datetime_column(
                frame,
                "Session End",
            ),
            "Target / Subscriber": _text_column(
                frame,
                "Subscriber Number",
            ),
            "IMSI": _text_column(
                frame,
                "IMSI",
            ),
            "Contact / Endpoint": "",
            "IP Address": ip_address,
            "Cell ID": _text_column(
                frame,
                "Cell ID",
            ),
            "Source File": _text_column(
                frame,
                "Source File",
            ),
            "Source Row Number": (
                frame[
                    "Source Row Number"
                ]
                if "Source Row Number" in frame.columns
                else pd.NA
            ),
            "Source Detail": _text_column(
                frame,
                "Technology",
            ),
        }
    )


def _build_cross_source_timeline(
    cdr: dict[str, Any],
    ipdr: dict[str, Any],
    gprs: dict[str, Any],
) -> pd.DataFrame:
    frames = [
        frame
        for frame in (
            _cdr_timeline(
                cdr
            ),
            _ipdr_timeline(
                ipdr
            ),
            _gprs_timeline(
                gprs
            ),
        )
        if not frame.empty
    ]

    if not frames:
        return _empty_frame(
            TIMELINE_COLUMNS
        )

    return (
        pd.concat(
            frames,
            ignore_index=True,
            sort=False,
        )[
            TIMELINE_COLUMNS
        ]
        .sort_values(
            [
                "Start Time",
                "Evidence Source",
                "Source File",
                "Source Row Number",
            ],
            ascending=[
                True,
                True,
                True,
                True,
            ],
            kind="stable",
            na_position="last",
        )
        .reset_index(
            drop=True
        )
    )


def _build_review_indicators(
    sources: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    found_sources = [
        source_name
        for source_name, result in sources.items()
        if _status(
            result
        ) == "FOUND"
    ]

    if len(
        found_sources
    ) >= 2:
        frames.append(
            pd.DataFrame(
                [
                    {
                        "Evidence Source": "CROSS-SOURCE",
                        "Indicator": (
                            "Device identifier appears in multiple evidence sources"
                        ),
                        "Observation": (
                            "The exact identifier was found in: "
                            + ", ".join(
                                found_sources
                            )
                            + "."
                        ),
                        "Caution": (
                            "CDR records, IPDR records and GPRS sessions "
                            "are different evidence types and must not be "
                            "combined into one event total."
                        ),
                    }
                ],
                columns=REVIEW_COLUMNS,
            )
        )

    for source_name, result in sources.items():
        value = result.get(
            "review_indicators"
        )

        if (
            not isinstance(
                value,
                pd.DataFrame,
            )
            or value.empty
        ):
            continue

        required = [
            "Indicator",
            "Observation",
            "Caution",
        ]

        if not all(
            column in value.columns
            for column in required
        ):
            continue

        frame = value[
            required
        ].copy()

        frame.insert(
            0,
            "Evidence Source",
            source_name,
        )

        frames.append(
            frame
        )

    if not frames:
        return _empty_frame(
            REVIEW_COLUMNS
        )

    return pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )[
        REVIEW_COLUMNS
    ]


def _build_data_quality(
    sources: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for source_name, result in sources.items():
        value = result.get(
            "data_quality"
        )

        if (
            not isinstance(
                value,
                pd.DataFrame,
            )
            or value.empty
        ):
            continue

        required = [
            "Check",
            "Count",
            "Meaning",
        ]

        if not all(
            column in value.columns
            for column in required
        ):
            continue

        frame = value[
            required
        ].copy()

        frame.insert(
            0,
            "Evidence Source",
            source_name,
        )

        frames.append(
            frame
        )

    if not frames:
        return _empty_frame(
            QUALITY_COLUMNS
        )

    return pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )[
        QUALITY_COLUMNS
    ]


def _overall_status(
    sources: dict[str, dict[str, Any]],
) -> str:
    statuses = {
        _status(
            result
        )
        for result in sources.values()
    }

    found = "FOUND" in statuses
    error = "ERROR" in statuses

    if found and error:
        return "PARTIAL"

    if found:
        return "FOUND"

    if error:
        return "ERROR"

    if statuses == {
        "NO_INPUT"
    }:
        return "NO_INPUT"

    if "NOT_FOUND" in statuses:
        return "NOT_FOUND"

    return "NO_INPUT"


def build_unified_imei_investigation(
    requested_imei: Any,
    *,
    loaded_cdrs: Mapping[str, Any] | None = None,
    ipdr_dataframe: pd.DataFrame | None = None,
    gprs_dataframe: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Run exact IMEI investigation across available evidence sources."""

    normalized_requested = normalize_imei(
        requested_imei
    )

    if not normalized_requested:
        return _empty_unified_bundle(
            "",
            status="INVALID_IMEI",
            message=(
                "Enter a valid 15- or 16-digit IMEI/IMEISV."
            ),
        )

    cdr_result = _safe_source_call(
        source_name="CDR",
        provided=loaded_cdrs is not None,
        builder=build_imei_investigation,
        arguments=(
            loaded_cdrs,
            normalized_requested,
        ),
    )

    ipdr_result = _safe_source_call(
        source_name="IPDR",
        provided=ipdr_dataframe is not None,
        builder=build_ipdr_imei_investigation,
        arguments=(
            ipdr_dataframe,
            normalized_requested,
        ),
    )

    gprs_result = _safe_source_call(
        source_name="GPRS",
        provided=gprs_dataframe is not None,
        builder=build_gprs_imei_investigation,
        arguments=(
            gprs_dataframe,
            normalized_requested,
        ),
    )

    sources = {
        "CDR": cdr_result,
        "IPDR": ipdr_result,
        "GPRS": gprs_result,
    }

    overall_status = _overall_status(
        sources
    )

    found_sources = [
        source_name
        for source_name, result in sources.items()
        if _status(
            result
        ) == "FOUND"
    ]

    if found_sources:
        message = (
            "Exact IMEI/IMEISV found in: "
            + ", ".join(
                found_sources
            )
            + "."
        )

    elif overall_status == "NOT_FOUND":
        message = (
            "The exact IMEI/IMEISV was not found "
            "in the provided evidence sources."
        )

    elif overall_status == "NO_INPUT":
        message = (
            "No CDR, IPDR or GPRS input was provided."
        )

    elif overall_status == "ERROR":
        message = (
            "One or more source analyses failed."
        )

    else:
        message = (
            "IMEI investigation completed with partial source errors."
        )

    return {
        "requested_imei": normalized_requested,
        "overall_status": overall_status,
        "message": message,
        "cdr": cdr_result,
        "ipdr": ipdr_result,
        "gprs": gprs_result,
        "source_summary": _build_source_summary(
            sources
        ),
        "associated_identities": _build_associated_identities(
            cdr_result,
            ipdr_result,
            gprs_result,
        ),
        "cross_source_timeline": _build_cross_source_timeline(
            cdr_result,
            ipdr_result,
            gprs_result,
        ),
        "review_indicators": _build_review_indicators(
            sources
        ),
        "data_quality": _build_data_quality(
            sources
        ),
    }
