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



def show_case_reports(case_id: str) -> None:
    """Show case reports, including latest Tower IPDR part-wise report."""

    print("" + "=" * 72)
    print("CASE REPORTS")
    print("=" * 72)

    _print_latest_tower_ipdr_report(case_id)

    reports = list_case_reports(case_id)

    print("\n" + "-" * 72)
    print("REGISTERED CASE REPORTS")
    print("-" * 72)

    if not reports:
        print("No registered case reports found.")
        return

    for index, report in enumerate(reports, start=1):
        if isinstance(report, dict):
            title = (
                report.get("title")
                or report.get("report_name")
                or report.get("name")
                or report.get("type")
                or f"Report {index}"
            )
            report_path = (
                report.get("path")
                or report.get("file_path")
                or report.get("report_path")
                or report.get("output_path")
                or "Path not available"
            )
            created_at = report.get("created_at") or report.get("timestamp") or ""

            print(f"{index}. {title}")
            print(f"   Path      : {report_path}")
            if created_at:
                print(f"   Created At: {created_at}")
        else:
            print(f"{index}. {report}")



