"""Case-aware Tower CDR Dump workspace.

Case users enter only CCTV date and time. Sighting IDs, time windows and
CGI handling are automatic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from modules.analysis.towerdump.window_partition import (
    create_sighting_partitions,
)
from modules.cases import (
    CaseError,
    attach_partition_report,
    case_evidence_dir,
    case_report_dir,
    clear_sightings,
    list_cgi_groups,
    list_sightings,
    load_latest_partition_manifest,
    log_case_event,
    register_analysis_run,
    register_report,
    replace_simple_sightings,
    save_partition_run,
)
from modules.core.paths import (
    TOWER_CDR_DUMP_DATA_DIR,
    TOWER_DUMP_DATA_DIR,
)


SUPPORTED_SUFFIXES = {".csv", ".txt", ".tsv", ".xlsx", ".xls"}


def _tower_cdr_menu(case: dict[str, Any]) -> str:
    print("\n" + "=" * 78)
    print(
        f"TOWER CDR DUMP WORKSPACE | "
        f"{case.get('case_id', '')} | {case.get('case_name', '')}"
    )
    print("=" * 78)
    print("1. Run Complete Tower CDR Dump Analysis")
    print("2. New Date-Time Partition Analysis")
    print("3. List Current Date-Time Partitions")
    print("4. Re-run Partition Using Saved Date-Times")
    print("5. Clear Saved Date-Time Partitions")
    print("6. View Latest Partition Summary")
    print("0. Back to Case Workspace")

    return input("\nChoose Action: ").strip()


def _has_supported_files(directory: Path) -> bool:
    return directory.is_dir() and any(
        path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        for path in directory.rglob("*")
    )


def _input_folder(case_id: str) -> Path:
    canonical_case_input = case_evidence_dir(
        case_id,
        "tower_dump",
        "cdr",
    )
    legacy_case_input = case_evidence_dir(
        case_id,
        "tower_dump",
        "normal",
    )

    for candidate in (
        canonical_case_input,
        legacy_case_input,
        TOWER_CDR_DUMP_DATA_DIR / "input",
        TOWER_DUMP_DATA_DIR / "input",
    ):
        if _has_supported_files(candidate):
            return candidate

    return TOWER_CDR_DUMP_DATA_DIR / "input"


def _print_sightings(case_id: str) -> None:
    sightings = list_sightings(case_id)

    print("\n" + "=" * 94)
    print("CCTV DATE-TIME WINDOWS")
    print("=" * 94)

    if not sightings:
        print("No CCTV date-time configured.")
        return

    print(
        f"{'#':<4}{'ID':<8}{'Partition Time':<24}"
        f"{'Window Start':<24}{'Window End':<24}"
    )
    print("-" * 94)

    for index, item in enumerate(sightings, start=1):
        print(
            f"{index:<4}"
            f"{str(item.get('sighting_id', '')):<8}"
            f"{str(item.get('cctv_timestamp', '')):<24}"
            f"{str(item.get('window_start', '')):<24}"
            f"{str(item.get('window_end', '')):<24}"
        )


def _collect_date_time_pairs() -> list[tuple[str, str]]:
    """Ask only date and time. Blank date completes the input."""

    print("\n" + "=" * 72)
    print("ENTER CCTV DATE AND TIME")
    print("=" * 72)
    print("Date example : 10-07-2026")
    print("Time example : 13:00 or 13:00:00")
    print("Sabhi sightings enter karne ke baad Date blank chhodkar Enter dabayein.")

    pairs: list[tuple[str, str]] = []
    number = 1

    while True:
        date_value = input(
            f"\nSighting {number} - Date (blank = finish): "
        ).strip()

        if not date_value:
            break

        time_value = input(
            f"Sighting {number} - Time: "
        ).strip()

        if not time_value:
            print("[-] Time required hai. Is sighting ko dobara enter karein.")
            continue

        pairs.append((date_value, time_value))
        number += 1

    return pairs


def _run_complete_analysis(
    case: dict[str, Any],
) -> dict[str, Any] | None:
    from modules.controllers.tower_controller import run_tower_dump_analysis
    from modules.reporting.tower_dump_console import print_tower_dump_report
    from modules.reporting.tower_dump_excel import (
        generate_tower_dump_excel_report,
    )

    case_id = str(case["case_id"])
    input_folder = _input_folder(case_id)
    print(f"[+] Tower CDR Dump input: {input_folder}")

    log_case_event(
        case_id,
        action="TOWER_CDR_DUMP_ANALYSIS_STARTED",
        details={"input_folder": str(input_folder)},
    )

    try:
        result = run_tower_dump_analysis(
            input_folder=input_folder,
            enrich_cgi=True,
            recursive=True,
        )

        if not isinstance(result, dict) or not result.get("ok"):
            errors = (
                result.get("errors", [])
                if isinstance(result, dict)
                else []
            )
            raise ValueError(
                "Tower CDR Dump load failed. "
                + " | ".join(map(str, errors))
            )

        print_tower_dump_report(result, row_limit=25)

        excel_path = generate_tower_dump_excel_report(
            result,
            output_dir=case_report_dir(case_id, "tower_cdr_dump"),
            case_name=case_id,
        )

        register_report(
            case_id,
            report_type="TOWER_CDR_DUMP",
            report_path=excel_path,
        )

        dataframe = result.get("df")

        register_analysis_run(
            case_id,
            analysis_type="TOWER_CDR_DUMP",
            status="COMPLETED",
            input_records=(
                len(dataframe)
                if isinstance(dataframe, pd.DataFrame)
                else 0
            ),
            output_records=(
                result.get("analysis", {}).get(
                    "completed_count",
                    0,
                )
            ),
            report_path=str(excel_path),
        )

        result["excel_report"] = str(excel_path)
        print(f"\n[+] Case report: {excel_path}")
        return result

    except Exception as error:
        register_analysis_run(
            case_id,
            analysis_type="TOWER_CDR_DUMP",
            status="FAILED",
            error_message=str(error),
        )
        print(f"[-] Tower Dump analysis failed: {error}")
        return None


def _run_partition_analysis(
    case: dict[str, Any],
) -> dict[str, Any] | None:
    from modules.loader.tower_dump_loader import load_tower_dump_case

    case_id = str(case["case_id"])
    sightings = list_sightings(case_id)

    if not sightings:
        print("[-] Pehle CCTV date-time enter karein.")
        return None

    input_folder = _input_folder(case_id)
    print(f"[+] Loading Tower CDR Dump: {input_folder}")

    load_result = load_tower_dump_case(
        input_folder,
        enrich_cgi=True,
        recursive=True,
        remove_exact_duplicates=False,
    )

    dataframe = load_result.get("df")

    if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
        print("[-] Koi valid Tower CDR Dump record load nahi hua.")

        for error in load_result.get("errors", []):
            print(f"    {error}")

        return None

    print(
        f"[+] Loaded {len(dataframe):,} records. "
        f"Creating {len(sightings)} automatic time partitions..."
    )

    result = create_sighting_partitions(
        dataframe,
        sightings=sightings,
        cgi_groups=list_cgi_groups(case_id),
    )

    # Reporting diagnostics are carried forward without re-running analysis.
    result["warnings"] = list(load_result.get("warnings", []) or [])
    result["errors"] = list(load_result.get("errors", []) or [])
    result["load_metadata"] = dict(load_result.get("metadata", {}) or {})
    result["operators"] = list(load_result.get("operators", []) or [])
    result["cell_ids"] = list(load_result.get("cell_ids", []) or [])
    result["rejected_rows"] = load_result.get("rejected_rows", pd.DataFrame())
    result["input_folder"] = str(input_folder)

    summary = result["partition_summary"]

    print("\n" + "=" * 120)
    print("WINDOW-WISE PARTITION SUMMARY")
    print("=" * 120)

    if summary.empty:
        print("No partitions generated.")
    else:
        print(summary.to_string(index=False))

    n_of_m = result["n_of_m_candidates"]
    strict = result["strict_common_candidates"]

    print("\n" + "=" * 82)
    print("COMMON CANDIDATE SUMMARY")
    print("=" * 82)
    print(f"Total Date-Time Partitions : {result['total_sightings']}")
    print(f"Candidates in 2+      : {len(n_of_m):,}")
    print(f"Candidates in all     : {len(strict):,}")

    if not n_of_m.empty:
        columns = [
            column
            for column in (
                "subscriber_number",
                "match_ratio",
                "matched_sightings",
                "total_events",
                "operators",
            )
            if column in n_of_m.columns
        ]

        print("\nTop candidates:")
        print(
            n_of_m[columns]
            .head(50)
            .to_string(index=False)
        )

    # Internal CSV tables remain backend data. Full raw partitions are not
    # duplicated in simple mode.
    saved = save_partition_run(
        case_id,
        result,
        export_full_partitions=False,
    )

    try:
        from modules.reporting.tower_partition_excel import (
            generate_tower_partition_excel_report,
        )

        excel_path = generate_tower_partition_excel_report(
            result,
            case=case,
            sightings=sightings,
            output_dir=case_report_dir(case_id, "tower_cdr_dump"),
            input_folder=input_folder,
            saved=saved,
        )

        attach_partition_report(
            case_id,
            run_id=saved["run_id"],
            report_path=excel_path,
        )

        register_report(
            case_id,
            report_type="TOWER_CDR_DUMP_PARTITION",
            report_path=excel_path,
        )

        register_analysis_run(
            case_id,
            analysis_type="TOWER_CDR_DUMP_PARTITION",
            status="COMPLETED",
            input_records=len(dataframe),
            output_records=len(n_of_m),
            report_path=str(excel_path),
        )

    except Exception as error:
        register_analysis_run(
            case_id,
            analysis_type="TOWER_CDR_DUMP_PARTITION",
            status="COMPLETED_WITH_REPORT_ERROR",
            input_records=len(dataframe),
            output_records=len(n_of_m),
            report_path=saved["run_directory"],
            error_message=str(error),
        )

        print(
            f"[-] Consolidated Excel report failed: "
            f"{type(error).__name__}: {error}"
        )
        print(
            f"[+] Internal backend data preserved: "
            f"{saved['run_directory']}"
        )

        result["saved"] = saved
        result["excel_report"] = ""
        return result

    print("\n" + "=" * 82)
    print("PARTITION ANALYSIS COMPLETED")
    print("=" * 82)
    print(f"Dynamic Partitions : {result['total_sightings']}")
    print(f"Candidates in 2+   : {len(n_of_m):,}")
    print(f"Candidates in All  : {len(strict):,}")
    print(f"Excel Report       : {excel_path}")
    print(f"Backend Data       : {saved['run_directory']}")
    print("=" * 82)
    print("[+] Raw Tower CDR Dump files unchanged hain.")
    print("[+] User-facing output ek consolidated Excel workbook hai.")

    result["saved"] = saved
    result["excel_report"] = str(excel_path)
    return result


def _new_partition_workflow(
    case: dict[str, Any],
) -> dict[str, Any] | None:
    case_id = str(case["case_id"])
    pairs = _collect_date_time_pairs()

    if not pairs:
        print("[-] Koi CCTV date-time enter nahi hua.")
        return None

    records = replace_simple_sightings(
        case_id,
        pairs,
        minutes_before=0,
        minutes_after=0,
    )

    print(
        f"\n[+] {len(records)} date-time partitions automatically created."
    )
    _print_sightings(case_id)

    return _run_partition_analysis(case)


def _show_latest(case_id: str) -> None:
    manifest = load_latest_partition_manifest(case_id)

    if not manifest:
        print("[-] Koi partition run available nahi hai.")
        return

    print("\n" + "=" * 90)
    print(f"LATEST PARTITION RUN: {manifest.get('run_id', '')}")
    print("=" * 90)
    print(f"Created At          : {manifest.get('created_at', '')}")
    print(f"Total Input Records : {manifest.get('total_input_records', 0)}")
    print(f"Total Sightings     : {manifest.get('total_sightings', 0)}")

    for item in manifest.get("partition_summary", []):
        print(
            f"- {item.get('sighting_id')} | "
            f"{item.get('cctv_timestamp')} | "
            f"records={item.get('filtered_records', 0)} | "
            f"subscribers={item.get('unique_subscribers', 0)} | "
            f"cells={item.get('unique_searched_cells', 0)}"
        )

    print(
        f"Consolidated Report : "
        f"{manifest.get('consolidated_excel_report', 'Not generated')}"
    )
    print(
        f"Backend Run Data    : "
        f"{manifest.get('run_id', '')}"
    )


def handle_tower_cdr_workspace(
    case: dict[str, Any],
) -> dict[str, Any] | None:
    case_id = str(case["case_id"])

    while True:
        try:
            choice = _tower_cdr_menu(case)

            if choice == "1":
                _run_complete_analysis(case)

            elif choice == "2":
                _new_partition_workflow(case)

            elif choice == "3":
                _print_sightings(case_id)

            elif choice == "4":
                _run_partition_analysis(case)

            elif choice == "5":
                clear_sightings(case_id)
                print("[+] Saved CCTV date-times cleared.")

            elif choice == "6":
                _show_latest(case_id)

            elif choice == "0":
                return None

            else:
                print("[-] Invalid choice. Select 0 to 6.")

        except CaseError as error:
            print(f"[-] Configuration error: {error}")

        except ValueError as error:
            print(f"[-] Invalid value: {error}")

        except KeyboardInterrupt:
            print("\n[-] Returning to Tower CDR Dump workspace.")

        except EOFError:
            return None

        except Exception as error:
            print(
                f"[-] Tower CDR Dump workspace error: "
                f"{type(error).__name__}: {error}"
            )
