
"""Shared batch SDR and CGI enrichment for telecom analysis tables."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import pandas as pd

from modules.database.cgi_repository import (
    normalize_cgi,
)
from modules.enrichment.cgi_address_enrichment import (
    lookup_cgi_addresses,
)
from modules.enrichment.sdr_subscriber_enrichment import (
    lookup_sdr_subscribers,
    normalize_mobile_number,
)


SDR_FIELDS = {
    "lookup_mobile": "lookup_mobile",
    "subscriber_name": "subscriber_name",
    "father_name": "father_name",
    "subscriber_address": "address",
    "id_type": "id_type",
    "id_number": "id_number",
    "operator": "operator",
    "circle": "circle",
    "activation_date": "activation_date",
    "caf_number": "caf_number",
    "source_file": "source_file",
    "sdr_found": "found",
}

CGI_FIELDS = {
    "operator": "operator",
    "circle": "circle",
    "state": "state",
    "district": "district",
    "police_station": "police_station",
    "town": "town",
    "site_name": "site_name",
    "address": "address",
    "latitude": "latitude",
    "longitude": "longitude",
    "source_file": "source_file",
}


IPDR_TABLE_SPECS = {
    "subscriber_summary": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "multi_file_subscribers": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "subscriber_file_presence": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "cgi_summary": {
        "cgi": (
            "cgi",
        ),
    },
    "cell_movement": {
        "sdr": (
            "subscriber_number",
        ),
        "cgi": (
            "first_cell_id",
            "last_cell_id",
        ),
    },
}


TOWER_IPDR_TABLE_SPECS = {
    "subscriber_summary": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "subscriber_multi_cell_candidates": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "subscriber_all_cell_candidates": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "uncommon_numbers": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "cell_summary": {
        "cgi": (
            "searched_cell_id",
        ),
    },
    "cell_movement_summary": {
        "sdr": (
            "subscriber_number",
        ),
        "cgi": (
            "first_cell_id",
            "last_cell_id",
            "searched_cell_id",
        ),
    },
}


TOWER_IPDR_PARTITION_SPECS = {
    "actual_event_hits": {
        "sdr": (
            "subscriber_number",
        ),
        "cgi": (
            "searched_cell_id",
        ),
    },
    "event_subscriber_presence": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "event_n_of_m_candidates": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "event_strict_common_candidates": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "allocation_overlap_hits": {
        "sdr": (
            "subscriber_number",
        ),
        "cgi": (
            "searched_cell_id",
        ),
    },
    "allocation_subscriber_presence": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "allocation_n_of_m_candidates": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "allocation_strict_common_candidates": {
        "sdr": (
            "subscriber_number",
        ),
    },
}


TOWER_IPDR_COMPLETE_SPECS = {
    "subscriber_activity": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "priority_review_queue": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "rare_presence": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "multi_spot_intelligence": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "device_sim_alerts": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "spot_cell_summary": {
        "cgi": (
            "searched_cell_id",
            "cell_id",
            "cgi",
        ),
    },
}



CDR_TABLE_SPECS = {
    "top_contacts": {
        "sdr": (
            "Contact",
            "contact",
            "b_party",
            "other_party",
            "Other Party",
        ),
    },
    "contact_ranking": {
        "sdr": (
            "Contact",
            "contact",
            "b_party",
            "other_party",
            "Other Party",
        ),
    },
    "top_contact_details": {
        "sdr": (
            "Contact",
            "contact",
            "b_party",
            "other_party",
            "Other Party",
        ),
    },
    "social_network": {
        "sdr": (
            "Contact",
            "contact",
            "b_party",
            "other_party",
        ),
    },
    "analyze_location": {
        "cgi": (
            "first_cell_id",
            "cell_id",
            "cgi",
            "Cell ID",
        ),
    },
    "frequent_locations": {
        "cgi": (
            "first_cell_id",
            "cell_id",
            "cgi",
            "Cell ID",
        ),
    },
    "tower_movement": {
        "cgi": (
            "first_cell_id",
            "last_cell_id",
            "cell_id",
            "cgi",
            "Cell ID",
            "Last Cell ID",
        ),
    },
    "tower_transition": {
        "cgi": (
            "first_cell_id",
            "last_cell_id",
            "start_cell_id",
            "end_cell_id",
            "Cell ID",
            "Last Cell ID",
            "Start Cell ID",
            "End Cell ID",
        ),
    },
    "tower_intelligence": {
        "cgi": (
            "first_cell_id",
            "cell_id",
            "cgi",
            "Cell ID",
        ),
    },
    "home_tower": {
        "cgi": (
            "first_cell_id",
            "cell_id",
            "cgi",
            "Cell ID",
        ),
    },
    "work_tower": {
        "cgi": (
            "first_cell_id",
            "cell_id",
            "cgi",
            "Cell ID",
        ),
    },
}


TOWER_CDR_TABLE_SPECS = {
    "subscriber_summary": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "tower_cdr_common_numbers": {
        "sdr": (
            "subscriber_number",
        ),
        "cgi": (
            "searched_cell_id",
            "first_cell_id",
            "last_cell_id",
        ),
    },
    "tower_cdr_uncommon_numbers": {
        "sdr": (
            "subscriber_number",
        ),
        "cgi": (
            "searched_cell_id",
            "first_cell_id",
            "last_cell_id",
        ),
    },
    "tower_cdr_multi_cell_presence": {
        "sdr": (
            "subscriber_number",
        ),
        "cgi": (
            "searched_cell_id",
            "first_cell_id",
            "last_cell_id",
        ),
    },
    "tower_cdr_device_consistency": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "tower_cdr_suspicious_timing": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "tower_cdr_priority_leads": {
        "sdr": (
            "subscriber_number",
        ),
        "cgi": (
            "searched_cell_id",
            "first_cell_id",
            "last_cell_id",
        ),
    },
    "searched_cell_summary": {
        "cgi": (
            "searched_cell_id",
            "cell_id",
            "cgi",
        ),
    },
    "cell_summary": {
        "cgi": (
            "searched_cell_id",
            "first_cell_id",
            "cell_id",
            "cgi",
        ),
    },
    "spot_summary": {
        "cgi": (
            "searched_cell_id",
            "cell_id",
            "cgi",
        ),
    },
}


TOWER_CDR_PARTITION_SPECS = {
    "subscriber_presence": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "n_of_m_candidates": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "strict_common_candidates": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "partition_visitor_intelligence": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "new_visitors": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "rare_visitors": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "repeat_relevant_visitors": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "regular_local_presence": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "multi_cell_relevant": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "partition_priority_leads": {
        "sdr": (
            "subscriber_number",
        ),
    },
}


TOWER_GPRS_TABLE_SPECS = {
    "subscriber_summary": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "gprs_common_numbers": {
        "sdr": (
            "subscriber_number",
        ),
        "cgi": (
            "searched_cell_id",
            "cgi",
            "cell_id",
        ),
    },
    "gprs_uncommon_numbers": {
        "sdr": (
            "subscriber_number",
        ),
        "cgi": (
            "searched_cell_id",
            "cgi",
            "cell_id",
        ),
    },
    "gprs_multi_cell_presence": {
        "sdr": (
            "subscriber_number",
        ),
        "cgi": (
            "searched_cell_id",
            "cgi",
            "cell_id",
        ),
    },
    "gprs_device_consistency": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "gprs_suspicious_timing": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "gprs_priority_leads": {
        "sdr": (
            "subscriber_number",
        ),
        "cgi": (
            "searched_cell_id",
            "cgi",
            "cell_id",
        ),
    },
    "cell_summary": {
        "cgi": (
            "searched_cell_id",
            "cgi",
            "cell_id",
        ),
    },
    "spot_summary": {
        "cgi": (
            "searched_cell_id",
            "cgi",
            "cell_id",
        ),
    },
}


TOWER_GPRS_PARTITION_SPECS = {
    "subscriber_presence": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "n_of_m_candidates": {
        "sdr": (
            "subscriber_number",
        ),
    },
    "strict_common_candidates": {
        "sdr": (
            "subscriber_number",
        ),
    },
}


def _clean_text(
    value: object,
) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(
            value
        ):
            return ""
    except (TypeError, ValueError):
        pass

    return str(
        value
    ).strip()


def _valid_mobile_key(
    value: object,
) -> str:
    normalized = _clean_text(
        normalize_mobile_number(
            value
        )
    )

    if (
        len(
            normalized
        ) == 10
        and normalized[0] in {
            "6",
            "7",
            "8",
            "9",
        }
        and normalized.isdigit()
    ):
        return normalized

    return ""


def _valid_cgi_key(
    value: object,
) -> str:
    return _clean_text(
        normalize_cgi(
            value
        )
    )


def _sdr_prefix(
    column: str,
) -> str:
    normalized = str(
        column
    ).strip().lower()

    if normalized in {
        "subscriber_number",
        "mobile_number",
        "msisdn",
    }:
        return "sdr_"

    return (
        normalized
        .replace(
            " ",
            "_",
        )
        .replace(
            "-",
            "_",
        )
        + "_sdr_"
    )


def _cgi_prefix(
    column: str,
) -> str:
    normalized = str(
        column
    ).strip().lower()

    mapping = {
        "cgi": "cgi_",
        "cell_id": "cell_",
        "searched_cell_id": "searched_cell_",
        "first_cell_id": "first_cell_",
        "last_cell_id": "last_cell_",
    }

    return mapping.get(
        normalized,
        (
            normalized
            .replace(
                " ",
                "_",
            )
            .replace(
                "-",
                "_",
            )
            + "_cgi_"
        ),
    )


def _existing_columns(
    dataframe: pd.DataFrame,
    requested: Iterable[str],
) -> list[str]:
    by_normalized = {
        str(
            column
        ).strip().lower(): str(
            column
        )
        for column in dataframe.columns
    }

    output = []

    for candidate in requested:
        found = by_normalized.get(
            str(
                candidate
            ).strip().lower()
        )

        if (
            found is not None
            and found not in output
        ):
            output.append(
                found
            )

    return output


def _lookup_map_frame(
    dataframe: pd.DataFrame,
    *,
    key_column: str,
) -> pd.DataFrame:
    if (
        dataframe is None
        or not isinstance(
            dataframe,
            pd.DataFrame,
        )
        or dataframe.empty
        or key_column not in dataframe.columns
    ):
        return pd.DataFrame()

    output = dataframe.copy()

    output[
        key_column
    ] = (
        output[
            key_column
        ]
        .fillna(
            ""
        )
        .astype(
            str
        )
        .str.strip()
    )

    output = output[
        output[
            key_column
        ].ne(
            ""
        )
    ].copy()

    if output.empty:
        return output

    return output.drop_duplicates(
        subset=[
            key_column,
        ],
        keep="last",
    )


def _apply_sdr_lookup(
    dataframe: pd.DataFrame,
    *,
    number_column: str,
    lookup: pd.DataFrame,
    lookup_failed: bool,
) -> pd.DataFrame:
    output = dataframe.copy()
    prefix = _sdr_prefix(
        number_column
    )

    raw_values = (
        output[
            number_column
        ]
        .fillna(
            ""
        )
        .astype(
            str
        )
        .str.strip()
    )

    lookup_column = (
        f"{prefix}lookup_mobile"
    )

    output[
        lookup_column
    ] = output[
        number_column
    ].map(
        _valid_mobile_key
    )

    output_columns = [
        f"{prefix}{target}"
        for target in SDR_FIELDS.values()
        if target != "lookup_mobile"
    ]

    output_columns.extend(
        [
            f"{prefix}lookup_status",
            f"{prefix}match_confidence",
        ]
    )

    existing_output = [
        column
        for column in output_columns
        if column in output.columns
    ]

    if existing_output:
        output = output.drop(
            columns=existing_output
        )

    lookup_frame = _lookup_map_frame(
        lookup,
        key_column="lookup_mobile",
    )

    if not lookup_frame.empty:
        rename_map = {
            source: f"{prefix}{target}"
            for source, target in SDR_FIELDS.items()
            if source != "lookup_mobile"
            and source in lookup_frame.columns
        }

        lookup_frame = lookup_frame.rename(
            columns=rename_map
        )

        keep_columns = [
            "lookup_mobile",
            *rename_map.values(),
        ]

        lookup_frame = lookup_frame[
            keep_columns
        ].rename(
            columns={
                "lookup_mobile": (
                    lookup_column
                ),
            }
        )

        output = output.merge(
            lookup_frame,
            on=lookup_column,
            how="left",
            sort=False,
        )

    for target in SDR_FIELDS.values():
        if target == "lookup_mobile":
            continue

        column = f"{prefix}{target}"

        if column not in output.columns:
            output[
                column
            ] = ""

    output[
        f"{prefix}found"
    ] = (
        output[
            f"{prefix}found"
        ]
        .fillna(
            "No"
        )
        .astype(
            str
        )
    )

    eligible = output[
        lookup_column
    ].ne(
        ""
    )

    found = (
        output[
            f"{prefix}found"
        ]
        .str.upper()
        .eq(
            "YES"
        )
    )

    status = pd.Series(
        "NOT_PROVIDED",
        index=output.index,
        dtype="string",
    )

    status.loc[
        raw_values.ne(
            ""
        )
        & ~eligible
    ] = "NOT_ELIGIBLE"

    status.loc[
        eligible
    ] = (
        "LOOKUP_ERROR"
        if lookup_failed
        else "NOT_FOUND"
    )

    status.loc[
        eligible
        & found
    ] = "FOUND"

    output[
        f"{prefix}lookup_status"
    ] = status

    output[
        f"{prefix}match_confidence"
    ] = ""

    output.loc[
        status.eq(
            "FOUND"
        ),
        f"{prefix}match_confidence",
    ] = "DIRECT_NORMALIZED_MSISDN"

    text_columns = [
        f"{prefix}{target}"
        for target in SDR_FIELDS.values()
        if target not in {
            "lookup_mobile",
        }
    ]

    for column in text_columns:
        if column in output.columns:
            output[
                column
            ] = output[
                column
            ].fillna(
                ""
            )

    return output


def _apply_cgi_lookup(
    dataframe: pd.DataFrame,
    *,
    cell_column: str,
    lookup: pd.DataFrame,
    lookup_failed: bool,
) -> pd.DataFrame:
    output = dataframe.copy()
    prefix = _cgi_prefix(
        cell_column
    )

    raw_values = (
        output[
            cell_column
        ]
        .fillna(
            ""
        )
        .astype(
            str
        )
        .str.strip()
    )

    lookup_column = (
        f"{prefix}lookup_key"
    )

    output[
        lookup_column
    ] = output[
        cell_column
    ].map(
        _valid_cgi_key
    )

    output_columns = [
        f"{prefix}{target}"
        for target in CGI_FIELDS.values()
    ]

    output_columns.extend(
        [
            f"{prefix}record_found",
            f"{prefix}address_found",
            f"{prefix}lookup_status",
            f"{prefix}match_confidence",
        ]
    )

    existing_output = [
        column
        for column in output_columns
        if column in output.columns
    ]

    if existing_output:
        output = output.drop(
            columns=existing_output
        )

    lookup_frame = _lookup_map_frame(
        lookup,
        key_column="cgi",
    )

    if not lookup_frame.empty:
        lookup_frame[
            f"{prefix}record_found"
        ] = "Yes"

        rename_map = {
            source: f"{prefix}{target}"
            for source, target in CGI_FIELDS.items()
            if source in lookup_frame.columns
        }

        lookup_frame = lookup_frame.rename(
            columns=rename_map
        )

        lookup_frame = lookup_frame.rename(
            columns={
                "cgi": lookup_column,
            }
        )

        keep_columns = [
            lookup_column,
            f"{prefix}record_found",
            *rename_map.values(),
        ]

        lookup_frame = lookup_frame[
            keep_columns
        ]

        output = output.merge(
            lookup_frame,
            on=lookup_column,
            how="left",
            sort=False,
        )

    if (
        f"{prefix}record_found"
        not in output.columns
    ):
        output[
            f"{prefix}record_found"
        ] = "No"

    output[
        f"{prefix}record_found"
    ] = (
        output[
            f"{prefix}record_found"
        ]
        .fillna(
            "No"
        )
        .astype(
            str
        )
    )

    for target in CGI_FIELDS.values():
        column = f"{prefix}{target}"

        if column not in output.columns:
            output[
                column
            ] = (
                pd.NA
                if target in {
                    "latitude",
                    "longitude",
                }
                else ""
            )

    address_values = (
        output[
            f"{prefix}address"
        ]
        .fillna(
            ""
        )
        .astype(
            str
        )
        .str.strip()
    )

    output[
        f"{prefix}address_found"
    ] = address_values.map(
        lambda value: (
            "Yes"
            if value
            else "No"
        )
    )

    eligible = output[
        lookup_column
    ].ne(
        ""
    )

    found = (
        output[
            f"{prefix}record_found"
        ]
        .str.upper()
        .eq(
            "YES"
        )
    )

    status = pd.Series(
        "NOT_PROVIDED",
        index=output.index,
        dtype="string",
    )

    status.loc[
        raw_values.ne(
            ""
        )
        & ~eligible
    ] = "NOT_ELIGIBLE"

    status.loc[
        eligible
    ] = (
        "LOOKUP_ERROR"
        if lookup_failed
        else "NOT_FOUND"
    )

    status.loc[
        eligible
        & found
    ] = "FOUND"

    output[
        f"{prefix}lookup_status"
    ] = status

    output[
        f"{prefix}match_confidence"
    ] = ""

    output.loc[
        status.eq(
            "FOUND"
        ),
        f"{prefix}match_confidence",
    ] = "DIRECT_NORMALIZED_CGI_KEY"

    for target in CGI_FIELDS.values():
        if target in {
            "latitude",
            "longitude",
        }:
            continue

        column = f"{prefix}{target}"

        output[
            column
        ] = output[
            column
        ].fillna(
            ""
        )

    return output


def _summary_frame(
    *,
    tables_processed: int,
    sdr_raw_rows: int,
    sdr_eligible_values: set[str],
    sdr_found_values: set[str],
    sdr_invalid_rows: int,
    cgi_raw_rows: int,
    cgi_eligible_values: set[str],
    cgi_found_values: set[str],
    warnings: list[str],
) -> pd.DataFrame:
    metrics = [
        (
            "Tables Enriched",
            tables_processed,
            "Only configured investigation summary and lead tables.",
        ),
        (
            "SDR Candidate Rows",
            sdr_raw_rows,
            "Non-empty subscriber/mobile values encountered.",
        ),
        (
            "SDR Eligible Unique Mobiles",
            len(
                sdr_eligible_values
            ),
            "Valid normalized 10-digit Indian mobile numbers.",
        ),
        (
            "SDR Profiles Found",
            len(
                sdr_found_values
            ),
            "Unique mobiles matched in primary or historical SDR master data.",
        ),
        (
            "SDR Profiles Not Found",
            max(
                len(
                    sdr_eligible_values
                )
                - len(
                    sdr_found_values
                ),
                0,
            ),
            "Eligible mobiles with no SDR master-data match.",
        ),
        (
            "Non-standard SDR Identifiers",
            sdr_invalid_rows,
            "IMSI, user IDs, IP values and invalid numbers excluded from SDR lookup.",
        ),
        (
            "CGI Candidate Rows",
            cgi_raw_rows,
            "Non-empty configured CGI/Cell values encountered.",
        ),
        (
            "CGI Eligible Unique Keys",
            len(
                cgi_eligible_values
            ),
            "Unique normalized CGI/Cell lookup keys.",
        ),
        (
            "CGI Records Found",
            len(
                cgi_found_values
            ),
            "Unique CGI keys matched in the master database.",
        ),
        (
            "CGI Records Not Found",
            max(
                len(
                    cgi_eligible_values
                )
                - len(
                    cgi_found_values
                ),
                0,
            ),
            "Normalized CGI keys without a master-data record.",
        ),
        (
            "Enrichment Warnings",
            len(
                warnings
            ),
            "Lookup errors do not stop core telecom analysis.",
        ),
    ]

    return pd.DataFrame(
        metrics,
        columns=[
            "Metric",
            "Value",
            "Meaning",
        ],
    )


def enrich_analysis_bundle(
    bundle: Mapping[str, Any],
    *,
    table_specs: Mapping[
        str,
        Mapping[str, Iterable[str]],
    ],
) -> dict[str, Any]:
    """
    Enrich configured analysis tables with one batch SDR and CGI lookup.

    Scalar values and unconfigured heavy evidence tables are preserved.
    Every DataFrame is copied before enrichment.
    """

    output: dict[str, Any] = {}

    for key, value in bundle.items():
        output[
            key
        ] = (
            value.copy()
            if isinstance(
                value,
                pd.DataFrame,
            )
            else value
        )

    sdr_values: set[str] = set()
    cgi_values: set[str] = set()

    sdr_raw_rows = 0
    cgi_raw_rows = 0
    sdr_invalid_rows = 0
    tables_processed = 0

    resolved_specs: dict[
        str,
        dict[str, list[str]],
    ] = {}

    for table_key, requested in table_specs.items():
        dataframe = output.get(
            table_key
        )

        if (
            not isinstance(
                dataframe,
                pd.DataFrame,
            )
            or dataframe.empty
        ):
            continue

        sdr_columns = _existing_columns(
            dataframe,
            requested.get(
                "sdr",
                (),
            ),
        )

        cgi_columns = _existing_columns(
            dataframe,
            requested.get(
                "cgi",
                (),
            ),
        )

        if (
            not sdr_columns
            and not cgi_columns
        ):
            continue

        resolved_specs[
            table_key
        ] = {
            "sdr": sdr_columns,
            "cgi": cgi_columns,
        }

        tables_processed += 1

        for column in sdr_columns:
            raw = (
                dataframe[
                    column
                ]
                .fillna(
                    ""
                )
                .astype(
                    str
                )
                .str.strip()
            )

            normalized = dataframe[
                column
            ].map(
                _valid_mobile_key
            )

            nonempty = raw.ne(
                ""
            )

            sdr_raw_rows += int(
                nonempty.sum()
            )

            sdr_invalid_rows += int(
                (
                    nonempty
                    & normalized.eq(
                        ""
                    )
                ).sum()
            )

            sdr_values.update(
                normalized[
                    normalized.ne(
                        ""
                    )
                ].tolist()
            )

        for column in cgi_columns:
            raw = (
                dataframe[
                    column
                ]
                .fillna(
                    ""
                )
                .astype(
                    str
                )
                .str.strip()
            )

            normalized = dataframe[
                column
            ].map(
                _valid_cgi_key
            )

            cgi_raw_rows += int(
                raw.ne(
                    ""
                ).sum()
            )

            cgi_values.update(
                normalized[
                    normalized.ne(
                        ""
                    )
                ].tolist()
            )

    warnings: list[str] = []
    sdr_failed = False
    cgi_failed = False

    try:
        sdr_lookup = (
            lookup_sdr_subscribers(
                sorted(
                    sdr_values
                )
            )
            if sdr_values
            else pd.DataFrame()
        )

    except Exception as error:
        sdr_lookup = pd.DataFrame()
        sdr_failed = True

        warnings.append(
            "SDR enrichment failed; core analysis was preserved. "
            f"{type(error).__name__}: {error}"
        )

    try:
        cgi_lookup = (
            lookup_cgi_addresses(
                sorted(
                    cgi_values
                )
            )
            if cgi_values
            else pd.DataFrame()
        )

    except Exception as error:
        cgi_lookup = pd.DataFrame()
        cgi_failed = True

        warnings.append(
            "CGI enrichment failed; core analysis was preserved. "
            f"{type(error).__name__}: {error}"
        )

    sdr_lookup = _lookup_map_frame(
        sdr_lookup,
        key_column="lookup_mobile",
    )

    cgi_lookup = _lookup_map_frame(
        cgi_lookup,
        key_column="cgi",
    )

    sdr_found_values: set[str] = set()

    if not sdr_lookup.empty:
        if "sdr_found" in sdr_lookup.columns:
            found_rows = sdr_lookup[
                sdr_lookup[
                    "sdr_found"
                ]
                .fillna(
                    ""
                )
                .astype(
                    str
                )
                .str.upper()
                .eq(
                    "YES"
                )
            ]
        else:
            found_rows = sdr_lookup

        sdr_found_values = set(
            found_rows[
                "lookup_mobile"
            ].astype(
                str
            )
        )

    cgi_found_values: set[str] = set()

    if not cgi_lookup.empty:
        cgi_found_values = set(
            cgi_lookup[
                "cgi"
            ].astype(
                str
            )
        )

    for table_key, resolved in resolved_specs.items():
        dataframe = output[
            table_key
        ]

        for column in resolved[
            "sdr"
        ]:
            dataframe = _apply_sdr_lookup(
                dataframe,
                number_column=column,
                lookup=sdr_lookup,
                lookup_failed=sdr_failed,
            )

        for column in resolved[
            "cgi"
        ]:
            dataframe = _apply_cgi_lookup(
                dataframe,
                cell_column=column,
                lookup=cgi_lookup,
                lookup_failed=cgi_failed,
            )

        output[
            table_key
        ] = dataframe

    summary = _summary_frame(
        tables_processed=tables_processed,
        sdr_raw_rows=sdr_raw_rows,
        sdr_eligible_values=sdr_values,
        sdr_found_values=sdr_found_values,
        sdr_invalid_rows=sdr_invalid_rows,
        cgi_raw_rows=cgi_raw_rows,
        cgi_eligible_values=cgi_values,
        cgi_found_values=cgi_found_values,
        warnings=warnings,
    )

    return {
        "bundle": output,
        "summary": summary,
        "warnings": warnings,
    }

def build_missing_cgi_summary_from_bundle(
    bundle: Mapping[str, Any],
    *,
    table_specs: Mapping[
        str,
        Mapping[str, Iterable[str]],
    ],
) -> pd.DataFrame:
    """
    Build a missing CGI summary from already-enriched tables.

    No additional database lookup is performed.
    """

    rows = []

    for table_key, specification in table_specs.items():
        dataframe = bundle.get(
            table_key
        )

        if (
            not isinstance(
                dataframe,
                pd.DataFrame,
            )
            or dataframe.empty
        ):
            continue

        cgi_columns = _existing_columns(
            dataframe,
            specification.get(
                "cgi",
                (),
            ),
        )

        for cell_column in cgi_columns:
            prefix = _cgi_prefix(
                cell_column
            )

            status_column = (
                f"{prefix}lookup_status"
            )

            if status_column not in dataframe.columns:
                continue

            missing = dataframe[
                dataframe[
                    status_column
                ]
                .fillna(
                    ""
                )
                .astype(
                    str
                )
                .str.upper()
                .eq(
                    "NOT_FOUND"
                )
            ]

            if missing.empty:
                continue

            grouped = (
                missing.groupby(
                    cell_column,
                    dropna=False,
                )
                .size()
                .reset_index(
                    name="records"
                )
                .rename(
                    columns={
                        cell_column: "cell_id",
                    }
                )
            )

            grouped[
                "source_table"
            ] = table_key

            rows.append(
                grouped
            )

    if not rows:
        return pd.DataFrame(
            columns=[
                "cell_id",
                "records",
                "source_table",
            ]
        )

    result = pd.concat(
        rows,
        ignore_index=True,
    )

    return (
        result.groupby(
            [
                "cell_id",
                "source_table",
            ],
            dropna=False,
        )[
            "records"
        ]
        .sum()
        .reset_index()
        .sort_values(
            [
                "records",
                "cell_id",
            ],
            ascending=[
                False,
                True,
            ],
        )
        .reset_index(
            drop=True
        )
    )
