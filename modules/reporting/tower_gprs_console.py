"""Console renderer for Tower GPRS Dump analysis."""

from __future__ import annotations

from typing import Any

import pandas as pd


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

    print(value.head(limit).to_string(index=False))

    if len(value) > limit:
        print(f"\n[+] Showing first {limit} of {len(value):,} rows.")


def print_gprs_analysis(
    result: dict[str, Any],
    *,
    row_limit: int = 15,
) -> None:
    """Print short investigator-focused Tower GPRS console report."""

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
        limit=row_limit,
    )
    _print_table(
        "PREPAID / POSTPAID SUMMARY",
        result.get("pre_post_summary"),
        limit=row_limit,
    )
    _print_table(
        "GPRS PRIORITY LEADS",
        result.get("gprs_priority_leads"),
        limit=row_limit,
    )
    _print_table(
        "GPRS UNCOMMON / NEW VISITOR NUMBERS",
        result.get("gprs_uncommon_numbers"),
        limit=row_limit,
    )
    _print_table(
        "GPRS COMMON / REPEAT NUMBERS",
        result.get("gprs_common_numbers"),
        limit=row_limit,
    )
    _print_table(
        "GPRS MULTI-CELL PRESENCE",
        result.get("gprs_multi_cell_presence"),
        limit=row_limit,
    )
    _print_table(
        "GPRS DEVICE CONSISTENCY",
        result.get("gprs_device_consistency"),
        limit=row_limit,
    )
    _print_table(
        "GPRS SUSPICIOUS TIMING",
        result.get("gprs_suspicious_timing"),
        limit=row_limit,
    )
    _print_table(
        "SHARED IMEI",
        result.get("shared_imei"),
        limit=row_limit,
    )
    _print_table(
        "SHARED IMSI",
        result.get("shared_imsi"),
        limit=row_limit,
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
