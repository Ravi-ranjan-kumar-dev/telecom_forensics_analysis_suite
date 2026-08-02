"""Main CLI workflow controller for the Telecom Forensics Analysis Suite."""

from __future__ import annotations

import importlib
import os
import traceback
from pathlib import Path
from typing import Any

import pandas as pd

from modules.loader.duplicate_flags import flag_potential_duplicates

from modules.cases import (
    CaseAlreadyExistsError,
    CaseNotFoundError,
    create_case,
    open_case,
    case_evidence_dir,
    case_report_dir,
    log_case_event,
    register_analysis_run,
    register_report,
    register_target,
)
from modules.controllers.case_controller import (
    print_case_details,
    prompt_archive_case,
    prompt_create_case,
    prompt_open_case,
    prompt_reopen_case,
    show_case_health,
    show_case_list,
    show_case_reports,
)
from modules.core.paths import PROJECT_ROOT, TOWER_DUMP_DATA_DIR
from modules.core.time_utils import new_run_id


DIRECT_ANALYSIS_CASE_ID = "DEV-WORKSPACE"
DIRECT_ANALYSIS_CASE_NAME = "Development Analysis Workspace"
CASE_MANAGEMENT_ENV = "TELECOM_FORENSICS_CASE_MANAGEMENT"


def _case_management_enabled() -> bool:
    """Return True only when the future case-management menu is explicitly enabled."""

    value = os.environ.get(CASE_MANAGEMENT_ENV, "").strip().lower()
    return value in {"1", "true", "yes", "on", "enabled", "case"}


def _direct_analysis_workspace() -> dict[str, Any]:
    """Open one hidden development workspace without asking the user to create a case."""

    try:
        case = open_case(DIRECT_ANALYSIS_CASE_ID, include_archived=True)
    except CaseNotFoundError:
        try:
            case = create_case(
                case_id=DIRECT_ANALYSIS_CASE_ID,
                case_name=DIRECT_ANALYSIS_CASE_NAME,
                description=(
                    "Temporary automatic workspace used while the software is under "
                    "development. Case-selection UI is intentionally bypassed."
                ),
            )
        except CaseAlreadyExistsError:
            case = open_case(DIRECT_ANALYSIS_CASE_ID, include_archived=True)

    if str(case.get("status", "active")).lower() != "active":
        raise RuntimeError(
            "Development workspace archived hai. "
            "cases/archived/DEV-WORKSPACE ko active state mein reopen karein."
        )
    return case


def get_direct_analysis_workspace() -> dict[str, Any]:
    """Return the active direct-analysis workspace."""

    return _direct_analysis_workspace()


def print_error(title: str, error: Exception, trace: str | None = None) -> None:
    print(f"\n[-] {title}")
    print(f"    Error Type : {type(error).__name__}")
    print(f"    Message    : {error}")

    error_trace = trace if trace is not None else traceback.format_exc(limit=8)

    if error_trace and error_trace.strip() != "NoneType: None":
        print("    Traceback:")
        print(error_trace.rstrip())


def safe_import(module_path: str, function_name: str):
    try:
        module = importlib.import_module(module_path)
        function = getattr(module, function_name, None)

        if not callable(function):
            raise AttributeError(
                f"{function_name} not found in {module_path}"
            )

        return function

    except Exception as error:
        print_error(
            f"Import failed: {module_path}.{function_name}",
            error,
        )
        return None


def validate_dataframe(df: Any, context: str) -> bool:
    if not isinstance(df, pd.DataFrame):
        print(
            f"[-] {context}: pandas DataFrame expected, "
            f"received {type(df).__name__}."
        )
        return False

    if df.empty:
        print(f"[-] {context}: DataFrame empty hai.")
        return False

    return True


def _case_metadata(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": case.get("case_id", ""),
        "case_name": case.get("case_name", ""),
        "fir_number": case.get("fir_number", ""),
        "incident_date": case.get("incident_date", ""),
        "incident_location": case.get("incident_location", ""),
        "investigator": case.get("investigator", ""),
        "unit_name": case.get("unit_name", ""),
    }


def build_metadata(
    target: str,
    df: pd.DataFrame,
    case: dict[str, Any],
    info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = _case_metadata(case)

    attrs = getattr(df, "attrs", {})

    if isinstance(attrs, dict) and isinstance(attrs.get("metadata"), dict):
        metadata.update(attrs["metadata"])

    if isinstance(info, dict):
        if isinstance(info.get("metadata"), dict):
            metadata.update(info["metadata"])

        if info.get("file"):
            metadata.setdefault("source_file", info["file"])

        if info.get("files"):
            metadata.setdefault("source_files", info["files"])

    metadata["target"] = str(target)
    metadata.setdefault("subscriber_name", "")
    metadata.setdefault("address", "")
    return metadata


def _main_menu() -> str:
    print("\n" + "=" * 64)
    print("       🛡️  TELECOM FORENSICS ANALYSIS SUITE")
    print("=" * 64)
    print("1. Create New Case")
    print("2. Open Existing Case")
    print("3. List Active Cases")
    print("4. List Archived Cases")
    print("5. Archive Case")
    print("6. Reopen Archived Case")
    print("7. Verify Case/Audit Health")
    print("0. Exit")
    return input("\nChoose Action: ").strip()


def _workspace_menu(
    case: dict[str, Any],
    *,
    direct_mode: bool = False,
) -> str:
    """Show the top-level investigator analysis workspace."""

    print("\n" + "=" * 72)

    if direct_mode:
        print(
            "       🛡️  TELECOM FORENSICS ANALYSIS SUITE"
        )
    else:
        print(
            f"ACTIVE CASE: "
            f"{case.get('case_id')} | "
            f"{case.get('case_name')}"
        )

    print("=" * 72)
    print("1. CDR Analysis")
    print("2. Tower Dump Analysis")
    print("3. IPDR Analysis")
    print("4. IMEI / Device Analysis")
    print("5. Lookup Services")
    print("6. View Case Details")
    print("7. View Case Reports")
    print("0. Close Case")

    return input(
        "\nChoose Action: "
    ).strip()


def _cdr_menu(case: dict[str, Any], *, direct_mode: bool = False) -> str:
    """Single/Multiple CDR submenu for the selected workspace."""

    print("\n" + "=" * 72)
    if direct_mode:
        print("CDR ANALYSIS")
    else:
        print(
            f"CDR ANALYSIS | "
            f"{case.get('case_id')} | "
            f"{case.get('case_name')}"
        )
    print("=" * 72)
    print("1. Single CDR Analysis")
    print("2. Multiple CDR Analysis")
    print("0. Back to Analysis Workspace")
    return input("\nChoose CDR Type: ").strip()


def _reporting_functions() -> dict[str, Any]:
    return {
        "build_bundle": safe_import(
            "modules.reporting",
            "build_single_analysis_bundle",
        ),
        "print_report": safe_import(
            "modules.reporting",
            "print_single_analysis_report",
        ),
        "single_excel": safe_import(
            "modules.reporting.cdr_compact_excel",
            "generate_single_cdr_compact_report",
        ),
        "completion": safe_import(
            "modules.reporting",
            "analysis_completion_summary",
        ),
    }


def _run_target_pipeline(
    *,
    df: pd.DataFrame,
    target: str,
    metadata: dict[str, Any],
    output_dir: Path,
    reporting: dict[str, Any],
) -> dict[str, Any]:
    build_bundle = reporting.get("build_bundle")
    print_report = reporting.get("print_report")
    single_excel = reporting.get("single_excel")
    completion = reporting.get("completion")

    if not callable(build_bundle):
        return {"bundle": None, "excel": None, "summary": {}}

    print("\n[+] Executing registered CDR analyses once...")

    bundle = build_bundle(df=df, target=target)

    if callable(print_report):
        print_report(
            bundle=bundle,
            target=target,
            max_rows_per_section=30,
        )

    excel_path = None

    if callable(single_excel):
        excel_path = single_excel(
            df=df,
            target=target,
            metadata=metadata,
            analysis_bundle=bundle,
            output_dir=output_dir,
        )

    summary = completion(bundle) if callable(completion) else {}

    return {
        "bundle": bundle,
        "excel": excel_path,
        "summary": summary if isinstance(summary, dict) else {},
    }


def _normalise_single_result(
    value: Any,
) -> tuple[pd.DataFrame | None, str | None]:
    if isinstance(value, tuple) and len(value) == 2:
        target = value[1]
        return value[0], str(target).strip() if target is not None else None

    if isinstance(value, dict):
        target = value.get("target")
        return (
            value.get("df"),
            str(target).strip() if target is not None else None,
        )

    return None, None


def handle_single_cdr(
    case: dict[str, Any],
    *,
    input_folder: str | Path | None = None,
) -> dict[str, Any] | None:
    run_single = safe_import(
        "modules.controllers.cdr_controller",
        "run_single",
    )

    if not callable(run_single):
        return None

    case_id = str(case["case_id"])
    analysis_run_id = new_run_id("single_cdr")
    log_case_event(
        case_id,
        action="SINGLE_CDR_ANALYSIS_STARTED",
    )

    try:
        controller_result = (
            run_single(input_folder)
            if input_folder is not None
            else run_single()
        )
        df, target = _normalise_single_result(
            controller_result
        )

        if not validate_dataframe(df, "Single CDR") or not target:
            raise ValueError("Valid Single CDR target/dataframe nahi mila.")

        register_target(
            case_id,
            target_type="MSISDN",
            target_value=target,
            description="Single CDR target",
        )

        output_dir = case_report_dir(case_id, "cdr_single")
        result = _run_target_pipeline(
            df=df,
            target=target,
            metadata=build_metadata(target, df, case),
            output_dir=output_dir,
            reporting=_reporting_functions(),
        )

        excel_path = result.get("excel")

        if excel_path:
            from modules.reporting.cdr_report_source import (
                create_cdr_source_run,
                link_report_to_source,
            )

            source_run = create_cdr_source_run(
                case_id=case_id,
                analysis_run_id=analysis_run_id,
                target_frames={str(target): df},
            )
            link_report_to_source(
                excel_path,
                source_run,
                targets=[str(target)],
            )
            register_report(
                case_id,
                report_type="SINGLE_CDR",
                report_path=excel_path,
                analysis_run_id=analysis_run_id,
            )

        register_analysis_run(
            case_id,
            analysis_type="SINGLE_CDR",
            status="COMPLETED",
            input_records=len(df),
            report_path=str(excel_path or ""),
            analysis_run_id=analysis_run_id,
        )

        print(f"\n[+] Case report: {excel_path or 'Unavailable'}")
        return result

    except Exception as error:
        register_analysis_run(
            case_id,
            analysis_type="SINGLE_CDR",
            status="FAILED",
            error_message=str(error),
            analysis_run_id=analysis_run_id,
        )
        print_error("Single CDR analysis failed", error)
        return None


def _normalise_multiple(value: Any) -> dict[str, dict[str, Any]]:
    if isinstance(value, dict):
        return {
            str(target): info
            for target, info in value.items()
            if isinstance(info, dict)
        }

    if not isinstance(value, list):
        return {}

    output: dict[str, dict[str, Any]] = {}

    for item in value:
        if not isinstance(item, dict) or item.get("target") is None:
            continue

        target = str(item["target"]).strip()

        if not target:
            continue

        if target not in output:
            output[target] = dict(item)
            continue

        first = output[target].get("df")
        second = item.get("df")

        if isinstance(first, pd.DataFrame) and isinstance(second, pd.DataFrame):
            output[target]["df"] = flag_potential_duplicates(
                pd.concat([first, second], ignore_index=True, sort=False)
            ).reset_index(drop=True)

    return output


def handle_multiple_cdr(
    case: dict[str, Any],
    *,
    input_folder: str | Path | None = None,
) -> dict[str, Any] | None:
    run_multiple = safe_import(
        "modules.controllers.cdr_controller",
        "run_multiple",
    )

    if not callable(run_multiple):
        return None

    case_id = str(case["case_id"])
    analysis_run_id = new_run_id("multiple_cdr")
    log_case_event(
        case_id,
        action="MULTIPLE_CDR_ANALYSIS_STARTED",
    )

    try:
        controller_result = (
            run_multiple(input_folder)
            if input_folder is not None
            else run_multiple()
        )
        loaded_cdrs = _normalise_multiple(
            controller_result
        )

        if not loaded_cdrs:
            raise ValueError("Koi valid Multiple CDR target load nahi hua.")

        reporting = _reporting_functions()
        individual_results: dict[str, Any] = {}
        individual_dir = case_report_dir(
            case_id,
            "cdr_multiple_individual",
        )

        for target, info in loaded_cdrs.items():
            df = info.get("df")

            if not validate_dataframe(df, f"Target {target}"):
                continue

            register_target(
                case_id,
                target_type="MSISDN",
                target_value=target,
                description="Multiple CDR target",
            )

            result = _run_target_pipeline(
                df=df,
                target=target,
                metadata=build_metadata(target, df, case, info),
                output_dir=individual_dir,
                reporting=reporting,
            )
            individual_results[target] = result

        cross_builder = safe_import(
            "modules.analysis.cdr.cross_target",
            "build_cross_target_analysis",
        )
        multi_excel = safe_import(
            "modules.reporting",
            "generate_multi_cdr_report",
        )

        cross_bundle = (
            cross_builder(loaded_cdrs, min_targets=2)
            if len(loaded_cdrs) >= 2 and callable(cross_builder)
            else None
        )

        common_path = None

        if len(loaded_cdrs) >= 2 and callable(multi_excel):
            common_path = multi_excel(
                loaded_cdrs=loaded_cdrs,
                metadata=_case_metadata(case),
                analysis_bundle=cross_bundle,
                output_dir=case_report_dir(
                    case_id,
                    "cdr_multiple_common",
                ),
                min_targets=2,
            )

        from modules.reporting.cdr_report_source import (
            create_cdr_source_run,
            link_report_to_source,
        )

        source_run = create_cdr_source_run(
            case_id=case_id,
            analysis_run_id=analysis_run_id,
            target_frames={
                target: info["df"]
                for target, info in loaded_cdrs.items()
                if isinstance(info.get("df"), pd.DataFrame)
                and not info["df"].empty
            },
        )

        for target, result in individual_results.items():
            report_path = result.get("excel") if isinstance(result, dict) else None
            if not report_path:
                continue
            link_report_to_source(
                report_path,
                source_run,
                targets=[target],
            )
            register_report(
                case_id,
                report_type="MULTIPLE_CDR_INDIVIDUAL",
                report_path=report_path,
                analysis_run_id=analysis_run_id,
            )

        if common_path:
            link_report_to_source(
                common_path,
                source_run,
                targets=loaded_cdrs.keys(),
            )
            register_report(
                case_id,
                report_type="MULTIPLE_CDR_COMMON",
                report_path=common_path,
                analysis_run_id=analysis_run_id,
            )

        total_records = sum(
            len(info.get("df"))
            for info in loaded_cdrs.values()
            if isinstance(info.get("df"), pd.DataFrame)
        )

        register_analysis_run(
            case_id,
            analysis_type="MULTIPLE_CDR",
            status="COMPLETED",
            input_records=total_records,
            output_records=len(individual_results),
            report_path=str(common_path or ""),
            analysis_run_id=analysis_run_id,
        )

        print(f"\n[+] Individual reports: {individual_dir}")
        print(f"[+] Common report: {common_path or 'Unavailable'}")

        return {
            "individual_reports": individual_results,
            "cross_target_analysis": cross_bundle,
            "multiple_common_report": common_path,
        }

    except Exception as error:
        register_analysis_run(
            case_id,
            analysis_type="MULTIPLE_CDR",
            status="FAILED",
            error_message=str(error),
            analysis_run_id=analysis_run_id,
        )
        print_error("Multiple CDR analysis failed", error)
        return None


def _has_supported_tower_files(directory: Path) -> bool:
    suffixes = {".csv", ".txt", ".tsv", ".xlsx", ".xls"}

    return any(
        path.is_file() and path.suffix.lower() in suffixes
        for path in directory.rglob("*")
    )


def handle_cdr_analysis(
    case: dict[str, Any],
    *,
    direct_mode: bool = False,
) -> None:
    """Open Single/Multiple CDR analysis under one CDR menu."""

    while True:
        try:
            choice = _cdr_menu(case, direct_mode=direct_mode)

            if choice == "1":
                handle_single_cdr(case)

            elif choice == "2":
                handle_multiple_cdr(case)

            elif choice == "0":
                return

            else:
                print("[-] Invalid choice. Select 0, 1 or 2.")

        except KeyboardInterrupt:
            print("\n[-] Returning to Analysis Workspace.")

        except EOFError:
            return

        except Exception as error:
            print_error("Unexpected CDR workspace error", error)


def handle_ipdr_analysis(case: dict[str, Any]) -> None:
    """Open future case-aware IPDR analysis without mixing Tower IPDR code."""

    case_id = str(case.get("case_id", ""))

    try:
        module = importlib.import_module(
            "modules.controllers.ipdr_case_controller"
        )

    except ModuleNotFoundError as error:
        if error.name == "modules.controllers.ipdr_case_controller":
            log_case_event(
                case_id,
                action="IPDR_ANALYSIS_REQUESTED",
                details={"status": "MODULE_PENDING"},
            )

            print("\n" + "=" * 72)
            print("IPDR ANALYSIS")
            print("=" * 72)
            print(
                "IPDR module implementation pending hai. "
                "Uploaded Jio IPDR/NAT sample future Phase mein "
                "isi section ke andar implement hoga."
            )
            print(
                "Tower GPRS aur Tower IPDR data ko mix nahi kiya jayega."
            )
            return

        print_error("IPDR module import failed", error)
        return

    except Exception as error:
        print_error("IPDR module import failed", error)
        return

    handler = getattr(module, "handle_ipdr_workspace", None)

    if not callable(handler):
        print(
            "[-] IPDR controller mila, lekin "
            "handle_ipdr_workspace() available nahi hai."
        )
        return

    handler(case)


def handle_tower_dump(case: dict[str, Any]) -> None:
    """Open the unified Tower Dump Analysis workspace."""

    handler = safe_import(
        "modules.controllers.tower_dump_controller",
        "handle_tower_dump_analysis",
    )

    if callable(handler):
        handler(case)

def handle_imei_device_analysis(
    case: dict[str, Any],
) -> None:
    """Open the case-aware IMEI and device workspace."""

    handler = safe_import(
        "modules.controllers.imei_device_controller",
        "handle_imei_device_workspace",
    )

    if callable(
        handler
    ):
        handler(
            case
        )



def case_workspace(
    case: dict[str, Any],
    *,
    direct_mode: bool = False,
) -> None:
    """Run the selected analysis workspace."""

    case_id = str(
        case[
            "case_id"
        ]
    )

    log_case_event(
        case_id,
        action="CASE_OPENED",
    )

    while True:
        try:
            choice = _workspace_menu(
                case,
                direct_mode=direct_mode,
            )

            if choice == "1":
                handle_cdr_analysis(
                    case,
                    direct_mode=direct_mode,
                )

            elif choice == "2":
                handle_tower_dump(
                    case
                )

            elif choice == "3":
                handle_ipdr_analysis(
                    case
                )

            elif choice == "4":
                handle_imei_device_analysis(
                    case
                )

            elif choice == "5":
                from modules.controllers.lookup_controller import (
                    run_lookup_services,
                )

                run_lookup_services(
                    case
                )

            elif choice == "6":
                print_case_details(
                    case
                )

            elif choice == "7":
                show_case_reports(
                    case_id
                )

            elif choice == "0":
                log_case_event(
                    case_id,
                    action="CASE_CLOSED",
                )
                return

            else:
                print(
                    "[-] Invalid choice. "
                    "Select 0 to 7."
                )

        except KeyboardInterrupt:
            print(
                "\n[-] Returning to "
                "Analysis Workspace."
            )

        except EOFError:
            return

        except Exception as error:
            print_error(
                "Unexpected case workspace error",
                error,
            )


def run_application() -> None:
    """Start direct analysis by default; retain case UI behind an environment flag."""

    if _case_management_enabled():
        _run_case_management_application()
        return

    try:
        case = _direct_analysis_workspace()
        case_workspace(case, direct_mode=True)
        print("\n[+] Application closed safely.")
    except KeyboardInterrupt:
        print("\n[-] Operation interrupted. Application closed.")
    except EOFError:
        return


def _run_case_management_application() -> None:
    while True:
        try:
            choice = _main_menu()

            if choice == "1":
                case = prompt_create_case()
                if case:
                    case_workspace(case)

            elif choice == "2":
                case = prompt_open_case()
                if case:
                    case_workspace(case)

            elif choice == "3":
                show_case_list(archived=False)

            elif choice == "4":
                show_case_list(archived=True)

            elif choice == "5":
                prompt_archive_case()

            elif choice == "6":
                prompt_reopen_case()

            elif choice == "7":
                show_case_health()

            elif choice == "0":
                print("\n[+] Application closed safely.")
                return

            else:
                print("[-] Invalid choice. Select 0 to 7.")

        except KeyboardInterrupt:
            print("\n[-] Operation interrupted. Returning to main menu.")

        except EOFError:
            return

        except Exception as error:
            print_error("Unexpected main-menu error", error)
