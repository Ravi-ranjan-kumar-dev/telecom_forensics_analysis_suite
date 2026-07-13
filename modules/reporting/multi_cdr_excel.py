"""Generate a separate cross-target Excel workbook for multiple CDR analysis."""

from __future__ import annotations

from modules.core.time_utils import utc_now, utc_now_iso

from datetime import datetime
from pathlib import Path
from typing import Any
import traceback

import pandas as pd
from openpyxl import Workbook

from modules.analysis.cdr.cross_target import build_cross_target_analysis
from .excel_styles import (
    finish_sheet,
    set_sensible_widths,
    style_data_area,
    style_metadata_block,
    style_table_header,
)
from .excel_security import excel_safe_value
from .report_guidance import append_methodology_sheet
from .report_paths import get_multi_report_path


SHEET_MAP = [
    ("1. Cross Summary", "Multiple CDR Cross Summary", "summary"),
    ("2. Target Overview", "Target Overview", "target_overview"),
    ("3. Common Numbers", "Common Contact Numbers", "common_numbers"),
    ("4. Direct Links", "Direct Target-to-Target Links", "direct_target_links"),
    ("5. Common Towers", "Common Tower IDs", "common_towers"),
    ("6. Common IMEI", "Common IMEI / Shared Device", "common_imeis"),
    ("7. Common IMSI", "Common IMSI", "common_imsis"),
    ("8. Contact Matrix", "Common Number vs Target Matrix", "contact_matrix"),
    ("9. Tower Matrix", "Common Tower vs Target Matrix", "tower_matrix"),
    ("10. IMEI Matrix", "Common IMEI vs Target Matrix", "imei_matrix"),
    ("11. IMSI Matrix", "Common IMSI vs Target Matrix", "imsi_matrix"),
    ("12. Source Files", "Source Files", "source_files"),
    ("13. Alerts", "Cross-Target Review Alerts", "alerts"),
    ("14. Errors", "Analysis Errors", "errors"),
]


def _metadata_rows(
    metadata: dict[str, Any],
    report_name: str,
    target_count: int,
) -> list[tuple[str, Any]]:
    return [
        ("Case", metadata.get("case_name", "")),
        ("Report", report_name),
        ("Targets Analyzed", target_count),
        ("Generated On", utc_now_iso()),
        ("Minimum Common Threshold", metadata.get("min_targets", 2)),
    ]


def _write_dataframe_sheet(
    workbook: Workbook,
    sheet_name: str,
    report_name: str,
    metadata: dict[str, Any],
    target_count: int,
    frame: pd.DataFrame | None,
) -> None:
    worksheet = workbook.create_sheet(title=sheet_name)
    data = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()

    if data.shape[1] == 0:
        data = pd.DataFrame(columns=["Result"])

    headers = list(data.columns)
    header_row = style_metadata_block(
        worksheet,
        _metadata_rows(metadata, report_name, target_count),
        max(1, len(headers)),
    )

    for column_index, header in enumerate(headers, start=1):
        worksheet.cell(row=header_row, column=column_index, value=excel_safe_value(str(header)))
    style_table_header(worksheet, header_row, len(headers))

    for row_index, row in enumerate(data.itertuples(index=False, name=None), start=header_row + 1):
        for column_index, value in enumerate(row, start=1):
            worksheet.cell(
                row=row_index,
                column=column_index,
                value=excel_safe_value(value),
            )

    last_row = header_row + len(data)
    style_data_area(worksheet, header_row + 1, last_row, len(headers))
    set_sensible_widths(worksheet, headers)
    finish_sheet(worksheet, header_row, last_row, len(headers))

    for column_index, header in enumerate(headers, start=1):
        header_lower = str(header).lower()
        if "first seen" in header_lower or "last seen" in header_lower or header_lower in {"from date", "to date"}:
            for row_index in range(header_row + 1, last_row + 1):
                cell = worksheet.cell(row=row_index, column=column_index)
                if hasattr(cell.value, "year"):
                    cell.number_format = "dd-mm-yyyy hh:mm:ss"


def generate_multi_cdr_report(
    loaded_cdrs: dict[str, dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    analysis_bundle: dict[str, Any] | None = None,
    output_dir: str | Path | None = None,
    min_targets: int = 2,
) -> str | None:
    """Generate the separate multiple-CDR common-analysis workbook."""
    if not isinstance(loaded_cdrs, dict) or len(loaded_cdrs) < 2:
        print("[-] Multi-CDR Excel report requires at least two loaded targets.")
        return None

    try:
        report_metadata = dict(metadata or {})
        report_metadata["min_targets"] = max(2, int(min_targets))
        bundle = analysis_bundle or build_cross_target_analysis(
            loaded_cdrs,
            min_targets=report_metadata["min_targets"],
        )

        workbook = Workbook()
        workbook.remove(workbook.active)

        for sheet_name, report_name, result_key in SHEET_MAP:
            _write_dataframe_sheet(
                workbook=workbook,
                sheet_name=sheet_name,
                report_name=report_name,
                metadata=report_metadata,
                target_count=len(loaded_cdrs),
                frame=bundle.get(result_key),
            )

        rejected_frames: list[pd.DataFrame] = []
        for target, info in loaded_cdrs.items():
            rejected = info.get("rejected_rows")
            if not isinstance(rejected, pd.DataFrame):
                dataframe = info.get("df")
                if isinstance(dataframe, pd.DataFrame):
                    rejected = dataframe.attrs.get("rejected_rows")
            if isinstance(rejected, pd.DataFrame) and not rejected.empty:
                frame = rejected.copy()
                frame.insert(0, "target", str(target))
                rejected_frames.append(frame)
        rejected_rows = (
            pd.concat(rejected_frames, ignore_index=True, sort=False)
            if rejected_frames else pd.DataFrame()
        )
        _write_dataframe_sheet(
            workbook=workbook,
            sheet_name="15. Rejected Rows",
            report_name="Rejected / Quarantined Source Rows",
            metadata=report_metadata,
            target_count=len(loaded_cdrs),
            frame=rejected_rows,
        )

        path = get_multi_report_path(
            case_name=report_metadata.get("case_name"),
            output_dir=output_dir,
        )
        append_methodology_sheet(workbook, "Multiple CDR Cross-Target Analysis")
        workbook.save(path)
        print(f"[+] Multiple CDR common-analysis Excel report generated: {path}")
        return str(path)

    except Exception as error:
        print("[-] Multiple CDR common-analysis Excel report generation failed.")
        print(f"    Error Type : {type(error).__name__}")
        print(f"    Message    : {error}")
        print(traceback.format_exc(limit=4).rstrip())
        return None
