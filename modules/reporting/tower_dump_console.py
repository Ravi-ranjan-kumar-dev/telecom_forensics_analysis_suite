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
                print(f"\n... {len(value) - limit} more rows")
    elif isinstance(value, pd.Series):
        print(value.head(limit).to_string())
    elif isinstance(value, dict):
        for key, item in value.items():
            print(f"{key}: {item}")
    else:
        print(value)


def print_tower_dump_report(
    result: dict[str, Any],
    *,
    row_limit: int = 25,
) -> None:
    metadata = result.get("metadata", {})
    print("\n" + "#" * 78)
    print("TOWER DUMP BATCH ANALYSIS")
    print("#" * 78)
    print(f"Files found       : {metadata.get('files_found', 0)}")
    print(f"Files loaded      : {metadata.get('files_loaded', 0)}")
    print(f"Files failed      : {metadata.get('files_failed', 0)}")
    print(f"Combined records  : {metadata.get('records_after_deduplication', 0)}")
    print(f"Possible duplicates: {metadata.get('potential_exact_duplicate_records', 0)}")
    print(f"Duplicates removed : {metadata.get('duplicates_removed', 0)}")
    print(f"Operators          : {', '.join(result.get('operators', [])) or 'None'}")
    print(f"Searched cells    : {len(result.get('cell_ids', []))}")

    analysis = result.get("analysis", {})
    results = analysis.get("results", {})

    for name, value in results.items():
        _print_value(name, value, row_limit)

    status = analysis.get("status")
    _print_value("analysis_status", status, 100)

    errors = analysis.get("errors")
    if isinstance(errors, pd.DataFrame) and not errors.empty:
        _print_value("analysis_errors", errors, 100)
