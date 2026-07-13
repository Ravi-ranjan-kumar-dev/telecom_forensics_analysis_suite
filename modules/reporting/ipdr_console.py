"""Console renderer for multi-operator IPDR analysis."""

from __future__ import annotations

from typing import Any

import pandas as pd


def _show(title: str, value: Any, limit: int = 20) -> None:
    print("\n" + "-" * 110)
    print(title)
    print("-" * 110)

    if isinstance(value, pd.DataFrame):
        if value.empty:
            print("No records.")
        else:
            print(value.head(limit).to_string(index=False))
    else:
        print(value)


def print_ipdr_analysis(
    analysis: dict[str, Any],
    *,
    row_limit: int = 20,
) -> None:
    print("\n" + "=" * 110)
    print("MULTI-OPERATOR IPDR ANALYSIS")
    print("=" * 110)

    for title, key in (
        ("EXECUTIVE SUMMARY", "summary"),
        ("QUERY / SOURCE SUMMARY", "query_summary"),
        ("TOP SUBSCRIBERS / USER IDs", "subscriber_summary"),
        ("MULTI-FILE SUBSCRIBERS", "multi_file_subscribers"),
        ("TOP DESTINATION IP", "destination_ip_summary"),
        ("TOP DESTINATION PORTS", "destination_port_summary"),
        ("REVERSE-IP QUERY VALIDATION", "reverse_query_validation"),
        ("DATA QUALITY", "data_quality"),
    ):
        _show(title, analysis.get(key), row_limit)

    print("\n" + "=" * 110)
