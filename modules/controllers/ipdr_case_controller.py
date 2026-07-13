"""Case-aware top-level Single/Multiple IPDR analysis workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from modules.analysis.ipdr import run_ipdr_analysis
from modules.cases import (
    case_evidence_dir,
    case_report_dir,
    log_case_event,
    register_analysis_run,
    register_evidence,
    register_report,
)
from modules.cases.ipdr_store import (
    attach_ipdr_report,
    load_latest_ipdr_manifest,
    save_ipdr_run,
)
from modules.core.paths import IPDR_DATA_DIR
from modules.loader.ipdr_loader import load_ipdr_case
from modules.reporting.ipdr_console import print_ipdr_analysis


SUPPORTED_SUFFIXES = {".csv", ".txt", ".xlsx", ".xls"}


def _menu(case: dict[str, Any]) -> str:
    print("\n" + "=" * 78)
    print(
        f"IPDR ANALYSIS | "
        f"{case.get('case_id', '')} | "
        f"{case.get('case_name', '')}"
    )
    print("=" * 78)
    print("1. Single IPDR Analysis")
    print("2. Multiple IPDR Analysis")
    print("3. View Latest Single IPDR Run")
    print("4. View Latest Multiple IPDR Run")
    print("0. Back to Case Workspace")
    return input("\nChoose Action: ").strip()


def _has_files(directory: Path) -> bool:
    return directory.is_dir() and any(
        path.is_file()
        and path.suffix.lower() in SUPPORTED_SUFFIXES
        for path in directory.rglob("*")
    )


def _input_folder(case_id: str, mode: str) -> Path:
    case_folder = case_evidence_dir(
        case_id,
        "ipdr",
        mode,
    )

    if _has_files(case_folder):
        return case_folder

    fallback = IPDR_DATA_DIR / mode
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _register_sources(
    case_id: str,
    load_result: dict[str, Any],
) -> None:
    for result in load_result.get("file_results", []) or []:
        metadata = result.get("metadata", {}) or {}

        register_evidence(
            case_id,
            evidence_type="IPDR",
            source_file=result.get("file", ""),
            operator=metadata.get("operator", ""),
            source_category=metadata.get("source_format", ""),
        )


def _execute(
    case: dict[str, Any],
    *,
    mode: str,
) -> dict[str, Any] | None:
    case_id = str(case["case_id"])
    mode = str(mode).strip().lower()
    analysis_type = f"IPDR_{mode.upper()}"

    log_case_event(
        case_id,
        action=f"{analysis_type}_ANALYSIS_STARTED",
    )

    try:
        input_folder = _input_folder(case_id, mode)
        print(f"[+] {mode.title()} IPDR input: {input_folder}")
        load_result = load_ipdr_case(
            input_folder,
            recursive=True,
        )

        for warning in load_result.get("warnings", []) or []:
            print(f"[WARNING] {warning}")

        for loader_error in load_result.get("errors", []) or []:
            print(f"[ERROR] {loader_error}")

        file_summary_preview = load_result.get("file_summary")

        if (
            isinstance(file_summary_preview, pd.DataFrame)
            and not file_summary_preview.empty
        ):
            print("\n[+] IPDR source-file load status:")

            for record in file_summary_preview.itertuples(index=False):
                filtered = int(
                    getattr(
                        record,
                        "filtered_non_data_rows",
                        0,
                    )
                    or 0
                )
                suffix = (
                    f" | filtered non-data rows: {filtered}"
                    if filtered
                    else ""
                )
                print(
                    f"    {getattr(record, 'status', ''):<18} "
                    f"{getattr(record, 'file_name', '')}"
                    f"{suffix}"
                )

        if not load_result.get("ok"):
            print("[-] Koi supported IPDR record ya search request load nahi hua.")

            for warning in load_result.get("warnings", []):
                print(f"    WARNING: {warning}")

            for error in load_result.get("errors", []):
                print(f"    ERROR: {error}")

            raise ValueError("IPDR loading failed.")

        _register_sources(case_id, load_result)
        dataframe = load_result.get("data")
        search_requests = load_result.get("search_requests")

        if not isinstance(dataframe, pd.DataFrame):
            dataframe = pd.DataFrame()

        if not isinstance(search_requests, pd.DataFrame):
            search_requests = pd.DataFrame()

        analysis = run_ipdr_analysis(
            dataframe,
            file_summary=load_result.get("file_summary"),
            search_requests=search_requests,
        )
        analysis["rejected_rows"] = load_result.get("rejected_rows", pd.DataFrame())
        print_ipdr_analysis(
            analysis,
            row_limit=20,
        )

        loaded_files = (
            load_result.get("file_summary", pd.DataFrame())
        )
        source_files = []

        if isinstance(loaded_files, pd.DataFrame) and not loaded_files.empty:
            source_files = loaded_files.loc[
                loaded_files["status"].isin(
                    ["LOADED", "LOADED_EMPTY"]
                ),
                "source_path",
            ].astype(str).tolist()

        saved = save_ipdr_run(
            case_id,
            mode=mode,
            analysis=analysis,
            input_folder=input_folder,
            source_files=source_files,
            warnings=load_result.get("warnings", []),
            errors=load_result.get("errors", []),
        )

        from modules.reporting.ipdr_excel import (
            generate_ipdr_excel_report,
        )

        report_key = (
            "ipdr_single"
            if mode == "single"
            else "ipdr_multiple"
        )
        excel_path = generate_ipdr_excel_report(
            case=case,
            mode=mode,
            load_result=load_result,
            analysis=analysis,
            output_dir=case_report_dir(
                case_id,
                report_key,
            ),
            saved=saved,
        )

        attach_ipdr_report(
            case_id,
            mode=mode,
            run_id=saved["run_id"],
            report_path=excel_path,
        )
        register_report(
            case_id,
            report_type=analysis_type,
            report_path=excel_path,
        )

        subscriber_summary = analysis.get("subscriber_summary")
        output_records = (
            len(subscriber_summary)
            if isinstance(subscriber_summary, pd.DataFrame)
            else 0
        )

        register_analysis_run(
            case_id,
            analysis_type=analysis_type,
            status="COMPLETED",
            input_records=len(dataframe),
            output_records=output_records,
            report_path=str(excel_path),
        )

        metadata = load_result.get("metadata", {}) or {}
        print("\n" + "=" * 78)
        print(f"{mode.upper()} IPDR ANALYSIS COMPLETED")
        print("=" * 78)
        print(f"Files Found      : {metadata.get('files_found', 0)}")
        print(f"Files Loaded     : {metadata.get('files_loaded', 0)}")
        print(
            f"Empty Result Files: "
            f"{metadata.get('empty_result_files', 0)}"
        )
        print(f"Normalized Rows  : {metadata.get('total_records', 0):,}")
        print(f"Search Requests  : {metadata.get('search_requests', 0):,}")
        print(f"Backend Run      : {saved['run_directory']}")
        print(f"Excel Report     : {excel_path}")
        print("=" * 78)

        return {
            "load": load_result,
            "analysis": analysis,
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
            f"[-] {mode.title()} IPDR analysis failed: "
            f"{type(error).__name__}: {error}"
        )
        return None


def _latest(
    case_id: str,
    mode: str,
) -> None:
    manifest = load_latest_ipdr_manifest(
        case_id,
        mode,
    )

    print("\n" + "=" * 78)
    print(f"LATEST {mode.upper()} IPDR RUN")
    print("=" * 78)

    if not manifest:
        print("No completed run found.")
        return

    print(f"Run ID        : {manifest.get('run_id', '')}")
    print(f"Created At    : {manifest.get('created_at', '')}")
    print(f"Input Folder  : {manifest.get('input_folder', '')}")
    print(f"Record Count  : {manifest.get('record_count', 0):,}")
    print(f"Report Status : {manifest.get('report_status', '')}")
    print(f"Excel Report  : {manifest.get('user_facing_report', '')}")


def handle_ipdr_workspace(
    case: dict[str, Any],
) -> None:
    while True:
        try:
            choice = _menu(case)

            if choice == "1":
                _execute(case, mode="single")

            elif choice == "2":
                _execute(case, mode="multiple")

            elif choice == "3":
                _latest(
                    str(case["case_id"]),
                    "single",
                )

            elif choice == "4":
                _latest(
                    str(case["case_id"]),
                    "multiple",
                )

            elif choice == "0":
                return

            else:
                print("[-] Invalid choice. Select 0 to 4.")

        except KeyboardInterrupt:
            print("\n[-] Returning to Case Workspace.")

        except EOFError:
            return

        except Exception as error:
            print(
                f"[-] IPDR workspace error: "
                f"{type(error).__name__}: {error}"
            )
