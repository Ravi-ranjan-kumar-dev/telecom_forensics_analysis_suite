"""Terminal-only Tower IPDR menu, prompt and display helpers.

Extracted without altering function AST bodies. No evidence or DB I/O.
"""

from __future__ import annotations

import pandas as pd


def _menu(case: dict[str, Any]) -> str:
    print("" + "=" * 78)
    print(
        f"TOWER IPDR DUMP ANALYSIS | "
        f"{case.get('case_id', '')} | "
        f"{case.get('case_name', '')}"
    )
    print("=" * 78)
    print("1. Run Complete Tower IPDR Dump Analysis")
    print("2. Create Date-Time Parts")
    print("3. Part-wise Analysis")
    print("4. View / Export Latest Report")
    print("0. Back to Tower Dump Analysis")
    return input("Choose Action: ").strip()


def _collect_date_time_pairs() -> list[tuple[str, str]]:
    print("\n" + "=" * 72)
    print("ENTER DATE-TIME PARTITIONS")
    print("=" * 72)
    print("Date example : 11-06-2026")
    print("Time example : 20:10 or 20:10:00")
    print("Input complete hone par next Date blank chhodkar Enter dabayein.")

    pairs: list[tuple[str, str]] = []
    number = 1

    while True:
        date_value = input(
            f"\nPartition {number} - Date (blank = finish): "
        ).strip()

        if not date_value:
            break

        time_value = input(f"Partition {number} - Time: ").strip()

        if not time_value:
            print("[-] Time required hai. Entry dobara karein.")
            continue

        pairs.append((date_value, time_value))
        number += 1

    return pairs


def _print_dataframe(title: str, dataframe: pd.DataFrame, *, max_rows: int = 20) -> None:
    print("" + "=" * 78)
    print(title)
    print("=" * 78)

    if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
        print("No records found.")
        return

    print(dataframe.head(max_rows).to_string(index=False))


def _print_tower_ipdr_backend_status(
    payload: dict[str, Any],
    *,
    title: str = "TOWER IPDR FAST ANALYSIS BACKEND READY",
) -> None:
    """Print user-friendly Tower IPDR backend status.

    Normal users should not see DuckDB/manifest/pipeline JSON paths.
    Developer can show backend paths using:
    TELECOM_DEBUG_BACKEND=1 python3 -u main.py
    """

    import os

    debug_backend = os.environ.get("TELECOM_DEBUG_BACKEND") == "1"

    stage = payload.get("stage", {}) or {}
    fingerprint = payload.get("input_fingerprint", {}) or {}
    import_summary = payload.get("import_summary", {}) or {}

    input_files = (
        import_summary.get("candidate_files")
        or fingerprint.get("file_count")
        or 0
    )

    print()
    print("=" * 78)
    print(title)
    print("=" * 78)
    print(f"Records indexed : {int(stage.get('record_count', 0)):,}")
    print(f"Columns indexed : {int(stage.get('column_count', 0)):,}")
    print(f"Input files     : {int(input_files):,}")

    if import_summary:
        print(f"Loaded files    : {int(import_summary.get('loaded_files', 0)):,}")
        print(f"Skipped files   : {int(import_summary.get('skipped_files', 0)):,}")
        print(f"Failed files    : {int(import_summary.get('failed_files', 0)):,}")
        print(f"Rows this run   : {int(import_summary.get('rows_loaded_this_run', 0)):,}")

    print("Speed mode      : DuckDB SQL internal backend")
    print("User output     : Excel / GUI report only")
    print("=" * 78)

    if debug_backend:
        print("DEBUG BACKEND FILES")
        print("-" * 78)
        print(f"DuckDB file     : {stage.get('duckdb_path', '')}")
        print(f"Manifest        : {stage.get('manifest_path', '')}")
        print(f"Pipeline state  : {payload.get('pipeline_state_path', '')}")
        print("-" * 78)


def _collect_date_time_ranges() -> list[tuple[str, str]]:
    print("\n" + "=" * 78)
    print("CREATE DATE-TIME PARTS")
    print("=" * 78)
    print("Har part ke liye Start Date-Time aur End Date-Time enter karein.")
    print("Example Date : 2026-06-11")
    print("Example Time : 20:00:00")
    print()
    print("Rule:")
    print("Part 1 Start + Part 1 End = Part 1")
    print("Part 2 Start + Part 2 End = Part 2")
    print("Blank Start Date = finish")
    print("=" * 78)

    ranges: list[tuple[str, str]] = []
    part_no = 1

    while True:
        print(f"\nPart {part_no}")

        start_date = input("  Start Date (blank = finish): ").strip()
        if not start_date:
            break

        start_time = input("  Start Time: ").strip()
        if not start_time:
            print("[-] Start Time required hai. Is part ko dobara enter karein.")
            continue

        end_date = input("  End Date  : ").strip()
        if not end_date:
            print("[-] End Date required hai. Is part ko dobara enter karein.")
            continue

        end_time = input("  End Time  : ").strip()
        if not end_time:
            print("[-] End Time required hai. Is part ko dobara enter karein.")
            continue

        ranges.append(
            (
                f"{start_date} {start_time}",
                f"{end_date} {end_time}",
            )
        )
        part_no += 1

    return ranges


