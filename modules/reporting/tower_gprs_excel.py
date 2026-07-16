"""One consolidated Excel workbook for Tower GPRS Dump analysis."""

from __future__ import annotations

from modules.core.time_utils import utc_now, utc_now_iso

import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .excel_security import excel_safe_value
from .report_guidance import append_methodology_sheet


MAX_DATA_ROWS = 1_000_000
TITLE_FILL = PatternFill("solid", fgColor="17365D")
HEADER_FILL = PatternFill("solid", fgColor="D9EAF7")
SUCCESS_FILL = PatternFill("solid", fgColor="E2F0D9")
WARNING_FILL = PatternFill("solid", fgColor="FFF2CC")
ERROR_FILL = PatternFill("solid", fgColor="FCE4D6")
WHITE_BOLD = Font(color="FFFFFF", bold=True)
HEADER_FONT = Font(bold=True)
THIN = Side(style="thin", color="B7C9DB")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value).strip())
    return cleaned.strip("_") or "CASE"


def _safe_value(value: Any) -> Any:
    """Compatibility wrapper around the shared Excel security boundary."""
    return excel_safe_value(value)


def _frame(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, list):
        return pd.DataFrame(value)
    if isinstance(value, dict):
        return pd.DataFrame([value])
    return pd.DataFrame()


def _sheet_name(workbook: Workbook, requested: str) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\]", " ", requested)
    cleaned = re.sub(r"\s+", " ", cleaned).strip() or "Sheet"
    cleaned = cleaned[:31]
    existing = {sheet.title.lower() for sheet in workbook.worksheets}

    if cleaned.lower() not in existing:
        return cleaned

    number = 2

    while True:
        suffix = f" {number}"
        candidate = cleaned[: 31 - len(suffix)] + suffix

        if candidate.lower() not in existing:
            return candidate

        number += 1


def _title(worksheet, text: str, subtitle: str, columns: int) -> int:
    last_column = max(2, columns)
    worksheet.merge_cells(
        start_row=1,
        start_column=1,
        end_row=1,
        end_column=last_column,
    )
    cell = worksheet.cell(1, 1, text)
    cell.fill = TITLE_FILL
    cell.font = Font(color="FFFFFF", bold=True, size=16)
    cell.alignment = Alignment(horizontal="center", vertical="center")
    worksheet.row_dimensions[1].height = 28

    worksheet.merge_cells(
        start_row=2,
        start_column=1,
        end_row=2,
        end_column=last_column,
    )
    sub = worksheet.cell(2, 1, subtitle)
    sub.font = Font(italic=True, color="44546A")
    sub.alignment = Alignment(
        horizontal="center",
        vertical="center",
        wrap_text=True,
    )
    worksheet.row_dimensions[2].height = 24
    return 4


def _widths(worksheet) -> None:
    for cells in worksheet.columns:
        letter = get_column_letter(cells[0].column)
        maximum = 0

        for cell in cells[:5000]:
            if cell.value is not None:
                maximum = max(maximum, len(str(cell.value)))

        worksheet.column_dimensions[letter].width = min(
            max(maximum + 2, 10),
            44,
        )


def _write_page(
    worksheet,
    dataframe: pd.DataFrame,
    *,
    title: str,
    subtitle: str,
) -> None:
    header_row = _title(
        worksheet,
        title,
        subtitle,
        max(2, len(dataframe.columns)),
    )

    if dataframe.empty:
        cell = worksheet.cell(header_row, 1, "No records found.")
        cell.fill = WARNING_FILL
        cell.font = HEADER_FONT
        worksheet.column_dimensions["A"].width = 34
        worksheet.freeze_panes = f"A{header_row + 1}"
        worksheet.sheet_view.showGridLines = False
        return

    for column_index, column in enumerate(dataframe.columns, start=1):
        cell = worksheet.cell(header_row, column_index, _safe_value(str(column)))
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.border = BORDER
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

    for row_index, record in enumerate(
        dataframe.itertuples(index=False, name=None),
        start=header_row + 1,
    ):
        for column_index, value in enumerate(record, start=1):
            cell = worksheet.cell(
                row_index,
                column_index,
                _safe_value(value),
            )
            cell.border = BORDER
            cell.alignment = Alignment(vertical="top")

            if isinstance(cell.value, (datetime, date)):
                cell.number_format = "yyyy-mm-dd hh:mm:ss"

    last_row = header_row + len(dataframe)
    last_column = get_column_letter(len(dataframe.columns))
    worksheet.auto_filter.ref = (
        f"A{header_row}:{last_column}{last_row}"
    )
    worksheet.freeze_panes = f"A{header_row + 1}"
    worksheet.sheet_view.showGridLines = False
    _widths(worksheet)


def _write_table(
    workbook: Workbook,
    base_name: str,
    dataframe: pd.DataFrame,
    *,
    subtitle: str,
) -> list[str]:
    dataframe = _frame(dataframe)

    if dataframe.empty:
        name = _sheet_name(workbook, base_name)
        worksheet = workbook.create_sheet(name)
        _write_page(
            worksheet,
            dataframe,
            title=base_name,
            subtitle=subtitle,
        )
        return [name]

    pages = max(1, math.ceil(len(dataframe) / MAX_DATA_ROWS))
    names: list[str] = []

    for page_index in range(pages):
        start = page_index * MAX_DATA_ROWS
        end = min(start + MAX_DATA_ROWS, len(dataframe))
        page = dataframe.iloc[start:end].reset_index(drop=True)
        requested = (
            base_name
            if pages == 1
            else f"{base_name} {page_index + 1}"
        )
        name = _sheet_name(workbook, requested)
        worksheet = workbook.create_sheet(name)
        page_subtitle = subtitle

        if pages > 1:
            page_subtitle = (
                f"{subtitle} | Part {page_index + 1}/{pages} | "
                f"Rows {start + 1:,}-{end:,}"
            )

        _write_page(
            worksheet,
            page,
            title=base_name,
            subtitle=page_subtitle,
        )
        names.append(name)

    return names


def _key_values(worksheet, start_row: int, rows: list[tuple[str, Any]]) -> None:
    for offset, (key, value) in enumerate(rows):
        row = start_row + offset
        key_cell = worksheet.cell(row, 1, key)
        value_cell = worksheet.cell(row, 2, _safe_value(value))
        key_cell.fill = HEADER_FILL
        key_cell.font = HEADER_FONT
        key_cell.border = BORDER
        value_cell.border = BORDER
        value_cell.alignment = Alignment(wrap_text=True, vertical="top")

    worksheet.column_dimensions["A"].width = 32
    worksheet.column_dimensions["B"].width = 58


def _warnings(
    load_result: dict[str, Any],
) -> pd.DataFrame:
    rows: list[dict[str, str]] = []

    for message in load_result.get("warnings", []) or []:
        rows.append({"Level": "WARNING", "Message": str(message)})

    for message in load_result.get("errors", []) or []:
        rows.append({"Level": "ERROR", "Message": str(message)})

    if not rows:
        rows.append(
            {
                "Level": "INFO",
                "Message": "No loader or analysis warning was reported.",
            }
        )

    return pd.DataFrame(rows)


def generate_tower_gprs_excel_report(
    *,
    case: dict[str, Any],
    load_result: dict[str, Any],
    analysis: dict[str, Any],
    partition: dict[str, Any] | None,
    output_dir: str | Path,
    saved: dict[str, Any] | None = None,
) -> Path:
    """Generate one consolidated Tower GPRS Dump workbook."""

    case_id = str(case.get("case_id", "")).strip() or "CASE"
    case_name = str(case.get("case_name", "")).strip()
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now().strftime("%Y%m%d_%H%M%S_%f")
    report_path = output / (
        f"Tower_GPRS_Dump_Analysis_"
        f"{_safe_filename(case_id)}_{timestamp}.xlsx"
    )

    workbook = Workbook()
    workbook.remove(workbook.active)

    overview = workbook.create_sheet(
        _sheet_name(workbook, "1. Executive Summary")
    )
    start = _title(
        overview,
        "Tower GPRS Dump Analysis",
        f"Case: {case_id}" + (f" | {case_name}" if case_name else ""),
        6,
    )

    metadata = load_result.get("metadata", {}) or {}
    subscriber_summary = _frame(analysis.get("subscriber_summary"))
    n_of_m = _frame(
        partition.get("n_of_m_candidates")
        if isinstance(partition, dict)
        else None
    )
    strict = _frame(
        partition.get("strict_common_candidates")
        if isinstance(partition, dict)
        else None
    )

    _key_values(
        overview,
        start,
        [
            ("Case ID", case_id),
            ("Case Name", case_name),
            ("Source Section", "Tower GPRS Dump"),
            ("Currently Supported Parser", "Airtel GPRS Session Dump"),
            ("Generated At", utc_now_iso()),
            ("Input Folder", metadata.get("input_folder", "")),
            ("Files Found", metadata.get("files_found", 0)),
            ("Files Loaded", metadata.get("files_loaded", 0)),
            ("Files Failed", metadata.get("files_failed", 0)),
            ("Normalized Sessions", metadata.get("records", 0)),
            ("Operators", ", ".join(load_result.get("operators", []) or [])),
            ("Searched CGI/Cells", len(load_result.get("cell_ids", []) or [])),
            ("Unique Subscribers", len(subscriber_summary)),
            (
                "Dynamic Partitions",
                partition.get("total_partitions", 0)
                if isinstance(partition, dict)
                else 0,
            ),
            ("Candidates in 2+ Partitions", len(n_of_m)),
            ("Candidates in All Partitions", len(strict)),
            (
                "Session-overlap Rule",
                partition.get("overlap_rule", "")
                if isinstance(partition, dict)
                else (
                    "session_start <= window_end AND "
                    "session_end >= window_start"
                ),
            ),
            (
                "Backend Run Directory",
                saved.get("run_directory", "")
                if isinstance(saved, dict)
                else "",
            ),
        ],
    )
    overview.freeze_panes = "A4"
    overview.sheet_view.showGridLines = False

    tables = [
        ("2. Source Files", load_result.get("file_summary"), "Loaded source-file diagnostics."),
        ("3. Session Summary", analysis.get("summary"), "Core GPRS session metrics."),
        ("4. Technology", analysis.get("technology_summary"), "4G/5G technology distribution."),
        ("5. Connection Type", analysis.get("pre_post_summary"), "Prepaid/Postpaid distribution."),
        ("6. Roaming", analysis.get("roaming_summary"), "Roaming-circle distribution."),
        ("7. Subscribers", analysis.get("subscriber_summary"), "Subscriber-wise session intelligence."),
        ("8. Repeat Subscribers", analysis.get("repeat_subscribers"), "Subscribers with multiple sessions."),
        ("8A. GPRS Common Repeat", analysis.get("gprs_common_numbers"), "Common/repeat GPRS numbers for investigator review."),
        ("8B. GPRS Uncommon", analysis.get("gprs_uncommon_numbers"), "Uncommon/new visitor style GPRS numbers."),
        ("8C. GPRS Multi Cell", analysis.get("gprs_multi_cell_presence"), "Numbers seen across multiple searched cells."),
        ("8D. GPRS Device Check", analysis.get("gprs_device_consistency"), "IMEI/IMSI/IP consistency review."),
        ("8E. GPRS Timing", analysis.get("gprs_suspicious_timing"), "High activity, high volume, and timing-based leads."),
        ("8F. GPRS Priority Leads", analysis.get("gprs_priority_leads"), "Ranked GPRS leads with priority, confidence and next action."),
        ("9. IMEI Summary", analysis.get("imei_summary"), "Device identity summary."),
        ("10. Shared IMEI", analysis.get("shared_imei"), "IMEI associated with multiple subscribers."),
        ("11. IMSI Summary", analysis.get("imsi_summary"), "SIM/subscriber identity summary."),
        ("12. Shared IMSI", analysis.get("shared_imsi"), "IMSI associated with multiple subscribers."),
        ("13. IP Analysis", analysis.get("ip_summary"), "IPv4 and IPv6 usage summary."),
        ("14. Duration Buckets", analysis.get("duration_buckets"), "Session-duration distribution."),
        ("15. Hourly Activity", analysis.get("hourly_activity"), "Session-start activity by hour."),
        ("16. Long Sessions", analysis.get("long_sessions"), "Longest sessions for review."),
        ("17. Zero Volume", analysis.get("zero_volume_sessions"), "Sessions with zero total data volume."),
        ("18. Nonstandard IDs", analysis.get("non_standard_identifiers"), "Non-standard subscriber identifiers."),
        ("19. Data Quality", analysis.get("data_quality"), "Validation and quality checks."),
        ("20. Rejected Rows", analysis.get("rejected_rows"), "Malformed/non-data rows quarantined with physical source-line provenance."),
    ]

    partition_tables = [
        ("21. Partition Windows", "partition_windows", "User-entered date/time and automatic ±10-minute windows."),
        ("22. Partition Summary", "partition_summary", "Window-wise overlapping-session summary."),
        ("23. Partition Status", "partition_status", "Valid, time-only and rejected sighting configurations."),
        ("24. Location Exclusions", "time_only_excluded_by_location", "Time-overlapping sessions excluded because the searched cell did not match."),
        ("25. Subscriber Presence", "subscriber_presence", "Subscriber presence across dynamic partitions."),
        ("26. N-of-M Candidates", "n_of_m_candidates", "Subscribers present in two or more partitions."),
        ("27. Strict Common", "strict_common_candidates", "Subscribers present in every partition."),
        ("28. IMEI Continuity", "imei_presence", "IMEI continuity across partitions."),
        ("29. IMSI Continuity", "imsi_presence", "IMSI continuity across partitions."),
        ("30. IPv4 Continuity", "ipv4_presence", "IPv4 continuity across partitions."),
        ("31. IPv6 Continuity", "ipv6_presence", "IPv6 continuity across partitions."),
    ]

    for name, dataframe, subtitle in tables:
        _write_table(
            workbook,
            name,
            _frame(dataframe),
            subtitle=subtitle,
        )

    for name, key, subtitle in partition_tables:
        dataframe = (
            _frame(partition.get(key))
            if isinstance(partition, dict)
            else pd.DataFrame()
        )
        _write_table(
            workbook,
            name,
            dataframe,
            subtitle=subtitle,
        )

    status = pd.DataFrame(
        [
            {
                "Stage": "Tower GPRS Loading",
                "Status": "COMPLETED",
                "Details": f"{metadata.get('records', 0):,} normalized sessions",
            },
            {
                "Stage": "Core Analysis",
                "Status": "COMPLETED",
                "Details": f"{len(tables)} analytical table groups",
            },
            {
                "Stage": "Date-Time Partitioning",
                "Status": (
                    "COMPLETED"
                    if isinstance(partition, dict)
                    else "NOT REQUESTED"
                ),
                "Details": (
                    f"{partition.get('total_partitions', 0)} partitions"
                    if isinstance(partition, dict)
                    else ""
                ),
            },
            {
                "Stage": "Consolidated Excel",
                "Status": "COMPLETED",
                "Details": str(report_path),
            },
        ]
    )
    _write_table(
        workbook,
        "29. Analysis Status",
        status,
        subtitle="Execution status for this report.",
    )
    warning_names = _write_table(
        workbook,
        "30. Warnings",
        _warnings(load_result),
        subtitle="Loader and normalization warnings.",
    )

    for sheet_name in warning_names:
        worksheet = workbook[sheet_name]

        for row in range(5, worksheet.max_row + 1):
            level = str(worksheet.cell(row, 1).value or "").upper()
            worksheet.cell(row, 1).fill = (
                ERROR_FILL
                if level == "ERROR"
                else WARNING_FILL
                if level == "WARNING"
                else SUCCESS_FILL
            )

    workbook.properties.title = (
        f"Tower GPRS Dump Analysis - {case_id}"
    )
    workbook.properties.subject = (
        "GPRS session and date-time part overlap analysis"
    )
    workbook.properties.creator = "Telecom Forensics Analysis Suite"
    append_methodology_sheet(workbook, "Tower GPRS Dump Analysis")
    workbook.save(report_path)
    return report_path
