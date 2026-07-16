from __future__ import annotations

from typing import Any

import pandas as pd


DISPLAY_COLUMNS: dict[str, list[str]] = {
    "cell_summary": [
        "searched_cell_id",
        "records",
        "unique_subscribers",
        "unique_imei",
        "unique_imsi",
        "first_seen",
        "last_seen",
    ],
    "call_type_summary": [
        "call_type",
        "records",
        "percentage",
    ],
    "tower_cdr_priority_leads": [
        "subscriber_number",
        "priority",
        "confidence",
        "priority_score",
        "event_count",
        "cells_seen",
        "imei_count",
        "imsi_count",
        "night_event_count",
        "first_seen",
        "last_seen",
        "why_important",
        "next_action",
    ],
    "tower_cdr_uncommon_numbers": [
        "subscriber_number",
        "priority",
        "confidence",
        "event_count",
        "first_seen",
        "last_seen",
        "cells_seen",
        "night_event_count",
        "searched_cells",
        "why_important",
        "next_action",
    ],
    "tower_cdr_common_numbers": [
        "subscriber_number",
        "priority",
        "confidence",
        "event_count",
        "cells_seen",
        "other_party_count",
        "first_seen",
        "last_seen",
        "why_important",
        "next_action",
    ],
    "tower_cdr_multi_cell_presence": [
        "subscriber_number",
        "priority",
        "confidence",
        "event_count",
        "cells_seen",
        "searched_cells",
        "first_seen",
        "last_seen",
        "why_important",
        "next_action",
    ],
    "tower_cdr_device_consistency": [
        "subscriber_number",
        "priority",
        "confidence",
        "event_count",
        "imei_count",
        "imsi_count",
        "cells_seen",
        "first_seen",
        "last_seen",
        "why_important",
        "next_action",
    ],
    "tower_cdr_suspicious_timing": [
        "subscriber_number",
        "priority",
        "confidence",
        "event_count",
        "night_event_count",
        "cells_seen",
        "first_seen",
        "last_seen",
        "why_important",
        "next_action",
    ],
    "shared_imei": [
        "imei",
        "total_events",
        "unique_subscribers",
        "unique_cells",
        "subscribers",
        "searched_cells",
    ],
    "shared_imsi": [
        "imsi",
        "total_events",
        "unique_subscribers",
        "unique_cells",
        "subscribers",
        "searched_cells",
    ],
    "investigative_indicators": [
        "indicator",
        "entity",
        "severity",
        "details",
        "caution",
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
    name: str,
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    wanted = DISPLAY_COLUMNS.get(name)

    if wanted:
        columns = [column for column in wanted if column in dataframe.columns]
        output = dataframe.loc[:, columns].copy()
    else:
        output = dataframe.copy()

    for column in output.columns:
        if pd.api.types.is_object_dtype(output[column]):
            output[column] = output[column].map(_short_text)

    return output


def _print_value(name: str, value: Any, limit: int) -> None:
    print("\n" + "=" * 78)
    print(name.replace("_", " ").upper())
    print("=" * 78)

    if isinstance(value, pd.DataFrame):
        if value.empty:
            print("No records found.")
        else:
            output = _prepare_dataframe_for_console(name, value)
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
    display_limit = min(int(row_limit or 15), 15)

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
        ("cell_summary", display_limit),
        ("call_type_summary", display_limit),
        ("tower_cdr_priority_leads", display_limit),
        ("tower_cdr_uncommon_numbers", display_limit),
        ("tower_cdr_common_numbers", display_limit),
        ("tower_cdr_multi_cell_presence", display_limit),
        ("tower_cdr_device_consistency", display_limit),
        ("tower_cdr_suspicious_timing", display_limit),
        ("shared_imei", display_limit),
        ("shared_imsi", display_limit),
        ("investigative_indicators", display_limit),
    ]

    for name, limit in sections:
        _print_value(name, results.get(name), limit)

    _print_analysis_status(analysis.get("status"))

    errors = analysis.get("errors")
    if isinstance(errors, pd.DataFrame) and not errors.empty:
        _print_value("analysis_errors", errors, 100)
