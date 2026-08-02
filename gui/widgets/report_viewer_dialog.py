"""Reusable investigator-facing Excel report viewer."""

from __future__ import annotations

import re
from itertools import chain, islice
from pathlib import Path
from typing import Any, Final

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

__all__ = [
    "RelatedRecordsDialog",
    "ReportViewerDialog",
    "canonical_phone_number",
    "detect_identifier_columns",
    "detect_number_columns",
    "prepare_related_records",
]


_NUMBER_HEADER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:^|\b)(?:contact|other party|common number|b[ -]?party|a[ -]?party|"
    r"source target|destination target|target(?: number)?|msisdn|"
    r"subscriber(?: number)?|mobile(?: number)?|phone(?: number)?)(?:\b|$)",
    re.IGNORECASE,
)
_CELL_HEADER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:^|\b)(?:cell(?: site)? id|cgi|towers?)(?:\b|$)",
    re.IGNORECASE,
)
_IMEI_HEADER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:^|\b)(?:imei|old imei|new imei|device id)(?:\b|$)", re.IGNORECASE
)
_IMSI_HEADER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:^|\b)(?:imsi|old imsi|new imsi|sim id)(?:\b|$)", re.IGNORECASE
)
_NON_IDENTIFIER_HEADER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:status|address|town|district|latitude|longitude|count|events?|"
    r"records?|duration|name|valid|invalid|found|unique|total)",
    re.IGNORECASE,
)
_MAX_VISIBLE_ROWS: Final[int] = 500
_HEADER_SCAN_ROWS: Final[int] = 25
_IDENTIFIER_LABELS: Final[dict[str, str]] = {
    "phone": "Phone Number",
    "cell_id": "Cell ID",
    "imei": "IMEI",
    "imsi": "IMSI",
}
_MINIMUM_IDENTIFIER_DIGITS: Final[dict[str, int]] = {
    "phone": 8,
    "cell_id": 4,
    "imei": 14,
    "imsi": 14,
}

_RELATED_RECORD_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("a_party", "Target Number"),
    ("target_number", "Target Number"),
    ("b_party", "Other Party"),
    ("call_date", "Date"),
    ("call_time", "Time"),
    ("call_type", "Event Type"),
    ("call_duration", "Duration (Seconds)"),
    ("first_cell_id", "First Cell ID"),
    ("first_bts_location", "First Tower Location"),
    ("last_cell_id", "Last Cell ID"),
    ("last_bts_location", "Last Tower Location"),
    ("imei", "IMEI"),
    ("imsi", "IMSI"),
    ("roaming_network", "Roaming Network"),
    ("service_type", "Service Type"),
)


class RelatedRecordsDialog(QDialog):
    """Display verified source Call/SMS records for one telecom identifier."""

    def __init__(
        self,
        identifier: str,
        records: Any,
        parent: QWidget | None = None,
        identifier_label: str = "Number",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            f"Related {identifier_label} Records - {identifier}"
        )
        self.resize(1280, 760)
        self.setModal(True)

        display_records, duplicates_hidden = prepare_related_records(records)

        title = QLabel(f"Related records for {identifier_label}: {identifier}")
        title.setObjectName("moduleTitle")
        duplicate_note = (
            f" Exact duplicates hidden: {duplicates_hidden:,}."
            if duplicates_hidden
            else ""
        )
        metadata = getattr(records, "attrs", {})
        result_limited = bool(metadata.get("result_limited", False))
        limit_note = ""
        if result_limited:
            try:
                result_limit = max(
                    1,
                    int(metadata.get("result_limit", len(records))),
                )
            except (TypeError, ValueError):
                result_limit = len(records)

            minimum_matches = max(
                result_limit + 1,
                len(records) + 1,
            )
            limit_note = (
                " Query limit reached: at least "
                f"{minimum_matches:,} matching source records were found; "
                f"the first {len(records):,} source records were loaded."
            )

        status = QLabel(
            f"Verified records shown: {len(display_records):,}."
            f"{duplicate_note}{limit_note} "
            "Source evidence was read without modification."
        )
        status.setWordWrap(True)

        table = QTableWidget()
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        columns = list(map(str, display_records.columns))
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setRowCount(len(display_records))
        for row_index, row in enumerate(
            display_records.itertuples(index=False, name=None)
        ):
            for column_index, value in enumerate(row):
                table.setItem(
                    row_index,
                    column_index,
                    QTableWidgetItem(_clean_cell(value)),
                )
        table.setSortingEnabled(True)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        table.horizontalHeader().setDefaultSectionSize(150)

        close_button = QPushButton("Close")
        close_button.setObjectName("primaryButton")
        close_button.clicked.connect(self.accept)
        controls = QHBoxLayout()
        controls.addStretch(1)
        controls.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(status)
        layout.addWidget(table, stretch=1)
        layout.addLayout(controls)

        self._table = table
        self._status = status


def prepare_related_records(records: Any) -> tuple[Any, int]:
    """Build a clean display copy and count exact duplicate source rows."""

    source = records.copy()
    duplicate_mask = source.duplicated(keep="first")
    duplicates_hidden = int(duplicate_mask.sum())
    unique_records = source.loc[~duplicate_mask].copy()

    selected: list[str] = []
    labels: list[str] = []
    used_labels: set[str] = set()
    for source_name, display_label in _RELATED_RECORD_COLUMNS:
        if source_name not in unique_records.columns:
            continue
        if display_label in used_labels:
            continue
        selected.append(source_name)
        labels.append(display_label)
        used_labels.add(display_label)

    if selected:
        display_records = unique_records.loc[:, selected].copy()
        display_records.columns = labels
    else:
        visible_columns = [
            column
            for column in unique_records.columns
            if not str(column).startswith("_")
        ]
        display_records = unique_records.loc[:, visible_columns].copy()

    return display_records.reset_index(drop=True), duplicates_hidden


def _clean_cell(value: object) -> str:
    """Return a safe display value without changing workbook data."""

    if value is None:
        return ""
    return str(value).strip()


def _canonical_digits(value: object) -> str:
    """Return digits from a telecom identifier without altering its source."""

    return re.sub(r"\D", "", _clean_cell(value))


def detect_number_columns(headers: list[object] | tuple[object, ...]) -> tuple[int, ...]:
    """Return indexes of columns that represent telephone numbers."""

    return tuple(
        index
        for index, header in enumerate(headers)
        if _NUMBER_HEADER_PATTERN.search(_clean_cell(header))
    )


def detect_identifier_columns(
    headers: list[object] | tuple[object, ...],
) -> dict[int, str]:
    """Map workbook columns to safe telecom identifier types."""

    patterns = (
        ("imei", _IMEI_HEADER_PATTERN),
        ("imsi", _IMSI_HEADER_PATTERN),
        ("cell_id", _CELL_HEADER_PATTERN),
        ("phone", _NUMBER_HEADER_PATTERN),
    )
    detected: dict[int, str] = {}
    for index, header in enumerate(headers):
        text = _clean_cell(header)
        if _NON_IDENTIFIER_HEADER_PATTERN.search(text):
            continue
        for identifier_type, pattern in patterns:
            if pattern.search(text):
                detected[index] = identifier_type
                break
    return detected


def canonical_phone_number(value: object) -> str:
    """Normalize an Indian phone value for safe report-summary matching."""

    digits = _canonical_digits(value)
    if len(digits) == 12 and digits.startswith("91"):
        return digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        return digits[1:]
    return digits


def _canonical_identifier(value: object, identifier_type: str) -> str:
    """Normalize an identifier for matching and verified source queries."""

    if identifier_type == "phone":
        return canonical_phone_number(value)
    return _canonical_digits(value)


def _header_index(rows: list[tuple[object, ...]]) -> int:
    """Find the most likely table header within the report title area."""

    if not rows:
        return 0

    def score(row: tuple[object, ...]) -> tuple[int, int]:
        populated = sum(bool(_clean_cell(value)) for value in row)
        number_labels = len(detect_identifier_columns(row))
        return number_labels, populated

    return max(range(len(rows)), key=lambda index: score(rows[index]))


class ReportViewerDialog(QDialog):
    """Display an Excel workbook without modifying the evidence file."""

    def __init__(
        self,
        report_path: str | Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._report_path = Path(report_path).expanduser().resolve(strict=False)
        self._workbook = None
        self._number_columns: tuple[int, ...] = ()
        self._identifier_columns: dict[int, str] = {}
        self._verified_source_link = None

        self.setWindowTitle("Investigation Report Viewer")
        self.resize(1200, 760)
        self.setModal(True)

        self._file_label = QLabel(self._report_path.name)
        self._file_label.setObjectName("moduleTitle")

        self._sheet_selector = QComboBox()
        self._sheet_selector.setAccessibleName("Report sheet")
        self._sheet_selector.currentTextChanged.connect(self._show_sheet)

        self._status = QLabel()
        self._status.setObjectName("cardText")
        self._status.setWordWrap(True)

        self._table = QTableWidget()
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.cellDoubleClicked.connect(self._show_identifier_records)

        external_button = QPushButton("Open Externally")
        external_button.setObjectName("secondaryButton")
        external_button.clicked.connect(self._open_externally)

        close_button = QPushButton("Close")
        close_button.setObjectName("primaryButton")
        close_button.clicked.connect(self.accept)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Sheet:"))
        controls.addWidget(self._sheet_selector, stretch=1)
        controls.addWidget(external_button)
        controls.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(self._file_label)
        layout.addLayout(controls)
        layout.addWidget(self._status)
        layout.addWidget(self._table, stretch=1)

        self._load_workbook()

    @property
    def number_columns(self) -> tuple[int, ...]:
        """Return number columns detected in the visible sheet."""

        return self._number_columns

    def _load_workbook(self) -> None:
        """Open the workbook in read-only mode and list its sheets."""

        try:
            self._workbook = load_workbook(
                self._report_path,
                read_only=True,
                data_only=True,
            )
        except Exception as error:
            self._status.setText(
                "This workbook could not be read. "
                f"{type(error).__name__}: {error}"
            )
            self._table.setEnabled(False)
            return

        self._sheet_selector.addItems(self._workbook.sheetnames)
        if self._workbook.sheetnames:
            self._show_sheet(self._workbook.sheetnames[0])

    def _show_sheet(self, sheet_name: str) -> None:
        """Render a bounded number of rows from the selected sheet."""

        if self._workbook is None or not sheet_name:
            return

        worksheet: Worksheet = self._workbook[sheet_name]
        rows = worksheet.iter_rows(values_only=True)
        scanned_rows = list(islice(rows, _HEADER_SCAN_ROWS))
        header_index = _header_index(scanned_rows)
        header_row = scanned_rows[header_index] if scanned_rows else ()
        headers = [
            _clean_cell(value) or f"Column {index + 1}"
            for index, value in enumerate(header_row)
        ]
        self._identifier_columns = detect_identifier_columns(headers)
        self._number_columns = tuple(
            index
            for index, identifier_type in self._identifier_columns.items()
            if identifier_type == "phone"
        )

        data_rows = chain(scanned_rows[header_index + 1 :], rows)
        visible_rows: list[tuple[object, ...]] = []
        for row_number, row in enumerate(data_rows):
            if row_number >= _MAX_VISIBLE_ROWS:
                break
            visible_rows.append(tuple(row))

        self._table.setSortingEnabled(False)
        self._table.clear()
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setRowCount(len(visible_rows))

        for row_index, row in enumerate(visible_rows):
            for column_index in range(len(headers)):
                value = row[column_index] if column_index < len(row) else None
                item = QTableWidgetItem(_clean_cell(value))
                if column_index in self._identifier_columns:
                    label = _IDENTIFIER_LABELS[
                        self._identifier_columns[column_index]
                    ]
                    item.setForeground(QColor("#285A1F"))
                    item.setToolTip(f"Double-click to view related {label} records")
                self._table.setItem(row_index, column_index, item)

        self._table.setSortingEnabled(True)
        worksheet_rows = worksheet.max_row or 0
        total_rows = max(worksheet_rows - header_index - 1, 0)
        limit_note = (
            f" Showing the first {_MAX_VISIBLE_ROWS:,} records."
            if total_rows > _MAX_VISIBLE_ROWS
            else ""
        )
        self._status.setText(
            f"Sheet: {sheet_name} | Records: {total_rows:,}."
            f"{limit_note} Highlighted identifiers open verified source records."
        )

    def _show_number_summary(self, row: int, column: int) -> None:
        """Backward-compatible phone-number drill-down entry point."""

        self._show_identifier_records(row, column)

    def _show_identifier_records(self, row: int, column: int) -> None:
        """Show verified records for a phone, Cell ID, IMEI or IMSI."""

        identifier_type = self._identifier_columns.get(column)
        if identifier_type is None:
            return

        label = _IDENTIFIER_LABELS[identifier_type]
        selected = self._table.item(row, column)
        identifier = selected.text().strip() if selected is not None else ""
        canonical_value = _canonical_identifier(identifier, identifier_type)
        if len(canonical_value) < _MINIMUM_IDENTIFIER_DIGITS[identifier_type]:
            QMessageBox.information(
                self,
                f"Invalid {label}",
                f"The selected value is not a valid {label}.",
            )
            return

        matches = 0
        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, column)
            if item is not None:
                candidate = _canonical_identifier(
                    item.text(),
                    identifier_type,
                )
                if candidate == canonical_value:
                    matches += 1

        try:
            from modules.reporting import cdr_report_source
        except ImportError:
            QMessageBox.warning(
                self,
                "Related Records Unavailable",
                "The verified source reader is not available in this installation.",
            )
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            if self._verified_source_link is None:
                self._verified_source_link = cdr_report_source.load_verified_source_link(
                    self._report_path
                )
            if self._verified_source_link is None:
                QMessageBox.information(
                    self,
                    f"{label} Summary",
                    (
                        f"Selected {label}: {identifier}\n"
                        f"Matching rows in the visible report sheet: {matches}\n\n"
                        "This older report has no verified source-data link. "
                        "Only the workbook summary can be shown safely."
                    ),
                )
                return

            records = cdr_report_source.query_related_records(
                self._verified_source_link,
                canonical_value,
                identifier_type=identifier_type,
            )
        except cdr_report_source.SourceLinkError as error:
            QMessageBox.warning(
                self,
                "Source Verification Failed",
                (
                    "Complete records were not opened because the report-to-source "
                    f"verification failed.\n\n{error}"
                ),
            )
            return
        except Exception as error:
            QMessageBox.warning(
                self,
                "Related Records",
                f"Related records could not be read.\n{type(error).__name__}: {error}",
            )
            return
        finally:
            QApplication.restoreOverrideCursor()

        if records.empty:
            QMessageBox.information(
                self,
                "Related Records",
                (
                    f"Selected {label}: {identifier}\n"
                    f"Matching rows in the visible report sheet: {matches}\n\n"
                    "No matching Call/SMS records were found in the verified source."
                ),
            )
            return

        RelatedRecordsDialog(
            identifier,
            records,
            self,
            identifier_label=label,
        ).exec()

    def _open_externally(self) -> None:
        """Open the report with the operating-system application."""

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._report_path))):
            QMessageBox.warning(
                self,
                "Open Report",
                "The operating system could not open the report.",
            )

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Release the read-only workbook handle when the dialog closes."""

        if self._workbook is not None:
            self._workbook.close()
        super().closeEvent(event)