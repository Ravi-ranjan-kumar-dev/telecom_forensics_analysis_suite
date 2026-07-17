"""Case-aware Tower GPRS Dump workspace.

The current parser supports the uploaded Airtel GPRS session format.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from modules.analysis.gprsdump import (
    create_gprs_partitions,
    run_gprs_analysis,
)
from modules.cases import (
    CaseError,
    case_evidence_dir,
    clear_sightings,
    list_sightings,
    list_cgi_groups,
    log_case_event,
    register_analysis_run,
    register_evidence,
    register_report,
    case_report_dir,
    replace_simple_sightings,
)
from modules.cases.gprs_store import (
    attach_gprs_report,
    load_latest_gprs_manifest,
    save_gprs_run,
)
from modules.core.paths import (
    GPRS_DUMP_DATA_DIR,
    TOWER_GPRS_DUMP_DATA_DIR,
)
from modules.loader.gprs_dump_loader import load_gprs_dump_case
from modules.reporting.tower_gprs_console import (
    print_gprs_analysis,
    print_gprs_partition,
)


SUPPORTED_SUFFIXES = {".csv", ".txt"}


def _menu(case: dict[str, Any]) -> str:
    print("\n" + "=" * 78)
    print(
        f"TOWER GPRS DUMP WORKSPACE | "
        f"{case.get('case_id', '')} | "
        f"{case.get('case_name', '')}"
    )
    print("=" * 78)
    print("1. Run Complete Tower GPRS Dump Analysis")
    print("2. New Date-Time Partition Analysis")
    print("3. List Current Date-Time Partitions")
    print("4. Re-run Partition Using Saved Date-Times")
    print("5. Clear Saved Date-Time Partitions")
    print("6. View Latest GPRS Run")
    print("0. Back to Case Workspace")
    return input("\nChoose Action: ").strip()


def _has_files(directory: Path) -> bool:
    return directory.is_dir() and any(
        path.is_file()
        and path.suffix.lower() in SUPPORTED_SUFFIXES
        for path in directory.rglob("*")
    )


def _input_folder(case_id: str) -> Path:
    canonical_case_folder = case_evidence_dir(
        case_id,
        "tower_dump",
        "gprs",
    )
    legacy_case_folder = case_evidence_dir(
        case_id,
        "gprs_dump",
    )

    for candidate in (
        canonical_case_folder,
        legacy_case_folder,
        TOWER_GPRS_DUMP_DATA_DIR / "input",
        GPRS_DUMP_DATA_DIR / "input",
    ):
        if _has_files(candidate):
            return candidate

    return TOWER_GPRS_DUMP_DATA_DIR / "input"


def _collect_date_time_pairs() -> list[tuple[str, str]]:
    print("\n" + "=" * 72)
    print("ENTER DATE-TIME PARTS")
    print("=" * 72)
    print("Date example : 11-06-2026")
    print("Time example : 19:50 or 19:50:00")
    print("Sabhi parts enter karne ke baad Date blank chhodkar Enter dabayein.")

    pairs: list[tuple[str, str]] = []
    number = 1

    while True:
        date_value = input(
            f"\nPartition {number} - Date (blank = finish): "
        ).strip()

        if not date_value:
            break

        time_value = input(
            f"Partition {number} - Time: "
        ).strip()

        if not time_value:
            print("[-] Time required hai. Entry dobara karein.")
            continue

        pairs.append((date_value, time_value))
        number += 1

    return pairs


def _print_sightings(case_id: str) -> None:
    sightings = list_sightings(case_id)

    print("\n" + "=" * 92)
    print("SAVED DATE-TIME PARTS")
    print("=" * 92)

    if not sightings:
        print("No date-time part configured.")
        return

    print(
        f"{'#':<4}{'Partition':<12}"
        f"{'Partition Time':<24}"
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
    print(f"[+] Tower GPRS Dump input folder: {input_folder}")

    load_result = load_gprs_dump_case(
        input_folder,
        recursive=True,
    )

    if not load_result.get("ok"):
        print("[-] Supported Tower GPRS Dump load nahi hua (current parser: Airtel GPRS session format).")

        for error in load_result.get("errors", []):
            print(f"    ERROR: {error}")

        for warning in load_result.get("warnings", []):
            print(f"    WARNING: {warning}")

        raise ValueError("Tower GPRS Dump loading failed.")

    for file_result in load_result.get("file_results", []):
        if not file_result.get("ok"):
            continue

        register_evidence(
            case_id,
            evidence_type="TOWER_GPRS_DUMP",
            source_file=file_result.get("file", ""),
            operator=(file_result.get("metadata", {}) or {}).get("operator", ""),
            source_category="TOWER_GPRS_SESSION",
        )

    return load_result, input_folder


def _execute(
    case: dict[str, Any],
    *,
    use_partitions: bool,
) -> dict[str, Any] | None:
    from modules.analysis.gprsdump.duckdb_presence import (
        build_tower_gprs_duckdb_presence,
    )
    from modules.pipeline.scalable_analysis_pipeline import (
        run_scalable_analysis_pipeline,
    )
    from modules.staging.tower_gprs_staging import (
        TOWER_GPRS_DATASET,
        TOWER_GPRS_TABLE,
        TOWER_GPRS_WORKFLOW,
    )

    case_id = str(case["case_id"])

    log_case_event(
        case_id,
        action=(
            "TOWER_GPRS_PARTITION_ANALYSIS_STARTED"
            if use_partitions
            else "TOWER_GPRS_ANALYSIS_STARTED"
        ),
    )

    try:
        input_folder = _input_folder(case_id)
        print(f"[+] Tower GPRS Dump input folder: {input_folder}")

        pipeline_result = run_scalable_analysis_pipeline(
            case_id=case_id,
            workflow=TOWER_GPRS_WORKFLOW,
            input_folder=input_folder,
            loader=load_gprs_dump_case,
            loader_kwargs={
                "recursive": True,
            },
            table_name=TOWER_GPRS_TABLE,
            dataset_name=TOWER_GPRS_DATASET,
            dataframe_key="df",
            sql_analysis=build_tower_gprs_duckdb_presence,
            sql_analysis_kwargs={"top_limit": 200},
            supported_suffixes=SUPPORTED_SUFFIXES,
            status_title="TOWER GPRS FAST ANALYSIS BACKEND READY",
            print_status=True,
        )

        load_result = pipeline_result.get("load_result", {})
        dataframe = pipeline_result.get("dataframe")

        if not isinstance(load_result, dict) or not load_result.get("ok"):
            print("[-] Supported Tower GPRS Dump load nahi hua (current parser: Airtel GPRS session format).")

            for error in load_result.get("errors", []):
                print(f"    ERROR: {error}")

            for warning in load_result.get("warnings", []):
                print(f"    WARNING: {warning}")

            raise ValueError("Tower GPRS Dump loading failed.")

        if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
            raise ValueError("Normalized GPRS DataFrame unavailable.")

        for file_result in load_result.get("file_results", []):
            if not file_result.get("ok"):
                continue

            register_evidence(
                case_id,
                evidence_type="TOWER_GPRS_DUMP",
                source_file=file_result.get("file", ""),
                operator=(file_result.get("metadata", {}) or {}).get("operator", ""),
                source_category="TOWER_GPRS_SESSION",
            )

        analysis = run_gprs_analysis(
            dataframe,
            file_summary=load_result.get("file_summary"),
        )

        sql_presence = pipeline_result.get("sql_analysis", {}) or {}

        if isinstance(sql_presence, dict):
            for key in (
                "gprs_common_numbers",
                "gprs_uncommon_numbers",
                "gprs_multi_cell_presence",
                "gprs_device_consistency",
                "gprs_suspicious_timing",
                "gprs_priority_leads",
            ):
                value = sql_presence.get(key)
                if isinstance(value, pd.DataFrame):
                    analysis[key] = value

            analysis["duckdb_sql_presence_status"] = pd.DataFrame(
                [
                    {
                        "analysis": "tower_gprs_duckdb_sql_presence_engine",
                        "status": "COMPLETED",
                        "rows": int(
                            (pipeline_result.get("sql_result_rows", {}) or {})
                            .get("subscriber_rollup", 0)
                            or 0
                        ),
                        "duration_ms": (
                            pipeline_result.get("timings", {}) or {}
                        ).get("sql_analysis_ms", 0),
                        "error": "",
                    }
                ]
            )

        analysis["rejected_rows"] = load_result.get("rejected_rows", pd.DataFrame())
        analysis["scalable_pipeline"] = {
            "stage": pipeline_result.get("stage", {}),
            "sql_result_rows": pipeline_result.get("sql_result_rows", {}),
            "timings": pipeline_result.get("timings", {}),
            "pipeline_state_path": pipeline_result.get("pipeline_state_path", ""),
        }

        print_gprs_analysis(analysis, row_limit=20)

        partition = None

        if use_partitions:
            sightings = list_sightings(case_id)

            if not sightings:
                raise CaseError(
                    "Date-time parts configured nahi hain."
                )

            partition = create_gprs_partitions(
                dataframe,
                sightings=sightings,
                cgi_groups=list_cgi_groups(case_id),
            )
            print_gprs_partition(partition, row_limit=50)

        saved = save_gprs_run(
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

        output_records = (
            len(partition.get("n_of_m_candidates", []))
            if isinstance(partition, dict)
            else len(analysis.get("subscriber_summary", []))
        )

        from modules.reporting.tower_gprs_excel import (
            generate_tower_gprs_excel_report,
        )

        excel_path = generate_tower_gprs_excel_report(
            case=case,
            load_result=load_result,
            analysis=analysis,
            partition=partition,
            output_dir=case_report_dir(
                case_id,
                "tower_gprs_dump",
            ),
            saved=saved,
        )

        attach_gprs_report(
            case_id,
            run_id=saved["run_id"],
            report_path=excel_path,
        )

        register_report(
            case_id,
            report_type="TOWER_GPRS_DUMP",
            report_path=excel_path,
        )

        from modules.cases.latest_reports import save_latest_report

        save_latest_report(
            case_id,
            "tower_gprs_dump",
            title="Tower GPRS Dump Analysis",
            report_path=excel_path,
            report_folder=case_report_dir(case_id, "tower_gprs_dump"),
            metadata={
                "input_records": len(dataframe),
                "sql_engine_ms": (
                    pipeline_result.get("timings", {}) or {}
                ).get("sql_analysis_ms", 0),
                "partition_report": bool(partition),
            },
        )

        register_analysis_run(
            case_id,
            analysis_type=(
                "TOWER_GPRS_DUMP_PARTITION"
                if use_partitions
                else "TOWER_GPRS_DUMP"
            ),
            status="COMPLETED",
            input_records=len(dataframe),
            output_records=output_records,
            report_path=str(excel_path),
        )

        print("\n" + "=" * 78)
        print("TOWER GPRS DUMP ANALYSIS COMPLETED")
        print("=" * 78)
        print(f"Input Records : {len(dataframe):,}")
        print(f"Backend Run   : {saved['run_directory']}")

        timings = pipeline_result.get("timings", {}) or {}
        print(f"SQL Engine ms : {timings.get('sql_analysis_ms', 0)}")
        print("Speed Mode    : DuckDB SQL + Parquet internal backend")
        print("User Output   : Excel report only")

        if isinstance(partition, dict):
            print(
                f"Partitions    : "
                f"{partition.get('total_partitions', 0)}"
            )
            print(
                f"Candidates 2+: "
                f"{len(partition.get('n_of_m_candidates', [])):,}"
            )
            print(
                f"Strict Common : "
                f"{len(partition.get('strict_common_candidates', [])):,}"
            )

        print(f"Excel Report  : {excel_path}")
        print("=" * 78)

        return {
            "load": load_result,
            "analysis": analysis,
            "partition": partition,
            "saved": saved,
            "excel_report": str(excel_path),
            "scalable_pipeline": pipeline_result,
        }

    except Exception as error:
        register_analysis_run(
            case_id,
            analysis_type=(
                "TOWER_GPRS_DUMP_PARTITION"
                if use_partitions
                else "TOWER_GPRS_DUMP"
            ),
            status="FAILED",
            error_message=str(error),
        )
        print(
            f"[-] GPRS analysis failed: "
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
        minutes_before=0,
        minutes_after=0,
    )
    _print_sightings(str(case["case_id"]))
    return _execute(case, use_partitions=True)


def _show_latest(case_id: str) -> None:
    manifest = load_latest_gprs_manifest(case_id)

    if not manifest:
        print("[-] Koi GPRS run available nahi hai.")
        return

    print("\n" + "=" * 78)
    print(f"LATEST TOWER GPRS RUN: {manifest.get('run_id', '')}")
    print("=" * 78)
    print(f"Created At      : {manifest.get('created_at', '')}")
    print(f"Input Folder    : {manifest.get('input_folder', '')}")
    print(f"Records         : {manifest.get('record_count', 0)}")
    print(f"Partitions      : {manifest.get('partition_count', 0)}")
    print(f"Overlap Rule    : {manifest.get('overlap_rule', '')}")
    print(f"Report Status   : {manifest.get('report_status', '')}")
    print(
        f"Excel Report    : "
        f"{manifest.get('user_facing_report', 'Not generated')}"
    )
    print(
        "Backend tables : "
        f"{len(manifest.get('saved_files', {}))}"
    )
    print("=" * 78)


def handle_tower_gprs_workspace(
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
                print("[+] Saved date-time parts cleared.")

            elif choice == "6":
                _show_latest(case_id)

            elif choice == "0":
                return None

            else:
                print("[-] Invalid choice. Select 0 to 6.")

        except KeyboardInterrupt:
            print("\n[-] Returning to GPRS workspace.")

        except EOFError:
            return None

        except Exception as error:
            print(
                f"[-] GPRS workspace error: "
                f"{type(error).__name__}: {error}"
            )
