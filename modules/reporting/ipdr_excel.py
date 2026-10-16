"""Focused, investigator-friendly Excel reporting for target/reverse multi-operator IPDR."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import re
from typing import Any

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from modules.core.time_utils import utc_now, utc_now_iso
from .excel_security import excel_safe_value
from .report_sanitizer import clean_report_dataframe


REPORT_TABLE_ROW_LIMIT = 5_000
EVENT_PREVIEW_ROWS = 5_000

TITLE_FILL = PatternFill("solid", fgColor="17365D")
HEADER_FILL = PatternFill("solid", fgColor="D9EAF7")
INFO_FILL = PatternFill("solid", fgColor="E2F0D9")
WARNING_FILL = PatternFill("solid", fgColor="FFF2CC")
ERROR_FILL = PatternFill("solid", fgColor="FCE4D6")
THIN = Side(style="thin", color="B7C9DB")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value).strip())
    return cleaned.strip("_") or "CASE"


def _safe_value(value: Any) -> Any:
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


def _write_title(
    worksheet,
    title: str,
    subtitle: str,
    columns: int,
) -> int:
    last_column = max(2, columns)
    worksheet.merge_cells(
        start_row=1,
        start_column=1,
        end_row=1,
        end_column=last_column,
    )
    title_cell = worksheet.cell(1, 1, title)
    title_cell.fill = TITLE_FILL
    title_cell.font = Font(
        color="FFFFFF",
        bold=True,
        size=16,
    )
    title_cell.alignment = Alignment(
        horizontal="center",
        vertical="center",
    )
    worksheet.row_dimensions[1].height = 28

    worksheet.merge_cells(
        start_row=2,
        start_column=1,
        end_row=2,
        end_column=last_column,
    )
    subtitle_cell = worksheet.cell(2, 1, subtitle)
    subtitle_cell.font = Font(
        italic=True,
        color="44546A",
    )
    subtitle_cell.alignment = Alignment(
        horizontal="center",
        vertical="center",
        wrap_text=True,
    )
    worksheet.row_dimensions[2].height = 26
    return 4


def _set_widths(worksheet) -> None:
    for cells in worksheet.columns:
        letter = get_column_letter(cells[0].column)
        maximum = 0
        for cell in cells[:500]:
            if cell.value is not None:
                maximum = max(maximum, len(str(cell.value)))
        worksheet.column_dimensions[letter].width = min(
            max(maximum + 2, 11),
            44,
        )


def _write_page(
    worksheet,
    dataframe: pd.DataFrame,
    *,
    title: str,
    subtitle: str,
) -> None:
    header_row = _write_title(
        worksheet,
        title,
        subtitle,
        max(2, len(dataframe.columns)),
    )

    for column_index, column in enumerate(
        dataframe.columns,
        start=1,
    ):
        cell = worksheet.cell(
            header_row,
            column_index,
            _safe_value(str(column)),
        )
        cell.fill = HEADER_FILL
        cell.font = Font(bold=True)
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
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=False,
            )
            if isinstance(cell.value, (datetime, date)):
                cell.number_format = "yyyy-mm-dd hh:mm:ss"

    last_row = header_row + len(dataframe)
    last_column = get_column_letter(len(dataframe.columns))
    worksheet.auto_filter.ref = (
        f"A{header_row}:{last_column}{last_row}"
    )
    worksheet.freeze_panes = f"A{header_row + 1}"
    worksheet.sheet_view.showGridLines = False
    _set_widths(worksheet)


def _write_table_if_not_empty(
    workbook: Workbook,
    sheet_number: int,
    base_title: str,
    dataframe: Any,
    *,
    subtitle: str,
    row_limit: int = REPORT_TABLE_ROW_LIMIT,
    keep_columns: set[str] | None = None,
) -> bool:
    """Clean and write a worksheet only when it has actual records and columns."""
    cleaned = clean_report_dataframe(
        _frame(dataframe),
        keep_columns=keep_columns,
    )
    if cleaned.empty or len(cleaned.columns) == 0:
        return False

    total_rows = len(cleaned)
    if total_rows > row_limit:
        cleaned = cleaned.head(row_limit).reset_index(drop=True)
        subtitle = (
            f"{subtitle} | Showing first {row_limit:,} of {total_rows:,} rows."
        )

    numbered_title = f"{sheet_number}. {base_title}"
    name = _sheet_name(workbook, numbered_title)
    worksheet = workbook.create_sheet(name)
    _write_page(
        worksheet,
        cleaned,
        title=numbered_title,
        subtitle=subtitle,
    )
    return True


def _key_values(
    worksheet,
    start_row: int,
    rows: list[tuple[str, Any]],
) -> None:
    for offset, (key, value) in enumerate(rows):
        row = start_row + offset
        key_cell = worksheet.cell(row, 1, key)
        value_cell = worksheet.cell(row, 2, _safe_value(value))
        key_cell.fill = HEADER_FILL
        key_cell.font = Font(bold=True)
        key_cell.border = BORDER
        value_cell.border = BORDER
        value_cell.alignment = Alignment(
            wrap_text=True,
            vertical="top",
        )
        if isinstance(value_cell.value, (datetime, date)):
            value_cell.number_format = "yyyy-mm-dd hh:mm:ss"

    worksheet.column_dimensions["A"].width = 36
    worksheet.column_dimensions["B"].width = 74


def _combine_imei_imsi(
    imei_df: pd.DataFrame,
    imsi_df: pd.DataFrame,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if isinstance(imei_df, pd.DataFrame) and not imei_df.empty and "imei" in imei_df.columns:
        part = imei_df.rename(columns={"imei": "Identifier"}).copy()
        part.insert(0, "Identity Type", "IMEI (Handset)")
        frames.append(part)
    if isinstance(imsi_df, pd.DataFrame) and not imsi_df.empty and "imsi" in imsi_df.columns:
        part = imsi_df.rename(columns={"imsi": "Identifier"}).copy()
        part.insert(0, "Identity Type", "IMSI (SIM)")
        frames.append(part)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def generate_ipdr_excel_report(
    *,
    case: dict[str, Any],
    mode: str,
    load_result: dict[str, Any],
    analysis: dict[str, Any],
    output_dir: str | Path,
    saved: dict[str, Any] | None = None,
) -> Path:
    """Generate a compact, non-empty, investigator-focused IPDR workbook."""
    case_id = str(case.get("case_id", "")).strip() or "CASE"
    case_name = str(case.get("case_name", "")).strip()
    mode = str(mode).strip().lower()
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now().strftime("%Y%m%d_%H%M%S_%f")
    report_path = output / (
        f"IPDR_Analysis_{mode.title()}_"
        f"{_safe_filename(case_id)}_{timestamp}.xlsx"
    )

    workbook = Workbook()
    workbook.remove(workbook.active)

    overview = workbook.create_sheet(
        _sheet_name(workbook, "1. Executive Summary")
    )
    start = _write_title(
        overview,
        f"{mode.title()} IPDR Investigation Report",
        f"Case: {case_id}" + (f" | {case_name}" if case_name else ""),
        6,
    )

    metadata = load_result.get("metadata", {}) or {}
    subscriber_summary = _frame(analysis.get("subscriber_summary"))
    app_usage = _frame(analysis.get("application_usage_summary"))
    vpn_voip = _frame(analysis.get("voip_vpn_highlights"))
    social_ips = _frame(analysis.get("p2p_social_calling_leads"))
    ipv4_df = _frame(analysis.get("ipv4_sessions"))
    ipv6_df = _frame(analysis.get("ipv6_sessions"))
    airtel_df = _frame(analysis.get("airtel_ips"))
    jio_df = _frame(analysis.get("jio_ips"))
    vi_df = _frame(analysis.get("vi_ips"))
    bsnl_df = _frame(analysis.get("bsnl_ips"))
    others_df = _frame(analysis.get("other_company_ips"))
    summary_df = _frame(analysis.get("summary"))

    kv_rows: list[tuple[str, Any]] = [
        ("Case ID", case_id),
        ("Case Name", case_name or "-"),
        ("Analysis Mode", mode.upper()),
        ("Generated At", utc_now_iso()),
        ("Files Found", metadata.get("files_found", 0)),
        ("Files Loaded", metadata.get("files_loaded", 0)),
        ("Total Normalized IPDR Records", metadata.get("total_records", 0)),
        ("Operators Detected", ", ".join(metadata.get("operators", []) or []) or "-"),
        ("Unique Target Subscribers / User IDs", len(subscriber_summary)),
        ("IPv4 Sessions", len(ipv4_df)),
        ("IPv6 Sessions", len(ipv6_df)),
        ("Airtel Destination IPs", len(airtel_df)),
        ("Jio Destination IPs", len(jio_df)),
        ("Vi Destination IPs", len(vi_df)),
        ("BSNL Destination IPs", len(bsnl_df)),
        ("Other Company (Apps/VPN/Cloud) IPs", len(others_df)),
        ("High-Priority VPN / VoIP Call Alerts", len(vpn_voip)),
        ("Suspected B-Party Social Calling IPs", len(social_ips)),
    ]

    if not summary_df.empty and {"Metric", "Value"}.issubset(summary_df.columns):
        for _, srow in summary_df.iterrows():
            m_name = str(srow.get("Metric", "")).strip()
            if m_name in {
                "Unique IMEI/Device IDs",
                "Unique IMSI",
                "Unique Source IP",
                "Unique Destination IP",
                "Unique CGI/Cells",
                "First Event Time",
                "Last Event Time",
                "Deduplicated Uplink Volume",
                "Deduplicated Downlink Volume",
            }:
                kv_rows.append((m_name, srow.get("Value", "")))

    _key_values(overview, start, kv_rows)
    overview.freeze_panes = "A4"
    overview.sheet_view.showGridLines = False

    device_sim_df = _combine_imei_imsi(
        _frame(analysis.get("imei_summary")),
        _frame(analysis.get("imsi_summary")),
    )

    coactivity_protected = {
        "Subscriber No.",
        "Operator",
        "IP Version",
        "Destination IP",
        "Destination Port",
        "IP Company",
        "Application",
        "Session From",
        "Session To",
        "Part",
        "Same Time Apps",
        "Same Time Companies",
    }

    candidate_sheets = [
        (
            "Session & Same-Time Apps",
            analysis.get("session_coactivity"),
            "Operator, IP Version, Destination IP, Port, Application, Session From/To, Part, Same-Time Apps & Same-Time Companies.",
            REPORT_TABLE_ROW_LIMIT,
            coactivity_protected,
        ),
        (
            "App & VPN Usage",
            analysis.get("application_usage_summary"),
            "Application, website, VoIP and VPN usage with company name and active duration.",
            REPORT_TABLE_ROW_LIMIT,
            None,
        ),
        (
            "VPN & VoIP Alerts",
            analysis.get("voip_vpn_highlights"),
            "High-priority VPN, Proxy, WhatsApp/Telegram/Signal/Zangi Call and P2P leads.",
            REPORT_TABLE_ROW_LIMIT,
            None,
        ),
        (
            "Social Calling IPs",
            analysis.get("p2p_social_calling_leads"),
            "Suspected B-Party Subscriber IPs & Ports for Reverse-IPDR lookup.",
            REPORT_TABLE_ROW_LIMIT,
            None,
        ),
        (
            "IPv4",
            ipv4_df,
            "All IPv4 sessions with Operator, Destination IP, Port, Application, Session From/To and Same-Time Apps.",
            REPORT_TABLE_ROW_LIMIT,
            coactivity_protected,
        ),
        (
            "IPv6",
            ipv6_df,
            "All IPv6 sessions with Operator, Destination IP, Port, Application, Session From/To and Same-Time Apps.",
            REPORT_TABLE_ROW_LIMIT,
            coactivity_protected,
        ),
        (
            "Source IP",
            analysis.get("source_ip_summary"),
            "Source / Public IP addresses allocated to the subscriber.",
            REPORT_TABLE_ROW_LIMIT,
            None,
        ),
        (
            "Destination IP",
            analysis.get("destination_endpoint_summary"),
            "Destination IP and Port combinations with identified Company and Application.",
            REPORT_TABLE_ROW_LIMIT,
            None,
        ),
        (
            "Airtel",
            airtel_df,
            "Sessions connected to Bharti Airtel IPs (Subscriber P2P or Airtel Infrastructure).",
            REPORT_TABLE_ROW_LIMIT,
            coactivity_protected,
        ),
        (
            "Jio",
            jio_df,
            "Sessions connected to Reliance Jio IPs (Subscriber P2P or Jio Infrastructure).",
            REPORT_TABLE_ROW_LIMIT,
            coactivity_protected,
        ),
        (
            "Vi",
            vi_df,
            "Sessions connected to Vodafone Idea (Vi) IPs.",
            REPORT_TABLE_ROW_LIMIT,
            coactivity_protected,
        ),
        (
            "BSNL",
            bsnl_df,
            "Sessions connected to BSNL / MTNL IPs.",
            REPORT_TABLE_ROW_LIMIT,
            coactivity_protected,
        ),
        (
            "Others",
            others_df,
            "Sessions connected to Other Companies (WhatsApp/Meta, Google, Telegram, Signal, Zangi, VPNs, Cloud CDNs).",
            REPORT_TABLE_ROW_LIMIT,
            coactivity_protected,
        ),
        (
            "Subscribers",
            analysis.get("subscriber_summary"),
            "Target subscriber activity summary with SDR details.",
            REPORT_TABLE_ROW_LIMIT,
            None,
        ),
        (
            "IMEI & IMSI",
            device_sim_df,
            "Handset IMEI and SIM IMSI identities used in IPDR sessions.",
            REPORT_TABLE_ROW_LIMIT,
            None,
        ),
        (
            "Cell Towers (CGI)",
            analysis.get("cgi_summary"),
            "Cell ID / CGI tower activity and enriched tower locations.",
            REPORT_TABLE_ROW_LIMIT,
            None,
        ),
        (
            "Hourly Activity",
            analysis.get("hourly_activity"),
            "Date and hour-wise internet session activity.",
            REPORT_TABLE_ROW_LIMIT,
            None,
        ),
    ]

    next_sheet_no = 2
    for base_title, table_data, subtitle, limit, keep_cols in candidate_sheets:
        wrote = _write_table_if_not_empty(
            workbook,
            next_sheet_no,
            base_title,
            table_data,
            subtitle=subtitle,
            row_limit=limit,
            keep_columns=keep_cols,
        )
        if wrote:
            next_sheet_no += 1

    workbook.properties.title = f"IPDR Analysis ({mode.title()}) - {case_id}"
    workbook.properties.subject = "Multi-operator IPDR forensic analysis"
    workbook.properties.creator = "Telecom Forensics Analysis Suite"
    workbook.save(report_path)
    return report_path
