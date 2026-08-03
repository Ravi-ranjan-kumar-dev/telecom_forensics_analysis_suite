"""Tower Dump analysis page for the desktop GUI."""

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

from gui.workers.tower_dump_worker import TowerDumpWorker
from modules.controllers.tower_dump_controller import (
    TOWER_DUMP_SOURCE_SUFFIXES,
    TOWER_DUMP_SOURCE_TYPES,
)
from modules.core.paths import PROJECT_ROOT


_MODE_LABELS = {
    "cdr": "Tower CDR Dump Analysis",
    "gprs": "Tower GPRS Dump Analysis",
    "ipdr": "Tower IPDR Dump Analysis",
}

_MODE_HELP = {
    "cdr": (
        "Select a folder containing Tower CDR files from supported "
        "operators. Files inside Spot subfolders are included."
    ),
    "gprs": (
        "Select a folder containing Airtel Tower GPRS session-dump "
        "files. Files inside Spot subfolders are included."
    ),
    "ipdr": (
        "Select a folder containing Jio CELL ID_IPDRNAT files. "
        "The scalable DuckDB complete-analysis workflow will run."
    ),
}


class TowerDumpPage(QFrame):
    """Provide complete Tower CDR, GPRS and IPDR analysis controls."""

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
            source_type: ""
            for source_type in TOWER_DUMP_SOURCE_TYPES
        }
        self._report_paths_by_source: dict[
            str,
            list[str],
        ] = {
            source_type: []
            for source_type in TOWER_DUMP_SOURCE_TYPES
        }
        self._thread: QThread | None = None
        self._worker: TowerDumpWorker | None = None

        self._mode_box = QComboBox()
        self._mode_box.setObjectName(
            "inputControl"
        )

        for source_type in TOWER_DUMP_SOURCE_TYPES:
            self._mode_box.addItem(
                _MODE_LABELS[
                    source_type
                ],
                source_type,
            )

        self._folder_edit = QLineEdit()
        self._folder_edit.setObjectName(
            "inputControl"
        )
        self._folder_edit.setReadOnly(
            True
        )
        self._folder_edit.setPlaceholderText(
            "Select a folder containing Tower Dump evidence"
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

        self._run_button = QPushButton(
            "Run Complete Analysis"
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
            2000
        )
        self._log.setPlaceholderText(
            "Tower Dump analysis progress will appear here."
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
        """Return the active Tower Dump source type."""

        return str(
            self._mode_box.currentData()
            or ""
        )

    @property
    def selected_folder(
        self,
    ) -> str:
        """Return the selected evidence folder for the active source."""

        return self._selected_folders.get(
            self.selected_mode,
            "",
        )

    @property
    def is_running(
        self,
    ) -> bool:
        """Return True while a worker thread is active."""

        return self._thread is not None

    @property
    def report_paths(
        self,
    ) -> tuple[str, ...]:
        """Return generated reports for the active source type."""

        return tuple(
            self._report_paths_by_source.get(
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
            "Run Tower Dump Analysis"
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
            "Select Tower CDR, GPRS or IPDR evidence, run the existing "
            "case-aware backend in the background, and open the generated "
            "investigator report. Source files remain unchanged."
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
            "Tower Dump Type"
        )
        mode_label.setObjectName(
            "fieldLabel"
        )

        folder_label = QLabel(
            "Evidence Folder"
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
        source_type: str,
    ) -> None:
        """Select one Tower Dump source type."""

        normalized_source = str(
            source_type
        ).strip().casefold()

        for index in range(
            self._mode_box.count()
        ):
            if (
                self._mode_box.itemData(
                    index
                )
                == normalized_source
            ):
                self._mode_box.setCurrentIndex(
                    index
                )
                return

        raise ValueError(
            f"Unsupported Tower Dump source type: {source_type}"
        )

    def set_selected_folder(
        self,
        folder: str | Path,
    ) -> None:
        """Set the evidence folder for the active source type."""

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
            return "Select an evidence folder before running analysis."

        folder = Path(
            folder_text
        )

        if not folder.is_dir():
            return "The selected evidence folder does not exist."

        files = self._evidence_files(
            folder,
            self.selected_mode,
        )

        if files:
            return ""

        suffixes = ", ".join(
            sorted(
                TOWER_DUMP_SOURCE_SUFFIXES[
                    self.selected_mode
                ]
            )
        )
        return (
            "No supported evidence files were found for "
            f"{_MODE_LABELS[self.selected_mode]}. Expected: {suffixes}."
        )

    def _mode_changed(
        self,
    ) -> None:
        source_type = self.selected_mode

        self._folder_edit.setText(
            self._selected_folders.get(
                source_type,
                "",
            )
        )
        self._helper_label.setText(
            _MODE_HELP[
                source_type
            ]
        )
        self._open_report_button.setEnabled(
            bool(
                self.report_paths
            )
        )

        if self.selected_folder:
            self._update_folder_summary()
        else:
            self._status_label.setText(
                "Ready"
            )

    def _default_folder(
        self,
    ) -> Path:
        return (
            PROJECT_ROOT
            / "data"
            / "tower_dump"
            / self.selected_mode
            / "input"
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
            "Select Tower Dump Evidence Folder",
            str(
                start_folder
            ),
        )

        if selected:
            self.set_selected_folder(
                selected
            )

    @staticmethod
    def _evidence_files(
        folder: Path,
        source_type: str,
    ) -> list[Path]:
        suffixes = TOWER_DUMP_SOURCE_SUFFIXES[
            source_type
        ]

        return sorted(
            path
            for path in folder.rglob(
                "*"
            )
            if (
                path.is_file()
                and path.suffix.casefold()
                in suffixes
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
            self._evidence_files(
                folder,
                self.selected_mode,
            )
        )
        self._status_label.setText(
            f"Selected folder contains {file_count} supported file(s)."
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
                "Tower Dump Input Review",
                error,
            )
            self._status_label.setText(
                error
            )
            return

        source_type = self.selected_mode
        self._report_paths_by_source[
            source_type
        ] = []
        self._open_report_button.setEnabled(
            False
        )
        self._log.clear()
        self._append_log(
            f"[+] Starting {_MODE_LABELS[source_type]}."
        )
        self._set_running_state(
            True
        )

        thread = QThread(
            self
        )
        worker = TowerDumpWorker(
            source_type=source_type,
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
        source_type = str(
            result.get(
                "source_type",
                self.selected_mode,
            )
        )

        if source_type not in TOWER_DUMP_SOURCE_TYPES:
            source_type = self.selected_mode

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
        self._report_paths_by_source[
            source_type
        ] = paths
        self._open_report_button.setEnabled(
            bool(
                self.report_paths
            )
        )

        if paths:
            self._status_label.setText(
                "Analysis completed. The investigator report is ready."
            )
            self._append_log(
                "[+] Analysis completed successfully."
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
            "Analysis failed. Review the progress log."
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
