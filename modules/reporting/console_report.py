"""Console renderer for cached CDR analysis results."""

from __future__ import annotations

from typing import Any
import json

import pandas as pd


DISPLAY_ORDER: tuple[tuple[str, str], ...] = (
    ("cdr_summary", "CDR SUMMARY"),
    ("top_contacts", "TOP CONTACTS"),
    ("top_contact_details", "TOP CONTACT DETAILS"),
    ("contact_ranking", "CONTACT RANKING"),
    ("incoming_outgoing", "INCOMING / OUTGOING TRAFFIC"),
    ("social_network", "SOCIAL NETWORK"),
    ("analyze_location", "LOCATION OVERVIEW"),
    ("frequent_locations", "FREQUENT LOCATIONS / TOWERS"),
    ("tower_movement", "TOWER MOVEMENT"),
    ("tower_transition", "TOWER TRANSITIONS"),
    ("movement_pattern", "MOVEMENT PATTERNS"),
    ("tower_intelligence", "TOWER INTELLIGENCE"),
    ("home_tower", "PROBABLE HOME TOWER"),
    ("work_tower", "PROBABLE WORK TOWER"),
    ("imei_summary", "IMEI SUMMARY"),
    ("imei_intelligence", "IMEI INTELLIGENCE"),
    ("sim_change", "SIM / DEVICE CHANGES"),
    ("activity_summary", "ACTIVITY SUMMARY"),
    ("hourly_activity", "HOURLY ACTIVITY"),
    ("daily_activity", "DAILY ACTIVITY"),
    ("weekly_activity", "WEEKLY ACTIVITY"),
    ("monthly_activity", "MONTHLY ACTIVITY"),
    ("behavioral_intelligence", "BEHAVIORAL OBSERVATIONS"),
    ("suspicious_activity", "REVIEW INDICATORS"),
)


def _print_value(value: Any, max_rows: int) -> None:
    if value is None:
        print("No result returned.")
        return

    if isinstance(value, pd.DataFrame):
        if value.empty:
            print("No records found.")
            return
        print(value.head(max_rows).to_string(index=False))
        if len(value) > max_rows:
            print(f"[+] Showing first {max_rows} of {len(value)} rows.")
        return

    if isinstance(value, pd.Series):
        if value.empty:
            print("No records found.")
            return
        print(value.head(max_rows).to_string())
        if len(value) > max_rows:
            print(f"[+] Showing first {max_rows} of {len(value)} rows.")
        return

    if isinstance(value, dict):
        for key, item in value.items():
            print(f"{key}: ", end="")
            if isinstance(item, (pd.DataFrame, pd.Series, dict, list, tuple, set)):
                print()
                _print_value(item, max_rows)
            else:
                print(item)
        return

    if isinstance(value, (list, tuple, set)):
        for item in list(value)[:max_rows]:
            if isinstance(item, (dict, list, tuple)):
                print(json.dumps(item, default=str, ensure_ascii=False))
            else:
                print(item)
        if len(value) > max_rows:
            print(f"[+] Showing first {max_rows} of {len(value)} entries.")
        return

    print(value)


def print_single_analysis_report(
    bundle: dict[str, Any],
    target: str,
    max_rows_per_section: int = 30,
) -> None:
    """Print all cached module results without executing any analysis again."""
    results = bundle.get("results", {}) if isinstance(bundle, dict) else {}
    errors = bundle.get("errors", {}) if isinstance(bundle, dict) else {}

    print("\n" + "=" * 80)
    print(f"SINGLE CDR FORENSIC ANALYSIS — TARGET: {target}")
    print("=" * 80)

    for key, title in DISPLAY_ORDER:
        print(f"\n===== {title} =====")
        if key not in results:
            print("Result unavailable. Check Analysis Status / Errors.")
            continue
        _print_value(results[key], max_rows_per_section)

    status = bundle.get("status") if isinstance(bundle, dict) else None
    print("\n===== ANALYSIS FUNCTION STATUS =====")
    if isinstance(status, pd.DataFrame) and not status.empty:
        columns = [
            column for column in
            ["Group", "Function", "Status", "Duration (sec)", "Error"]
            if column in status.columns
        ]
        print(status[columns].to_string(index=False))
    else:
        print("Status unavailable.")

    if errors:
        print("\n===== ANALYSIS ERRORS =====")
        for name, message in errors.items():
            if name.endswith("_traceback"):
                continue
            print(f"{name}: {message}")
