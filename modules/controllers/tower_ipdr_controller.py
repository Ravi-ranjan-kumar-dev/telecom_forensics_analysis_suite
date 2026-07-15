"""Case-aware multi-cell Tower IPDR/NAT workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from modules.analysis.toweripdr import (
    create_tower_ipdr_partitions,
    run_tower_ipdr_analysis,
)
from modules.cases import (
    CaseError,
    case_evidence_dir,
    case_report_dir,
    clear_sightings,
    list_sightings,
    list_cgi_groups,
    log_case_event,
    register_analysis_run,
    register_evidence,
    register_report,
    replace_simple_sightings,
)
from modules.cases.tower_ipdr_store import (
    attach_tower_ipdr_report,
    load_latest_tower_ipdr_manifest,
    save_tower_ipdr_run,
)
from modules.core.paths import TOWER_IPDR_DUMP_DATA_DIR
from modules.loader.tower_ipdr_loader import load_tower_ipdr_case
from modules.staging.tower_ipdr_staging import (
    count_tower_ipdr_events,
    import_tower_ipdr_folder_to_duckdb,
    tower_ipdr_cell_counts,
    tower_ipdr_database_path,
    tower_ipdr_manifest_path,
    tower_ipdr_minute_count,
    tower_ipdr_time_count,
    tower_ipdr_uncommon_in_minute,
)
from modules.reporting.tower_ipdr_console import (
    print_tower_ipdr_analysis,
    print_tower_ipdr_partition,
)


SUPPORTED_SUFFIXES = {".csv", ".txt"}


def _menu(case: dict[str, Any]) -> str:
    print("" + "=" * 78)
    print(
        f"TOWER IPDR DUMP WORKSPACE | "
        f"{case.get('case_id', '')} | "
        f"{case.get('case_name', '')}"
    )
    print("=" * 78)
    print("1. Load / Rebuild Tower IPDR Dump")
    print("2. Date-Time Partitioning")
    print("3. Run Fast Partition Analysis")
    print("4. View Staging Status")
    print("5. Advanced Tools")
    print("0. Back to Tower Dump Analysis")
    return input("Choose Action: ").strip()

def _has_files(directory: Path) -> bool:
    return directory.is_dir() and any(
        path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        for path in directory.rglob("*")
    )


def _input_folder(case_id: str) -> Path:
    case_folder = case_evidence_dir(case_id, "tower_dump", "ipdr")

    if _has_files(case_folder):
        return case_folder

    return TOWER_IPDR_DUMP_DATA_DIR / "input"


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


def _print_sightings(case_id: str) -> None:
    sightings = list_sightings(case_id)

    print("\n" + "=" * 92)
    print("SAVED DATE-TIME PARTITIONS")
    print("=" * 92)

    if not sightings:
        print("No date-time partitions configured.")
        return

    print(
        f"{'#':<4}{'Partition':<12}"
        f"{'Partition Time':<24}"
        f"{'Start Time':<24}"
        f"{'End Time':<24}"
    )
    print("-" * 92)

    for index, item in enumerate(sightings, start=1):
        print(
            f"{index:<4}"
            f"{'P' + str(index):<12}"
            f"{str(item.get('cctv_timestamp', '')):<24}"
            f"{str(item.get('window_start', '')):<24}"
            f"{str(item.get('window_end', '')):<24}"
        )


def _load(case_id: str) -> tuple[dict[str, Any], Path]:
    input_folder = _input_folder(case_id)
    print(f"[+] Tower IPDR Dump input folder: {input_folder}")

    load_result = load_tower_ipdr_case(input_folder, recursive=True)

    if not load_result.get("ok"):
        print(
            "[-] Supported Tower IPDR dump load nahi hua "
            "(current parser: Jio CELL ID_IPDRNAT)."
        )

        for error in load_result.get("errors", []):
            print(f"    ERROR: {error}")

        for warning in load_result.get("warnings", []):
            print(f"    WARNING: {warning}")

        raise ValueError("Tower IPDR loading failed.")

    for file_result in load_result.get("file_results", []):
        if not file_result.get("ok"):
            continue

        register_evidence(
            case_id,
            evidence_type="TOWER_IPDR_DUMP",
            source_file=file_result.get("file", ""),
            operator=(file_result.get("metadata", {}) or {}).get("operator", "Jio"),
            source_category="TOWER_IPDR_NAT",
        )

    return load_result, input_folder


def _execute(
    case: dict[str, Any],
    *,
    use_partitions: bool,
) -> dict[str, Any] | None:
    case_id = str(case["case_id"])
    analysis_type = (
        "TOWER_IPDR_DUMP_PARTITION"
        if use_partitions
        else "TOWER_IPDR_DUMP"
    )

    log_case_event(
        case_id,
        action=(
            "TOWER_IPDR_PARTITION_ANALYSIS_STARTED"
            if use_partitions
            else "TOWER_IPDR_ANALYSIS_STARTED"
        ),
    )

    try:
        load_result, input_folder = _load(case_id)
        dataframe = load_result.get("df")

        if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
            raise ValueError("Normalized Tower IPDR DataFrame unavailable.")

        sightings: list[dict[str, Any]] = []
        uncommon_window_start = None
        uncommon_window_end = None

        if use_partitions:
            sightings = list_sightings(case_id)

            if not sightings:
                raise CaseError("Date-time partitions configured nahi hain.")

            for sighting in sightings:
                window_start = sighting.get("window_start")
                window_end = sighting.get("window_end")

                if window_start and window_end:
                    uncommon_window_start = str(window_start)
                    uncommon_window_end = str(window_end)
                    break

        analysis = run_tower_ipdr_analysis(
            dataframe,
            file_summary=load_result.get("file_summary"),
            uncommon_window_start=uncommon_window_start,
            uncommon_window_end=uncommon_window_end,
        )
        analysis["rejected_rows"] = load_result.get("rejected_rows", pd.DataFrame())
        print_tower_ipdr_analysis(analysis, row_limit=20)

        partition = None

        if use_partitions:
            partition = create_tower_ipdr_partitions(
                dataframe,
                sightings=sightings,
                cgi_groups=list_cgi_groups(case_id),
            )
            print_tower_ipdr_partition(partition, row_limit=50)

        saved = save_tower_ipdr_run(
            case_id,
            analysis=analysis,
            partition=partition,
            input_folder=input_folder,
            source_files=[
                result.get("file", "")
                for result in load_result.get("file_results", [])
                if result.get("ok")
            ],
            warnings=load_result.get("warnings", []),
            errors=load_result.get("errors", []),
        )

        from modules.reporting.tower_ipdr_excel import (
            generate_tower_ipdr_excel_report,
        )

        excel_path = generate_tower_ipdr_excel_report(
            case=case,
            load_result=load_result,
            analysis=analysis,
            partition=partition,
            output_dir=case_report_dir(case_id, "tower_ipdr_dump"),
            saved=saved,
        )

        attach_tower_ipdr_report(
            case_id,
            run_id=saved["run_id"],
            report_path=excel_path,
        )
        register_report(
            case_id,
            report_type="TOWER_IPDR_DUMP",
            report_path=excel_path,
        )

        output_records = (
            len(partition.get("event_n_of_m_candidates", []))
            if isinstance(partition, dict)
            else len(analysis.get("subscriber_multi_cell_candidates", []))
        )
        register_analysis_run(
            case_id,
            analysis_type=analysis_type,
            status="COMPLETED",
            input_records=len(dataframe),
            output_records=output_records,
            report_path=str(excel_path),
        )

        print("\n" + "=" * 78)
        print("TOWER IPDR DUMP ANALYSIS COMPLETED")
        print("=" * 78)
        print(f"Input Events   : {len(dataframe):,}")
        print(f"Searched Cells : {analysis.get('total_cells', 0):,}")
        print(
            "Multi-cell Subs: "
            f"{len(analysis.get('subscriber_multi_cell_candidates', [])):,}"
        )
        print(f"Backend Run    : {saved['run_directory']}")

        if isinstance(partition, dict):
            print(f"Partitions     : {partition.get('total_partitions', 0)}")
            print(
                "Event N-of-M   : "
                f"{len(partition.get('event_n_of_m_candidates', [])):,}"
            )
            print(
                "Allocation N/M : "
                f"{len(partition.get('allocation_n_of_m_candidates', [])):,}"
            )

        print(f"Excel Report   : {excel_path}")
        print("=" * 78)

        return {
            "load": load_result,
            "analysis": analysis,
            "partition": partition,
            "saved": saved,
            "excel_report": str(excel_path),
        }

    except Exception as error:
        register_analysis_run(
            case_id,
            analysis_type=analysis_type,
            status="FAILED",
            error_message=str(error),
        )
        print(
            f"[-] Tower IPDR analysis failed: "
            f"{type(error).__name__}: {error}"
        )
        return None


def _new_partition(case: dict[str, Any]) -> dict[str, Any] | None:
    pairs = _collect_date_time_pairs()

    if not pairs:
        print("[-] Koi date-time enter nahi hua.")
        return None

    case_id = str(case["case_id"])

    replace_simple_sightings(
        case_id,
        pairs,
        minutes_before=0,
        minutes_after=0,
    )

    _print_sightings(case_id)
    print("[+] Date-time partitions saved. Fast SQL query ke liye options 5, 6, 7 use karein.")

    return {
        "case_id": case_id,
        "partitions": list_sightings(case_id),
    }


def _print_dataframe(title: str, dataframe: pd.DataFrame, *, max_rows: int = 20) -> None:
    print("" + "=" * 78)
    print(title)
    print("=" * 78)

    if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
        print("No records found.")
        return

    print(dataframe.head(max_rows).to_string(index=False))


def _import_staging(case: dict[str, Any]) -> None:
    case_id = str(case["case_id"])
    input_folder = _input_folder(case_id)

    print(f"[+] Tower IPDR staging input folder: {input_folder}")

    summary = import_tower_ipdr_folder_to_duckdb(
        case_id,
        input_folder,
        recursive=True,
        force_rebuild=True,
    )

    print("" + "=" * 78)
    print("TOWER IPDR STAGING IMPORT COMPLETED")
    print("=" * 78)
    print(f"Candidate Files : {summary.get('candidate_files', 0):,}")
    print(f"Loaded Files    : {summary.get('loaded_files', 0):,}")
    print(f"Skipped Files   : {summary.get('skipped_files', 0):,}")
    print(f"Failed Files    : {summary.get('failed_files', 0):,}")
    print(f"Rows This Run   : {summary.get('rows_loaded_this_run', 0):,}")
    print(f"Rows In DB      : {summary.get('total_rows_in_database', 0):,}")
    print(f"Database        : {summary.get('database_path', '')}")
    print(f"Manifest        : {summary.get('manifest_path', '')}")

    _print_dataframe(
        "TOP CELL COUNTS",
        tower_ipdr_cell_counts(case_id).head(20),
        max_rows=20,
    )


def _show_staging_status(case_id: str) -> None:
    database_path = tower_ipdr_database_path(case_id)
    manifest_path = tower_ipdr_manifest_path(case_id)
    row_count = count_tower_ipdr_events(case_id)

    print("" + "=" * 78)
    print("TOWER IPDR STAGING STATUS")
    print("=" * 78)
    print(f"Database Exists : {database_path.exists()}")
    print(f"Manifest Exists : {manifest_path.exists()}")
    print(f"Database Path   : {database_path}")
    print(f"Manifest Path   : {manifest_path}")
    print(f"Rows In DB      : {row_count:,}")

    if row_count:
        _print_dataframe(
            "TOP CELL COUNTS",
            tower_ipdr_cell_counts(case_id).head(20),
            max_rows=20,
        )


def _saved_partition_times(case_id: str) -> list[str]:
    values: list[str] = []

    for item in list_sightings(case_id):
        value = item.get("cctv_timestamp") or item.get("window_start") or ""
        value = str(value).strip()

        if value:
            values.append(value)

    return values


def _ask_partition_time(case_id: str) -> str:
    saved_times = _saved_partition_times(case_id)

    if saved_times:
        _print_sightings(case_id)
        print("Saved partition number enter karein, ya exact date-time type karein.")
        print("Blank Enter = first saved partition.")

    value = input("Date-time partition (number/date-time): ").strip()

    if not value and saved_times:
        return saved_times[0]

    if value.isdigit() and saved_times:
        index = int(value)

        if 1 <= index <= len(saved_times):
            return saved_times[index - 1]

    if not value:
        raise CaseError("Date-time partition required hai.")

    return value


def _run_exact_partition_query(case: dict[str, Any]) -> None:
    case_id = str(case["case_id"])
    partition_time = _ask_partition_time(case_id)

    _print_dataframe(
        f"EXACT DATE-TIME PARTITION | {partition_time}",
        tower_ipdr_time_count(case_id, partition_time),
    )


def _run_minute_partition_query(case: dict[str, Any]) -> None:
    case_id = str(case["case_id"])
    partition_time = _ask_partition_time(case_id)

    _print_dataframe(
        f"SAME-MINUTE DATE-TIME PARTITION | {partition_time}",
        tower_ipdr_minute_count(case_id, partition_time),
    )


def _run_minute_uncommon_query(case: dict[str, Any]) -> None:
    case_id = str(case["case_id"])
    partition_time = _ask_partition_time(case_id)

    _print_dataframe(
        f"SAME-MINUTE UNCOMMON LEADS | {partition_time}",
        tower_ipdr_uncommon_in_minute(case_id, partition_time, limit=50),
        max_rows=50,
    )


def _run_legacy_full_analysis(case: dict[str, Any]) -> None:
    print("[WARNING] यह legacy full pandas analysis है.")
    print("[WARNING] Large Tower IPDR dump पर यह ज्यादा time और memory ले सकता है.")
    confirm = input("Run legacy full pandas analysis? Type YES to continue: ").strip()

    if confirm != "YES":
        print("[+] Legacy analysis cancelled.")
        return

    _execute(case, use_partitions=False)


def _partition_menu(case: dict[str, Any]) -> None:
    case_id = str(case["case_id"])

    while True:
        print("\n" + "=" * 78)
        print("DATE-TIME PARTITIONING")
        print("=" * 78)
        print("1. Add / Replace Date-Time Partitions")
        print("2. List Date-Time Partitions")
        print("3. Clear Date-Time Partitions")
        print("0. Back")

        choice = input("\nChoose Action: ").strip()

        if choice == "1":
            _new_partition(case)
        elif choice == "2":
            _print_sightings(case_id)
        elif choice == "3":
            clear_sightings(case_id)
            print("[+] Saved date-time partitions cleared.")
        elif choice == "0":
            return
        else:
            print("[-] Invalid choice. Select 0 to 3.")


def _run_fast_partition_analysis(case: dict[str, Any]) -> None:
    case_id = str(case["case_id"])
    partition_time = _ask_partition_time(case_id)

    print("\n" + "=" * 78)
    print(f"FAST DATE-TIME PARTITION ANALYSIS | {partition_time}")
    print("=" * 78)

    _print_dataframe(
        "1. EXACT SECOND COUNT",
        tower_ipdr_time_count(case_id, partition_time),
    )

    _print_dataframe(
        "2. SAME-MINUTE COUNT",
        tower_ipdr_minute_count(case_id, partition_time),
    )

    _print_dataframe(
        "3. SAME-MINUTE UNCOMMON LEADS",
        tower_ipdr_uncommon_in_minute(case_id, partition_time, limit=50),
        max_rows=50,
    )


def _advanced_menu(case: dict[str, Any]) -> None:
    case_id = str(case["case_id"])

    while True:
        print("\n" + "=" * 78)
        print("ADVANCED TOWER IPDR TOOLS")
        print("=" * 78)
        print("1. Exact-second Query Only")
        print("2. Same-minute Query Only")
        print("3. Same-minute Uncommon Leads Only")
        print("4. Legacy Full Pandas Analysis")
        print("5. View Latest Legacy Tower IPDR Run")
        print("0. Back")

        choice = input("\nChoose Action: ").strip()

        if choice == "1":
            _run_exact_partition_query(case)
        elif choice == "2":
            _run_minute_partition_query(case)
        elif choice == "3":
            _run_minute_uncommon_query(case)
        elif choice == "4":
            _run_legacy_full_analysis(case)
        elif choice == "5":
            _show_latest(case_id)
        elif choice == "0":
            return
        else:
            print("[-] Invalid choice. Select 0 to 5.")


def _show_latest(case_id: str) -> None:
    manifest = load_latest_tower_ipdr_manifest(case_id)

    if not manifest:
        print("[-] Koi Tower IPDR run available nahi hai.")
        return

    print("\n" + "=" * 78)
    print(f"LATEST TOWER IPDR RUN: {manifest.get('run_id', '')}")
    print("=" * 78)
    print(f"Created At      : {manifest.get('created_at', '')}")
    print(f"Input Folder    : {manifest.get('input_folder', '')}")
    print(f"Events          : {manifest.get('record_count', 0)}")
    print(f"Searched Cells  : {manifest.get('cell_count', 0)}")
    print(f"Partitions      : {manifest.get('partition_count', 0)}")
    print(f"Actual Rule     : {manifest.get('actual_event_rule', '')}")
    print(f"Allocation Rule : {manifest.get('allocation_overlap_rule', '')}")
    print(f"Report Status   : {manifest.get('report_status', '')}")
    print(
        "Excel Report    : "
        f"{manifest.get('user_facing_report', 'Not generated')}"
    )
    print(f"Backend tables  : {len(manifest.get('saved_files', {}))}")
    print("=" * 78)


def handle_tower_ipdr_workspace(
    case: dict[str, Any],
) -> dict[str, Any] | None:
    case_id = str(case["case_id"])

    while True:
        try:
            choice = _menu(case)

            if choice == "1":
                _execute(case, use_partitions=False)

            elif choice == "2":
                _new_partition(case)

            elif choice == "3":
                _print_sightings(case_id)

            elif choice == "4":
                _execute(case, use_partitions=True)

            elif choice == "5":
                clear_sightings(case_id)
                print("[+] Saved date-time partitions cleared.")

            elif choice == "6":
                _show_latest(case_id)

            elif choice == "0":
                return None

            else:
                print("[-] Invalid choice. Select 0 to 6.")

        except KeyboardInterrupt:
            print("\n[-] Returning to Tower IPDR workspace.")

        except EOFError:
            return None

        except Exception as error:
            print(
                f"[-] Tower IPDR workspace error: "
                f"{type(error).__name__}: {error}"
            )
