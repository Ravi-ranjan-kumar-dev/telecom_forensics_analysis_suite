"""Tower CDR common/uncommon presence helpers.

This module builds investigator-friendly lead tables:
- common/repeat numbers
- uncommon/new visitor style rare numbers
- multi-cell presence
- device/SIM consistency
- suspicious timing/high activity
- priority leads

The selected-period uncommon wrapper reuses:

    modules.analysis.common.uncommon_numbers
"""

from __future__ import annotations

import pandas as pd

from modules.analysis.common.uncommon_numbers import (
    UncommonNumberConfig,
    find_uncommon_numbers,
    split_current_and_baseline_by_window,
)


TOWER_CDR_UNCOMMON_CONFIG = UncommonNumberConfig(
    entity_col="subscriber_number",
    time_col="call_datetime",
    cell_col="searched_cell_id",
    imei_col="imei",
    imsi_col="imsi",
    source_module="tower_cdr",
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


def find_tower_cdr_uncommon_numbers(
    dataframe: pd.DataFrame,
    *,
    window_start,
    window_end,
    min_score: int = 50,
) -> pd.DataFrame:
    """Find Tower CDR uncommon/new visitor numbers for selected period."""

    current, baseline = split_current_and_baseline_by_window(
        dataframe,
        time_col="call_datetime",
        window_start=window_start,
        window_end=window_end,
    )

    return find_uncommon_numbers(
        current,
        baseline,
        config=TOWER_CDR_UNCOMMON_CONFIG,
        min_score=min_score,
    )


def _empty_presence_tables() -> dict[str, pd.DataFrame]:
    empty = pd.DataFrame()
    return {
        "common_numbers": empty,
        "uncommon_numbers": empty,
        "multi_cell_presence": empty,
        "device_consistency": empty,
        "suspicious_timing": empty,
        "priority_leads": empty,
    }


def build_tower_cdr_presence_intelligence(
    dataframe: pd.DataFrame,
    *,
    top_limit: int = 200,
) -> dict[str, pd.DataFrame]:
    """Build full-dump Tower CDR presence intelligence tables.

    These are investigation leads, not final proof.
    """

    if dataframe is None or dataframe.empty:
        return _empty_presence_tables()

    if "subscriber_number" not in dataframe.columns:
        raise ValueError("subscriber_number column missing in Tower CDR data.")

    work = dataframe.copy()
    work["_subscriber"] = _clean_text(work["subscriber_number"])
    work = work.loc[work["_subscriber"].ne("")].copy()

    if work.empty:
        return _empty_presence_tables()

    if "call_datetime" in work.columns:
        work["_event_time"] = pd.to_datetime(
            work["call_datetime"],
            errors="coerce",
        )
    else:
        work["_event_time"] = pd.NaT

    if "call_duration" in work.columns:
        work["_duration_seconds"] = pd.to_numeric(
            work["call_duration"],
            errors="coerce",
        ).fillna(0)
    else:
        work["_duration_seconds"] = 0

    hour = work["_event_time"].dt.hour
    work["_night_event"] = hour.ge(22) | hour.lt(5)

    grouped = work.groupby("_subscriber", dropna=True)

    summary = grouped.agg(
        event_count=("subscriber_number", "size"),
        first_seen=("_event_time", "min"),
        last_seen=("_event_time", "max"),
        total_duration_seconds=("_duration_seconds", "sum"),
        night_event_count=("_night_event", "sum"),
    ).reset_index().rename(columns={"_subscriber": "subscriber_number"})

    for source_col, output_col in [
        ("searched_cell_id", "searched_cells_seen"),
        ("first_cell_id", "first_cells_seen"),
        ("imei", "imei_count"),
        ("imsi", "imsi_count"),
        ("other_party", "other_party_count"),
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
        ("operator", "operators"),
        ("call_type", "call_types"),
        ("searched_cell_id", "searched_cells"),
        ("first_cell_id", "first_cells"),
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
        "searched_cells_seen",
        "first_cells_seen",
        "imei_count",
        "imsi_count",
        "other_party_count",
        "night_event_count",
    ]:
        summary[col] = summary[col].fillna(0).astype(int)

    summary["cells_seen"] = summary[
        ["searched_cells_seen", "first_cells_seen"]
    ].max(axis=1)

    summary["priority_score"] = 0
    summary.loc[summary["event_count"].eq(1), "priority_score"] += 25
    summary.loc[summary["cells_seen"].ge(2), "priority_score"] += 35
    summary.loc[summary["event_count"].ge(5), "priority_score"] += 25
    summary.loc[summary["imei_count"].ge(2), "priority_score"] += 20
    summary.loc[summary["imsi_count"].ge(2), "priority_score"] += 20
    summary.loc[summary["other_party_count"].ge(5), "priority_score"] += 15
    summary.loc[summary["night_event_count"].ge(1), "priority_score"] += 15

    def _priority(score: int) -> str:
        if score >= 70:
            return "High"
        if score >= 45:
            return "Medium"
        return "Low"

    def _confidence(row: pd.Series) -> str:
        if int(row.get("cells_seen", 0) or 0) >= 2 and int(row.get("event_count", 0) or 0) >= 2:
            return "High"
        if int(row.get("event_count", 0) or 0) >= 2:
            return "Medium"
        return "Low"

    def _reason(row: pd.Series) -> str:
        reasons: list[str] = []

        if int(row.get("event_count", 0) or 0) == 1:
            reasons.append("single-event/rare presence")

        if int(row.get("cells_seen", 0) or 0) >= 2:
            reasons.append("multi-cell presence")

        if int(row.get("event_count", 0) or 0) >= 5:
            reasons.append("repeat/high activity")

        if int(row.get("imei_count", 0) or 0) >= 2:
            reasons.append("multiple IMEI")

        if int(row.get("imsi_count", 0) or 0) >= 2:
            reasons.append("multiple IMSI")

        if int(row.get("night_event_count", 0) or 0) >= 1:
            reasons.append("night-time activity")

        return ", ".join(reasons) if reasons else "low-priority presence"

    summary["priority"] = summary["priority_score"].apply(_priority)
    summary["confidence"] = summary.apply(_confidence, axis=1)
    summary["why_important"] = summary.apply(_reason, axis=1)
    summary["next_action"] = (
        "Verify with CDR/SDR/CAF, IMEI/IMSI, tower location, call context and field/local input."
    )

    common_numbers = summary.loc[
        summary["event_count"].ge(2)
    ].sort_values(
        ["event_count", "cells_seen", "other_party_count"],
        ascending=[False, False, False],
    ).head(top_limit).reset_index(drop=True)

    uncommon_numbers = summary.loc[
        summary["event_count"].eq(1)
    ].sort_values(
        ["cells_seen", "night_event_count", "first_seen"],
        ascending=[False, False, True],
    ).head(top_limit).reset_index(drop=True)

    multi_cell_presence = summary.loc[
        summary["cells_seen"].ge(2)
    ].sort_values(
        ["cells_seen", "event_count", "other_party_count"],
        ascending=[False, False, False],
    ).head(top_limit).reset_index(drop=True)

    device_consistency = summary.sort_values(
        ["imei_count", "imsi_count", "event_count"],
        ascending=[False, False, False],
    ).head(top_limit).reset_index(drop=True)

    suspicious_timing = summary.sort_values(
        ["night_event_count", "event_count", "cells_seen"],
        ascending=[False, False, False],
    ).head(top_limit).reset_index(drop=True)

    priority_leads = summary.sort_values(
        ["priority_score", "cells_seen", "event_count", "night_event_count"],
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


# ===========================================================================
# SPOT-WISE PRESENCE INTELLIGENCE
# ===========================================================================

def build_tower_cdr_spot_intelligence(
    dataframe: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Build investigator-friendly Spot-wise Tower CDR intelligence.

    This analysis compares every subscriber separately at every uploaded
    Spot. It does not declare a person to be an outsider or suspect.
    Results are investigative leads requiring CDR/SDR/IMEI and field
    verification.
    """

    output_keys = (
        "spot_presence",
        "cross_spot_presence",
        "spot_priority_leads",
    )

    empty_output = {
        key: pd.DataFrame()
        for key in output_keys
    }

    if (
        not isinstance(dataframe, pd.DataFrame)
        or dataframe.empty
    ):
        return empty_output

    required_columns = {
        "subscriber_number",
        "spot_id",
        "spot_name",
        "call_datetime",
    }

    missing_columns = sorted(
        required_columns.difference(
            dataframe.columns
        )
    )

    if missing_columns:
        return {
            **empty_output,
            "spot_presence": pd.DataFrame(
                [
                    {
                        "analysis_status": (
                            "REQUIRED_COLUMNS_MISSING"
                        ),
                        "missing_columns": ", ".join(
                            missing_columns
                        ),
                    }
                ]
            ),
        }

    data = dataframe.copy()

    # ---------------------------------------------------------------
    # Required text fields
    # ---------------------------------------------------------------

    for column in (
        "subscriber_number",
        "spot_id",
        "spot_name",
    ):
        data[column] = (
            data[column]
            .fillna("")
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

    data = data.loc[
        data["subscriber_number"].ne("")
        & data["spot_id"].ne("")
        & data["spot_name"].ne("")
    ].copy()

    if data.empty:
        return empty_output

    # ---------------------------------------------------------------
    # Datetime normalization
    # ---------------------------------------------------------------

    event_time = pd.to_datetime(
        data["call_datetime"],
        errors="coerce",
    )

    failed_mask = event_time.isna()

    if failed_mask.any():
        event_time.loc[failed_mask] = pd.to_datetime(
            data.loc[
                failed_mask,
                "call_datetime",
            ],
            errors="coerce",
            dayfirst=True,
        )

    data["_event_time"] = event_time

    data = data.dropna(
        subset=["_event_time"]
    ).copy()

    if data.empty:
        return empty_output

    data["_event_date"] = (
        data["_event_time"].dt.date
    )

    data["_event_hour"] = (
        data["_event_time"].dt.hour
    )

    data["_is_night"] = (
        data["_event_hour"].ge(22)
        | data["_event_hour"].lt(6)
    ).astype("int8")

    # Optional columns are created for API consistency.
    for column in (
        "searched_cell_id",
        "first_cell_id",
        "imei",
        "imsi",
        "other_party",
        "operator",
    ):
        if column not in data.columns:
            data[column] = ""

        data[column] = (
            data[column]
            .fillna("")
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

    # ---------------------------------------------------------------
    # Canonical IMEI device identity
    # ---------------------------------------------------------------

    def _normalize_imei_digits(
        value: object,
    ) -> str:
        """Return digit-only IMEI text without changing source data."""

        from decimal import (
            Decimal,
            InvalidOperation,
        )
        import re

        if pd.isna(value):
            return ""

        value_text = str(value).strip()

        if value_text.lower() in {
            "",
            "nan",
            "none",
            "<na>",
            "null",
        }:
            return ""

        numeric_pattern = (
            r"[+-]?\d+(?:\.\d+)?"
            r"(?:[eE][+-]?\d+)?"
        )

        if re.fullmatch(
            numeric_pattern,
            value_text,
        ):
            try:
                decimal_value = Decimal(
                    value_text
                )

                if (
                    decimal_value
                    == decimal_value.to_integral_value()
                ):
                    value_text = format(
                        decimal_value.quantize(
                            Decimal("1")
                        ),
                        "f",
                    )
            except InvalidOperation:
                pass

        return re.sub(
            r"\D",
            "",
            value_text,
        )

    data["_imei_digits"] = (
        data["imei"].map(
            _normalize_imei_digits
        )
    )

    imei_length = (
        data["_imei_digits"].str.len()
    )

    valid_imei_length = (
        imei_length.between(
            14,
            16,
            inclusive="both",
        )
    )

    # First 14 digits represent the stable equipment base.
    # Last-digit-only differences are treated as formatting,
    # check-digit or software-version variants.
    data["_imei_device_base14"] = (
        data["_imei_digits"]
        .where(
            valid_imei_length,
            "",
        )
        .str[:14]
    )

    group_columns = [
        "spot_id",
        "spot_name",
        "subscriber_number",
    ]

    # ---------------------------------------------------------------
    # Core Spot-wise aggregation
    # ---------------------------------------------------------------

    spot_summary = (
        data.groupby(
            group_columns,
            dropna=False,
            observed=True,
        )
        .agg(
            spot_event_count=(
                "_event_time",
                "size",
            ),
            spot_first_seen=(
                "_event_time",
                "min",
            ),
            spot_last_seen=(
                "_event_time",
                "max",
            ),
            spot_active_days=(
                "_event_date",
                "nunique",
            ),
            night_event_count=(
                "_is_night",
                "sum",
            ),
            searched_cells_seen=(
                "searched_cell_id",
                lambda values: values[
                    values.ne("")
                ].nunique(),
            ),
            first_cells_seen=(
                "first_cell_id",
                lambda values: values[
                    values.ne("")
                ].nunique(),
            ),
            imei_count=(
                "imei",
                lambda values: values[
                    values.ne("")
                ].nunique(),
            ),
            normalized_imei_count=(
                "_imei_digits",
                lambda values: values[
                    values.ne("")
                ].nunique(),
            ),
            device_base14_count=(
                "_imei_device_base14",
                lambda values: values[
                    values.ne("")
                ].nunique(),
            ),
            imsi_count=(
                "imsi",
                lambda values: values[
                    values.ne("")
                ].nunique(),
            ),
            other_party_count=(
                "other_party",
                lambda values: values[
                    values.ne("")
                ].nunique(),
            ),
            operator_count=(
                "operator",
                lambda values: values[
                    values.ne("")
                ].nunique(),
            ),
        )
        .reset_index()
    )

    spot_summary["cells_seen"] = (
        spot_summary[
            [
                "searched_cells_seen",
                "first_cells_seen",
            ]
        ]
        .max(axis=1)
        .fillna(0)
        .astype(int)
    )

    spot_summary["observed_span_minutes"] = (
        (
            spot_summary["spot_last_seen"]
            - spot_summary["spot_first_seen"]
        )
        .dt.total_seconds()
        .div(60)
        .round(2)
        .fillna(0)
    )

    # ---------------------------------------------------------------
    # Overall subscriber baseline across all uploaded Spots
    # ---------------------------------------------------------------

    overall = (
        data.groupby(
            "subscriber_number",
            dropna=False,
            observed=True,
        )
        .agg(
            overall_event_count=(
                "_event_time",
                "size",
            ),
            overall_first_seen=(
                "_event_time",
                "min",
            ),
            overall_last_seen=(
                "_event_time",
                "max",
            ),
            overall_active_days=(
                "_event_date",
                "nunique",
            ),
            spots_seen=(
                "spot_id",
                "nunique",
            ),
        )
        .reset_index()
    )

    first_spot = (
        data.sort_values(
            [
                "subscriber_number",
                "_event_time",
                "spot_id",
            ],
            kind="stable",
        )
        .drop_duplicates(
            subset=["subscriber_number"],
            keep="first",
        )
        [
            [
                "subscriber_number",
                "spot_id",
                "spot_name",
            ]
        ]
        .rename(
            columns={
                "spot_id": "first_spot_id",
                "spot_name": "first_spot_name",
            }
        )
    )

    overall = overall.merge(
        first_spot,
        on="subscriber_number",
        how="left",
        validate="one_to_one",
    )

    spot_summary = spot_summary.merge(
        overall,
        on="subscriber_number",
        how="left",
        validate="many_to_one",
    )

    # ---------------------------------------------------------------
    # Spot-level interpretation
    # ---------------------------------------------------------------

    spot_summary[
        "seen_at_another_spot_before"
    ] = (
        spot_summary["spot_first_seen"]
        > spot_summary["overall_first_seen"]
    ) & (
        spot_summary["spot_id"]
        != spot_summary["first_spot_id"]
    )

    spot_summary[
        "is_first_spot_in_upload"
    ] = (
        spot_summary["spot_id"]
        == spot_summary["first_spot_id"]
    )

    spot_summary["is_spot_only"] = (
        spot_summary["spots_seen"].eq(1)
    )

    spot_summary["is_cross_spot"] = (
        spot_summary["spots_seen"].ge(2)
    )

    # ---------------------------------------------------------------
    # Evidence classification
    # ---------------------------------------------------------------

    # One event cannot prove a short stay. It only proves one
    # network observation at that Spot.
    spot_summary["is_single_event_presence"] = (
        spot_summary["spot_event_count"].eq(1)
    )

    spot_summary["is_rare_at_spot"] = (
        spot_summary["spot_event_count"].between(
            1,
            2,
            inclusive="both",
        )
    )

    # Short observed presence requires at least two events.
    # A single event has a zero-minute span but must not be
    # interpreted as a short physical stay.
    spot_summary["is_short_observed_span"] = (
        spot_summary["spot_event_count"].between(
            2,
            3,
            inclusive="both",
        )
        & spot_summary["spot_active_days"].eq(1)
        & spot_summary[
            "observed_span_minutes"
        ].gt(0)
        & spot_summary[
            "observed_span_minutes"
        ].le(30)
    )

    spot_summary["night_event_ratio"] = (
        pd.to_numeric(
            spot_summary["night_event_count"],
            errors="coerce",
        )
        .fillna(0)
        .div(
            pd.to_numeric(
                spot_summary["spot_event_count"],
                errors="coerce",
            )
            .replace(0, pd.NA)
        )
        .fillna(0)
        .round(4)
    )

    # One occasional night event is not enough. Night activity
    # becomes relevant only when at least half of the Spot activity
    # occurred during the configured night period.
    spot_summary["is_night_concentrated"] = (
        spot_summary["night_event_count"].ge(1)
        & spot_summary["night_event_ratio"].ge(0.50)
    )

    # Keep raw IMEI count for transparency, but never use it
    # directly as proof of a device change.
    spot_summary["raw_imei_count"] = (
        spot_summary["imei_count"]
    )

    spot_summary["imei_variant_count"] = (
        spot_summary[
            "normalized_imei_count"
        ]
        .sub(
            spot_summary[
                "device_base14_count"
            ]
        )
        .clip(lower=0)
        .astype(int)
    )

    spot_summary["has_verified_device_change"] = (
        spot_summary[
            "device_base14_count"
        ].ge(2)
    )

    spot_summary["has_imei_format_variant"] = (
        spot_summary[
            "normalized_imei_count"
        ].ge(2)
        & spot_summary[
            "device_base14_count"
        ].eq(1)
    )

    spot_summary["has_strong_imsi_signal"] = (
        spot_summary["imsi_count"].ge(2)
    )

    # Compatibility field used by the existing scoring engine.
    # It now means verified distinct device bases only.
    spot_summary["has_device_change_signal"] = (
        spot_summary[
            "has_verified_device_change"
        ]
    )

    # Combined evidence is more meaningful than an isolated factor.
    spot_summary["has_rare_short_combination"] = (
        spot_summary["is_rare_at_spot"]
        & spot_summary["is_short_observed_span"]
    )

    spot_summary["has_cross_spot_rare_combination"] = (
        spot_summary["is_cross_spot"]
        & spot_summary["is_rare_at_spot"]
    )

    spot_summary["has_cross_spot_device_combination"] = (
        spot_summary["is_cross_spot"]
        & spot_summary["has_device_change_signal"]
    )

    spot_summary["has_night_rare_combination"] = (
        spot_summary["is_night_concentrated"]
        & spot_summary["is_rare_at_spot"]
    )

    # ---------------------------------------------------------------
    # Conservative evidence-based scoring
    # ---------------------------------------------------------------

    spot_summary["spot_priority_score"] = 0

    # Weak standalone indicators.
    spot_summary.loc[
        spot_summary["is_rare_at_spot"],
        "spot_priority_score",
    ] += 5

    spot_summary.loc[
        spot_summary["is_short_observed_span"],
        "spot_priority_score",
    ] += 5

    spot_summary.loc[
        spot_summary["is_cross_spot"],
        "spot_priority_score",
    ] += 5

    # Device/SIM findings require verification but are stronger.
    spot_summary.loc[
        spot_summary["has_device_change_signal"],
        "spot_priority_score",
    ] += 15

    spot_summary.loc[
        spot_summary["has_strong_imsi_signal"],
        "spot_priority_score",
    ] += 15

    # Combined evidence receives additional weight.
    spot_summary.loc[
        spot_summary["has_rare_short_combination"],
        "spot_priority_score",
    ] += 15

    spot_summary.loc[
        spot_summary[
            "has_cross_spot_rare_combination"
        ],
        "spot_priority_score",
    ] += 15

    spot_summary.loc[
        spot_summary[
            "has_cross_spot_device_combination"
        ],
        "spot_priority_score",
    ] += 15

    spot_summary.loc[
        spot_summary["has_night_rare_combination"],
        "spot_priority_score",
    ] += 10

    # Multiple cells and earlier appearance at another uploaded
    # Spot remain useful context, but they do not independently
    # increase suspicion.
    spot_summary["spot_priority_score"] = (
        spot_summary["spot_priority_score"]
        .clip(upper=100)
        .astype(int)
    )

    spot_summary["evidence_signal_count"] = (
        spot_summary[
            "is_rare_at_spot"
        ].astype("int8")
        + spot_summary[
            "is_short_observed_span"
        ].astype("int8")
        + spot_summary[
            "is_cross_spot"
        ].astype("int8")
        + spot_summary[
            "has_device_change_signal"
        ].astype("int8")
        + spot_summary[
            "is_night_concentrated"
        ].astype("int8")
    ).astype(int)

    # A number becomes a priority lead only when:
    # 1. score reaches the minimum threshold, and
    # 2. at least two independent signals exist,
    #    or a strong multiple-IMSI signal exists.
    spot_summary["is_investigation_lead"] = (
        spot_summary[
            "spot_priority_score"
        ].ge(30)
        & (
            spot_summary[
                "evidence_signal_count"
            ].ge(2)
            | spot_summary[
                "has_strong_imsi_signal"
            ]
        )
    )

    def classify_spot_presence(
        row: pd.Series,
    ) -> str:
        if bool(
            row.get(
                "seen_at_another_spot_before",
                False,
            )
        ):
            return (
                "SEEN EARLIER AT ANOTHER "
                "UPLOADED SPOT"
            )

        if (
            bool(row.get("is_spot_only", False))
            and bool(
                row.get(
                    "is_rare_at_spot",
                    False,
                )
            )
        ):
            return "SPOT-ONLY RARE PRESENCE"

        if bool(
            row.get(
                "is_first_spot_in_upload",
                False,
            )
        ) and bool(
            row.get(
                "is_cross_spot",
                False,
            )
        ):
            return "FIRST OBSERVED SPOT IN CURRENT UPLOAD"

        if bool(
            row.get(
                "is_rare_at_spot",
                False,
            )
        ):
            return "RARE AT THIS SPOT"

        if bool(
            row.get(
                "is_cross_spot",
                False,
            )
        ):
            return "REPEAT ACROSS MULTIPLE SPOTS"

        return "REPEAT AT THIS SPOT"

    def priority_level(
        score: int,
    ) -> str:
        if score >= 70:
            return "HIGH"
        if score >= 50:
            return "MEDIUM_HIGH"
        if score >= 30:
            return "MEDIUM"
        return "LOW"

    def confidence_level(
        row: pd.Series,
    ) -> str:
        if (
            int(
                row.get(
                    "spot_event_count",
                    0,
                )
                or 0
            )
            >= 3
            and int(
                row.get(
                    "spot_active_days",
                    0,
                )
                or 0
            )
            >= 2
        ):
            return "HIGH"

        if int(
            row.get(
                "spot_event_count",
                0,
            )
            or 0
        ) >= 2:
            return "MEDIUM"

        return "LOW"

    def build_reason(
        row: pd.Series,
    ) -> str:
        reasons: list[str] = []

        if bool(
            row.get(
                "seen_at_another_spot_before",
                False,
            )
        ):
            reasons.append(
                "पहले दूसरे uploaded Spot पर मिला"
            )

        if bool(
            row.get(
                "is_rare_at_spot",
                False,
            )
        ):
            reasons.append(
                "इस Spot पर बहुत कम activity"
            )

        if bool(
            row.get(
                "is_short_observed_span",
                False,
            )
        ):
            reasons.append(
                "कम observed time-span"
            )

        if int(
            row.get(
                "spots_seen",
                0,
            )
            or 0
        ) >= 2:
            reasons.append(
                "एक से अधिक Spots पर presence"
            )

        if int(
            row.get(
                "cells_seen",
                0,
            )
            or 0
        ) >= 2:
            reasons.append(
                "एक से अधिक Cells पर presence"
            )

        if bool(
            row.get(
                "has_verified_device_change",
                False,
            )
        ):
            reasons.append(
                "सत्यापित रूप से अलग device bases"
            )

        if int(
            row.get(
                "imsi_count",
                0,
            )
            or 0
        ) >= 2:
            reasons.append(
                "एक से अधिक IMSI"
            )

        if bool(
            row.get(
                "is_night_concentrated",
                False,
            )
        ):
            reasons.append(
                "अधिकांश activity रात के समय"
            )

        if not reasons:
            return (
                "सामान्य Spot-level presence; "
                "अन्य evidence से मिलान करें"
            )

        return "; ".join(reasons)

    spot_summary["spot_category"] = (
        spot_summary.apply(
            classify_spot_presence,
            axis=1,
        )
    )

    spot_summary["priority"] = (
        spot_summary[
            "spot_priority_score"
        ].apply(priority_level)
    )

    spot_summary["confidence"] = (
        spot_summary.apply(
            confidence_level,
            axis=1,
        )
    )

    spot_summary["why_flagged"] = (
        spot_summary.apply(
            build_reason,
            axis=1,
        )
    )

    def describe_imei_evidence(
        row: pd.Series,
    ) -> str:
        if bool(
            row.get(
                "has_verified_device_change",
                False,
            )
        ):
            return (
                "VERIFIED DISTINCT DEVICE BASES"
            )

        if bool(
            row.get(
                "has_imei_format_variant",
                False,
            )
        ):
            return (
                "SAME DEVICE BASE - "
                "LAST-DIGIT/FORMAT VARIANT"
            )

        device_count = int(
            row.get(
                "device_base14_count",
                0,
            )
            or 0
        )

        if device_count == 1:
            return "SINGLE VERIFIED DEVICE BASE"

        return "IMEI NOT AVAILABLE OR INVALID"

    spot_summary["imei_interpretation"] = (
        spot_summary.apply(
            describe_imei_evidence,
            axis=1,
        )
    )

    spot_summary["recommended_verification"] = (
        "SDR/CAF, IMEI/IMSI continuity, exact Tower time, "
        "other Spot sequence, contact context और field information "
        "से verify करें।"
    )

    spot_summary["interpretation_caution"] = (
        "Tower presence केवल investigative lead है। "
        "Observed span continuous physical presence सिद्ध नहीं करता।"
    )

    # ---------------------------------------------------------------
    # Investigator-facing outputs
    # ---------------------------------------------------------------

    priority_order = {
        "HIGH": 1,
        "MEDIUM_HIGH": 2,
        "MEDIUM": 3,
        "LOW": 4,
    }

    spot_summary["_priority_order"] = (
        spot_summary["priority"]
        .map(priority_order)
        .fillna(9)
        .astype(int)
    )

    spot_presence = (
        spot_summary.sort_values(
            [
                "_priority_order",
                "spot_priority_score",
                "spots_seen",
                "spot_event_count",
                "spot_name",
                "subscriber_number",
            ],
            ascending=[
                True,
                False,
                False,
                False,
                True,
                True,
            ],
            kind="stable",
        )
        .drop(
            columns=["_priority_order"]
        )
        .reset_index(drop=True)
    )

    cross_spot_presence = (
        spot_presence.loc[
            spot_presence["spots_seen"].ge(2)
        ]
        .copy()
        .reset_index(drop=True)
    )

    spot_priority_leads = (
        spot_presence.loc[
            spot_presence[
                "is_investigation_lead"
            ].fillna(False)
        ]
        .copy()
        .reset_index(drop=True)
    )

    return {
        "spot_presence": spot_presence,
        "cross_spot_presence": (
            cross_spot_presence
        ),
        "spot_priority_leads": (
            spot_priority_leads
        ),
    }
