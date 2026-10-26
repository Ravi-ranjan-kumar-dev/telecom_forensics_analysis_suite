"""Subscriber IPDR analysis page for the desktop GUI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.workers.ipdr_worker import IpdrWorker
from modules.controllers.ipdr_case_controller import (
    IPDR_ANALYSIS_MODES,
    SUPPORTED_SUFFIXES,
)
from modules.core.paths import PROJECT_ROOT


_MODE_LABELS = {
    "single": "Single Subscriber",
    "multiple": "Multiple Subscribers",
}

_MODE_HELP = {
    "single": (
        "Select a folder for one subscriber or IPDR query. Related "
        "request and result files may remain together."
    ),
    "multiple": (
        "Select a folder containing two or more subscriber or IPDR "
        "query reports for combined analysis."
    ),
}


class IpdrPage(QFrame):
    """Provide Single and Multiple subscriber IPDR controls."""

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent
        )

        self.setObjectName(
            "pageSurface"
        )

        self._selected_folders = {
            mode: ""
            for mode in IPDR_ANALYSIS_MODES
        }
        self._report_paths_by_mode: dict[
            str,
            list[str],
        ] = {
            mode: []
            for mode in IPDR_ANALYSIS_MODES
        }
        self._thread: QThread | None = None
        self._worker: IpdrWorker | None = None

        self._mode_box = QComboBox()
        self._mode_box.setObjectName(
            "inputControl"
        )

        for mode in IPDR_ANALYSIS_MODES:
            self._mode_box.addItem(
                _MODE_LABELS[
                    mode
                ],
                mode,
            )

        self._folder_edit = QLineEdit()
        self._folder_edit.setObjectName(
            "inputControl"
        )
        self._folder_edit.setReadOnly(
            False
        )
        self._folder_edit.editingFinished.connect(lambda: self.set_selected_folder(self._folder_edit.text().strip()) if self._folder_edit.text().strip() else None)
        self._folder_edit.setPlaceholderText(
            "Select a folder containing subscriber IPDR evidence"
        )

        self._browse_button = QPushButton(
            "Select Folder"
        )
        self._browse_button.setObjectName(
            "secondaryButton"
        )

        self._browse_files_button = QPushButton(
            "Select File(s)"
        )
        self._browse_files_button.setObjectName(
            "secondaryButton"
        )
        self._browse_files_button.clicked.connect(
            self._browse_files_anywhere
        )

        self._helper_label = QLabel()
        self._helper_label.setObjectName(
            "cardText"
        )
        self._helper_label.setWordWrap(
            True
        )

        self._separation_note = QLabel(
            "CELL ID_IPDRNAT tower folders belong in Tower Dump "
            "Analysis, not in this subscriber IPDR screen."
        )
        self._separation_note.setObjectName(
            "cardText"
        )
        self._separation_note.setWordWrap(
            True
        )

        self._run_button = QPushButton(
            "Start Analysis"
        )
        self._run_button.setObjectName(
            "primaryButton"
        )

        self._open_report_button = QPushButton(
            "Open Latest Report"
        )
        self._open_report_button.setObjectName(
            "secondaryButton"
        )
        self._open_report_button.setEnabled(
            False
        )

        self._progress = QProgressBar()
        self._progress.setObjectName(
            "analysisProgress"
        )
        self._progress.setRange(
            0,
            0,
        )
        self._progress.setVisible(
            False
        )

        self._status_label = QLabel(
            "Ready"
        )
        self._status_label.setObjectName(
            "statusText"
        )
        self._status_label.setWordWrap(
            True
        )

        self._log = QPlainTextEdit()
        self._log.setObjectName(
            "analysisLog"
        )
        self._log.setReadOnly(
            True
        )
        self._log.document().setMaximumBlockCount(
            1800
        )
        self._log.setPlaceholderText(
            "IPDR analysis progress will appear here."
        )

        self._build_layout()

        self._mode_box.currentIndexChanged.connect(
            self._mode_changed
        )
        self._browse_button.clicked.connect(
            self._browse_folder
        )
        self._run_button.clicked.connect(
            self._start_analysis
        )
        self._open_report_button.clicked.connect(
            self._open_latest_report
        )

        self._mode_changed()

    @property
    def selected_mode(
        self,
    ) -> str:
        """Return the selected subscriber IPDR mode."""

        return str(
            self._mode_box.currentData()
            or ""
        )

    @property
    def selected_folder(
        self,
    ) -> str:
        """Return the selected evidence folder for the active mode."""

        return self._selected_folders.get(
            self.selected_mode,
            "",
        )

    @property
    def is_running(
        self,
    ) -> bool:
        """Return True while an IPDR worker is active."""

        return self._thread is not None

    @property
    def report_paths(
        self,
    ) -> tuple[str, ...]:
        """Return generated reports for the active mode."""

        return tuple(
            self._report_paths_by_mode.get(
                self.selected_mode,
                [],
            )
        )

    def _build_layout(
        self,
    ) -> None:
        layout = QVBoxLayout(
            self
        )
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(12)

        controls = QFrame()
        controls.setObjectName(
            "infoCard"
        )

        controls_layout = QVBoxLayout(
            controls
        )
        controls_layout.setContentsMargins(
            22,
            20,
            22,
            20,
        )
        controls_layout.setSpacing(
            14
        )

        mode_label = QLabel(
            "Analysis Type"
        )
        mode_label.setObjectName(
            "fieldLabel"
        )

        folder_label = QLabel(
            "Subscriber IPDR Evidence Folder"
        )
        folder_label.setObjectName(
            "fieldLabel"
        )

        folder_row = QHBoxLayout()
        folder_row.setSpacing(
            10
        )
        folder_row.addWidget(
            self._folder_edit,
            stretch=1,
        )
        folder_row.addWidget(
            self._browse_button
        )
        folder_row.addWidget(
            self._browse_files_button
        )

        action_row = QHBoxLayout()
        action_row.setSpacing(
            10
        )
        action_row.addWidget(
            self._run_button
        )
        action_row.addWidget(
            self._open_report_button
        )
        action_row.addStretch()

        controls_layout.addWidget(
            mode_label
        )
        controls_layout.addWidget(
            self._mode_box
        )
        controls_layout.addWidget(
            folder_label
        )
        controls_layout.addLayout(
            folder_row
        )
        # Contextual file-type warnings are handled by validation.
        controls_layout.addLayout(
            action_row
        )
        controls_layout.addWidget(
            self._progress
        )
        controls_layout.addWidget(
            self._status_label
        )

        log_card = QFrame()
        log_card.setObjectName(
            "infoCard"
        )

        log_layout = QVBoxLayout(
            log_card
        )
        log_layout.setContentsMargins(
            22,
            18,
            22,
            20,
        )
        log_layout.setSpacing(
            10
        )

        log_heading = QLabel(
            "Live Progress"
        )
        log_heading.setObjectName(
            "cardHeading"
        )

        log_layout.addWidget(
            log_heading
        )
        log_layout.addWidget(
            self._log,
            stretch=1,
        )

        # The active analysis module is highlighted in the sidebar.
        # Do not repeat its heading, backend badge, or instruction paragraph.
        layout.addWidget(
            controls
        )
        layout.addWidget(
            log_card,
            stretch=1,
        )

    def set_mode(
        self,
        mode: str,
    ) -> None:
        """Select one subscriber IPDR analysis mode."""

        normalized = str(
            mode
        ).strip().casefold()

        for index in range(
            self._mode_box.count()
        ):
            if (
                self._mode_box.itemData(
                    index
                )
                == normalized
            ):
                self._mode_box.setCurrentIndex(
                    index
                )
                return

        raise ValueError(
            f"Unsupported IPDR mode: {mode}"
        )

    def set_selected_folder(
        self,
        folder: str | Path,
    ) -> None:
        """Set the current subscriber IPDR evidence folder."""

        path = Path(
            folder
        ).expanduser().resolve(
            strict=False
        )

        self._selected_folders[
            self.selected_mode
        ] = str(
            path
        )
        self._folder_edit.setText(
            str(
                path
            )
        )
        self._update_folder_summary()

    def validation_error(
        self,
    ) -> str:
        """Return an investigator-friendly input validation message."""

        folder_text = self.selected_folder

        if not folder_text:
            return "Select an IPDR evidence folder before running analysis."

        folder = Path(
            folder_text
        )

        if not folder.is_dir():
            return "The selected IPDR evidence folder does not exist."

        files = self._supported_files(
            folder
        )

        if not files:
            suffixes = ", ".join(
                sorted(
                    SUPPORTED_SUFFIXES
                )
            )
            return (
                "No supported subscriber IPDR files were found. "
                f"Supported types: {suffixes}."
            )

        if (
            self.selected_mode == "multiple"
            and len(
                files
            ) < 2
        ):
            return (
                "Multiple IPDR Analysis requires at least two supported "
                f"files. Found: {len(files)}."
            )

        return ""

    def _mode_changed(
        self,
    ) -> None:
        mode = self.selected_mode

        self._folder_edit.setText(
            self._selected_folders.get(
                mode,
                "",
            )
        )
        self._helper_label.setText(
            _MODE_HELP.get(
                mode,
                "Select a subscriber IPDR evidence folder.",
            )
            + " Supported files: CSV, TXT, XLSX and XLS."
        )
        self._open_report_button.setEnabled(
            bool(
                self.report_paths
            )
        )
        self._status_label.setText(
            "Ready"
        )
        self._update_folder_summary()

    def _default_folder(
        self,
    ) -> Path:
        return (
            PROJECT_ROOT
            / "data"
            / "ipdr"
            / self.selected_mode
        )

    def _browse_folder(
        self,
    ) -> None:
        start_folder = (
            Path(
                self.selected_folder
            )
            if self.selected_folder
            else self._default_folder()
        )

        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Subscriber IPDR Evidence Folder",
            str(
                start_folder
            ),
        )

        if selected:
            self.set_selected_folder(
                selected
            )

    @staticmethod
    def _supported_files(
        folder: Path,
    ) -> list[Path]:
        return sorted(
            path
            for path in folder.rglob(
                "*"
            )
            if (
                path.is_file()
                and path.suffix.casefold()
                in SUPPORTED_SUFFIXES
            )
        )

    def _update_folder_summary(
        self,
    ) -> None:
        folder_text = self.selected_folder

        if not folder_text:
            return

        folder = Path(
            folder_text
        )

        if not folder.is_dir():
            self._status_label.setText(
                "Selected folder is not available."
            )
            return

        file_count = len(
            self._supported_files(
                folder
            )
        )
        self._status_label.setText(
            "Selected folder contains "
            f"{file_count} supported IPDR file(s)."
        )

    def _start_analysis(
        self,
    ) -> None:
        if self.is_running:
            return

        error = self.validation_error()

        if error:
            QMessageBox.warning(
                self,
                "IPDR Input Review",
                error,
            )
            self._status_label.setText(
                error
            )
            return

        mode = self.selected_mode
        self._report_paths_by_mode[
            mode
        ] = []
        self._open_report_button.setEnabled(
            False
        )
        self._log.clear()
        self._append_log(
            "[+] Starting subscriber IPDR analysis."
        )
        self._set_running_state(
            True
        )

        thread = QThread(
            self
        )
        worker = IpdrWorker(
            mode=mode,
            input_folder=self.selected_folder,
        )

        worker.moveToThread(
            thread
        )
        thread.started.connect(
            worker.run
        )
        worker.log.connect(
            self._append_log
        )
        worker.completed.connect(
            self._analysis_completed
        )
        worker.failed.connect(
            self._analysis_failed
        )
        worker.finished.connect(
            thread.quit
        )
        worker.finished.connect(
            worker.deleteLater
        )
        thread.finished.connect(
            thread.deleteLater
        )
        thread.finished.connect(
            self._thread_finished
        )

        self._thread = thread
        self._worker = worker

        thread.start()

    def _set_running_state(
        self,
        running: bool,
    ) -> None:
        self._mode_box.setEnabled(
            not running
        )
        self._browse_button.setEnabled(
            not running
        )
        self._run_button.setEnabled(
            not running
        )
        self._progress.setVisible(
            running
        )

        if running:
            self._status_label.setText(
                "Analysis is running. Keep this window open."
            )

    def _append_log(
        self,
        message: str,
    ) -> None:
        text = str(
            message
        ).strip()

        if text:
            self._log.appendPlainText(
                text
            )

    def _analysis_completed(
        self,
        payload: object,
    ) -> None:
        result = (
            payload
            if isinstance(
                payload,
                dict,
            )
            else {}
        )
        gui_sheets = result.get("gui_sheets")
        if isinstance(gui_sheets, dict) and gui_sheets:
            self._data_viewer_panel.load_dataframe(gui_sheets)
            if hasattr(self, '_workspace_tabs'):
                self._workspace_tabs.setCurrentIndex(1)
            self._append_log(f"[+] Loaded {len(gui_sheets)} analyzed table(s) into Interactive GUI Viewer.")
        mode = str(
            result.get(
                "mode",
                self.selected_mode,
            )
        )
        paths = [
            str(
                path
            )
            for path in result.get(
                "report_paths",
                [],
            )
            if str(
                path
            ).strip()
        ]
        self._report_paths_by_mode[
            mode
        ] = paths
        self._open_report_button.setEnabled(
            bool(
                self.report_paths
            )
        )

        if paths:
            self._status_label.setText(
                "IPDR analysis completed and the report is ready."
            )
            self._append_log(
                "[+] IPDR analysis completed successfully."
            )

            for report_path in paths:
                self._append_log(
                    f"[+] Report: {report_path}"
                )
        else:
            self._status_label.setText(
                "Analysis completed, but no report path was returned."
            )
            self._append_log(
                "[!] No generated report path was returned."
            )

    def _analysis_failed(
        self,
        message: str,
    ) -> None:
        text = str(
            message
        ).strip()
        self._status_label.setText(
            "IPDR analysis failed. Review the progress log."
        )
        self._append_log(
            f"[-] {text}"
        )

    def _thread_finished(
        self,
    ) -> None:
        self._thread = None
        self._worker = None
        self._set_running_state(
            False
        )

    def _open_latest_report(
        self,
    ) -> None:
        if not self.report_paths:
            return

        report_path = Path(
            self.report_paths[
                0
            ]
        )

        if not report_path.is_file():
            QMessageBox.warning(
                self,
                "Report Not Found",
                f"The report file is not available:\n{report_path}",
            )
            return

        opened = QDesktopServices.openUrl(
            QUrl.fromLocalFile(
                str(
                    report_path
                )
            )
        )

        if not opened:
            QMessageBox.warning(
                self,
                "Open Report",
                "The operating system could not open the report.",
            )

    def _browse_files_anywhere(
        self,
    ) -> None:
        from modules.core.flexible_input import stage_selected_files_as_folder
        start_dir = Path(self.selected_folder) if self.selected_folder and Path(self.selected_folder).exists() else Path.home()
        if start_dir.is_file():
            start_dir = start_dir.parent
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Evidence File(s) from Anywhere on Computer",
            str(start_dir),
            "IPDR Files (*.csv *.txt *.xlsx *.xls);;All Files (*)",
        )
        if not files:
            return
        try:
            staged_folder = stage_selected_files_as_folder(
                files,
                workflow="ipdr",
            )
            self.set_selected_folder(staged_folder)
        except Exception as error:
            # EA_HANDLED_DIAGNOSTICS_V1
            try:
                from modules.core.diagnostic_events import record_handled_exception as _ea_record_handled_exception
                _ea_record_handled_exception()
            except Exception:
                pass
            QMessageBox.warning(
                self,
                "File Selection Error",
                str(error),
            )


# === FULLSCREEN_COMPLETION_HOOK ===
_ORIG_IpdrPage_COMPLETED = IpdrPage._analysis_completed


def _enhanced_IpdrPage_completed(self, payload: object) -> None:
    from gui.utils.thread_dispatcher import _is_main_thread, run_on_main_thread
    if not _is_main_thread():
        run_on_main_thread(lambda p=payload: _enhanced_IpdrPage_completed(self, p))
        return
    from pathlib import Path as _Path
    from modules.reporting.gui_result_store import get_latest_gui_meta, get_latest_gui_sheets
    from gui.dialogs.fullscreen_results_window import open_fullscreen_results_window

    result = payload if isinstance(payload, dict) else {}
    sheets = result.get("gui_sheets") if isinstance(result.get("gui_sheets"), dict) and result.get("gui_sheets") else get_latest_gui_sheets()
    meta = get_latest_gui_meta()
    win_title = str(meta.get("title") or "IPDR Analysis Results")

    report_paths = [
        _Path(p) for p in (result.get("report_paths") or []) if p
    ]

    if report_paths:
        _ORIG_IpdrPage_COMPLETED(self, payload)
        if sheets:
            open_fullscreen_results_window(self, sheets, title=win_title)
        return

    if sheets:
        if hasattr(self, "_set_running_state"):
            self._set_running_state(False)
        if hasattr(self, "_open_report_button"):
            self._open_report_button.setEnabled(True)
            self._open_report_button.setText("Open Analyzed Results (Full Screen)")
        if hasattr(self, "_summary_label"):
            total_rows = sum(len(df) for df in sheets.values())
            self._summary_label.setText(
                f"Loaded {len(sheets)} analyzed table(s) ({total_rows:,} total rows) in Interactive GUI Viewer."
            )
        if hasattr(self, "_append_log"):
            self._append_log(
                f"[+] Analysis complete: {len(sheets)} table(s) ready. Opening Full-Screen Interactive Viewer..."
            )
        open_fullscreen_results_window(self, sheets, title=win_title)
        return

    _ORIG_IpdrPage_COMPLETED(self, payload)


IpdrPage._analysis_completed = _enhanced_IpdrPage_completed

if hasattr(IpdrPage, "_open_latest_report"):
    _ORIG_IpdrPage_OPEN_REPORT = IpdrPage._open_latest_report

    def _enhanced_IpdrPage_open_report(self) -> None:
        from modules.reporting.gui_result_store import get_latest_gui_meta, get_latest_gui_sheets
        from gui.dialogs.fullscreen_results_window import open_fullscreen_results_window

        sheets = get_latest_gui_sheets()
        if sheets and not getattr(self, "_latest_report_paths", None):
            meta = get_latest_gui_meta()
            open_fullscreen_results_window(
                self,
                sheets,
                title=str(meta.get("title") or "IPDR Analysis Results"),
            )
            return
        _ORIG_IpdrPage_OPEN_REPORT(self)

    IpdrPage._open_latest_report = _enhanced_IpdrPage_open_report
