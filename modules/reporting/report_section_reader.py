"""Discover and read structured tables in investigator Excel reports."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Any, Final


__all__ = [
    "ReportSection",
    "discover_report_sections",
    "read_report_section_rows",
]


_NO_RECORDS_TEXT: Final[str] = "No records available for this section."
_DEFAULT_ROW_LIMIT: Final[int] = 500


@dataclass(frozen=True, slots=True)
class ReportSection:
    """Describe one table section without copying its workbook records."""

    title: str
    guidance: str
    title_row: int
    header_row: int | None
    data_start_row: int | None
    data_end_row: int | None
    headers: tuple[str, ...]
    record_count: int

    @property
    def is_empty(self) -> bool:
        """Return whether the report contains no records in this section."""

        return self.record_count == 0


def _clean_cell(value: object) -> str:
    """Return a stable text value for report structure checks."""

    if value is None:
        return ""
    return str(value).strip()


def _has_table_border(cell: Any) -> bool:
    """Return whether a cell carries the report table-border style."""

    border = getattr(cell, "border", None)
    if border is None:
        return False

    return any(
        getattr(side, "style", None)
        for side in (
            border.left,
            border.right,
            border.top,
            border.bottom,
        )
    )


def _is_section_title_cell(cell: Any) -> bool:
    """Identify a merged section title by its structural formatting."""

    return bool(
        _clean_cell(cell.value)
        and cell.fill.fill_type == "solid"
        and cell.font.bold
        and not _has_table_border(cell)
    )


def _is_header_cell(cell: Any) -> bool:
    """Identify the first cell of a canonical table header row."""

    return bool(
        _clean_cell(cell.value)
        and cell.fill.fill_type == "solid"
        and cell.font.bold
        and _has_table_border(cell)
    )


def _read_headers(worksheet: Any, row_number: int) -> tuple[str, ...]:
    """Read one header row and remove only unused trailing columns."""

    rows = worksheet.iter_rows(
        min_row=row_number,
        max_row=row_number,
        values_only=True,
    )
    values = tuple(next(rows, ()))
    last_used = 0
    for index, value in enumerate(values, start=1):
        if _clean_cell(value):
            last_used = index

    return tuple(
        _clean_cell(value) or f"Column {index + 1}"
        for index, value in enumerate(values[:last_used])
    )


def discover_report_sections(worksheet: Any) -> tuple[ReportSection, ...]:
    """Return canonical table sections in worksheet order.

    Discovery scans only the first column. The compact report writer applies
    section, header and table-border styles there even when a record value is
    blank, so large worksheets do not need to be copied into memory.
    """

    title_candidates: dict[int, str] = {}
    header_rows: set[int] = set()
    table_rows: set[int] = set()
    first_column_text: dict[int, str] = {}

    for row_number, row in enumerate(
        worksheet.iter_rows(min_col=1, max_col=1),
        start=1,
    ):
        cell = row[0]
        text = _clean_cell(cell.value)
        if text:
            first_column_text[row_number] = text

        if _is_section_title_cell(cell):
            title_candidates[row_number] = text
        elif _is_header_cell(cell):
            header_rows.add(row_number)
        elif _has_table_border(cell):
            table_rows.add(row_number)

    markers: list[tuple[int, str, int | None, str]] = []
    for title_row, title in title_candidates.items():
        marker_row: int | None = None
        for offset in (1, 2):
            candidate_row = title_row + offset
            if (
                candidate_row in header_rows
                or first_column_text.get(candidate_row) == _NO_RECORDS_TEXT
            ):
                marker_row = candidate_row
                break

        if marker_row is None:
            continue

        guidance = (
            first_column_text.get(title_row + 1, "")
            if marker_row == title_row + 2
            else ""
        )
        header_row = marker_row if marker_row in header_rows else None
        markers.append((title_row, title, header_row, guidance))

    markers.sort(key=lambda item: item[0])
    ordered_table_rows = sorted(table_rows)
    sections: list[ReportSection] = []
    worksheet_last_row = int(getattr(worksheet, "max_row", 0) or 0)

    for index, (title_row, title, header_row, guidance) in enumerate(markers):
        next_title_row = (
            markers[index + 1][0]
            if index + 1 < len(markers)
            else worksheet_last_row + 1
        )

        if header_row is None:
            sections.append(
                ReportSection(
                    title=title,
                    guidance=guidance,
                    title_row=title_row,
                    header_row=None,
                    data_start_row=None,
                    data_end_row=None,
                    headers=(),
                    record_count=0,
                )
            )
            continue

        first_data_index = bisect_right(ordered_table_rows, header_row)
        next_section_index = bisect_left(
            ordered_table_rows,
            next_title_row,
        )
        section_data_rows = ordered_table_rows[
            first_data_index:next_section_index
        ]
        sections.append(
            ReportSection(
                title=title,
                guidance=guidance,
                title_row=title_row,
                header_row=header_row,
                data_start_row=(
                    section_data_rows[0] if section_data_rows else None
                ),
                data_end_row=(
                    section_data_rows[-1] if section_data_rows else None
                ),
                headers=_read_headers(worksheet, header_row),
                record_count=len(section_data_rows),
            )
        )

    return tuple(sections)


def read_report_section_rows(
    worksheet: Any,
    section: ReportSection,
    *,
    limit: int = _DEFAULT_ROW_LIMIT,
) -> tuple[tuple[object, ...], ...]:
    """Read bounded rows from exactly one discovered report section."""

    if limit < 1:
        raise ValueError("The report section row limit must be positive.")
    if (
        section.record_count == 0
        or section.data_start_row is None
        or section.data_end_row is None
        or not section.headers
    ):
        return ()

    output: list[tuple[object, ...]] = []
    for row in worksheet.iter_rows(
        min_row=section.data_start_row,
        max_row=section.data_end_row,
        min_col=1,
        max_col=len(section.headers),
    ):
        if not row or not _has_table_border(row[0]):
            continue
        output.append(tuple(cell.value for cell in row))
        if len(output) >= limit:
            break

    return tuple(output)
