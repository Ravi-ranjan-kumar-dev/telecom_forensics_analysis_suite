"""Console renderer for Tower GPRS Dump analysis."""

from __future__ import annotations

from typing import Any

import pandas as pd


DISPLAY_COLUMNS: dict[str, list[str]] = {
    "TOWER GPRS DUMP EXECUTIVE SUMMARY": [
        "Metric",
        "Value",
    ],
    "TECHNOLOGY SUMMARY": [
        "Technology",
        "Sessions",
    ],
    "PREPAID / POSTPAID SUMMARY": [
        "Connection_Type",
        "Sessions",
    ],
    "GPRS PRIORITY LEADS": [
        "subscriber_number",
        "priority",
        "confidence",
        "priority_score",
        "session_count",
        "cells_seen",
        "imei_count",
        "imsi_count",
        "total_volume",
        "first_seen",
        "last_seen",
        "why_important",
        "next_action",
    ],
    "GPRS UNCOMMON / NEW VISITOR NUMBERS": [
        "subscriber_number",
        "priority",
        "confidence",
        "session_count",
        "first_seen",
        "last_seen",
        "total_volume",
        "cells_seen",
        "searched_cells",
        "why_important",
        "next_action",
    ],
    "GPRS COMMON / REPEAT NUMBERS": [
        "subscriber_number",
        "priority",
        "confidence",
        "session_count",
        "cells_seen",
        "total_volume",
        "first_seen",
        "last_seen",
        "why_important",
        "next_action",
    ],
    "GPRS MULTI-CELL PRESENCE": [
        "subscriber_number",
        "priority",
        "confidence",
        "session_count",
        "cells_seen",
        "searched_cells",
        "total_volume",
        "first_seen",
        "last_seen",
        "why_important",
        "next_action",
    ],
    "GPRS DEVICE CONSISTENCY": [
        "subscriber_number",
        "priority",
        "confidence",
        "session_count",
        "imei_count",
        "imsi_count",
        "ipv4_count",
        "ipv6_count",
        "cells_seen",
        "why_important",
        "next_action",
    ],
    "GPRS SUSPICIOUS TIMING": [
        "subscriber_number",
        "priority",
        "confidence",
        "session_count",
        "total_duration_seconds",
        "total_volume",
        "cells_seen",
        "first_seen",
        "last_seen",
        "why_important",
        "next_action",
    ],
    "SHARED IMEI": [
        "imei",
        "Sessions",
        "Subscriber_Count",
        "Subscribers",
        "First_Seen",
        "Last_Seen",
        "Total_Volume",
        "Technology",
    ],
    "SHARED IMSI": [
        "imsi",
        "Sessions",
        "Subscriber_Count",
        "Subscribers",
        "First_Seen",
        "Last_Seen",
        "Total_Volume",
        "Technology",
    ],
    "DATA QUALITY": [
        "Check",
        "Rows",
        "Percentage",
    ],
}


def _short_text(value: Any, *, max_chars: int = 70) -> str:
    if value is None:
        return ""

    text = str(value).strip()

    if text in {"nan", "NaT", "None", "<NA>"}:
        return ""

    if len(text) <= max_chars:
        return text

    return text[: max_chars - 3] + "..."


def _prepare_dataframe_for_console(
    title: str,
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    wanted = DISPLAY_COLUMNS.get(title)

    if wanted:
        columns = [column for column in wanted if column in dataframe.columns]
        output = dataframe.loc[:, columns].copy()
    else:
        output = dataframe.copy()

    for column in output.columns:
        if pd.api.types.is_object_dtype(output[column]):
            output[column] = output[column].map(_short_text)

    return output


def _print_table(
    title: str,
    value: Any,
    *,
    limit: int = 15,
) -> None:
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)

    if not isinstance(value, pd.DataFrame) or value.empty:
        print("No records found.")
        return

    output = _prepare_dataframe_for_console(title, value)

    with pd.option_context(
        "display.max_columns",
        30,
        "display.max_colwidth",
        72,
        "display.width",
        220,
    ):
        print(output.head(limit).to_string(index=False))

    if len(value) > limit:
        print(f"\n[+] Showing first {limit} of {len(value):,} rows. Full details are in Excel.")


def print_gprs_analysis(
    result: dict[str, Any],
    *,
    row_limit: int = 15,
) -> None:
    """Print short investigator-focused Tower GPRS console report."""

    display_limit = min(int(row_limit or 15), 15)

    print("\n" + "#" * 90)
    print("TOWER GPRS DUMP ANALYSIS")
    print("#" * 90)

    print("\n" + "-" * 90)
    print("Console par sirf important investigation leads dikhaye ja rahe hain.")
    print("Full details Excel report me available rahenge.")
    print("-" * 90)

    _print_table(
        "TOWER GPRS DUMP EXECUTIVE SUMMARY",
        result.get("summary"),
        limit=50,
    )
    _print_table(
        "TECHNOLOGY SUMMARY",
        result.get("technology_summary"),
        limit=display_limit,
    )
    _print_table(
        "PREPAID / POSTPAID SUMMARY",
        result.get("pre_post_summary"),
        limit=display_limit,
    )
    _print_table(
        "GPRS PRIORITY LEADS",
        result.get("gprs_priority_leads"),
        limit=display_limit,
    )
    _print_table(
        "GPRS UNCOMMON / NEW VISITOR NUMBERS",
        result.get("gprs_uncommon_numbers"),
        limit=display_limit,
    )
    _print_table(
        "GPRS COMMON / REPEAT NUMBERS",
        result.get("gprs_common_numbers"),
        limit=display_limit,
    )
    _print_table(
        "GPRS MULTI-CELL PRESENCE",
        result.get("gprs_multi_cell_presence"),
        limit=display_limit,
    )
    _print_table(
        "GPRS DEVICE CONSISTENCY",
        result.get("gprs_device_consistency"),
        limit=display_limit,
    )
    _print_table(
        "GPRS SUSPICIOUS TIMING",
        result.get("gprs_suspicious_timing"),
        limit=display_limit,
    )
    _print_table(
        "SHARED IMEI",
        result.get("shared_imei"),
        limit=display_limit,
    )
    _print_table(
        "SHARED IMSI",
        result.get("shared_imsi"),
        limit=display_limit,
    )
    _print_table(
        "DATA QUALITY",
        result.get("data_quality"),
        limit=50,
    )


def print_tower_gprs_report(
    result: dict[str, Any],
    *,
    row_limit: int = 15,
) -> None:
    """Backward/alternate name for the same GPRS console report."""

    print_gprs_analysis(result, row_limit=row_limit)


def print_gprs_partition(
    result: dict[str, Any],
    *,
    row_limit: int = 50,
) -> None:
    """Print Tower GPRS date-time partition report."""

    _print_table(
        "GPRS PARTITION WINDOWS",
        result.get("partition_windows"),
        limit=100,
    )
    _print_table(
        "GPRS PARTITION SUMMARY",
        result.get("partition_summary"),
        limit=100,
    )
    _print_table(
        "N-OF-M COMMON CANDIDATES",
        result.get("n_of_m_candidates"),
        limit=row_limit,
    )
    _print_table(
        "STRICT COMMON CANDIDATES",
        result.get("strict_common_candidates"),
        limit=row_limit,
    )
    _print_table(
        "PARTITION SUBSCRIBER PRESENCE",
        result.get("subscriber_presence"),
        limit=row_limit,
    )
