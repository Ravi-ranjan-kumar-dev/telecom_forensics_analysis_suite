"""CLI controller for common case-management operations."""

from __future__ import annotations

from typing import Any

from modules.cases import (
    CaseError,
    archive_case,
    case_health,
    create_case,
    list_case_reports,
    list_cases,
    open_case,
    reopen_case,
)


def _required_input(label: str) -> str:
    while True:
        value = input(label).strip()

        if value:
            return value

        print("[-] Ye field required hai.")


def print_case_details(case: dict[str, Any]) -> None:
    print("\n" + "=" * 72)
    print(f"CASE: {case.get('case_id', '')}")
    print("=" * 72)
    print(f"Case Name          : {case.get('case_name', '')}")
    print(f"FIR/Reference No.  : {case.get('fir_number', '') or '-'}")
    print(f"Incident Date      : {case.get('incident_date', '') or '-'}")
    print(f"Incident Location  : {case.get('incident_location', '') or '-'}")
    print(f"Investigator       : {case.get('investigator', '') or '-'}")
    print(f"Police Unit        : {case.get('unit_name', '') or '-'}")
    print(f"Status             : {case.get('status', '')}")
    print(f"Description        : {case.get('description', '') or '-'}")
    print(f"Created At         : {case.get('created_at', '')}")
    print(f"Updated At         : {case.get('updated_at', '')}")
    print("=" * 72)


def prompt_create_case() -> dict[str, Any] | None:
    """Create a case by asking only for the case name."""

    print("\n" + "=" * 72)
    print("CREATE NEW CASE")
    print("=" * 72)

    try:
        case_name = _required_input("Case Name: ")
        case = create_case(case_name=case_name)

    except CaseError as error:
        print(f"[-] Case create nahi hua: {error}")
        return None

    except Exception as error:
        print(f"[-] Unexpected case creation error: {error}")
        return None

    print("\n[+] Case created successfully.")
    print(f"[+] Auto Case ID: {case.get('case_id', '')}")
    print_case_details(case)
    return case


def _print_case_table(
    cases: list[dict[str, Any]],
    title: str,
) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)

    if not cases:
        print("No cases found.")
        return

    print(
        f"{'#':<4}"
        f"{'Case ID':<22}"
        f"{'Case Name':<32}"
        f"{'Incident Date':<16}"
        f"{'Status':<12}"
        f"{'Investigator'}"
    )
    print("-" * 100)

    for index, case in enumerate(cases, start=1):
        print(
            f"{index:<4}"
            f"{str(case.get('case_id', ''))[:20]:<22}"
            f"{str(case.get('case_name', ''))[:30]:<32}"
            f"{str(case.get('incident_date', ''))[:14]:<16}"
            f"{str(case.get('status', ''))[:10]:<12}"
            f"{str(case.get('investigator', ''))[:25]}"
        )


def show_case_list(
    *,
    archived: bool = False,
) -> list[dict[str, Any]]:
    cases = list_cases(archived=archived)

    _print_case_table(
        cases,
        "ARCHIVED CASES" if archived else "ACTIVE CASES",
    )

    return cases


def prompt_open_case() -> dict[str, Any] | None:
    cases = show_case_list(archived=False)

    if not cases:
        return None

    case_id = input("\nEnter Case ID to open: ").strip()

    try:
        case = open_case(case_id)

    except CaseError as error:
        print(f"[-] Case open nahi hua: {error}")
        return None

    print_case_details(case)
    return case


def prompt_archive_case() -> bool:
    cases = show_case_list(archived=False)

    if not cases:
        return False

    case_id = input("\nEnter Case ID to archive: ").strip()

    confirmation = input(
        f"Archive case {case_id}? Type YES to confirm: "
    ).strip().upper()

    if confirmation != "YES":
        print("[-] Archive cancelled.")
        return False

    try:
        case = archive_case(case_id)

    except CaseError as error:
        print(f"[-] Case archive nahi hua: {error}")
        return False

    print(f"[+] Case archived: {case.get('case_id')}")
    return True



def prompt_reopen_case() -> bool:
    cases = show_case_list(archived=True)
    if not cases:
        return False
    case_id = input("\nEnter archived Case ID to reopen: ").strip()
    reason = _required_input("Reason for reopening: ")
    try:
        case = reopen_case(case_id, reason=reason)
    except CaseError as error:
        print(f"[-] Case reopen nahi hua: {error}")
        return False
    print(f"[+] Case reopened: {case.get('case_id')}")
    return True


def show_case_health() -> None:
    results = case_health()
    print("\n" + "=" * 100)
    print("CASE WORKSPACE AND AUDIT HEALTH")
    print("=" * 100)
    if not results:
        print("No case workspaces found.")
        return
    for item in results:
        state = "OK" if item.get("healthy") else "REVIEW REQUIRED"
        print(
            f"{item.get('case_id', ''):<24} "
            f"{item.get('storage', ''):<10} "
            f"{state:<16} "
            f"Audit events: {item.get('audit_events', 0)}"
        )
        for error in item.get("audit_errors", []) or []:
            print(f"    - {error}")
        if item.get("error"):
            print(f"    - {item['error']}")

def _print_latest_tower_ipdr_report(case_id: str) -> None:
    """Show latest Tower IPDR part-wise report paths without rerunning analysis."""

    try:
        from modules.staging.tower_ipdr_staging import load_tower_ipdr_partwise_latest_report
    except Exception as exc:
        print("\n[!] Tower IPDR latest report check available nahi hai.")
        print(f"    Reason: {exc}")
        return

    latest = load_tower_ipdr_partwise_latest_report(case_id)

    if not latest:
        return

    print("\n" + "-" * 72)
    print("LATEST TOWER IPDR PART-WISE REPORT")
    print("-" * 72)
    print(f"Report Folder : {latest.get('output_dir') or 'Not available'}")
    print(f"Main Report   : {latest.get('main_report') or 'Not available'}")
    print(f"Summary CSV   : {latest.get('summary_csv') or 'Not available'}")
    print(f"Excel Report  : {latest.get('excel_workbook') or 'Not available'}")
    print(f"Manifest      : {latest.get('manifest') or 'Not available'}")
    print(f"Updated At    : {latest.get('updated_at') or 'Not available'}")
    print("Meaning       : Latest Tower IPDR Date-Time Part-wise investigation report.")




def _print_latest_tower_ipdr_complete_report(case_id: str) -> None:
    """Print latest Complete Tower IPDR report paths in View Case Reports."""

    import json
    from pathlib import Path

    pointer_path = (
        Path("cases")
        / "active"
        / str(case_id)
        / "reports"
        / "tower_dump"
        / "ipdr"
        / "complete"
        / "latest_complete_report.json"
    )

    if not pointer_path.exists():
        return

    try:
        payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    except Exception as error:
        print("[-] Latest Complete Tower IPDR report pointer read nahi ho saka.")
        print(f"    Error: {type(error).__name__}: {error}")
        return

    print()
    print("LATEST COMPLETE TOWER IPDR REPORT")
    print("-" * 78)
    print(f"Run ID       : {payload.get('run_id', '')}")
    print(f"Generated At : {payload.get('generated_at', '')}")
    print(f"Report Folder: {payload.get('report_folder', '')}")
    print(f"Main Summary : {payload.get('main_summary', '')}")
    print(f"Excel Report : {payload.get('excel_report', '')}")

def show_case_reports(case: dict[str, Any] | str) -> None:
    """Show clean user-facing latest case reports.

    Normal mode:
    - Show grouped latest reports from common latest_reports.json registry.
    - Show only latest registered report from old report history.
    - Hide backend/internal details.

    Debug mode:
    - Show full registered report history using:
      TELECOM_DEBUG_REPORTS=1 python3 -u main.py
    """

    import os

    from modules.cases.latest_reports import list_latest_reports

    if isinstance(case, dict):
        case_id = str(case.get("case_id", ""))
    else:
        case_id = str(case)

    debug_reports = os.environ.get("TELECOM_DEBUG_REPORTS") == "1"

    def _value(value: Any) -> str:
        return str(value or "").strip()

    def _report_path(report: dict[str, Any]) -> str:
        if not isinstance(report, dict):
            return ""

        return (
            _value(report.get("report_path"))
            or _value(report.get("path"))
            or _value(report.get("file"))
        )

    def _report_created_at(report: dict[str, Any]) -> str:
        if not isinstance(report, dict):
            return ""

        return (
            _value(report.get("generated_at"))
            or _value(report.get("created_at"))
            or _value(report.get("timestamp"))
        )

    def _report_type(report: dict[str, Any], fallback_index: int) -> str:
        if not isinstance(report, dict):
            return f"Report {fallback_index}"

        value = (
            _value(report.get("title"))
            or _value(report.get("report_type"))
            or _value(report.get("type"))
            or _value(report.get("analysis_type"))
        )

        value = value.replace("_", " ").title()

        return value if value else f"Report {fallback_index}"

    def _is_backend_path(value: str) -> bool:
        lowered = value.lower()

        backend_markers = (
            ".duckdb",
            ".parquet",
            "manifest.json",
            "latest_pipeline.json",
            "/staging/",
            "/configuration/",
            "backend_state",
        )

        return any(marker in lowered for marker in backend_markers)

    def _print_latest_registry_reports() -> None:
        latest_reports = list_latest_reports(case_id)

        print("\n" + "-" * 72)
        print("LATEST REPORTS")
        print("-" * 72)

        if not latest_reports:
            print("No latest report registry entry found yet.")
            print("Run any analysis once to populate latest reports.")
            return

        for index, report in enumerate(latest_reports, start=1):
            title = _report_type(report, index)
            path_value = _report_path(report)
            summary_path = _value(report.get("summary_path"))
            report_folder = _value(report.get("report_folder"))
            generated_at = _report_created_at(report)
            metadata = report.get("metadata", {}) or {}

            print(f"{index}. {title}")

            if path_value:
                print(f"   Report    : {path_value}")

            if summary_path:
                print(f"   Summary   : {summary_path}")

            if report_folder:
                print(f"   Folder    : {report_folder}")

            if generated_at:
                print(f"   Time      : {generated_at}")

            if metadata:
                useful_items = []

                for key, value in metadata.items():
                    if value in ("", None, [], {}):
                        continue

                    label = str(key).replace("_", " ").title()
                    useful_items.append(f"{label}: {value}")

                if useful_items:
                    print(f"   Details   : {' | '.join(useful_items[:4])}")

            print()

    def _print_registered_history() -> None:
        reports = list_case_reports(case_id)

        print("\n" + "-" * 72)
        print("REGISTERED REPORT HISTORY")
        print("-" * 72)

        if not reports:
            print("No registered case reports found.")
            return

        print(f"Total Registered Reports: {len(reports)}")
        print("Meaning: Purane generated reports case history me safely registered hain.")

        visible_reports = [
            report
            for report in reports
            if not _is_backend_path(_report_path(report))
        ]

        if not visible_reports:
            print("\nNo user-facing registered report found.")
            return

        latest_report = visible_reports[-1]
        latest_index = reports.index(latest_report) + 1

        print("\nLatest Registered Report:")
        print(f"{latest_index}. {_report_type(latest_report, latest_index)}")
        print(f"   Path      : {_report_path(latest_report)}")

        created_at = _report_created_at(latest_report)
        if created_at:
            print(f"   Created At: {created_at}")

        print("\nNote: Normal screen par full old report list hidden hai.")
        print("      Full list ke liye developer/debug mode use karein:")
        print("      TELECOM_DEBUG_REPORTS=1 python3 -u main.py")

        if not debug_reports:
            return

        print("\n" + "-" * 72)
        print("FULL REGISTERED REPORT HISTORY - DEBUG MODE")
        print("-" * 72)

        for index, report in enumerate(reports, start=1):
            title = _report_type(report, index)
            path_value = _report_path(report)

            print(f"{index}. {title}")
            print(f"   Path      : {path_value}")

            created_at = _report_created_at(report)
            if created_at:
                print(f"   Created At: {created_at}")

    print("" + "=" * 72)
    print("CASE REPORTS")
    print("=" * 72)

    _print_latest_registry_reports()
    _print_registered_history()

