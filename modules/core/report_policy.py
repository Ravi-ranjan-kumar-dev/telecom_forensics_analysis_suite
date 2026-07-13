#report/output control wali common file

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import pandas as pd

from modules.core.processing_policy import ProcessingPolicy


DEFAULT_HEAVY_COLUMNS = {
    "source_file",
    "source_files",
    "Source_File",
    "Source_Files",
    "source_path",
    "source_paths",
    "raw_record",
    "raw_row",
}


@dataclass(frozen=True)
class ReportPolicy:
    console_row_limit: int
    excel_preview_rows: int
    max_excel_rows_per_sheet: int
    should_generate_full_excel: bool
    should_print_large_tables: bool
    hide_heavy_console_columns: bool
    heavy_columns: set[str]
    backend_full_data_required: bool
    gui_progress_enabled: bool

    def to_dict(self) -> dict:
        data = asdict(self)
        data["heavy_columns"] = sorted(self.heavy_columns)
        return data


def build_report_policy(
    processing_policy: ProcessingPolicy,
    *,
    extra_heavy_columns: Iterable[str] | None = None,
) -> ReportPolicy:
    heavy_columns = set(DEFAULT_HEAVY_COLUMNS)

    if extra_heavy_columns:
        heavy_columns.update(str(column) for column in extra_heavy_columns)

    return ReportPolicy(
        console_row_limit=processing_policy.console_row_limit,
        excel_preview_rows=processing_policy.excel_preview_rows,
        max_excel_rows_per_sheet=processing_policy.max_excel_rows_per_sheet,
        should_generate_full_excel=processing_policy.should_generate_full_excel,
        should_print_large_tables=processing_policy.should_print_large_tables,
        hide_heavy_console_columns=not processing_policy.should_print_large_tables,
        heavy_columns=heavy_columns,
        backend_full_data_required=not processing_policy.should_generate_full_excel,
        gui_progress_enabled=True,
    )


def compact_dataframe_for_console(
    dataframe: pd.DataFrame,
    report_policy: ReportPolicy,
    *,
    row_limit: int | None = None,
    hide_columns: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Return a small DataFrame suitable for terminal display.

    This function does not modify the original DataFrame.
    """

    if dataframe is None or dataframe.empty:
        return pd.DataFrame()

    limit = row_limit or report_policy.console_row_limit

    hidden = set(hide_columns or set())

    if report_policy.hide_heavy_console_columns:
        hidden.update(report_policy.heavy_columns)

    visible_columns = [
        column
        for column in dataframe.columns
        if column not in hidden
    ]

    compact = dataframe.loc[:, visible_columns].head(limit).copy()
    return compact


def dataframe_overflow_count(
    dataframe: pd.DataFrame,
    *,
    shown_rows: int,
) -> int:
    if dataframe is None:
        return 0

    return max(len(dataframe) - shown_rows, 0)


def should_write_excel_sheet(
    dataframe: pd.DataFrame,
    report_policy: ReportPolicy,
    *,
    is_summary_sheet: bool = False,
) -> bool:
    """Decide whether a DataFrame should be written to Excel.

    Summary sheets are always allowed. Large detail sheets are only allowed
    when full Excel generation is enabled or row count is within preview limit.
    """

    if dataframe is None or dataframe.empty:
        return True

    if is_summary_sheet:
        return True

    if report_policy.should_generate_full_excel:
        return len(dataframe) <= report_policy.max_excel_rows_per_sheet

    return len(dataframe) <= report_policy.excel_preview_rows


def limit_dataframe_for_excel(
    dataframe: pd.DataFrame,
    report_policy: ReportPolicy,
    *,
    is_summary_sheet: bool = False,
) -> pd.DataFrame:
    """Limit DataFrame rows for Excel export according to policy."""

    if dataframe is None or dataframe.empty:
        return pd.DataFrame()

    if is_summary_sheet:
        return dataframe.copy()

    if report_policy.should_generate_full_excel:
        return dataframe.head(
            report_policy.max_excel_rows_per_sheet
        ).copy()

    return dataframe.head(
        report_policy.excel_preview_rows
    ).copy()


def make_report_note(
    dataframe: pd.DataFrame,
    report_policy: ReportPolicy,
    *,
    sheet_name: str,
    is_summary_sheet: bool = False,
) -> str:
    """Create a clear note for console/Excel report limitation."""

    total_rows = 0 if dataframe is None else len(dataframe)

    if is_summary_sheet:
        return f"{sheet_name}: summary sheet, rows={total_rows}"

    if report_policy.should_generate_full_excel:
        limit = report_policy.max_excel_rows_per_sheet
    else:
        limit = report_policy.excel_preview_rows

    if total_rows <= limit:
        return f"{sheet_name}: full rows included, rows={total_rows}"

    return (
        f"{sheet_name}: preview only, rows_included={limit}, "
        f"total_rows={total_rows}. Full data must be kept in backend storage."
    )


def print_report_policy(
    report_policy: ReportPolicy,
) -> None:
    print("\nREPORT POLICY")
    print("-" * 70)
    print(f"Console row limit          : {report_policy.console_row_limit}")
    print(f"Excel preview rows         : {report_policy.excel_preview_rows}")
    print(f"Max Excel rows/sheet       : {report_policy.max_excel_rows_per_sheet}")
    print(f"Generate full Excel        : {report_policy.should_generate_full_excel}")
    print(f"Print large tables         : {report_policy.should_print_large_tables}")
    print(f"Hide heavy console columns : {report_policy.hide_heavy_console_columns}")
    print(f"Backend full data required : {report_policy.backend_full_data_required}")
    print(f"GUI progress enabled       : {report_policy.gui_progress_enabled}")