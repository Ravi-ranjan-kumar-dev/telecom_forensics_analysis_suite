"""Multi-Spot Tower CDR investigation analysis.

This module compares subscriber, IMEI and IMSI presence across
investigation Spot folders. A Spot is identified by the canonical
`spot_id` and `spot_name` columns attached by the Tower CDR loader.

Important interpretation:
- A telecom record indicates network-record presence.
- It does not independently prove the physical presence, identity,
  movement or participation of a person.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


EXCLUDED_SPOT_IDS = {
    "",
    "UNASSIGNED-ROOT",
}


def _clean_text(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .replace(
            {
                "nan": "",
                "None": "",
                "<NA>": "",
            }
        )
    )


def _join_unique(values: pd.Series) -> str:
    cleaned = _clean_text(values)

    return ", ".join(
        sorted(
            {
                value
                for value in cleaned
                if value
            }
        )
    )


def _unique_values(values: pd.Series) -> list[str]:
    return sorted(
        {
            value
            for value in _clean_text(values)
            if value
        }
    )


def _prepare_multi_spot_dataframe(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Return validated and normalized Multi-Spot analysis input."""

    if not isinstance(
        dataframe,
        pd.DataFrame,
    ):
        raise TypeError(
            "Multi-Spot analysis requires a pandas DataFrame."
        )

    required = {
        "subscriber_number",
        "spot_id",
    }

    missing = sorted(
        required.difference(
            dataframe.columns
        )
    )

    if missing:
        raise ValueError(
            "Multi-Spot analysis ke liye required column(s) "
            f"missing hain: {', '.join(missing)}"
        )

    # Already-normalized DataFrame ko baar-baar copy aur clean
    # karne se bachata hai.
    if dataframe.attrs.get(
        "_tower_multi_spot_prepared_v2"
    ) is True:
        return dataframe

    work = dataframe.copy()

    optional_columns = (
        "spot_name",
        "operator",
        "searched_cell_id",
        "imei",
        "imsi",
        "call_datetime",
        "source_file",
        "source_relative_path",
    )

    for column in optional_columns:
        if column not in work.columns:
            work[column] = ""

    work["subscriber_number"] = _clean_text(
        work["subscriber_number"]
    )
    work["spot_id"] = _clean_text(
        work["spot_id"]
    )
    work["spot_name"] = _clean_text(
        work["spot_name"]
    )

    work["spot_name"] = work[
        "spot_name"
    ].where(
        work["spot_name"].ne(""),
        work["spot_id"],
    )

    for column in (
        "operator",
        "searched_cell_id",
        "imei",
        "imsi",
        "source_file",
        "source_relative_path",
    ):
        work[column] = _clean_text(
            work[column]
        )

    work["call_datetime"] = pd.to_datetime(
        work["call_datetime"],
        errors="coerce",
    )

    valid_mask = (
        work["subscriber_number"].ne("")
        & ~work["spot_id"].isin(
            EXCLUDED_SPOT_IDS
        )
    )

    result = work.loc[
        valid_mask
    ].copy()

    result.attrs[
        "_tower_multi_spot_prepared_v2"
    ] = True

    return result

def _group_joined_unique(
    dataframe: pd.DataFrame,
    *,
    group_columns: list[str],
    value_column: str,
    output_column: str,
) -> pd.DataFrame:
    """Join distinct non-empty values without Python group loops."""

    output_columns = [
        *group_columns,
        output_column,
    ]

    if dataframe.empty:
        return pd.DataFrame(
            columns=output_columns
        )

    unique_rows = (
        dataframe.loc[
            dataframe[
                value_column
            ].ne(""),
            [
                *group_columns,
                value_column,
            ],
        ]
        .drop_duplicates()
    )

    if unique_rows.empty:
        return pd.DataFrame(
            columns=output_columns
        )

    unique_rows = unique_rows.sort_values(
        [
            *group_columns,
            value_column,
        ],
        kind="stable",
    )

    return (
        unique_rows.groupby(
            group_columns,
            sort=False,
            dropna=False,
            observed=True,
        )[
            value_column
        ]
        .agg(", ".join)
        .reset_index(
            name=output_column
        )
    )



def filter_multi_spot_time_range(
    dataframe: pd.DataFrame,
    *,
    start_time: Any,
    end_time: Any,
) -> pd.DataFrame:
    """Filter using a half-open date-time range.

    Rule:
        start_time <= call_datetime < end_time
    """

    work = _prepare_multi_spot_dataframe(
        dataframe
    )

    start = pd.to_datetime(
        start_time,
        errors="coerce",
    )
    end = pd.to_datetime(
        end_time,
        errors="coerce",
    )

    if pd.isna(start) or pd.isna(end):
        raise ValueError(
            "Valid Start aur End Date-Time required hain."
        )

    if end <= start:
        raise ValueError(
            "End Date-Time, Start Date-Time ke baad hona chahiye."
        )

    mask = work["call_datetime"].between(
        start,
        end,
        inclusive="left",
    )

    return work.loc[
        mask
    ].copy()


def build_spot_summary(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Build investigation-friendly Spot coverage summary."""

    work = _prepare_multi_spot_dataframe(
        dataframe
    )

    columns = [
        "spot_id",
        "spot_name",
        "records",
        "unique_subscribers",
        "unique_searched_cells",
        "source_files",
        "operators",
        "first_record",
        "last_record",
    ]

    if work.empty:
        return pd.DataFrame(
            columns=columns
        )

    rows: list[dict[str, Any]] = []

    for (
        spot_id,
        spot_name,
    ), group in work.groupby(
        [
            "spot_id",
            "spot_name",
        ],
        sort=True,
        dropna=False,
    ):
        datetimes = group[
            "call_datetime"
        ].dropna()

        rows.append(
            {
                "spot_id": spot_id,
                "spot_name": spot_name,
                "records": len(group),
                "unique_subscribers": int(
                    group[
                        "subscriber_number"
                    ].nunique()
                ),
                "unique_searched_cells": int(
                    group[
                        "searched_cell_id"
                    ]
                    .replace("", pd.NA)
                    .nunique(
                        dropna=True
                    )
                ),
                "source_files": int(
                    group[
                        "source_relative_path"
                    ]
                    .replace("", pd.NA)
                    .nunique(
                        dropna=True
                    )
                ),
                "operators": _join_unique(
                    group["operator"]
                ),
                "first_record": (
                    datetimes.min()
                    if not datetimes.empty
                    else pd.NaT
                ),
                "last_record": (
                    datetimes.max()
                    if not datetimes.empty
                    else pd.NaT
                ),
            }
        )

    return pd.DataFrame(
        rows,
        columns=columns,
    ).sort_values(
        [
            "spot_id",
            "spot_name",
        ],
        ignore_index=True,
    )


def build_subscriber_spot_detail(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Build one vectorized row per subscriber per Spot."""

    work = _prepare_multi_spot_dataframe(
        dataframe
    )

    columns = [
        "subscriber_number",
        "spot_id",
        "spot_name",
        "event_count",
        "unique_searched_cells",
        "operators",
        "imei_count",
        "imsi_count",
        "first_seen",
        "last_seen",
    ]

    if work.empty:
        return pd.DataFrame(
            columns=columns
        )

    group_columns = [
        "subscriber_number",
        "spot_id",
        "spot_name",
    ]

    aggregate_source = work.assign(
        _searched_cell=work[
            "searched_cell_id"
        ].replace(
            "",
            pd.NA,
        ),
        _imei=work[
            "imei"
        ].replace(
            "",
            pd.NA,
        ),
        _imsi=work[
            "imsi"
        ].replace(
            "",
            pd.NA,
        ),
    )

    result = (
        aggregate_source.groupby(
            group_columns,
            sort=False,
            dropna=False,
            observed=True,
        )
        .agg(
            event_count=(
                "subscriber_number",
                "size",
            ),
            unique_searched_cells=(
                "_searched_cell",
                "nunique",
            ),
            imei_count=(
                "_imei",
                "nunique",
            ),
            imsi_count=(
                "_imsi",
                "nunique",
            ),
            first_seen=(
                "call_datetime",
                "min",
            ),
            last_seen=(
                "call_datetime",
                "max",
            ),
        )
        .reset_index()
    )

    operator_table = (
        _group_joined_unique(
            work,
            group_columns=group_columns,
            value_column="operator",
            output_column="operators",
        )
    )

    result = result.merge(
        operator_table,
        on=group_columns,
        how="left",
        validate="one_to_one",
    )

    result["operators"] = result[
        "operators"
    ].fillna("")

    return result[
        columns
    ].sort_values(
        [
            "subscriber_number",
            "spot_id",
        ],
        ignore_index=True,
    )



def build_subscriber_spot_presence(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Build vectorized N-of-M Spot presence matrix."""

    work = _prepare_multi_spot_dataframe(
        dataframe
    )

    detail = build_subscriber_spot_detail(
        work
    )

    spot_catalog = (
        work[
            [
                "spot_id",
                "spot_name",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            [
                "spot_id",
                "spot_name",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    total_spots = len(
        spot_catalog
    )

    base_columns = [
        "subscriber_number",
        "spots_seen_count",
        "total_spots",
        "match_ratio",
        "spot_ids",
        "spot_names",
        "total_events",
        "unique_searched_cells",
        "operators",
        "imei_count",
        "imsi_count",
        "first_seen",
        "last_seen",
    ]

    dynamic_columns: list[str] = []

    for spot_id in spot_catalog[
        "spot_id"
    ]:
        dynamic_columns.extend(
            [
                f"{spot_id}_present",
                f"{spot_id}_events",
            ]
        )

    if work.empty or detail.empty:
        return pd.DataFrame(
            columns=[
                *base_columns,
                *dynamic_columns,
            ]
        )

    presence = (
        detail.groupby(
            "subscriber_number",
            sort=False,
            observed=True,
        )
        .agg(
            spots_seen_count=(
                "spot_id",
                "nunique",
            ),
            total_events=(
                "event_count",
                "sum",
            ),
        )
        .reset_index()
    )

    aggregate_source = work.assign(
        _searched_cell=work[
            "searched_cell_id"
        ].replace(
            "",
            pd.NA,
        ),
        _imei=work[
            "imei"
        ].replace(
            "",
            pd.NA,
        ),
        _imsi=work[
            "imsi"
        ].replace(
            "",
            pd.NA,
        ),
    )

    subscriber_stats = (
        aggregate_source.groupby(
            "subscriber_number",
            sort=False,
            observed=True,
        )
        .agg(
            unique_searched_cells=(
                "_searched_cell",
                "nunique",
            ),
            imei_count=(
                "_imei",
                "nunique",
            ),
            imsi_count=(
                "_imsi",
                "nunique",
            ),
            first_seen=(
                "call_datetime",
                "min",
            ),
            last_seen=(
                "call_datetime",
                "max",
            ),
        )
        .reset_index()
    )

    spot_ids = _group_joined_unique(
        detail,
        group_columns=[
            "subscriber_number",
        ],
        value_column="spot_id",
        output_column="spot_ids",
    )

    spot_names = _group_joined_unique(
        detail,
        group_columns=[
            "subscriber_number",
        ],
        value_column="spot_name",
        output_column="spot_names",
    )

    operators = _group_joined_unique(
        work,
        group_columns=[
            "subscriber_number",
        ],
        value_column="operator",
        output_column="operators",
    )

    presence = presence.merge(
        subscriber_stats,
        on="subscriber_number",
        how="left",
        validate="one_to_one",
    )

    for table in (
        spot_ids,
        spot_names,
        operators,
    ):
        presence = presence.merge(
            table,
            on="subscriber_number",
            how="left",
            validate="one_to_one",
        )

    event_pivot = detail.pivot_table(
        index="subscriber_number",
        columns="spot_id",
        values="event_count",
        aggfunc="sum",
        fill_value=0,
        observed=True,
    ).reset_index()

    rename_columns = {
        str(spot_id): (
            f"{spot_id}_events"
        )
        for spot_id in spot_catalog[
            "spot_id"
        ]
    }

    event_pivot = event_pivot.rename(
        columns=rename_columns
    )

    presence = presence.merge(
        event_pivot,
        on="subscriber_number",
        how="left",
        validate="one_to_one",
    )

    presence["total_spots"] = int(
        total_spots
    )

    presence["match_ratio"] = (
        presence[
            "spots_seen_count"
        ]
        .astype("int64")
        .astype(str)
        + "/"
        + str(total_spots)
    )

    for column in (
        "spot_ids",
        "spot_names",
        "operators",
    ):
        presence[column] = presence[
            column
        ].fillna("")

    for spot_id in spot_catalog[
        "spot_id"
    ]:
        event_column = (
            f"{spot_id}_events"
        )
        present_column = (
            f"{spot_id}_present"
        )

        if event_column not in presence.columns:
            presence[event_column] = 0

        presence[event_column] = (
            pd.to_numeric(
                presence[event_column],
                errors="coerce",
            )
            .fillna(0)
            .astype("int64")
        )

        presence[present_column] = (
            presence[event_column]
            .gt(0)
            .astype("int64")
        )

    return presence[
        [
            *base_columns,
            *dynamic_columns,
        ]
    ].sort_values(
        [
            "spots_seen_count",
            "total_events",
            "subscriber_number",
        ],
        ascending=[
            False,
            False,
            True,
        ],
        ignore_index=True,
    )



def build_cross_spot_device_continuity(
    dataframe: pd.DataFrame,
    subscriber_presence: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Evaluate vectorized IMEI/IMSI continuity across Spots."""

    work = _prepare_multi_spot_dataframe(
        dataframe
    )

    presence = (
        subscriber_presence.copy()
        if isinstance(
            subscriber_presence,
            pd.DataFrame,
        )
        else build_subscriber_spot_presence(
            work
        )
    )

    columns = [
        "subscriber_number",
        "spots_seen_count",
        "spot_names",
        "imei_count",
        "imei_values",
        "imei_continuity",
        "imsi_count",
        "imsi_values",
        "imsi_continuity",
        "confidence",
        "why_important",
        "next_verification",
    ]

    if work.empty or presence.empty:
        return pd.DataFrame(
            columns=columns
        )

    candidates = presence.loc[
        presence[
            "spots_seen_count"
        ].ge(2),
        [
            "subscriber_number",
            "spots_seen_count",
            "spot_names",
        ],
    ].copy()

    if candidates.empty:
        return pd.DataFrame(
            columns=columns
        )

    candidate_numbers = candidates[
        "subscriber_number"
    ]

    records = work.loc[
        work[
            "subscriber_number"
        ].isin(
            candidate_numbers
        )
    ]

    aggregate_source = records.assign(
        _imei=records[
            "imei"
        ].replace(
            "",
            pd.NA,
        ),
        _imsi=records[
            "imsi"
        ].replace(
            "",
            pd.NA,
        ),
    )

    identifier_counts = (
        aggregate_source.groupby(
            "subscriber_number",
            sort=False,
            observed=True,
        )
        .agg(
            imei_count=(
                "_imei",
                "nunique",
            ),
            imsi_count=(
                "_imsi",
                "nunique",
            ),
        )
        .reset_index()
    )

    imei_values = _group_joined_unique(
        records,
        group_columns=[
            "subscriber_number",
        ],
        value_column="imei",
        output_column="imei_values",
    )

    imsi_values = _group_joined_unique(
        records,
        group_columns=[
            "subscriber_number",
        ],
        value_column="imsi",
        output_column="imsi_values",
    )

    result = candidates.merge(
        identifier_counts,
        on="subscriber_number",
        how="left",
        validate="one_to_one",
    )

    result = result.merge(
        imei_values,
        on="subscriber_number",
        how="left",
        validate="one_to_one",
    )

    result = result.merge(
        imsi_values,
        on="subscriber_number",
        how="left",
        validate="one_to_one",
    )

    for column in (
        "imei_count",
        "imsi_count",
    ):
        result[column] = (
            pd.to_numeric(
                result[column],
                errors="coerce",
            )
            .fillna(0)
            .astype("int64")
        )

    for column in (
        "imei_values",
        "imsi_values",
    ):
        result[column] = result[
            column
        ].fillna("")

    result["imei_continuity"] = result[
        "imei_count"
    ].map(
        {
            0: "IMEI NOT AVAILABLE",
            1: "SAME IMEI ACROSS SPOTS",
        }
    ).fillna(
        "MULTIPLE IMEI ACROSS SPOTS"
    )

    result["imsi_continuity"] = result[
        "imsi_count"
    ].map(
        {
            0: "IMSI NOT AVAILABLE",
            1: "SAME IMSI ACROSS SPOTS",
        }
    ).fillna(
        "MULTIPLE IMSI ACROSS SPOTS"
    )

    same_imei = result[
        "imei_count"
    ].eq(1)

    same_imsi = result[
        "imsi_count"
    ].eq(1)

    result["confidence"] = "LOW"

    result.loc[
        same_imei | same_imsi,
        "confidence",
    ] = "MEDIUM"

    result.loc[
        same_imei & same_imsi,
        "confidence",
    ] = "HIGH"

    result["why_important"] = (
        "Same subscriber number ka device/SIM identifier "
        "multiple Spots ke telecom records mein compare kiya gaya."
    )

    result["next_verification"] = (
        "Operator records, SDR/CAF, handset seizure aur "
        "case timeline se independently verify karein."
    )

    return result[
        columns
    ].sort_values(
        [
            "confidence",
            "spots_seen_count",
            "subscriber_number",
        ],
        ascending=[
            True,
            False,
            True,
        ],
        ignore_index=True,
    )



def build_shared_identifier_across_spots(
    dataframe: pd.DataFrame,
    *,
    identifier_column: str,
) -> pd.DataFrame:
    """Find one IMEI/IMSI appearing across multiple Spots."""

    work = _prepare_multi_spot_dataframe(
        dataframe
    )

    columns = [
        identifier_column,
        "spots_seen_count",
        "spot_names",
        "unique_subscribers",
        "subscriber_numbers",
        "total_events",
        "first_seen",
        "last_seen",
        "why_important",
        "next_verification",
    ]

    if identifier_column not in {
        "imei",
        "imsi",
    }:
        raise ValueError(
            "identifier_column must be 'imei' or 'imsi'."
        )

    work = work.loc[
        work[
            identifier_column
        ].ne("")
    ]

    if work.empty:
        return pd.DataFrame(
            columns=columns
        )

    summary = (
        work.groupby(
            identifier_column,
            sort=False,
            observed=True,
        )
        .agg(
            spots_seen_count=(
                "spot_id",
                "nunique",
            ),
            unique_subscribers=(
                "subscriber_number",
                "nunique",
            ),
            total_events=(
                identifier_column,
                "size",
            ),
            first_seen=(
                "call_datetime",
                "min",
            ),
            last_seen=(
                "call_datetime",
                "max",
            ),
        )
        .reset_index()
    )

    summary = summary.loc[
        summary[
            "spots_seen_count"
        ].ge(2)
    ].copy()

    if summary.empty:
        return pd.DataFrame(
            columns=columns
        )

    valid_identifiers = summary[
        identifier_column
    ]

    relevant = work.loc[
        work[
            identifier_column
        ].isin(
            valid_identifiers
        )
    ]

    spot_names = _group_joined_unique(
        relevant,
        group_columns=[
            identifier_column,
        ],
        value_column="spot_name",
        output_column="spot_names",
    )

    subscriber_numbers = (
        _group_joined_unique(
            relevant,
            group_columns=[
                identifier_column,
            ],
            value_column="subscriber_number",
            output_column="subscriber_numbers",
        )
    )

    result = summary.merge(
        spot_names,
        on=identifier_column,
        how="left",
        validate="one_to_one",
    )

    result = result.merge(
        subscriber_numbers,
        on=identifier_column,
        how="left",
        validate="one_to_one",
    )

    result["spot_names"] = result[
        "spot_names"
    ].fillna("")

    result["subscriber_numbers"] = result[
        "subscriber_numbers"
    ].fillna("")

    result["why_important"] = (
        f"Same {identifier_column.upper()} multiple Spots "
        "ke telecom records mein mila."
    )

    result["next_verification"] = (
        "Operator export semantics, device/SIM ownership "
        "aur source-data quality verify karein."
    )

    return result[
        columns
    ].sort_values(
        [
            "spots_seen_count",
            "unique_subscribers",
            "total_events",
        ],
        ascending=[
            False,
            False,
            False,
        ],
        ignore_index=True,
    )



def build_cross_spot_sequence(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Build time-ordered telecom-record transitions between Spots."""

    work = _prepare_multi_spot_dataframe(
        dataframe
    )

    columns = [
        "subscriber_number",
        "from_spot_id",
        "from_spot_name",
        "to_spot_id",
        "to_spot_name",
        "from_record_time",
        "to_record_time",
        "time_gap_seconds",
        "time_gap_minutes",
        "imei",
        "imsi",
        "operator",
        "interpretation",
        "caution",
    ]

    work = work.loc[
        work[
            "call_datetime"
        ].notna()
    ].copy()

    if work.empty:
        return pd.DataFrame(
            columns=columns
        )

    work = work.sort_values(
        [
            "subscriber_number",
            "call_datetime",
            "spot_id",
        ],
        kind="stable",
    ).reset_index(
        drop=True
    )

    grouped = work.groupby(
        "subscriber_number",
        sort=False,
    )

    work["previous_spot_id"] = grouped[
        "spot_id"
    ].shift()
    work["previous_spot_name"] = grouped[
        "spot_name"
    ].shift()
    work["previous_record_time"] = grouped[
        "call_datetime"
    ].shift()

    changed = work.loc[
        work[
            "previous_spot_id"
        ].notna()
        & work[
            "previous_spot_id"
        ].ne(
            work[
                "spot_id"
            ]
        )
    ].copy()

    if changed.empty:
        return pd.DataFrame(
            columns=columns
        )

    changed[
        "time_gap_seconds"
    ] = (
        changed["call_datetime"]
        - changed[
            "previous_record_time"
        ]
    ).dt.total_seconds()

    changed = changed.loc[
        changed[
            "time_gap_seconds"
        ].ge(
            0
        )
    ].copy()

    result = pd.DataFrame(
        {
            "subscriber_number": changed[
                "subscriber_number"
            ],
            "from_spot_id": changed[
                "previous_spot_id"
            ],
            "from_spot_name": changed[
                "previous_spot_name"
            ],
            "to_spot_id": changed[
                "spot_id"
            ],
            "to_spot_name": changed[
                "spot_name"
            ],
            "from_record_time": changed[
                "previous_record_time"
            ],
            "to_record_time": changed[
                "call_datetime"
            ],
            "time_gap_seconds": changed[
                "time_gap_seconds"
            ],
            "time_gap_minutes": (
                changed[
                    "time_gap_seconds"
                ]
                / 60
            ).round(
                2
            ),
            "imei": changed["imei"],
            "imsi": changed["imsi"],
            "operator": changed[
                "operator"
            ],
            "interpretation": (
                "Time-ordered telecom-record presence "
                "across different Spots."
            ),
            "caution": (
                "Yeh exact physical movement ya person identity "
                "ka independent proof nahi hai."
            ),
        }
    )

    return result.sort_values(
        [
            "time_gap_seconds",
            "subscriber_number",
            "to_record_time",
        ],
        ascending=[
            True,
            True,
            True,
        ],
        ignore_index=True,
    )


def build_multi_spot_analysis(
    dataframe: pd.DataFrame,
    *,
    start_time: Any | None = None,
    end_time: Any | None = None,
) -> dict[str, Any]:
    """Build complete whole-period or selected Date-Time analysis."""

    if (
        start_time is None
    ) != (
        end_time is None
    ):
        raise ValueError(
            "Start aur End Date-Time dono dena required hai."
        )

    if (
        start_time is not None
        and end_time is not None
    ):
        work = filter_multi_spot_time_range(
            dataframe,
            start_time=start_time,
            end_time=end_time,
        )
        time_scope = "SELECTED_DATE_TIME"
    else:
        work = _prepare_multi_spot_dataframe(
            dataframe
        )
        time_scope = "WHOLE_PERIOD"

    spot_summary = build_spot_summary(
        work
    )
    spot_detail = build_subscriber_spot_detail(
        work
    )
    presence = build_subscriber_spot_presence(
        work
    )

    total_spots = len(
        spot_summary
    )

    if presence.empty:
        n_of_m = presence.copy()
        all_spot_common = presence.copy()
        exclusive = presence.copy()
    else:
        n_of_m = presence.loc[
            presence[
                "spots_seen_count"
            ].ge(
                2
            )
        ].copy()

        all_spot_common = presence.loc[
            presence[
                "spots_seen_count"
            ].eq(
                total_spots
            )
        ].copy()

        exclusive = presence.loc[
            presence[
                "spots_seen_count"
            ].eq(
                1
            )
        ].copy()

        if not exclusive.empty:
            exclusive[
                "exclusive_spot_id"
            ] = exclusive[
                "spot_ids"
            ]
            exclusive[
                "exclusive_spot_name"
            ] = exclusive[
                "spot_names"
            ]

    device_continuity = (
        build_cross_spot_device_continuity(
            work,
            subscriber_presence=presence,
        )
    )

    shared_imei = (
        build_shared_identifier_across_spots(
            work,
            identifier_column="imei",
        )
    )

    shared_imsi = (
        build_shared_identifier_across_spots(
            work,
            identifier_column="imsi",
        )
    )

    sequence = build_cross_spot_sequence(
        work
    )

    warnings: list[str] = []

    if total_spots < 2:
        warnings.append(
            "Cross-Spot comparison ke liye kam se kam "
            "do valid Spot folders required hain."
        )

    return {
        "time_scope": time_scope,
        "start_time": start_time,
        "end_time": end_time,
        "total_records": len(work),
        "total_spots": total_spots,
        "spot_summary": spot_summary,
        "subscriber_spot_detail": spot_detail,
        "subscriber_spot_presence": presence,
        "n_of_m_spot_presence": n_of_m,
        "all_spot_common_numbers": all_spot_common,
        "spot_exclusive_numbers": exclusive,
        "cross_spot_device_continuity": device_continuity,
        "shared_imei_across_spots": shared_imei,
        "shared_imsi_across_spots": shared_imsi,
        "cross_spot_sequence": sequence,
        "warnings": warnings,
        "range_rule": (
            "start_time <= call_datetime < end_time"
        ),
    }
