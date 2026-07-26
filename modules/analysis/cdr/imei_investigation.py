"""Cross-CDR IMEI investigation.

This module searches an exact canonical IMEI or IMEISV across already-loaded
CDR targets. It does not reload source files and does not modify raw evidence.
"""

from __future__ import annotations

import re

from collections.abc import Mapping
from typing import Any

import pandas as pd

from modules.loader.telecom_identifiers import (
    normalize_imei,
    normalize_imsi,
)

from .contact_classifier import classify_contact
from .datetime_utils import canonical_datetime
from .tower_utils import valid_cell_mask


SUMMARY_COLUMNS = [
    "Metric",
    "Value",
]

TARGET_COLUMNS = [
    "Target Number",
    "Source File",
    "Total Events",
    "First Seen",
    "Last Seen",
    "Unique IMSIs",
    "Unique Human Contacts",
    "Unique Valid Towers",
    "Total Duration (Sec)",
]

SIM_COLUMNS = [
    "IMSI",
    "Linked Targets",
    "Target Count",
    "Total Events",
    "First Seen",
    "Last Seen",
]

CONTACT_COLUMNS = [
    "Contact",
    "Linked Targets",
    "Target Count",
    "Total Events",
    "Incoming",
    "Outgoing",
    "SMS",
    "Total Duration (Sec)",
    "First Seen",
    "Last Seen",
]

TOWER_COLUMNS = [
    "Cell ID",
    "Linked Targets",
    "Target Count",
    "Total Events",
    "Unique Human Contacts",
    "First Seen",
    "Last Seen",
]

TIMELINE_COLUMNS = [
    "Target Number",
    "Source File",
    "Date-Time",
    "Call Type",
    "Other Party",
    "Contact Category",
    "Duration (Sec)",
    "IMSI",
    "First Cell ID",
    "Last Cell ID",
    "Raw IMEI",
    "Normalized IMEI",
    "Source Row Number",
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



def _normalize_requested_device_identifier(
    value: Any,
) -> str:
    """Normalize an explicit report-query or observed device identifier."""

    digits = re.sub(
        r"\D",
        "",
        str(
            value or ""
        ),
    )

    return (
        digits
        if len(
            digits
        )
        in {
            14,
            15,
            16,
        }
        else ""
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
        "matched_events": _empty_frame(
            TIMELINE_COLUMNS
        ),
        "summary": _empty_frame(
            SUMMARY_COLUMNS
        ),
        "associated_targets": _empty_frame(
            TARGET_COLUMNS
        ),
        "associated_sims": _empty_frame(
            SIM_COLUMNS
        ),
        "contacts": _empty_frame(
            CONTACT_COLUMNS
        ),
        "towers": _empty_frame(
            TOWER_COLUMNS
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


def _extract_dataframe(
    value: Any,
) -> pd.DataFrame | None:
    if isinstance(
        value,
        pd.DataFrame,
    ):
        return value

    if isinstance(
        value,
        Mapping,
    ):
        dataframe = value.get(
            "df"
        )

        if isinstance(
            dataframe,
            pd.DataFrame,
        ):
            return dataframe

    return None


def _source_label(
    value: Any,
    target: str,
) -> str:
    if isinstance(
        value,
        Mapping,
    ):
        for key in (
            "source_file",
            "file_name",
            "filename",
            "file_path",
            "input_file",
            "source_path",
        ):
            candidate = value.get(
                key
            )

            if candidate is None:
                continue

            text = str(
                candidate
            ).strip()

            if text:
                return text

    return f"Loaded CDR: {target}"


def _join_unique(
    values: pd.Series,
) -> str:
    return ", ".join(
        sorted(
            {
                str(
                    value
                ).strip()
                for value in values.dropna()
                if str(
                    value
                ).strip()
            }
        )
    )


def _prepare_target_events(
    *,
    target: str,
    value: Any,
    requested_imei: str,
) -> pd.DataFrame:
    dataframe = _extract_dataframe(
        value
    )

    if (
        dataframe is None
        or dataframe.empty
        or "imei" not in dataframe.columns
    ):
        return pd.DataFrame()

    raw_imei = (
        dataframe[
            "imei"
        ]
        .astype(
            "string"
        )
        .fillna(
            ""
        )
        .str.strip()
    )

    normalized_imei = raw_imei.map(
        normalize_imei
    )

    query_identifier = pd.Series(
        "",
        index=dataframe.index,
        dtype="string",
    )

    for query_column in (
        "query_identifier_normalized",
        "query_identifier_raw",
    ):
        if query_column not in dataframe.columns:
            continue

        candidate = (
            dataframe[
                query_column
            ]
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
        )

        query_identifier = query_identifier.where(
            query_identifier.ne(
                ""
            ),
            candidate,
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

    match_basis.loc[
        exact_observed_match
    ] = "EXACT_OBSERVED"

    if "match_relation" in dataframe.columns:
        match_relation = (
            dataframe[
                "match_relation"
            ]
            .astype(
                "string"
            )
            .fillna(
                ""
            )
            .str.strip()
            .str.upper()
        )

    else:
        match_relation = pd.Series(
            "",
            index=dataframe.index,
            dtype="string",
        )

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

    match_relation = match_relation.where(
        match_relation.ne(
            ""
        ),
        fallback_relation,
    )

    data = dataframe.loc[
        match_mask
    ].copy()

    # Internal calculations must not carry source DataFrame metadata.
    data.attrs = {}

    data[
        "_target"
    ] = str(
        target
    ).strip()

    fallback_source = _source_label(
        value,
        target,
    )

    if "source_file" in data.columns:
        row_source = (
            data[
                "source_file"
            ]
            .astype(
                "string"
            )
            .fillna(
                ""
            )
            .str.strip()
        )

        data[
            "_source_file"
        ] = row_source.where(
            row_source.ne(
                ""
            ),
            fallback_source,
        )

    else:
        data[
            "_source_file"
        ] = fallback_source

    data[
        "_imei_raw"
    ] = raw_imei.loc[
        match_mask
    ].astype(
        str
    )

    data[
        "_imei_normalized"
    ] = normalized_imei.loc[
        match_mask
    ].astype(
        str
    )

    data[
        "_query_identifier"
    ] = query_identifier.loc[
        match_mask
    ].astype(
        str
    )

    data[
        "_match_basis"
    ] = match_basis.loc[
        match_mask
    ].astype(
        str
    )

    data[
        "_match_relation"
    ] = match_relation.loc[
        match_mask
    ].astype(
        str
    )

    data[
        "_event_datetime"
    ] = canonical_datetime(
        data
    )

    if "call_duration" in data.columns:
        data[
            "_duration"
        ] = (
            pd.to_numeric(
                data[
                    "call_duration"
                ],
                errors="coerce",
            )
            .fillna(
                0
            )
            .clip(
                lower=0
            )
        )
    else:
        data[
            "_duration"
        ] = 0

    if "imsi" in data.columns:
        imsi_text = (
            data[
                "imsi"
            ]
            .astype(
                "string"
            )
            .fillna(
                ""
            )
            .str.strip()
        )

        data[
            "_imsi"
        ] = imsi_text.map(
            normalize_imsi
        )
    else:
        data[
            "_imsi"
        ] = ""

    if "b_party" in data.columns:
        data[
            "_contact"
        ] = (
            data[
                "b_party"
            ]
            .astype(
                "string"
            )
            .fillna(
                ""
            )
            .str.strip()
        )
    else:
        data[
            "_contact"
        ] = ""

    data[
        "_contact_category"
    ] = data[
        "_contact"
    ].map(
        classify_contact
    )

    data[
        "_human_contact"
    ] = data[
        "_contact"
    ].where(
        data[
            "_contact_category"
        ].eq(
            "human_mobile"
        ),
        "",
    )

    if "call_type" in data.columns:
        data[
            "_call_type"
        ] = (
            data[
                "call_type"
            ]
            .astype(
                "string"
            )
            .fillna(
                "unknown"
            )
            .str.lower()
            .str.strip()
        )
    else:
        data[
            "_call_type"
        ] = "unknown"

    data[
        "_is_sms"
    ] = data[
        "_call_type"
    ].str.contains(
        "sms",
        na=False,
    )

    data[
        "_is_incoming"
    ] = data[
        "_call_type"
    ].isin(
        {
            "incoming",
            "incoming_call",
            "incoming voice",
            "smsin",
            "incoming_sms",
        }
    )

    data[
        "_is_outgoing"
    ] = data[
        "_call_type"
    ].isin(
        {
            "outgoing",
            "outgoing_call",
            "outgoing voice",
            "smsout",
            "outgoing_sms",
        }
    )

    if "first_cell_id" in data.columns:
        first_cell = (
            data[
                "first_cell_id"
            ]
            .astype(
                "string"
            )
            .fillna(
                ""
            )
            .str.strip()
        )

        data[
            "_valid_first_cell"
        ] = first_cell.where(
            valid_cell_mask(
                first_cell
            ),
            "",
        )
    else:
        data[
            "_valid_first_cell"
        ] = ""

    if "last_cell_id" in data.columns:
        last_cell = (
            data[
                "last_cell_id"
            ]
            .astype(
                "string"
            )
            .fillna(
                ""
            )
            .str.strip()
        )

        data[
            "_valid_last_cell"
        ] = last_cell.where(
            valid_cell_mask(
                last_cell
            ),
            "",
        )
    else:
        data[
            "_valid_last_cell"
        ] = ""

    if "source_row_number" in data.columns:
        data[
            "_source_row_number"
        ] = data[
            "source_row_number"
        ]
    else:
        data[
            "_source_row_number"
        ] = pd.NA

    return data


def _build_summary(
    events: pd.DataFrame,
    requested_imei: str,
) -> pd.DataFrame:
    valid_datetimes = events[
        "_event_datetime"
    ].dropna()

    first_seen = (
        valid_datetimes.min()
        if not valid_datetimes.empty
        else pd.NaT
    )

    last_seen = (
        valid_datetimes.max()
        if not valid_datetimes.empty
        else pd.NaT
    )

    values = [
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
            "Total Matched Events",
            len(
                events
            ),
        ),
        (
            "Linked Target Numbers",
            events[
                "_target"
            ].nunique(),
        ),
        (
            "Source CDR Files",
            events[
                "_source_file"
            ].nunique(),
        ),
        (
            "Associated IMSIs",
            events[
                "_imsi"
            ]
            .replace(
                "",
                pd.NA,
            )
            .dropna()
            .nunique(),
        ),
        (
            "Unique Human Contacts",
            events[
                "_human_contact"
            ]
            .replace(
                "",
                pd.NA,
            )
            .dropna()
            .nunique(),
        ),
        (
            "Unique Valid First Towers",
            events[
                "_valid_first_cell"
            ]
            .replace(
                "",
                pd.NA,
            )
            .dropna()
            .nunique(),
        ),
        (
            "First Seen",
            first_seen,
        ),
        (
            "Last Seen",
            last_seen,
        ),
        (
            "Total Duration (Sec)",
            int(
                events[
                    "_duration"
                ].sum()
            ),
        ),
    ]

    return pd.DataFrame(
        values,
        columns=SUMMARY_COLUMNS,
    )


def _build_target_summary(
    events: pd.DataFrame,
) -> pd.DataFrame:
    result = (
        events.groupby(
            [
                "_target",
                "_source_file",
            ],
            dropna=False,
        )
        .agg(
            **{
                "Total Events": (
                    "_imei_normalized",
                    "size",
                ),
                "First Seen": (
                    "_event_datetime",
                    "min",
                ),
                "Last Seen": (
                    "_event_datetime",
                    "max",
                ),
                "Unique IMSIs": (
                    "_imsi",
                    lambda values: (
                        values.replace(
                            "",
                            pd.NA,
                        )
                        .dropna()
                        .nunique()
                    ),
                ),
                "Unique Human Contacts": (
                    "_human_contact",
                    lambda values: (
                        values.replace(
                            "",
                            pd.NA,
                        )
                        .dropna()
                        .nunique()
                    ),
                ),
                "Unique Valid Towers": (
                    "_valid_first_cell",
                    lambda values: (
                        values.replace(
                            "",
                            pd.NA,
                        )
                        .dropna()
                        .nunique()
                    ),
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
                "_target": "Target Number",
                "_source_file": "Source File",
            }
        )
    )

    result[
        "Total Duration (Sec)"
    ] = result[
        "Total Duration (Sec)"
    ].astype(
        int
    )

    return result[
        TARGET_COLUMNS
    ].sort_values(
        [
            "Total Events",
            "Target Number",
        ],
        ascending=[
            False,
            True,
        ],
        kind="stable",
    ).reset_index(
        drop=True
    )


def _build_sim_summary(
    events: pd.DataFrame,
) -> pd.DataFrame:
    sims = events.loc[
        events[
            "_imsi"
        ].astype(
            str
        ).str.strip().ne(
            ""
        )
    ].copy()

    if sims.empty:
        return _empty_frame(
            SIM_COLUMNS
        )

    result = (
        sims.groupby(
            "_imsi",
            dropna=False,
        )
        .agg(
            **{
                "Linked Targets": (
                    "_target",
                    _join_unique,
                ),
                "Target Count": (
                    "_target",
                    "nunique",
                ),
                "Total Events": (
                    "_imei_normalized",
                    "size",
                ),
                "First Seen": (
                    "_event_datetime",
                    "min",
                ),
                "Last Seen": (
                    "_event_datetime",
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

    return result[
        SIM_COLUMNS
    ].sort_values(
        [
            "Total Events",
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


def _build_contact_summary(
    events: pd.DataFrame,
) -> pd.DataFrame:
    contacts = events.loc[
        events[
            "_contact_category"
        ].eq(
            "human_mobile"
        )
        & events[
            "_contact"
        ].astype(
            str
        ).str.strip().ne(
            ""
        )
    ].copy()

    if contacts.empty:
        return _empty_frame(
            CONTACT_COLUMNS
        )

    contacts[
        "_incoming_count"
    ] = contacts[
        "_is_incoming"
    ].astype(
        int
    )

    contacts[
        "_outgoing_count"
    ] = contacts[
        "_is_outgoing"
    ].astype(
        int
    )

    contacts[
        "_sms_count"
    ] = contacts[
        "_is_sms"
    ].astype(
        int
    )

    result = (
        contacts.groupby(
            "_contact",
            dropna=False,
        )
        .agg(
            **{
                "Linked Targets": (
                    "_target",
                    _join_unique,
                ),
                "Target Count": (
                    "_target",
                    "nunique",
                ),
                "Total Events": (
                    "_imei_normalized",
                    "size",
                ),
                "Incoming": (
                    "_incoming_count",
                    "sum",
                ),
                "Outgoing": (
                    "_outgoing_count",
                    "sum",
                ),
                "SMS": (
                    "_sms_count",
                    "sum",
                ),
                "Total Duration (Sec)": (
                    "_duration",
                    "sum",
                ),
                "First Seen": (
                    "_event_datetime",
                    "min",
                ),
                "Last Seen": (
                    "_event_datetime",
                    "max",
                ),
            }
        )
        .reset_index()
        .rename(
            columns={
                "_contact": "Contact",
            }
        )
    )

    for column in (
        "Incoming",
        "Outgoing",
        "SMS",
        "Total Duration (Sec)",
    ):
        result[
            column
        ] = result[
            column
        ].astype(
            int
        )

    return result[
        CONTACT_COLUMNS
    ].sort_values(
        [
            "Total Events",
            "Total Duration (Sec)",
            "Contact",
        ],
        ascending=[
            False,
            False,
            True,
        ],
        kind="stable",
    ).reset_index(
        drop=True
    )


def _build_tower_summary(
    events: pd.DataFrame,
) -> pd.DataFrame:
    towers = events.loc[
        events[
            "_valid_first_cell"
        ].astype(
            str
        ).str.strip().ne(
            ""
        )
    ].copy()

    if towers.empty:
        return _empty_frame(
            TOWER_COLUMNS
        )

    result = (
        towers.groupby(
            "_valid_first_cell",
            dropna=False,
        )
        .agg(
            **{
                "Linked Targets": (
                    "_target",
                    _join_unique,
                ),
                "Target Count": (
                    "_target",
                    "nunique",
                ),
                "Total Events": (
                    "_imei_normalized",
                    "size",
                ),
                "Unique Human Contacts": (
                    "_human_contact",
                    lambda values: (
                        values.replace(
                            "",
                            pd.NA,
                        )
                        .dropna()
                        .nunique()
                    ),
                ),
                "First Seen": (
                    "_event_datetime",
                    "min",
                ),
                "Last Seen": (
                    "_event_datetime",
                    "max",
                ),
            }
        )
        .reset_index()
        .rename(
            columns={
                "_valid_first_cell": "Cell ID",
            }
        )
    )

    return result[
        TOWER_COLUMNS
    ].sort_values(
        [
            "Total Events",
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
    events: pd.DataFrame,
) -> pd.DataFrame:
    timeline = pd.DataFrame(
        {
            "Target Number": events[
                "_target"
            ],
            "Source File": events[
                "_source_file"
            ],
            "Date-Time": events[
                "_event_datetime"
            ],
            "Call Type": events[
                "_call_type"
            ],
            "Other Party": events[
                "_contact"
            ],
            "Contact Category": events[
                "_contact_category"
            ],
            "Duration (Sec)": events[
                "_duration"
            ],
            "IMSI": events[
                "_imsi"
            ],
            "First Cell ID": events[
                "_valid_first_cell"
            ],
            "Last Cell ID": events[
                "_valid_last_cell"
            ],
            "Raw IMEI": events[
                "_imei_raw"
            ],
            "Normalized IMEI": events[
                "_imei_normalized"
            ],
            "Source Row Number": events[
                "_source_row_number"
            ],
        }
    )

    timeline[
        "Duration (Sec)"
    ] = timeline[
        "Duration (Sec)"
    ].astype(
        int
    )

    return timeline.sort_values(
        [
            "Date-Time",
            "Target Number",
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
    events: pd.DataFrame,
    requested_imei: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    target_count = events[
        "_target"
    ].nunique()

    imsi_count = (
        events[
            "_imsi"
        ]
        .replace(
            "",
            pd.NA,
        )
        .dropna()
        .nunique()
    )

    source_count = events[
        "_source_file"
    ].nunique()

    if target_count > 1:
        rows.append(
            {
                "Indicator": (
                    "Device identifier appears in multiple target CDRs"
                ),
                "Observation": (
                    f"The exact identifier appears in "
                    f"{target_count} target CDR datasets."
                ),
                "Caution": (
                    "Verify source records, ownership periods and handset "
                    "transfer before drawing an identity conclusion."
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
                    f"The device identifier is associated with "
                    f"{imsi_count} normalized IMSI values."
                ),
                "Caution": (
                    "This may reflect SIM changes, dual-SIM handling, "
                    "source formatting or different usage periods."
                ),
            }
        )

    if source_count > 1:
        rows.append(
            {
                "Indicator": (
                    "Evidence appears in multiple source files"
                ),
                "Observation": (
                    f"Matching events occur in {source_count} loaded files."
                ),
                "Caution": (
                    "Check overlapping date ranges and duplicate records "
                    "before aggregating event counts."
                ),
            }
        )

    if len(
        requested_imei
    ) == 16:
        rows.append(
            {
                "Indicator": (
                    "16-digit device identifier"
                ),
                "Observation": (
                    "The investigation used an exact 16-digit normalized "
                    "identifier."
                ),
                "Caution": (
                    "It was not silently truncated or merged with a "
                    "different 15-digit identifier."
                ),
            }
        )

    query_scope_count = int(
        events[
            "_match_basis"
        ]
        .eq(
            "QUERY_SCOPE"
        )
        .sum()
    )

    if query_scope_count:
        relations = ", ".join(
            sorted(
                {
                    value
                    for value in events[
                        "_match_relation"
                    ]
                    .fillna(
                        ""
                    )
                    .astype(
                        str
                    )
                    .str.strip()
                    if value
                }
            )
        )

        rows.append(
            {
                "Indicator": (
                    "Dedicated IMEI report query matched"
                ),
                "Observation": (
                    f"{query_scope_count} event(s) were included because "
                    "the requested identifier exactly matched the report "
                    f"query. Recorded relation(s): "
                    f"{relations or 'UNAVAILABLE'}."
                ),
                "Caution": (
                    "The report-query identifier and observed IMEI/IMEISV "
                    "remain separate and must be verified against the "
                    "original evidence."
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
                    "The exact identifier was found without a configured "
                    "multi-target or multi-SIM condition."
                ),
                "Caution": (
                    "Absence of an indicator does not establish normality "
                    "or ownership."
                ),
            }
        )

    return pd.DataFrame(
        rows,
        columns=REVIEW_COLUMNS,
    )


def _build_data_quality(
    events: pd.DataFrame,
) -> pd.DataFrame:
    rows = [
        {
            "Check": "Matched events",
            "Count": len(
                events
            ),
            "Meaning": (
                'Rows included by exact observed matching or dedicated report-query scope. The recorded match relation remains available for review.'
            ),
        },
        {
            "Check": "Missing or invalid date-time",
            "Count": int(
                events[
                    "_event_datetime"
                ].isna().sum()
            ),
            "Meaning": (
                "Matched rows that cannot be placed reliably on the timeline."
            ),
        },
        {
            "Check": "Missing or invalid IMSI",
            "Count": int(
                events[
                    "_imsi"
                ].astype(
                    str
                ).str.strip().eq(
                    ""
                ).sum()
            ),
            "Meaning": (
                "Matched rows without a valid normalized SIM identity."
            ),
        },
        {
            "Check": "Missing or invalid first Cell ID",
            "Count": int(
                events[
                    "_valid_first_cell"
                ].astype(
                    str
                ).str.strip().eq(
                    ""
                ).sum()
            ),
            "Meaning": (
                "Matched rows without a valid first tower identifier."
            ),
        },
        {
            "Check": "16-digit matched rows",
            "Count": int(
                events[
                    "_imei_normalized"
                ].astype(
                    str
                ).str.len().eq(
                    16
                ).sum()
            ),
            "Meaning": (
                "Rows retained as exact 16-digit identifiers."
            ),
        },
    ]

    return pd.DataFrame(
        rows,
        columns=QUALITY_COLUMNS,
    )


def build_imei_investigation(
    loaded_cdrs: Mapping[str, Any],
    requested_imei: Any,
) -> dict[str, Any]:
    """Search one exact canonical IMEI/IMEISV across loaded CDR targets.

    Parameters
    ----------
    loaded_cdrs:
        Mapping of target number to either a DataFrame or an information
        dictionary containing a ``df`` DataFrame.
    requested_imei:
        Investigator-supplied IMEI or IMEISV. Only canonical 15- or 16-digit
        values are accepted.

    Returns
    -------
    dict
        Investigator-ready analysis tables. Source DataFrames are never
        modified.
    """

    normalized_requested = (
        _normalize_requested_device_identifier(
            requested_imei
        )
    )

    if not normalized_requested:
        return _empty_bundle(
            "",
            status="INVALID_IMEI",
            message=(
                "Enter a valid 14-digit report query, 15-digit IMEI or 16-digit IMEISV."
            ),
        )

    if not isinstance(
        loaded_cdrs,
        Mapping,
    ):
        return _empty_bundle(
            normalized_requested,
            status="NO_INPUT",
            message=(
                "No loaded CDR target collection was provided."
            ),
        )

    matched_frames: list[pd.DataFrame] = []

    for target, value in loaded_cdrs.items():
        prepared = _prepare_target_events(
            target=str(
                target
            ),
            value=value,
            requested_imei=normalized_requested,
        )

        if not prepared.empty:
            matched_frames.append(
                prepared
            )

    if not matched_frames:
        return _empty_bundle(
            normalized_requested,
            status="NOT_FOUND",
            message=(
                "The exact normalized IMEI/IMEISV was not found "
                "in the loaded CDR datasets."
            ),
        )

    events = pd.concat(
        matched_frames,
        ignore_index=True,
        sort=False,
    )

    timeline = _build_timeline(
        events
    )

    return {
        "requested_imei": normalized_requested,
        "status": "FOUND",
        "message": (
            f"Found {len(events)} matching event(s) "
            f"across {events['_target'].nunique()} target(s)."
        ),
        "matched_events": timeline.copy(),
        "summary": _build_summary(
            events,
            normalized_requested,
        ),
        "associated_targets": _build_target_summary(
            events
        ),
        "associated_sims": _build_sim_summary(
            events
        ),
        "contacts": _build_contact_summary(
            events
        ),
        "towers": _build_tower_summary(
            events
        ),
        "timeline": timeline,
        "review_indicators": _build_review_indicators(
            events,
            normalized_requested,
        ),
        "data_quality": _build_data_quality(
            events
        ),
    }
