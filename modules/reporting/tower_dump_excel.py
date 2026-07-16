from __future__ import annotations

from modules.core.time_utils import utc_now, utc_now_iso

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .excel_security import excel_safe_value
from .report_guidance import append_methodology_sheet


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "reports" / "tower_dump"

TITLE_FILL = "1F4E78"
HEADER_FILL = "BDD7EE"
WHITE = "FFFFFF"


def _safe_sheet_name(name: str) -> str:
    invalid = ["\\", "/", "?", "*", "[", "]", ":"]
    for char in invalid:
        name = name.replace(char, " ")
    return name[:31].strip() or "Sheet"


def _clean_value(value: Any) -> Any:
    """Compatibility wrapper around the shared Excel security boundary."""
    return excel_safe_value(value)


def _as_dataframe(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, pd.Series):
        return value.reset_index()
    if isinstance(value, dict):
        return pd.DataFrame(
            [{"Field": key, "Value": _clean_value(item)} for key, item in value.items()]
        )
    if isinstance(value, list):
        if not value:
            return pd.DataFrame()
        if all(isinstance(item, dict) for item in value):
            return pd.DataFrame(value)
        return pd.DataFrame({"Value": value})
    if value is None:
        return pd.DataFrame()
    return pd.DataFrame({"Value": [value]})


def _style_worksheet(ws) -> None:
    ws.freeze_panes = "A2"
    thin = Side(style="thin", color="D9E2F3")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = border

    if ws.max_row >= 1:
        for cell in ws[1]:
            cell.font = Font(bold=True, color="000000")
            cell.fill = PatternFill("solid", fgColor=HEADER_FILL)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for column_cells in ws.columns:
        length = 0
        letter = get_column_letter(column_cells[0].column)
        for cell in column_cells[:300]:
            text = "" if cell.value is None else str(cell.value)
            length = max(length, min(len(text), 70))
        ws.column_dimensions[letter].width = max(12, min(length + 2, 45))


def _write_dataframe(
    wb: Workbook,
    sheet_name: str,
    value: Any,
    *,
    max_rows: int | None = None,
) -> None:
    ws = wb.create_sheet(_safe_sheet_name(sheet_name))
    df = _as_dataframe(value)

    if max_rows is not None and len(df) > max_rows:
        df = df.head(max_rows).copy()
        marker = {column: "" for column in df.columns}
        if len(df.columns) > 0:
            marker[df.columns[0]] = f"... trimmed to first {max_rows} rows"
            df.loc[len(df)] = marker

    if df.empty:
        ws.append(["Message"])
        ws.append(["No records found."])
        _style_worksheet(ws)
        return

    ws.append([_clean_value(str(column)) for column in df.columns])

    for _, row in df.iterrows():
        ws.append([_clean_value(row.get(column)) for column in df.columns])

    _style_worksheet(ws)


def _write_section(
    ws,
    title: str,
    row_index: int,
    value: Any,
    *,
    max_rows: int | None = None,
) -> int:
    ws.cell(row_index, 1, title)
    ws.cell(row_index, 1).font = Font(bold=True, color=WHITE)
    ws.cell(row_index, 1).fill = PatternFill("solid", fgColor=TITLE_FILL)
    ws.merge_cells(start_row=row_index, start_column=1, end_row=row_index, end_column=8)
    row_index += 1

    df = _as_dataframe(value)

    if max_rows is not None and len(df) > max_rows:
        df = df.head(max_rows).copy()

    if df.empty:
        ws.cell(row_index, 1, "No records found.")
        return row_index + 3

    for col_index, column in enumerate(df.columns, start=1):
        cell = ws.cell(row_index, col_index, _clean_value(str(column)))
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor=HEADER_FILL)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    row_index += 1

    for _, data_row in df.iterrows():
        for col_index, column in enumerate(df.columns, start=1):
            ws.cell(row_index, col_index, _clean_value(data_row.get(column)))
        row_index += 1

    return row_index + 2


def _style_section_sheet(ws) -> None:
    thin = Side(style="thin", color="D9E2F3")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = border

    for column_cells in ws.columns:
        length = 0
        letter = get_column_letter(column_cells[0].column)
        for cell in column_cells[:300]:
            text = "" if cell.value is None else str(cell.value)
            length = max(length, min(len(text), 70))
        ws.column_dimensions[letter].width = max(12, min(length + 2, 45))


def _overview(result: dict[str, Any]) -> pd.DataFrame:
    metadata = result.get("metadata", {}) or {}
    analysis = result.get("analysis", {}) or {}

    rows = [
        ("Report Generated At", utc_now_iso()),
        ("Input Folder", metadata.get("input_folder", "")),
        ("Files Found", metadata.get("files_found", 0)),
        ("Files Loaded", metadata.get("files_loaded", 0)),
        ("Files Failed", metadata.get("files_failed", 0)),
        ("Records Before Deduplication", metadata.get("records_before_deduplication", 0)),
        ("Records After Deduplication", metadata.get("records_after_deduplication", 0)),
        ("Duplicates Removed", metadata.get("duplicates_removed", 0)),
        ("Operators", ", ".join(result.get("operators", []))),
        ("Searched Cell IDs", len(result.get("cell_ids", []))),
        ("Date From", metadata.get("date_from", "")),
        ("Date To", metadata.get("date_to", "")),
        ("Analysis Functions", analysis.get("function_count", 0)),
        ("Completed Analyses", analysis.get("completed_count", 0)),
        ("Failed Analyses", analysis.get("failed_count", 0)),
    ]
    return pd.DataFrame(rows, columns=["Field", "Value"])


def _report_name(case_name: str | None = None) -> str:
    stamp = utc_now().strftime("%Y%m%d_%H%M%S_%f")
    if case_name:
        clean = "".join(ch if ch.isalnum() or ch in (" ", "_", "-") else "_" for ch in case_name)
        clean = "_".join(clean.split())
        return f"Tower_Dump_{clean}_{stamp}.xlsx"
    return f"Tower_Dump_Analysis_{stamp}.xlsx"


def generate_tower_dump_excel_report(
    result: dict[str, Any],
    *,
    output_dir: str | Path | None = None,
    case_name: str | None = None,
    raw_row_limit: int = 200000,
) -> Path:
    target_dir = Path(output_dir).expanduser().resolve() if output_dir else DEFAULT_OUTPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    workbook_path = target_dir / _report_name(case_name)

    wb = Workbook()
    wb.remove(wb.active)

    analysis = result.get("analysis", {}) or {}
    results = analysis.get("results", {}) or {}

    _write_dataframe(wb, "1. Executive Summary", _overview(result))
    _write_dataframe(wb, "2. File Summary", result.get("file_summary", pd.DataFrame()))

    ws = wb.create_sheet("3. Tower Summary")
    row = 1
    row = _write_section(ws, "OPERATOR SUMMARY", row, results.get("operator_summary"))
    row = _write_section(ws, "SEARCHED CELL / CGI SUMMARY", row, results.get("cell_summary"))
    row = _write_section(ws, "CALL TYPE SUMMARY", row, results.get("call_type_summary"))
    _style_section_sheet(ws)

    ws = wb.create_sheet("4. Subscriber Intel")
    row = 1
    row = _write_section(ws, "SUBSCRIBER SUMMARY", row, results.get("subscriber_summary"), max_rows=50000)
    row = _write_section(ws, "FREQUENT VISITORS", row, results.get("frequent_visitors"), max_rows=1000)
    row = _write_section(ws, "REPEAT VISITORS", row, results.get("repeat_visitors"), max_rows=5000)
    _style_section_sheet(ws)

    ws = wb.create_sheet("5. Device Intel")
    row = 1
    row = _write_section(ws, "IMEI SUMMARY", row, results.get("imei_summary"), max_rows=50000)
    row = _write_section(ws, "IMSI SUMMARY", row, results.get("imsi_summary"), max_rows=50000)
    row = _write_section(ws, "SHARED IMEI", row, results.get("shared_imei"), max_rows=10000)
    row = _write_section(ws, "SHARED IMSI", row, results.get("shared_imsi"), max_rows=10000)
    _style_section_sheet(ws)

    ws = wb.create_sheet("6. Common Entities")
    row = 1
    row = _write_section(ws, "SUBSCRIBERS ACROSS MULTIPLE CELLS", row, results.get("subscribers_across_cells"), max_rows=50000)
    row = _write_section(ws, "SUBSCRIBERS ACROSS OPERATORS", row, results.get("subscribers_across_operators"), max_rows=50000)
    _style_section_sheet(ws)

    _write_dataframe(wb, "7. Subscriber Matrix", results.get("common_subscriber_matrix"), max_rows=200000)

    ws = wb.create_sheet("8. Time Analysis")
    row = 1
    row = _write_section(ws, "HOURLY ACTIVITY", row, results.get("hourly_activity"))
    row = _write_section(ws, "DAILY ACTIVITY", row, results.get("daily_activity"))
    row = _write_section(ws, "NIGHT ACTIVITY", row, results.get("night_activity"), max_rows=50000)
    _style_section_sheet(ws)

    ws = wb.create_sheet("9. Movement Analysis")
    row = 1
    row = _write_section(ws, "SUBSCRIBER MOVEMENTS", row, results.get("subscriber_movements"), max_rows=100000)
    row = _write_section(ws, "CELL TRANSITION SUMMARY", row, results.get("cell_transition_summary"), max_rows=50000)
    _style_section_sheet(ws)

    _write_dataframe(wb, "10. Review Indicators", results.get("investigative_indicators"), max_rows=100000)
    _write_dataframe(wb, "10A. CDR Common Repeat", results.get("tower_cdr_common_numbers"), max_rows=50000)
    _write_dataframe(wb, "10B. CDR Uncommon", results.get("tower_cdr_uncommon_numbers"), max_rows=50000)
    _write_dataframe(wb, "10C. CDR Multi Cell", results.get("tower_cdr_multi_cell_presence"), max_rows=50000)
    _write_dataframe(wb, "10D. CDR Device Check", results.get("tower_cdr_device_consistency"), max_rows=50000)
    _write_dataframe(wb, "10E. CDR Timing", results.get("tower_cdr_suspicious_timing"), max_rows=50000)
    _write_dataframe(wb, "10F. CDR Priority Leads", results.get("tower_cdr_priority_leads"), max_rows=50000)
    _write_dataframe(wb, "11. Analysis Status", analysis.get("status", pd.DataFrame()))
    _write_dataframe(wb, "12. Analysis Errors", analysis.get("errors", pd.DataFrame()))

    diagnostics = pd.DataFrame(
        [{"type": "WARNING", "message": item} for item in (result.get("warnings") or [])]
        + [{"type": "ERROR", "message": item} for item in (result.get("errors") or [])]
    )
    _write_dataframe(wb, "13. Load Diagnostics", diagnostics)
    _write_dataframe(
        wb,
        "14. Rejected Rows",
        result.get("rejected_rows", pd.DataFrame()),
        max_rows=raw_row_limit,
    )
    _write_dataframe(wb, "15. Normalized Dump", result.get("df", pd.DataFrame()), max_rows=raw_row_limit)

    append_methodology_sheet(wb, "Tower CDR Dump Analysis")
    wb.save(workbook_path)
    return workbook_path
