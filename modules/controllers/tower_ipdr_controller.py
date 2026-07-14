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
from modules.reporting.tower_ipdr_console import (
    print_tower_ipdr_analysis,
    print_tower_ipdr_partition,
)


SUPPORTED_SUFFIXES = {".csv", ".txt"}


def _menu(case: dict[str, Any]) -> str:
    print("\n" + "=" * 78)
    print(
        f"TOWER IPDR DUMP WORKSPACE | "
        f"{case.get('case_id', '')} | "
        f"{case.get('case_name', '')}"
    )
    print("=" * 78)
    print("1. Run Complete Multi-Cell Tower IPDR Analysis")
    print("2. New CCTV Date-Time Partition Analysis")
    print("3. List Current CCTV Date-Times")
    print("4. Re-run Partition Using Saved Date-Times")
    print("5. Clear Saved CCTV Date-Times")
    print("6. View Latest Tower IPDR Run")
    print("0. Back to Tower Dump Analysis")
    return input("\nChoose Action: ").strip()


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
    print("ENTER CCTV DATE AND TIME")
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
    print("SAVED CCTV DATE-TIME WINDOWS")
    print("=" * 92)

    if not sightings:
        print("No CCTV date-time configured.")
        return

    print(
        f"{'#':<4}{'Partition':<12}"
        f"{'CCTV Timestamp':<24}"
        f"{'Window Start':<24}"
        f"{'Window End':<24}"
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
                raise CaseError("CCTV date-time windows configured nahi hain.")

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

    replace_simple_sightings(
        str(case["case_id"]),
        pairs,
        minutes_before=10,
        minutes_after=10,
    )
    _print_sightings(str(case["case_id"]))
    return _execute(case, use_partitions=True)


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
                print("[+] Saved CCTV date-times cleared.")

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
