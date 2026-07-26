"""Common analysis across multiple dedicated IMEI CDR queries."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import pandas as pd

from modules.analysis.cdr.contact_classifier import (
    classify_contact,
)
from modules.analysis.cdr.tower_utils import (
    valid_cell_mask,
)


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


def _text_series(
    frame: pd.DataFrame,
    column: str,
) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(
            "",
            index=frame.index,
            dtype="string",
        )

    return (
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


def _event_time(
    frame: pd.DataFrame,
) -> pd.Series:
    if "call_datetime" in frame.columns:
        return pd.to_datetime(
            frame[
                "call_datetime"
            ],
            errors="coerce",
            dayfirst=True,
        )

    date_value = _text_series(
        frame,
        "call_date",
    )

    time_value = _text_series(
        frame,
        "call_time",
    )

    return pd.to_datetime(
        (
            date_value
            + " "
            + time_value
        ).str.strip(),
        errors="coerce",
        dayfirst=True,
    )


def _device_family(
    value: Any,
) -> str:
    """Return the non-destructive 14-digit device-family key."""

    digits = _digits(
        value
    )

    if len(
        digits
    ) not in {
        14,
        15,
        16,
    }:
        return ""

    return digits[
        :14
    ]


def _shared_contact_summary(
    events: pd.DataFrame,
    *,
    categories: set[str],
    output_column: str,
) -> pd.DataFrame:
    """Summarize shared contacts within selected contact categories."""

    work = events.loc[
        events[
            "Contact Category"
        ].isin(
            categories
        )
    ].copy()

    result = _shared_summary(
        work,
        source_column="Other Party",
        output_column=output_column,
    )

    columns = [
        output_column,
        "Contact Category",
        "Query Identifier Count",
        "Device Family Count",
        "Query Identifiers",
        "Device Families",
        "Total Events",
        "First Seen",
        "Last Seen",
        "Source Files",
    ]

    if result.empty:
        return pd.DataFrame(
            columns=columns
        )

    result.insert(
        1,
        "Contact Category",
        result[
            output_column
        ].map(
            classify_contact
        ),
    )

    return result[
        columns
    ]


def _common_tower_mask(
    series: pd.Series,
) -> pd.Series:
    """Return Cell IDs suitable for common-device tower analysis.

    The canonical validator remains the first validation layer.
    PLMN-only values such as 405856 are excluded because they do
    not contain a cell-specific component.
    """

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

    # Pandas with the PyArrow string backend may preserve string dtype
    # when mapping an empty Series. Return an explicit boolean mask.
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

def _invalid_tower_count(
    events: pd.DataFrame,
) -> int:
    """Count non-empty Cell IDs excluded from common-tower analysis."""

    count = 0

    for column in (
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

        valid = _common_tower_mask(
            values
        )

        count += int(
            (
                values.ne(
                    ""
                )
                & ~valid
            ).sum()
        )

    return count

def _shared_summary(
    events: pd.DataFrame,
    *,
    source_column: str,
    output_column: str,
) -> pd.DataFrame:
    """Return values shared across at least two device families."""

    columns = [
        output_column,
        "Query Identifier Count",
        "Device Family Count",
        "Query Identifiers",
        "Device Families",
        "Total Events",
        "First Seen",
        "Last Seen",
        "Source Files",
    ]

    if (
        not isinstance(
            events,
            pd.DataFrame,
        )
        or events.empty
        or source_column not in events.columns
    ):
        return pd.DataFrame(
            columns=columns
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
        return pd.DataFrame(
            columns=columns
        )

    result = (
        work.groupby(
            source_column,
            dropna=False,
        )
        .agg(
            **{
                "Query Identifier Count": (
                    "Query Identifier",
                    "nunique",
                ),
                "Device Family Count": (
                    "Device Family",
                    "nunique",
                ),
                "Query Identifiers": (
                    "Query Identifier",
                    _join_unique,
                ),
                "Device Families": (
                    "Device Family",
                    _join_unique,
                ),
                "Total Events": (
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

    # Two representations of the same BASE14 family must not create
    # a false cross-device relationship.
    result = result.loc[
        result[
            "Device Family Count"
        ].ge(
            2
        )
    ]

    if result.empty:
        return pd.DataFrame(
            columns=columns
        )

    return (
        result[
            columns
        ]
        .sort_values(
            [
                "Device Family Count",
                "Query Identifier Count",
                "Total Events",
                output_column,
            ],
            ascending=[
                False,
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


def _prepare_events(
    device_frames: Mapping[
        str,
        pd.DataFrame,
    ],
) -> pd.DataFrame:
    """Prepare immutable cross-device event rows."""

    frames: list[
        pd.DataFrame
    ] = []

    output_columns = [
        "Query Identifier",
        "Device Family",
        "Observed IMEI / IMEISV",
        "Target Number",
        "Event Time",
        "Call Type",
        "Other Party",
        "Contact Category",
        "Duration (Sec)",
        "IMSI",
        "First Cell ID",
        "Last Cell ID",
        "Source File",
        "Source Path",
        "Source Row Number",
        "Match Relation",
    ]

    for query_identifier, source in (
        device_frames.items()
    ):
        identifier = _digits(
            query_identifier
        )

        family = _device_family(
            identifier
        )

        if (
            not family
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

        observed_column = _text_series(
            frame,
            "observed_imei_normalized",
        )

        observed = observed_column.where(
            observed_column.ne(
                ""
            ),
            _text_series(
                frame,
                "imei",
            ),
        )

        other_party = _text_series(
            frame,
            "b_party",
        )

        if "call_duration" in frame.columns:
            duration = pd.to_numeric(
                frame[
                    "call_duration"
                ],
                errors="coerce",
            ).fillna(
                0
            )

        else:
            duration = pd.Series(
                0,
                index=frame.index,
                dtype="int64",
            )

        prepared = pd.DataFrame(
            {
                "Query Identifier": identifier,
                "Device Family": family,
                "Observed IMEI / IMEISV": observed,
                "Target Number": _text_series(
                    frame,
                    "target",
                ),
                "Event Time": _event_time(
                    frame
                ),
                "Call Type": _text_series(
                    frame,
                    "call_type",
                ),
                "Other Party": other_party,
                "Contact Category": other_party.map(
                    classify_contact
                ),
                "Duration (Sec)": duration,
                "IMSI": _text_series(
                    frame,
                    "imsi",
                ),
                "First Cell ID": _text_series(
                    frame,
                    "first_cell_id",
                ),
                "Last Cell ID": _text_series(
                    frame,
                    "last_cell_id",
                ),
                "Source File": _text_series(
                    frame,
                    "source_file",
                ),
                "Source Path": _text_series(
                    frame,
                    "source_path",
                ),
                "Source Row Number": (
                    frame[
                        "source_row_number"
                    ]
                    if "source_row_number"
                    in frame.columns
                    else pd.NA
                ),
                "Match Relation": _text_series(
                    frame,
                    "match_relation",
                ),
            }
        )

        frames.append(
            prepared
        )

    if not frames:
        return pd.DataFrame(
            columns=output_columns
        )

    return pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )[
        output_columns
    ]


def _tower_events(
    events: pd.DataFrame,
) -> pd.DataFrame:
    """Return canonically valid, cell-specific tower evidence."""

    frames: list[
        pd.DataFrame
    ] = []

    output_columns = [
        "Query Identifier",
        "Device Family",
        "Event Time",
        "Source File",
        "Cell ID",
    ]

    for column in (
        "First Cell ID",
        "Last Cell ID",
    ):
        if column not in events.columns:
            continue

        valid = _common_tower_mask(
            events[
                column
            ]
        )

        subset = events.loc[
            valid,
            [
                "Query Identifier",
                "Device Family",
                "Event Time",
                "Source File",
                column,
            ],
        ].copy()

        if subset.empty:
            continue

        subset = subset.rename(
            columns={
                column: "Cell ID",
            }
        )

        frames.append(
            subset
        )

    if not frames:
        return pd.DataFrame(
            columns=output_columns
        )

    return (
        pd.concat(
            frames,
            ignore_index=True,
            sort=False,
        )
        .drop_duplicates(
            subset=[
                "Query Identifier",
                "Device Family",
                "Event Time",
                "Source File",
                "Cell ID",
            ],
            keep="first",
        )
        .reset_index(
            drop=True
        )[
            output_columns
        ]
    )


def _device_overview(
    events: pd.DataFrame,
    identifiers: list[str],
    acquisition_manifest: pd.DataFrame,
) -> pd.DataFrame:
    """Build one row per report-query identifier."""

    rows = []

    for identifier in identifiers:
        family = _device_family(
            identifier
        )

        work = events.loc[
            events[
                "Query Identifier"
            ].eq(
                identifier
            )
        ]

        manifest = (
            acquisition_manifest.loc[
                acquisition_manifest[
                    "Query Identifier"
                ]
                .astype(
                    str
                )
                .eq(
                    identifier
                )
            ]
            if (
                isinstance(
                    acquisition_manifest,
                    pd.DataFrame,
                )
                and not acquisition_manifest.empty
                and "Query Identifier"
                in acquisition_manifest.columns
            )
            else pd.DataFrame()
        )

        supported_manifest = manifest

        if (
            not manifest.empty
            and "Source Type"
            in manifest.columns
        ):
            supported_manifest = manifest.loc[
                manifest[
                    "Source Type"
                ]
                .astype(
                    str
                )
                .str.upper()
                .eq(
                    "CDR"
                )
            ]

        tower_rows = _tower_events(
            work
        )

        human_contacts = work.loc[
            work[
                "Contact Category"
            ].eq(
                "human_mobile"
            ),
            "Other Party",
        ]

        service_identifiers = work.loc[
            work[
                "Contact Category"
            ].ne(
                "human_mobile"
            )
            & work[
                "Other Party"
            ].ne(
                ""
            ),
            "Other Party",
        ]

        rows.append(
            {
                "Query Identifier": identifier,
                "Device Family": family,
                "Identifier Type": {
                    14: "BASE14",
                    15: "IMEI15",
                    16: "IMEISV16",
                }.get(
                    len(
                        identifier
                    ),
                    "UNKNOWN",
                ),
                "Acquisition Files": len(
                    manifest
                ),
                "Unique CDR Content Groups": (
                    supported_manifest[
                        "SHA-256"
                    ]
                    .replace(
                        "",
                        pd.NA,
                    )
                    .dropna()
                    .nunique()
                    if (
                        not supported_manifest.empty
                        and "SHA-256"
                        in supported_manifest.columns
                    )
                    else 0
                ),
                "Inspection Status": (
                    _join_unique(
                        manifest[
                            "Inspection Status"
                        ]
                    )
                    if (
                        not manifest.empty
                        and "Inspection Status"
                        in manifest.columns
                    )
                    else ""
                ),
                "Normalized Events": len(
                    work
                ),
                "Observed IMEI / IMEISV": (
                    _join_unique(
                        work[
                            "Observed IMEI / IMEISV"
                        ]
                    )
                    if not work.empty
                    else ""
                ),
                "Target Count": work[
                    "Target Number"
                ].replace(
                    "",
                    pd.NA,
                ).nunique(),
                "IMSI Count": work[
                    "IMSI"
                ].replace(
                    "",
                    pd.NA,
                ).nunique(),
                "Human Contact Count": (
                    human_contacts
                    .replace(
                        "",
                        pd.NA,
                    )
                    .nunique()
                ),
                "Service Identifier Count": (
                    service_identifiers
                    .replace(
                        "",
                        pd.NA,
                    )
                    .nunique()
                ),
                "Valid Tower Count": tower_rows[
                    "Cell ID"
                ].replace(
                    "",
                    pd.NA,
                ).nunique(),
                "First Seen": work[
                    "Event Time"
                ].min(),
                "Last Seen": work[
                    "Event Time"
                ].max(),
            }
        )

    return pd.DataFrame(
        rows
    )


def build_common_imei_cdr_analysis(
    device_frames: Mapping[
        str,
        pd.DataFrame,
    ],
    acquisition_manifest: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Build cross-device evidence without merging IMEI representations."""

    if not isinstance(
        device_frames,
        Mapping,
    ):
        device_frames = {}

    identifiers = sorted(
        {
            _digits(
                identifier
            )
            for identifier in device_frames
            if len(
                _digits(
                    identifier
                )
            )
            in {
                14,
                15,
                16,
            }
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

    base_result = {
        # Backward-compatible field used by the current report generator.
        "device_count": len(
            identifiers
        ),
        "query_identifier_count": len(
            identifiers
        ),
        "device_family_count": len(
            families
        ),
        "device_overview": _device_overview(
            events,
            identifiers,
            manifest,
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
                "Common IMEI analysis requires at least "
                "two unique report-query identifiers."
            ),
            "common_targets": pd.DataFrame(),
            "common_imsis": pd.DataFrame(),
            "common_contacts": pd.DataFrame(),
            "shared_service_identifiers": pd.DataFrame(),
            "common_towers": pd.DataFrame(),
            "cross_device_timeline": events,
            "review_indicators": pd.DataFrame(),
            "data_quality": pd.DataFrame(),
        }

    towers = _tower_events(
        events
    )

    common_targets = _shared_summary(
        events,
        source_column="Target Number",
        output_column="Target Number",
    )

    common_imsis = _shared_summary(
        events,
        source_column="IMSI",
        output_column="IMSI",
    )

    common_contacts = _shared_contact_summary(
        events,
        categories={
            "human_mobile",
        },
        output_column="Contact Number",
    )

    shared_service_identifiers = (
        _shared_contact_summary(
            events,
            categories={
                "service_sender_id",
                "short_code",
                "unknown_contact",
            },
            output_column="Service / Other Identifier",
        )
    )

    common_towers = _shared_summary(
        towers,
        source_column="Cell ID",
        output_column="Cell ID",
    )

    review_rows = []

    for label, frame in (
        (
            "Common target/subscriber numbers",
            common_targets,
        ),
        (
            "Common IMSIs",
            common_imsis,
        ),
        (
            "Common human contacts",
            common_contacts,
        ),
        (
            "Shared service or other identifiers",
            shared_service_identifiers,
        ),
        (
            "Common valid towers",
            common_towers,
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
                    "Verify source files, source rows, time ranges, "
                    "ownership periods and duplicate-content status."
                ),
            }
        )

    if manifest.empty:
        all_content_groups = 0
        supported_cdr_groups = 0
        non_cdr_acquisitions = 0
        duplicate_cdr_acquisitions = 0
        empty_report_count = 0

    else:
        sha_values = _text_series(
            manifest,
            "SHA-256",
        )

        source_types = _text_series(
            manifest,
            "Source Type",
        ).str.upper()

        statuses = _text_series(
            manifest,
            "Inspection Status",
        ).str.upper()

        analysis_roles = _text_series(
            manifest,
            "Analysis Content Role",
        ).str.upper()

        supported_mask = (
            source_types.eq(
                "CDR"
            )
            & statuses.isin(
                {
                    "HAS_DATA",
                    "EMPTY_NO_DATA",
                }
            )
        )

        all_content_groups = (
            sha_values
            .replace(
                "",
                pd.NA,
            )
            .dropna()
            .nunique()
        )

        supported_cdr_groups = (
            sha_values.loc[
                supported_mask
            ]
            .replace(
                "",
                pd.NA,
            )
            .dropna()
            .nunique()
        )

        non_cdr_acquisitions = int(
            source_types.ne(
                "CDR"
            ).sum()
        )

        duplicate_cdr_acquisitions = int(
            (
                supported_mask
                & analysis_roles.eq(
                    "DUPLICATE_CONTENT"
                )
            ).sum()
        )

        empty_report_count = int(
            (
                source_types.eq(
                    "CDR"
                )
                & statuses.eq(
                    "EMPTY_NO_DATA"
                )
            ).sum()
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
                "Check": "Analytical CDR event rows",
                "Count": len(
                    events
                ),
                "Meaning": (
                    "Rows loaded from supported unique CDR content."
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
                "Check": "Invalid/incomplete Cell IDs excluded",
                "Count": _invalid_tower_count(
                    events
                ),
                "Meaning": (
                    "Non-empty Cell IDs rejected by canonical "
                    "tower validation."
                ),
            },
            {
                "Check": "Physical acquisitions",
                "Count": len(
                    manifest
                ),
                "Meaning": (
                    "Every physical evidence path retained."
                ),
            },
            {
                "Check": "All acquisition SHA-256 groups",
                "Count": all_content_groups,
                "Meaning": (
                    "Unique content across every acquisition type."
                ),
            },
            {
                "Check": "Supported CDR analytical content groups",
                "Count": supported_cdr_groups,
                "Meaning": (
                    "Unique supported CDR content eligible for analysis."
                ),
            },
            {
                "Check": "Non-CDR acquisitions excluded",
                "Count": non_cdr_acquisitions,
                "Meaning": (
                    "Files retained in the manifest but not analyzed as CDR."
                ),
            },
            {
                "Check": "Duplicate CDR acquisitions",
                "Count": duplicate_cdr_acquisitions,
                "Meaning": (
                    "Physical CDR copies preserved but analyzed once."
                ),
            },
            {
                "Check": "Valid empty CDR reports",
                "Count": empty_report_count,
                "Meaning": (
                    "Operator reports containing no result records."
                ),
            },
        ]
    )

    return {
        **base_result,
        "status": "FOUND",
        "message": (
            f"Common analysis completed across "
            f"{len(identifiers)} query identifier(s) representing "
            f"{len(families)} device family/families."
        ),
        "common_targets": common_targets,
        "common_imsis": common_imsis,
        "common_contacts": common_contacts,
        "shared_service_identifiers": (
            shared_service_identifiers
        ),
        "common_towers": common_towers,
        "cross_device_timeline": (
            events.sort_values(
                [
                    "Event Time",
                    "Device Family",
                    "Query Identifier",
                    "Source File",
                    "Source Row Number",
                ],
                kind="stable",
                na_position="last",
            ).reset_index(
                drop=True
            )
        ),
        "review_indicators": pd.DataFrame(
            review_rows
        ),
        "data_quality": data_quality,
    }
