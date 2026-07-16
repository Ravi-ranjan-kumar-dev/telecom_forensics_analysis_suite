from __future__ import annotations

from typing import Any

import pandas as pd


def _print_value(name: str, value: Any, limit: int) -> None:
    print("\n" + "=" * 78)
    print(name.replace("_", " ").upper())
    print("=" * 78)

    if isinstance(value, pd.DataFrame):
        if value.empty:
            print("No records found.")
        else:
            print(value.head(limit).to_string(index=False))
            if len(value) > limit:
                print(f"\n[+] Showing first {limit} of {len(value):,} rows.")
    elif isinstance(value, pd.Series):
        print(value.head(limit).to_string())
    elif isinstance(value, dict):
        for key, item in value.items():
            print(f"{key}: {item}")
    else:
        print(value)


def _print_analysis_status(status: Any) -> None:
    if not isinstance(status, pd.DataFrame) or status.empty:
        return

    compact_columns = [
        column
        for column in ["analysis", "status", "rows", "duration_ms", "error"]
        if column in status.columns
    ]

    _print_value(
        "analysis_status",
        status[compact_columns],
        limit=100,
    )


def print_tower_dump_report(
    result: dict[str, Any],
    *,
    row_limit: int = 15,
) -> None:
    metadata = result.get("metadata", {})

    print("\n" + "#" * 78)
    print("TOWER CDR DUMP ANALYSIS")
    print("#" * 78)
    print(f"Files found        : {metadata.get('files_found', 0)}")
    print(f"Files loaded       : {metadata.get('files_loaded', 0)}")
    print(f"Files failed       : {metadata.get('files_failed', 0)}")
    print(f"Combined records   : {metadata.get('records_after_deduplication', 0)}")
    print(f"Possible duplicates: {metadata.get('potential_exact_duplicate_records', 0)}")
    print(f"Duplicates removed : {metadata.get('duplicates_removed', 0)}")
    print(f"Operators          : {', '.join(result.get('operators', [])) or 'None'}")
    print(f"Searched cells     : {len(result.get('cell_ids', []))}")

    analysis = result.get("analysis", {})
    results = analysis.get("results", {})

    print("\n" + "-" * 78)
    print("Console par sirf important investigation leads dikhaye ja rahe hain.")
    print("Full details Excel report me available rahenge.")
    print("-" * 78)

    sections = [
        ("tower_dump_summary", 50),
        ("cell_summary", row_limit),
        ("call_type_summary", row_limit),
        ("tower_cdr_priority_leads", row_limit),
        ("tower_cdr_uncommon_numbers", row_limit),
        ("tower_cdr_common_numbers", row_limit),
        ("tower_cdr_multi_cell_presence", row_limit),
        ("tower_cdr_device_consistency", row_limit),
        ("tower_cdr_suspicious_timing", row_limit),
        ("shared_imei", row_limit),
        ("shared_imsi", row_limit),
        ("investigative_indicators", row_limit),
    ]

    for name, limit in sections:
        _print_value(name, results.get(name), limit)

    _print_analysis_status(analysis.get("status"))

    errors = analysis.get("errors")
    if isinstance(errors, pd.DataFrame) and not errors.empty:
        _print_value("analysis_errors", errors, 100)
