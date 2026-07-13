"""Console output for Tower IPDR/NAT analysis."""

from __future__ import annotations

from typing import Any

import pandas as pd


def _print_table(title: str, dataframe: Any, limit: int = 20) -> None:
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)

    if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
        print("No records.")
        return

    print(dataframe.head(limit).to_string(index=False))

    if len(dataframe) > limit:
        print(f"... {len(dataframe) - limit:,} more row(s)")


def print_tower_ipdr_analysis(
    analysis: dict[str, Any],
    *,
    row_limit: int = 20,
) -> None:
    _print_table("TOWER IPDR/NAT EXECUTIVE SUMMARY", analysis.get("summary"), 100)
    _print_table("SEARCHED CELL SUMMARY", analysis.get("cell_summary"), row_limit)
    _print_table(
        "MULTI-CELL SUBSCRIBER CANDIDATES",
        analysis.get("subscriber_multi_cell_candidates"),
        row_limit,
    )
    _print_table(
        "ALL-CELL SUBSCRIBER CANDIDATES",
        analysis.get("subscriber_all_cell_candidates"),
        row_limit,
    )
    _print_table("TOP DESTINATION IP", analysis.get("destination_ip_summary"), row_limit)
    _print_table("TOP DESTINATION PORT", analysis.get("destination_port_summary"), row_limit)
    _print_table("DATA QUALITY", analysis.get("data_quality"), 100)


def print_tower_ipdr_partition(
    partition: dict[str, Any],
    *,
    row_limit: int = 50,
) -> None:
    _print_table("CCTV PARTITION WINDOWS", partition.get("partition_windows"), 100)
    _print_table("PARTITION SUMMARY", partition.get("partition_summary"), 100)
    _print_table(
        "ACTUAL EVENT N-OF-M CANDIDATES",
        partition.get("event_n_of_m_candidates"),
        row_limit,
    )
    _print_table(
        "ACTUAL EVENT STRICT COMMON",
        partition.get("event_strict_common_candidates"),
        row_limit,
    )
    _print_table(
        "ALLOCATION-OVERLAP N-OF-M CANDIDATES",
        partition.get("allocation_n_of_m_candidates"),
        row_limit,
    )
    _print_table(
        "ALLOCATION-OVERLAP STRICT COMMON",
        partition.get("allocation_strict_common_candidates"),
        row_limit,
    )
