"""SDR, CGI and master-data lookup page for the desktop GUI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.workers.lookup_worker import LookupWorker
from modules.database.lookup_service import (
    DATABASE_ERROR,
    INVALID_INPUT,
    MATCHED,
    NOT_FOUND,
)
from modules.database.master_import_service import (
    SUPPORTED_MASTER_SUFFIXES,
)

# SDR table columns
_SDR_COLUMNS = (
    ("mobile_number", "Mobile Number"),
    ("subscriber_name", "Subscriber Name"),
    ("father_name", "Father / Husband"),
    ("clean_address", "Readable Address"),
    ("id_number", "Identity Number"),
    ("operator_or_source_category", "Operator / Source"),
    ("circle", "Circle"),
    ("activation_date", "Activation Date"),
    ("source_file", "Source File"),
)

# CGI table columns
_CGI_COLUMNS = (
    ("cgi", "CGI / Cell ID"),
    ("operator", "Operator"),
    ("technology", "Technology"),
    ("circle", "Circle"),
    ("state", "State"),
    ("district", "District"),
    ("police_station", "Police Station"),
    ("address", "Tower Address"),
    ("town", "Town"),
    ("landmark", "Landmark"),
    ("site_name", "Site Name"),
    ("latitude", "Latitude"),
    ("longitude", "Longitude"),
    ("azimuth", "Azimuth"),
    ("status", "Tower Status"),
    ("status_change_date", "Status Change Date"),
    ("mcc_mnc", "MCC-MNC"),
    ("lac", "LAC"),
    ("cid", "CID"),
    ("tac_id", "TAC"),
    ("site_id", "Site ID"),
    ("gnb_id", "gNB ID"),
    ("cell_id", "Cell ID"),
    ("source_file", "Source File"),
)

_IMPORT_FIELDS = (
    ("status", "Status"),
    ("import_type", "Detected Type"),
    ("target_table", "Target Table"),
    ("source_file", "Source File"),
    ("rows_read", "Rows Read"),
    ("valid_rows", "Valid Rows"),
    ("invalid_rows", "Invalid Rows"),
    ("duplicate_rows", "Duplicate Rows"),
    ("inserted_rows", "Inserted Rows"),
    ("updated_rows", "Updated Rows"),
    ("skipped_rows", "Skipped Rows"),
    ("before_count", "Before Count"),
    ("after_count", "After Count"),
    ("duration_seconds", "Duration Seconds"),
    ("backup_path", "Backup"),
    ("log_path", "Import Log"),
    ("message", "Message"),
)


def _display_value(value: object) -> str:
    """Convert a value to a display-friendly string."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return f"{value:,}"
    text = str(value).strip()
    return text or "-"


class LookupPage(QFrame):
    """Provide SDR, CGI and one-click master-data operations."""

    def __init__(
        self,
        parent: QWidget | None = None,
        api_client=None,
    ) -> None:
        super().__init__(parent)
        self.api_client = api_client  # Store API client for future use
        self.setObjectName("pageSurface")

        self._thread: QThread | None = None
        self._worker: LookupWorker | None = None
        self._last_results: dict[str, dict[str, Any]] = {}

        self._sdr_input = QLineEdit()
        self._sdr_input.setObjectName("inputControl")
        self._sdr_input.setPlaceholderText("Enter mobile numbers (comma separated) e.g. 9876543210, 9123456789")
        self._sdr_input.setClearButtonEnabled(True)
        self._sdr_button = QPushButton("Search SDR")
        self._sdr_button.setObjectName("primaryButton")
        self._sdr_table = self._build_sdr_table()

        self._cgi_input = QLineEdit()
        self._cgi_input.setObjectName("inputControl")
        self._cgi_input.setPlaceholderText("Enter CGI/Cell IDs (comma separated) e.g. 405-52-3347-232803094, 405-55-1234-56789012")
        self._cgi_input.setClearButtonEnabled(True)
        self._cgi_button = QPushButton("Search CGI / Cell")
        self._cgi_button.setObjectName("primaryButton")
        self._cgi_table = self._build_cgi_table()

        self._import_edit = QLineEdit()
        self._import_edit.setObjectName("inputControl")
        self._import_edit.setReadOnly(True)
        self._import_edit.setPlaceholderText("Select one SDR/CGI file or a folder containing multiple files")
        self._import_browse_button = QPushButton("Select File")
        self._import_browse_button.setObjectName("secondaryButton")
        self._import_folder_button = QPushButton("Select Folder")
        self._import_folder_button.setObjectName("secondaryButton")
        self._import_button = QPushButton("Import / Update Master Data")
        self._import_button.setObjectName("primaryButton")
        self._import_table = self._build_import_table()

        self._tabs = QTabWidget()
        self._tabs.setObjectName("lookupTabs")
        self._tabs.addTab(self._build_sdr_tab(), "SDR Number Lookup")
        self._tabs.addTab(self._build_cgi_tab(), "CGI / Cell Lookup")
        self._tabs.addTab(self._build_import_tab(), "Master Data Import")

        self._progress = QProgressBar()
        self._progress.setObjectName("analysisProgress")
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)

        self._status_label = QLabel("Ready")
        self._status_label.setObjectName("statusText")
        self._status_label.setWordWrap(True)

        self._log = QPlainTextEdit()
        self._log.setObjectName("analysisLog")
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(96)
        self._log.document().setMaximumBlockCount(300)
        self._log.setPlaceholderText("Lookup and import messages will appear here.")

        self._build_layout()

        self._sdr_button.clicked.connect(self._start_sdr_lookup)
        self._sdr_input.returnPressed.connect(self._start_sdr_lookup)
        self._cgi_button.clicked.connect(self._start_cgi_lookup)
        self._cgi_input.returnPressed.connect(self._start_cgi_lookup)
        self._import_browse_button.clicked.connect(self._browse_import_file)
        self._import_folder_button.clicked.connect(self._browse_import_folder)
        self._import_button.clicked.connect(self._start_import)

    @property
    def is_running(self) -> bool:
        """Return True while a lookup or import worker is active."""
        return self._thread is not None

    @property
    def last_results(self) -> dict[str, dict[str, Any]]:
        """Return a copy of the latest result for every operation."""
        return {key: dict(value) for key, value in self._last_results.items()}

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(16)

        heading_row = QHBoxLayout()
        heading = QLabel("Search Telecom Master Data")
        heading.setObjectName("moduleTitle")
        badge = QLabel("CASE-AUDITED LOOKUP")
        badge.setObjectName("statusBadge")
        heading_row.addWidget(heading)
        heading_row.addStretch()
        heading_row.addWidget(badge)

        description = QLabel(
            "Search subscriber and tower master data or safely import one "
            "new SDR/CGI source file. Lookup activity records only minimal "
            "query metadata in the active case audit trail."
        )
        description.setObjectName("moduleDescription")
        description.setWordWrap(True)

        layout.addLayout(heading_row)
        layout.addWidget(description)
        layout.addWidget(self._tabs, stretch=1)
        layout.addWidget(self._progress)
        layout.addWidget(self._status_label)
        layout.addWidget(self._log)

    def _build_sdr_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        note = QLabel(
            "Search one or multiple Indian mobile numbers. Multiple historical or "
            "source matches remain visible as separate rows. Separate numbers with commas."
        )
        note.setObjectName("cardText")
        note.setWordWrap(True)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._sdr_input, stretch=1)
        row.addWidget(self._sdr_button)

        caution = QLabel(
            "Subscriber identity and address must be verified against the "
            "original CAF or operator record."
        )
        caution.setObjectName("noticeText")
        caution.setWordWrap(True)

        layout.addWidget(note)
        layout.addLayout(row)
        layout.addWidget(caution)
        layout.addWidget(self._sdr_table, stretch=1)
        return tab

    def _build_cgi_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        note = QLabel(
            "Search one or multiple CGI/ECGI values. Separate with commas. "
            "Results will appear in the table below."
        )
        note.setObjectName("cardText")
        note.setWordWrap(True)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._cgi_input, stretch=1)
        row.addWidget(self._cgi_button)

        caution = QLabel(
            "Tower addresses, coordinates and azimuth are investigative "
            "leads and should be verified with current field/operator data."
        )
        caution.setObjectName("noticeText")
        caution.setWordWrap(True)

        layout.addWidget(note)
        layout.addLayout(row)
        layout.addWidget(caution)
        layout.addWidget(self._cgi_table, stretch=1)
        return tab

    def _build_import_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        note = QLabel(
            "Select one SDR or CGI master file, or a folder containing multiple files. "
            "The software detects file type, creates a backup, imports safely, "
            "and handles duplicates automatically."
        )
        note.setObjectName("cardText")
        note.setWordWrap(True)

        file_row = QHBoxLayout()
        file_row.setSpacing(10)
        file_row.addWidget(self._import_edit, stretch=1)
        file_row.addWidget(self._import_browse_button)
        file_row.addWidget(self._import_folder_button)

        action_row = QHBoxLayout()
        action_row.addWidget(self._import_button)
        action_row.addStretch()

        layout.addWidget(note)
        layout.addLayout(file_row)
        layout.addLayout(action_row)
        layout.addWidget(self._import_table, stretch=1)
        return tab

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.setObjectName("dataTable")
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setWordWrap(False)

    def _build_sdr_table(self) -> QTableWidget:
        table = QTableWidget(0, len(_SDR_COLUMNS))
        self._configure_table(table)
        table.setHorizontalHeaderLabels([label for _, label in _SDR_COLUMNS])
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setColumnWidth(0, 125)
        table.setColumnWidth(1, 170)
        table.setColumnWidth(2, 150)
        table.setColumnWidth(3, 260)
        table.setColumnWidth(4, 145)
        table.setColumnWidth(5, 160)
        table.setColumnWidth(6, 100)
        table.setColumnWidth(7, 120)
        table.setColumnWidth(8, 150)
        return table

    def _build_cgi_table(self) -> QTableWidget:
        table = QTableWidget(0, len(_CGI_COLUMNS))
        self._configure_table(table)
        table.setHorizontalHeaderLabels([label for _, label in _CGI_COLUMNS])
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setColumnWidth(0, 140)
        table.setColumnWidth(1, 100)
        table.setColumnWidth(2, 100)
        table.setColumnWidth(3, 100)
        table.setColumnWidth(4, 100)
        table.setColumnWidth(5, 100)
        table.setColumnWidth(6, 130)
        table.setColumnWidth(7, 260)
        table.setColumnWidth(8, 120)
        table.setColumnWidth(9, 120)
        table.setColumnWidth(10, 120)
        table.setColumnWidth(11, 100)
        table.setColumnWidth(12, 100)
        table.setColumnWidth(13, 90)
        table.setColumnWidth(14, 100)
        table.setColumnWidth(15, 130)
        table.setColumnWidth(16, 100)
        table.setColumnWidth(17, 90)
        table.setColumnWidth(18, 130)
        table.setColumnWidth(19, 100)
        table.setColumnWidth(20, 90)
        table.setColumnWidth(21, 120)
        table.setColumnWidth(22, 160)
        return table

    def _build_import_table(self) -> QTableWidget:
        table = QTableWidget(0, 2)
        self._configure_table(table)
        table.setHorizontalHeaderLabels(["Field", "Value"])
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        return table

    def set_sdr_query(self, value: object) -> None:
        """Set the SDR query text."""
        self._sdr_input.setText(str(value or "").strip())

    def set_cgi_query(self, value: object) -> None:
        """Set the CGI query text."""
        self._cgi_input.setText(str(value or "").strip())

    def set_import_file(self, value: str | Path) -> None:
        """Set the import file path."""
        self._import_edit.setText(str(Path(value).expanduser().resolve(strict=False)))
        self._import_edit.setProperty("isFolder", False)

    def set_import_folder(self, value: str | Path) -> None:
        """Set the import folder path."""
        self._import_edit.setText(str(Path(value).expanduser().resolve(strict=False)))
        self._import_edit.setProperty("isFolder", True)

    def refresh(self) -> None:
        """Keep the current lookup results visible when revisiting the page."""
        # No refresh logic needed yet

    def _browse_import_file(self) -> None:
        """Open file dialog to select a master data file."""
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select SDR or CGI Master Data",
            self._import_edit.text().strip(),
            ("Master Data (*.csv *.txt *.tsv *.xlsx *.xls *.xlsb);;All Files (*)"),
        )
        if selected:
            self.set_import_file(selected)

    def _browse_import_folder(self) -> None:
        """Open folder dialog to select a directory."""
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Master Data Folder",
            self._import_edit.text().strip(),
        )
        if selected:
            self.set_import_folder(selected)

    def _start_sdr_lookup(self) -> None:
        """Start SDR lookup for entered mobile numbers."""
        value = self._sdr_input.text().strip()
        if not value:
            self._show_validation("Enter at least one mobile number for SDR lookup.")
            return
        self._start_worker("sdr", value)

    def _start_cgi_lookup(self) -> None:
        """Start CGI lookup for entered CGI values."""
        value = self._cgi_input.text().strip()
        if not value:
            self._show_validation("Enter at least one CGI or Cell ID for lookup.")
            return
        self._start_worker("cgi", value)

    def _start_import(self) -> None:
        """Start master data import (single file or folder)."""
        value = self._import_edit.text().strip()
        if not value:
            self._show_validation("Select a file or folder for import.")
            return

        path = Path(value)
        if path.is_dir():
            self._start_worker("import_folder", value)
        elif path.is_file():
            if path.suffix.casefold() not in SUPPORTED_MASTER_SUFFIXES:
                self._show_validation("The selected file type is not supported.")
                return
            self._start_worker("import", value)
        else:
            self._show_validation("Selected path does not exist.")

    def _show_validation(self, message: str) -> None:
        """Show a validation warning message."""
        QMessageBox.warning(self, "Lookup Input Review", message)
        self._status_label.setText(message)

    def _start_worker(self, operation: str, value: str) -> None:
        """Start a background worker thread for the operation."""
        if self.is_running:
            return

        self._log.clear()
        labels = {
            "sdr": "SDR lookup",
            "cgi": "CGI / Cell lookup",
            "import": "master-data import",
            "import_folder": "master-data folder import",
        }
        self._append_log(f"[+] Starting {labels[operation]}.")
        self._set_running_state(True)

        thread = QThread(self)
        worker = LookupWorker(operation=operation, value=value, api_client=self.api_client)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.log.connect(self._append_log)
        worker.completed.connect(self._operation_completed)
        worker.failed.connect(self._operation_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _set_running_state(self, running: bool) -> None:
        """Enable/disable controls based on running state."""
        for control in (
            self._sdr_input,
            self._sdr_button,
            self._cgi_input,
            self._cgi_button,
            self._import_browse_button,
            self._import_folder_button,
            self._import_button,
        ):
            control.setEnabled(not running)
        self._progress.setVisible(running)
        if running:
            self._status_label.setText("Operation is running. Keep this window open.")

    def _append_log(self, message: str) -> None:
        """Append a message to the log panel."""
        text = str(message).strip()
        if text:
            self._log.appendPlainText(text)

    def _operation_completed(self, payload: object) -> None:
        """Handle operation completion."""
        value = payload if isinstance(payload, dict) else {}
        operation = str(value.get("operation", ""))
        result = value.get("result")
        result = result if isinstance(result, dict) else {}
        self._last_results[operation] = dict(result)

        if operation == "sdr":
            self._display_sdr_result(result)
        elif operation == "cgi":
            self._display_cgi_result(result)
        elif operation in {"import", "import_folder"}:
            self._display_import_result(result)
        else:
            self._operation_failed("Unknown lookup result type.")

    def _display_sdr_result(self, result: dict[str, Any]) -> None:
        """Display SDR lookup results in the table."""
        status = str(result.get("status", ""))
        records = result.get("records", [])
        if not isinstance(records, list):
            records = []

        valid_records = []
        for record in records:
            if not isinstance(record, dict):
                continue
            rec = {k: v for k, v in record.items() if k != "__status"}
            valid_records.append(rec)

        self._sdr_table.setRowCount(len(valid_records))
        for row, record in enumerate(valid_records):
            for column, (key, _) in enumerate(_SDR_COLUMNS):
                self._set_item(
                    self._sdr_table,
                    row,
                    column,
                    _display_value(record.get(key)),
                )

        if valid_records:
            self._status_label.setText(
                f"SDR lookup completed | Records shown: {len(valid_records)}"
            )
            self._append_log(f"[+] SDR lookup returned {len(valid_records)} result(s).")
        else:
            self._show_lookup_status("SDR", status, result)

    def _display_cgi_result(self, result: dict[str, Any]) -> None:
        """Display CGI lookup results in the table."""
        status = str(result.get("status", ""))
        records = result.get("records", [])
        if not isinstance(records, list):
            records = []

        valid_records = []
        for record in records:
            if not isinstance(record, dict):
                continue
            rec = {k: v for k, v in record.items() if k != "__status"}
            valid_records.append(rec)

        self._cgi_table.setRowCount(len(valid_records))
        for row, record in enumerate(valid_records):
            for column, (key, _) in enumerate(_CGI_COLUMNS):
                self._set_item(
                    self._cgi_table,
                    row,
                    column,
                    _display_value(record.get(key)),
                )

        if valid_records:
            self._status_label.setText(
                f"CGI / Cell lookup completed | Records shown: {len(valid_records)}"
            )
            self._append_log(f"[+] CGI lookup returned {len(valid_records)} result(s).")
        else:
            self._show_lookup_status("CGI / Cell", status, result)

    def _show_lookup_status(
        self,
        label: str,
        status: str,
        result: dict[str, Any],
    ) -> None:
        """Show a status message for NOT_FOUND or error cases."""
        message = str(result.get("message", "")).strip()
        if status == NOT_FOUND:
            text = message or f"{label} record was not found."
        elif status == INVALID_INPUT:
            text = message or f"Enter a valid {label} value."
        elif status == DATABASE_ERROR:
            detail = str(result.get("error", "")).strip()
            text = f"{label} database lookup failed. {detail}".strip()
        else:
            text = message or f"{label} lookup returned an unknown status."
        self._status_label.setText(text)
        self._append_log(f"[!] {text}")

    def _display_import_result(self, result: dict[str, Any]) -> None:
        """Display import result in the key-value table."""
        self._populate_key_value_table(
            self._import_table,
            result,
            _IMPORT_FIELDS,
        )
        status = str(result.get("status", "")).strip().upper()
        message = str(result.get("message", "")).strip()

        if status == "SUCCESS":
            self._status_label.setText("Master data import completed successfully.")
            self._append_log("[+] Master data import completed successfully.")
        elif status.startswith("SKIPPED"):
            self._status_label.setText(
                message or "Master data import was safely skipped."
            )
            self._append_log("[=] Master data import was safely skipped.")
        else:
            self._status_label.setText(message or "Master data import failed.")
            self._append_log("[-] Master data import failed.")

    @staticmethod
    def _set_item(
        table: QTableWidget,
        row: int,
        column: int,
        text: str,
    ) -> None:
        """Set a cell item in a QTableWidget."""
        item = QTableWidgetItem(text)
        item.setToolTip(text)
        table.setItem(row, column, item)

    def _populate_key_value_table(
        self,
        table: QTableWidget,
        record: dict[str, Any],
        fields: tuple[tuple[str, str], ...],
    ) -> None:
        """Fill a key-value table with fields from a record."""
        table.setRowCount(len(fields))
        for row, (key, label) in enumerate(fields):
            self._set_item(table, row, 0, label)
            self._set_item(
                table,
                row,
                1,
                _display_value(record.get(key)),
            )

    def _operation_failed(self, message: str) -> None:
        """Handle operation failure."""
        text = str(message).strip()
        self._status_label.setText("Lookup operation failed. Review the activity log.")
        self._append_log(f"[-] {text}")

    def _thread_finished(self) -> None:
        """Clean up after worker thread finishes."""
        self._thread = None
        self._worker = None
        self._set_running_state(False)