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
    "single": "Single Subscriber IPDR Analysis",
    "multiple": "Multiple Subscriber IPDR Analysis",
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
            True
        )
        self._folder_edit.setPlaceholderText(
            "Select a folder containing subscriber IPDR evidence"
        )

        self._browse_button = QPushButton(
            "Select Folder"
        )
        self._browse_button.setObjectName(
            "secondaryButton"
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
            "Run IPDR Analysis"
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
        layout.setContentsMargins(
            30,
            28,
            30,
            28,
        )
        layout.setSpacing(
            18
        )

        title_row = QHBoxLayout()
        title_row.setSpacing(
            12
        )

        title = QLabel(
            "Run Subscriber IPDR Analysis"
        )
        title.setObjectName(
            "moduleTitle"
        )

        badge = QLabel(
            "BACKEND CONNECTED"
        )
        badge.setObjectName(
            "statusBadge"
        )

        title_row.addWidget(
            title
        )
        title_row.addStretch()
        title_row.addWidget(
            badge
        )

        description = QLabel(
            "Select subscriber IPDR evidence, run the existing "
            "case-aware workflow in the background, and open the "
            "generated investigator report. Source files remain unchanged."
        )
        description.setObjectName(
            "moduleDescription"
        )
        description.setWordWrap(
            True
        )

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
        controls_layout.addWidget(
            self._helper_label
        )
        controls_layout.addWidget(
            self._separation_note
        )
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

        layout.addLayout(
            title_row
        )
        layout.addWidget(
            description
        )
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
