
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import pandas as pd

from modules.analysis.cdr.tower_utils import (
    valid_cell_mask,
)


VALID_IDENTIFIER_LENGTHS = {
    14,
    15,
    16,
}


TIMELINE_COLUMNS = [
    "Event Time",
    "Allocation End",
    "Query Identifier",
    "Device Family",
    "Observed IMEI / IMEISV",
    "Subscriber / User ID",
    "IMSI",
    "Source IP",
    "Destination Endpoint",
    "Protocol",
    "Cell ID",
    "Source File",
    "Source Row Number",
    "Match Basis",
    "Match Relation",
]


INTERNAL_EVENT_COLUMNS = [
    *TIMELINE_COLUMNS,
    "CGI",
    "First Cell ID",
    "Last Cell ID",
]


DEVICE_OVERVIEW_COLUMNS = [
    "Query Identifier",
    "Identifier Type",
    "Device Family",
    "Analysis Status",
    "IPDR Records",
    "Observed IMEI / IMEISV",
    "Subscribers",
    "IMSIs",
    "Source IPs",
    "Destination Endpoints",
    "Valid Cells",
    "First Seen",
    "Last Seen",
    "Supported IPDR Acquisitions",
    "All Acquisitions",
]


REVIEW_COLUMNS = [
    "Indicator",
    "Shared Values",
    "Meaning",
    "Verification",
]


QUALITY_COLUMNS = [
    "Check",
    "Count",
    "Meaning",
]


def _digits(
    value: Any,
) -> str:
    return re.sub(
        r"\D",
        "",
        str(
            value or ""
        ),
    )


def _device_family(
    value: Any,
) -> str:
    digits = _digits(
        value
    )

    if len(
        digits
    ) not in VALID_IDENTIFIER_LENGTHS:
        return ""

    return digits[
        :14
    ]


def _identifier_type(
    value: Any,
) -> str:
    length = len(
        _digits(
            value
        )
    )

    return {
        14: "BASE14",
        15: "IMEI15",
        16: "IMEISV16",
    }.get(
        length,
        "UNKNOWN",
    )


def _text_series(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
) -> pd.Series:
    result = pd.Series(
        "",
        index=frame.index,
        dtype="string",
    )

    for column in columns:
        if column not in frame.columns:
            continue

        candidate = (
            frame[
                column
            ]
            .astype(
                "string"
            )
            .fillna(
                ""
            )
            .str.strip()
        )

        result = result.where(
            result.ne(
                ""
            ),
            candidate,
        )

    return result.astype(
        "string"
    )


def _datetime_series(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
) -> pd.Series:
    result = pd.Series(
        pd.NaT,
        index=frame.index,
        dtype="datetime64[ns]",
    )

    for column in columns:
        if column not in frame.columns:
            continue

        candidate = pd.to_datetime(
            frame[
                column
            ],
            errors="coerce",
            dayfirst=True,
        )

        result = result.where(
            result.notna(),
            candidate,
        )

    return result


def _source_row_series(
    frame: pd.DataFrame,
) -> pd.Series:
    for column in (
        "source_row_number",
        "raw_row_number",
        "row_number",
    ):
        if column in frame.columns:
            return frame[
                column
            ].copy()

    return pd.Series(
        pd.NA,
        index=frame.index,
        dtype="object",
    )


def _join_unique(
    values: pd.Series,
) -> str:
    return ", ".join(
        sorted(
            {
                str(
                    value
                ).strip()
                for value in values
                if str(
                    value
                ).strip()
            }
        )
    )


def _nunique_nonempty(
    values: pd.Series,
) -> int:
    return int(
        values
        .astype(
            "string"
        )
        .fillna(
            ""
        )
        .str.strip()
        .replace(
            "",
            pd.NA,
        )
        .dropna()
        .nunique()
    )


def _port_text(
    frame: pd.DataFrame,
) -> pd.Series:
    raw = _text_series(
        frame,
        (
            "destination_port",
            "public_port",
            "server_port",
        ),
    )

    numeric = pd.to_numeric(
        raw,
        errors="coerce",
    )

    whole_number = (
        numeric.notna()
        & numeric.mod(
            1
        ).eq(
            0
        )
    )

    result = raw.astype(
        "object"
    )

    result.loc[
        whole_number
    ] = (
        numeric.loc[
            whole_number
        ]
        .astype(
            "Int64"
        )
        .astype(
            "string"
        )
    )

    return result.astype(
        "string"
    )


def _destination_endpoint(
    destination_ip: pd.Series,
    destination_port: pd.Series,
) -> pd.Series:
    ip_values = (
        destination_ip
        .astype(
            "string"
        )
        .fillna(
            ""
        )
        .str.strip()
    )

    port_values = (
        destination_port
        .astype(
            "string"
        )
        .fillna(
            ""
        )
        .str.strip()
    )

    host = ip_values.copy()

    ipv6_mask = (
        host.ne(
            ""
        )
        & host.str.contains(
            ":",
            regex=False,
            na=False,
        )
    )

    host.loc[
        ipv6_mask
    ] = (
        "["
        + host.loc[
            ipv6_mask
        ]
        + "]"
    )

    endpoint = host.copy()

    with_port = (
        host.ne(
            ""
        )
        & port_values.ne(
            ""
        )
    )

    endpoint.loc[
        with_port
    ] = (
        host.loc[
            with_port
        ]
        + ":"
        + port_values.loc[
            with_port
        ]
    )

    endpoint.loc[
        host.eq(
            ""
        )
    ] = ""

    return endpoint.astype(
        "string"
    )


def _derived_match_basis(
    frame: pd.DataFrame,
    *,
    identifier: str,
    observed: pd.Series,
) -> pd.Series:
    provided = _text_series(
        frame,
        (
            "match_basis",
            "Match Basis",
        ),
    )

    query_scope = _text_series(
        frame,
        (
            "query_identifier_normalized",
            "query_identifier",
        ),
    )

    result = provided.copy()

    query_match = (
        result.eq(
            ""
        )
        & query_scope.eq(
            identifier
        )
    )

    result.loc[
        query_match
    ] = "QUERY_SCOPE"

    observed_match = (
        result.eq(
            ""
        )
        & observed.eq(
            identifier
        )
    )

    result.loc[
        observed_match
    ] = "OBSERVED_EXACT"

    result.loc[
        result.eq(
            ""
        )
    ] = "REPORT_SCOPE"

    return result.astype(
        "string"
    )


def _derived_match_relation(
    frame: pd.DataFrame,
    *,
    identifier: str,
    observed: pd.Series,
) -> pd.Series:
    provided = _text_series(
        frame,
        (
            "match_relation",
            "Match Relation",
        ),
    )

    result = provided.copy()

    exact_mask = (
        result.eq(
            ""
        )
        & observed.eq(
            identifier
        )
    )

    result.loc[
        exact_mask
    ] = "EXACT"

    identifier_family = _device_family(
        identifier
    )

    observed_family = (
        observed
        .astype(
            "string"
        )
        .fillna(
            ""
        )
        .str.replace(
            r"\D",
            "",
            regex=True,
        )
        .str.slice(
            0,
            14,
        )
    )

    same_family = (
        result.eq(
            ""
        )
        & observed.ne(
            ""
        )
        & observed_family.eq(
            identifier_family
        )
    )

    result.loc[
        same_family
    ] = "SAME_BASE14"

    result.loc[
        result.eq(
            ""
        )
        & observed.eq(
            ""
        )
    ] = "UNAVAILABLE"

    result.loc[
        result.eq(
            ""
        )
    ] = "REPORT_SCOPE"

    return result.astype(
        "string"
    )


def _prepare_events(
    device_frames: Mapping[
        str,
        pd.DataFrame,
    ],
) -> pd.DataFrame:
    frames: list[
        pd.DataFrame
    ] = []

    for raw_identifier, source in (
        device_frames.items()
    ):
        identifier = _digits(
            raw_identifier
        )

        if (
            len(
                identifier
            )
            not in VALID_IDENTIFIER_LENGTHS
            or not isinstance(
                source,
                pd.DataFrame,
            )
            or source.empty
        ):
            continue

        frame = source.copy(
            deep=True
        )

        observed = _text_series(
            frame,
            (
                "observed_imei_normalized",
                "imei",
                "observed_imei_raw",
            ),
        )

        destination_ip = _text_series(
            frame,
            (
                "destination_ip",
                "public_ip",
                "server_ip",
            ),
        )

        destination_port = _port_text(
            frame
        )

        cgi = _text_series(
            frame,
            (
                "cgi",
                "cell_id",
            ),
        )

        first_cell = _text_series(
            frame,
            (
                "first_cell_id",
                "first_cgi",
            ),
        )

        last_cell = _text_series(
            frame,
            (
                "last_cell_id",
                "last_cgi",
            ),
        )

        selected_cell = cgi.where(
            cgi.ne(
                ""
            ),
            first_cell,
        ).where(
            lambda values: values.ne(
                ""
            ),
            last_cell,
        )

        prepared = pd.DataFrame(
            {
                "Event Time": _datetime_series(
                    frame,
                    (
                        "event_time",
                        "session_start",
                        "allocation_start",
                        "start_time",
                    ),
                ),
                "Allocation End": _datetime_series(
                    frame,
                    (
                        "allocation_end",
                        "session_end",
                        "end_time",
                    ),
                ),
                "Query Identifier": identifier,
                "Device Family": _device_family(
                    identifier
                ),
                "Observed IMEI / IMEISV": observed,
                "Subscriber / User ID": _text_series(
                    frame,
                    (
                        "subscriber_number",
                        "subscriber_id",
                        "user_id",
                        "msisdn",
                        "target",
                    ),
                ),
                "IMSI": _text_series(
                    frame,
                    (
                        "imsi",
                    ),
                ),
                "Source IP": _text_series(
                    frame,
                    (
                        "source_ip",
                        "private_ip",
                        "ipv4_address",
                        "ipv6_address",
                    ),
                ),
                "Destination Endpoint": _destination_endpoint(
                    destination_ip,
                    destination_port,
                ),
                "Protocol": _text_series(
                    frame,
                    (
                        "protocol",
                        "transport_protocol",
                    ),
                ),
                "Cell ID": selected_cell,
                "Source File": _text_series(
                    frame,
                    (
                        "source_file",
                        "filename",
                    ),
                ),
                "Source Row Number": _source_row_series(
                    frame
                ),
                "Match Basis": _derived_match_basis(
                    frame,
                    identifier=identifier,
                    observed=observed,
                ),
                "Match Relation": _derived_match_relation(
                    frame,
                    identifier=identifier,
                    observed=observed,
                ),
                "CGI": cgi,
                "First Cell ID": first_cell,
                "Last Cell ID": last_cell,
            }
        )

        frames.append(
            prepared
        )

    if not frames:
        return pd.DataFrame(
            columns=INTERNAL_EVENT_COLUMNS
        )

    return pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )[
        INTERNAL_EVENT_COLUMNS
    ]


def _common_cell_mask(
    series: pd.Series,
) -> pd.Series:
    values = (
        series
        .astype(
            "string"
        )
        .fillna(
            ""
        )
        .str.strip()
    )

    if values.empty:
        return pd.Series(
            False,
            index=values.index,
            dtype="bool",
        )

    canonical_result = valid_cell_mask(
        values
    ).fillna(
        False
    )

    canonical_valid = pd.Series(
        canonical_result.to_numpy(
            dtype=bool,
            na_value=False,
        ),
        index=values.index,
        dtype="bool",
    )

    compact_digits = values.str.replace(
        r"\D",
        "",
        regex=True,
    )

    plmn_result = (
        compact_digits
        .str.fullmatch(
            r"(?:404|405)\d{2,3}",
            na=False,
        )
        .fillna(
            False
        )
    )

    plmn_only = pd.Series(
        plmn_result.to_numpy(
            dtype=bool,
            na_value=False,
        ),
        index=values.index,
        dtype="bool",
    )

    return (
        canonical_valid
        & ~plmn_only
    ).astype(
        "bool"
    )


def _cell_events(
    events: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "Cell ID",
        "Query Identifier",
        "Device Family",
        "Event Time",
        "Source File",
        "Source Row Number",
    ]

    frames = []

    for source_column in (
        "CGI",
        "First Cell ID",
        "Last Cell ID",
    ):
        if source_column not in events.columns:
            continue

        frame = events[
            [
                "Query Identifier",
                "Device Family",
                "Event Time",
                "Source File",
                "Source Row Number",
            ]
        ].copy()

        frame[
            "Cell ID"
        ] = (
            events[
                source_column
            ]
            .astype(
                "string"
            )
            .fillna(
                ""
            )
            .str.strip()
        )

        frame = frame.loc[
            frame[
                "Cell ID"
            ].ne(
                ""
            )
        ]

        if not frame.empty:
            frames.append(
                frame
            )

    if not frames:
        return pd.DataFrame(
            columns=columns
        )

    combined = pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )

    valid = _common_cell_mask(
        combined[
            "Cell ID"
        ]
    )

    combined = combined.loc[
        valid
    ]

    if combined.empty:
        return pd.DataFrame(
            columns=columns
        )

    return (
        combined[
            columns
        ]
        .drop_duplicates(
            subset=[
                "Cell ID",
                "Query Identifier",
                "Device Family",
                "Event Time",
                "Source File",
                "Source Row Number",
            ]
        )
        .reset_index(
            drop=True
        )
    )


def _empty_shared_summary(
    output_column: str,
) -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            output_column,
            "Device Family Count",
            "Query Identifiers",
            "Total Records",
            "First Seen",
            "Last Seen",
            "Source Files",
        ]
    )


def _shared_summary(
    events: pd.DataFrame,
    *,
    source_column: str,
    output_column: str,
) -> pd.DataFrame:
    columns = [
        output_column,
        "Device Family Count",
        "Query Identifiers",
        "Total Records",
        "First Seen",
        "Last Seen",
        "Source Files",
    ]

    if (
        events.empty
        or source_column not in events.columns
    ):
        return _empty_shared_summary(
            output_column
        )

    work = events.loc[
        events[
            source_column
        ]
        .astype(
            "string"
        )
        .fillna(
            ""
        )
        .str.strip()
        .ne(
            ""
        )
    ].copy()

    if work.empty:
        return _empty_shared_summary(
            output_column
        )

    result = (
        work.groupby(
            source_column,
            dropna=False,
        )
        .agg(
            **{
                "Device Family Count": (
                    "Device Family",
                    "nunique",
                ),
                "Query Identifiers": (
                    "Query Identifier",
                    _join_unique,
                ),
                "Total Records": (
                    "Query Identifier",
                    "size",
                ),
                "First Seen": (
                    "Event Time",
                    "min",
                ),
                "Last Seen": (
                    "Event Time",
                    "max",
                ),
                "Source Files": (
                    "Source File",
                    _join_unique,
                ),
            }
        )
        .reset_index()
        .rename(
            columns={
                source_column: output_column,
            }
        )
    )

    result = result.loc[
        result[
            "Device Family Count"
        ].ge(
            2
        )
    ]

    if result.empty:
        return _empty_shared_summary(
            output_column
        )

    return (
        result[
            columns
        ]
        .sort_values(
            [
                "Device Family Count",
                "Total Records",
                output_column,
            ],
            ascending=[
                False,
                False,
                True,
            ],
            kind="stable",
        )
        .reset_index(
            drop=True
        )
    )


def _manifest_text(
    manifest: pd.DataFrame,
    column: str,
) -> pd.Series:
    if column not in manifest.columns:
        return pd.Series(
            "",
            index=manifest.index,
            dtype="string",
        )

    return (
        manifest[
            column
        ]
        .astype(
            "string"
        )
        .fillna(
            ""
        )
        .str.strip()
    )


def _manifest_metrics(
    manifest: pd.DataFrame,
) -> dict[str, int]:
    if manifest.empty:
        return {
            "physical_acquisitions": 0,
            "all_content_groups": 0,
            "supported_ipdr_groups": 0,
            "non_ipdr_acquisitions": 0,
            "duplicate_ipdr_acquisitions": 0,
            "empty_ipdr_reports": 0,
        }

    sha_values = _manifest_text(
        manifest,
        "SHA-256",
    )

    source_types = _manifest_text(
        manifest,
        "Source Type",
    ).str.upper()

    statuses = _manifest_text(
        manifest,
        "Inspection Status",
    ).str.upper()

    analysis_roles = _manifest_text(
        manifest,
        "Analysis Content Role",
    ).str.upper()

    supported_mask = (
        source_types.eq(
            "IPDR"
        )
        & statuses.isin(
            {
                "HAS_DATA",
                "EMPTY_NO_DATA",
            }
        )
    )

    return {
        "physical_acquisitions": len(
            manifest
        ),
        "all_content_groups": int(
            sha_values
            .replace(
                "",
                pd.NA,
            )
            .dropna()
            .nunique()
        ),
        "supported_ipdr_groups": int(
            sha_values.loc[
                supported_mask
            ]
            .replace(
                "",
                pd.NA,
            )
            .dropna()
            .nunique()
        ),
        "non_ipdr_acquisitions": int(
            source_types.ne(
                "IPDR"
            ).sum()
        ),
        "duplicate_ipdr_acquisitions": int(
            (
                supported_mask
                & analysis_roles.eq(
                    "DUPLICATE_CONTENT"
                )
            ).sum()
        ),
        "empty_ipdr_reports": int(
            (
                source_types.eq(
                    "IPDR"
                )
                & statuses.eq(
                    "EMPTY_NO_DATA"
                )
            ).sum()
        ),
    }


def _device_overview(
    *,
    identifiers: list[str],
    events: pd.DataFrame,
    cells: pd.DataFrame,
    manifest: pd.DataFrame,
) -> pd.DataFrame:
    rows = []

    manifest_query = _manifest_text(
        manifest,
        "Query Identifier",
    )

    manifest_source_type = _manifest_text(
        manifest,
        "Source Type",
    ).str.upper()

    manifest_status = _manifest_text(
        manifest,
        "Inspection Status",
    ).str.upper()

    for identifier in identifiers:
        identifier_events = events.loc[
            events[
                "Query Identifier"
            ].eq(
                identifier
            )
        ]

        identifier_cells = cells.loc[
            cells[
                "Query Identifier"
            ].eq(
                identifier
            )
        ]

        acquisition_mask = manifest_query.eq(
            identifier
        )

        supported_mask = (
            acquisition_mask
            & manifest_source_type.eq(
                "IPDR"
            )
            & manifest_status.isin(
                {
                    "HAS_DATA",
                    "EMPTY_NO_DATA",
                }
            )
        )

        empty_report = bool(
            (
                acquisition_mask
                & manifest_source_type.eq(
                    "IPDR"
                )
                & manifest_status.eq(
                    "EMPTY_NO_DATA"
                )
            ).any()
        )

        if not identifier_events.empty:
            status = "FOUND"

        elif empty_report:
            status = "EMPTY_NO_DATA"

        else:
            status = "NO_DATA"

        event_times = identifier_events[
            "Event Time"
        ].dropna()

        rows.append(
            {
                "Query Identifier": identifier,
                "Identifier Type": _identifier_type(
                    identifier
                ),
                "Device Family": _device_family(
                    identifier
                ),
                "Analysis Status": status,
                "IPDR Records": len(
                    identifier_events
                ),
                "Observed IMEI / IMEISV": _join_unique(
                    identifier_events[
                        "Observed IMEI / IMEISV"
                    ]
                ),
                "Subscribers": _nunique_nonempty(
                    identifier_events[
                        "Subscriber / User ID"
                    ]
                ),
                "IMSIs": _nunique_nonempty(
                    identifier_events[
                        "IMSI"
                    ]
                ),
                "Source IPs": _nunique_nonempty(
                    identifier_events[
                        "Source IP"
                    ]
                ),
                "Destination Endpoints": _nunique_nonempty(
                    identifier_events[
                        "Destination Endpoint"
                    ]
                ),
                "Valid Cells": _nunique_nonempty(
                    identifier_cells[
                        "Cell ID"
                    ]
                ),
                "First Seen": (
                    event_times.min()
                    if not event_times.empty
                    else pd.NaT
                ),
                "Last Seen": (
                    event_times.max()
                    if not event_times.empty
                    else pd.NaT
                ),
                "Supported IPDR Acquisitions": int(
                    supported_mask.sum()
                ),
                "All Acquisitions": int(
                    acquisition_mask.sum()
                ),
            }
        )

    return pd.DataFrame(
        rows,
        columns=DEVICE_OVERVIEW_COLUMNS,
    )


def _invalid_cell_count(
    events: pd.DataFrame,
) -> int:
    candidates = []

    for column in (
        "CGI",
        "First Cell ID",
        "Last Cell ID",
    ):
        if column not in events.columns:
            continue

        values = (
            events[
                column
            ]
            .astype(
                "string"
            )
            .fillna(
                ""
            )
            .str.strip()
        )

        values = values.loc[
            values.ne(
                ""
            )
        ]

        if not values.empty:
            candidates.append(
                values
            )

    if not candidates:
        return 0

    combined = pd.concat(
        candidates,
        ignore_index=True,
    )

    valid = _common_cell_mask(
        combined
    )

    return int(
        (
            ~valid
        ).sum()
    )


def build_common_imei_ipdr_analysis(
    device_frames: Mapping[
        str,
        pd.DataFrame,
    ],
    acquisition_manifest: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Build cross-device IMEI IPDR evidence.

    Query identifiers, observed IMEI/IMEISV values and acquisition
    provenance remain separate. A value is common only when it occurs
    across at least two distinct 14-digit device-family keys.
    """

    if not isinstance(
        device_frames,
        Mapping,
    ):
        device_frames = {}

    identifiers = sorted(
        {
            identifier
            for identifier in (
                _digits(
                    value
                )
                for value in device_frames
            )
            if len(
                identifier
            )
            in VALID_IDENTIFIER_LENGTHS
        }
    )

    families = sorted(
        {
            family
            for family in (
                _device_family(
                    identifier
                )
                for identifier in identifiers
            )
            if family
        }
    )

    manifest = (
        acquisition_manifest.copy(
            deep=True
        )
        if isinstance(
            acquisition_manifest,
            pd.DataFrame,
        )
        else pd.DataFrame()
    )

    events = _prepare_events(
        device_frames
    )

    cells = _cell_events(
        events
    )

    metrics = _manifest_metrics(
        manifest
    )

    data_bearing_count = sum(
        1
        for identifier in identifiers
        if (
            isinstance(
                device_frames.get(
                    identifier
                ),
                pd.DataFrame,
            )
            and not device_frames[
                identifier
            ].empty
        )
    )

    base_result = {
        "device_count": len(
            identifiers
        ),
        "query_identifier_count": len(
            identifiers
        ),
        "device_family_count": len(
            families
        ),
        "data_bearing_device_count": int(
            data_bearing_count
        ),
        "empty_report_count": metrics[
            "empty_ipdr_reports"
        ],
        "device_overview": _device_overview(
            identifiers=identifiers,
            events=events,
            cells=cells,
            manifest=manifest,
        ),
        "acquisition_manifest": manifest,
    }

    if len(
        identifiers
    ) < 2:
        return {
            **base_result,
            "status": "NOT_APPLICABLE",
            "message": (
                "Common IMEI IPDR analysis requires at least "
                "two unique report-query identifiers."
            ),
            "common_subscribers": _empty_shared_summary(
                "Subscriber / User ID"
            ),
            "common_imsis": _empty_shared_summary(
                "IMSI"
            ),
            "common_destination_endpoints": (
                _empty_shared_summary(
                    "Destination Endpoint"
                )
            ),
            "common_source_ips": _empty_shared_summary(
                "Source IP"
            ),
            "common_cells": _empty_shared_summary(
                "Cell ID"
            ),
            "cross_device_timeline": events[
                TIMELINE_COLUMNS
            ].copy(),
            "review_indicators": pd.DataFrame(
                columns=REVIEW_COLUMNS
            ),
            "data_quality": pd.DataFrame(
                columns=QUALITY_COLUMNS
            ),
        }

    common_subscribers = _shared_summary(
        events,
        source_column="Subscriber / User ID",
        output_column="Subscriber / User ID",
    )

    common_imsis = _shared_summary(
        events,
        source_column="IMSI",
        output_column="IMSI",
    )

    common_destination_endpoints = _shared_summary(
        events,
        source_column="Destination Endpoint",
        output_column="Destination Endpoint",
    )

    common_source_ips = _shared_summary(
        events,
        source_column="Source IP",
        output_column="Source IP",
    )

    common_cells = _shared_summary(
        cells,
        source_column="Cell ID",
        output_column="Cell ID",
    )

    review_rows = []

    for label, frame in (
        (
            "Common subscribers",
            common_subscribers,
        ),
        (
            "Common IMSIs",
            common_imsis,
        ),
        (
            "Common destination endpoints",
            common_destination_endpoints,
        ),
        (
            "Common source IPs",
            common_source_ips,
        ),
        (
            "Common valid cells",
            common_cells,
        ),
    ):
        review_rows.append(
            {
                "Indicator": label,
                "Shared Values": len(
                    frame
                ),
                "Meaning": (
                    "Values appearing with at least two "
                    "distinct device families."
                ),
                "Verification": (
                    "Verify source rows, ownership periods, timestamps, "
                    "network translation context and duplicate-content status."
                ),
            }
        )

    data_quality = pd.DataFrame(
        [
            {
                "Check": "Unique query identifiers",
                "Count": len(
                    identifiers
                ),
                "Meaning": (
                    "Distinct report-query identifiers retained."
                ),
            },
            {
                "Check": "Unique device families",
                "Count": len(
                    families
                ),
                "Meaning": (
                    "Distinct first-14-digit device-family keys."
                ),
            },
            {
                "Check": "Data-bearing query identifiers",
                "Count": int(
                    data_bearing_count
                ),
                "Meaning": (
                    "Query identifiers containing normalized IPDR rows."
                ),
            },
            {
                "Check": "Valid empty IPDR reports",
                "Count": metrics[
                    "empty_ipdr_reports"
                ],
                "Meaning": (
                    "Recognized operator IPDR reports containing no rows."
                ),
            },
            {
                "Check": "Analytical IPDR rows",
                "Count": len(
                    events
                ),
                "Meaning": (
                    "Rows from supported unique IPDR content."
                ),
            },
            {
                "Check": "Missing event time",
                "Count": int(
                    events[
                        "Event Time"
                    ].isna().sum()
                ),
                "Meaning": (
                    "Rows not reliably placeable on the timeline."
                ),
            },
            {
                "Check": "Invalid or incomplete Cell IDs excluded",
                "Count": _invalid_cell_count(
                    events
                ),
                "Meaning": (
                    "Non-empty Cell IDs rejected by canonical validation."
                ),
            },
            {
                "Check": "Physical acquisitions",
                "Count": metrics[
                    "physical_acquisitions"
                ],
                "Meaning": (
                    "Every physical evidence path retained."
                ),
            },
            {
                "Check": "All acquisition SHA-256 groups",
                "Count": metrics[
                    "all_content_groups"
                ],
                "Meaning": (
                    "Unique content across every acquisition type."
                ),
            },
            {
                "Check": "Supported IPDR analytical content groups",
                "Count": metrics[
                    "supported_ipdr_groups"
                ],
                "Meaning": (
                    "Unique supported IPDR content eligible for analysis."
                ),
            },
            {
                "Check": "Non-IPDR acquisitions excluded",
                "Count": metrics[
                    "non_ipdr_acquisitions"
                ],
                "Meaning": (
                    "Files retained in the manifest but not analyzed as IPDR."
                ),
            },
            {
                "Check": "Duplicate IPDR acquisitions",
                "Count": metrics[
                    "duplicate_ipdr_acquisitions"
                ],
                "Meaning": (
                    "Physical IPDR copies preserved but analyzed once."
                ),
            },
        ],
        columns=QUALITY_COLUMNS,
    )

    timeline = (
        events[
            TIMELINE_COLUMNS
        ]
        .sort_values(
            [
                "Event Time",
                "Device Family",
                "Query Identifier",
                "Source File",
                "Source Row Number",
            ],
            kind="stable",
            na_position="last",
        )
        .reset_index(
            drop=True
        )
    )

    return {
        **base_result,
        "status": "FOUND",
        "message": (
            f"Common IMEI IPDR analysis completed across "
            f"{len(identifiers)} query identifier(s), "
            f"{len(families)} device family/families and "
            f"{data_bearing_count} data-bearing identifier(s)."
        ),
        "common_subscribers": common_subscribers,
        "common_imsis": common_imsis,
        "common_destination_endpoints": (
            common_destination_endpoints
        ),
        "common_source_ips": common_source_ips,
        "common_cells": common_cells,
        "cross_device_timeline": timeline,
        "review_indicators": pd.DataFrame(
            review_rows,
            columns=REVIEW_COLUMNS,
        ),
        "data_quality": data_quality,
    }
