"""Console renderer for Tower GPRS Dump analysis."""

from __future__ import annotations

from typing import Any

import pandas as pd


def _print_table(
    title: str,
    value: Any,
    *,
    limit: int = 20,
) -> None:
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)

    if not isinstance(value, pd.DataFrame) or value.empty:
        print("No records found.")
        return

    print(value.head(limit).to_string(index=False))

    if len(value) > limit:
        print(f"[+] Showing first {limit} of {len(value):,} rows.")


def print_gprs_analysis(
    result: dict[str, Any],
    *,
    row_limit: int = 20,
) -> None:
    _print_table(
        "TOWER GPRS DUMP EXECUTIVE SUMMARY",
        result.get("summary"),
        limit=100,
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
        "TOP SUBSCRIBERS",
        result.get("subscriber_summary"),
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
        limit=100,
    )


def print_gprs_partition(
    result: dict[str, Any],
    *,
    row_limit: int = 50,
) -> None:
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
