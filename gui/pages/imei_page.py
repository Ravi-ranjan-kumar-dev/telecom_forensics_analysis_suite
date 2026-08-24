"""Automatic IMEI and device analysis page for the desktop GUI."""

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

from gui.workers.imei_worker import ImeiWorker
from modules.controllers.imei_device_controller import (
    resolve_imei_cdr_input_folder,
    resolve_imei_gprs_input_folder,
    resolve_imei_ipdr_input_folder,
    resolve_imei_unified_input_folder,
)
from modules.loader.imei_evidence_loader import (
    SUPPORTED_SUFFIXES as IMEI_EVIDENCE_SUFFIXES,
)

IMEI_MODES = (
    "cdr",
    "ipdr",
    "gprs",
    "unified",
)

_MODE_LABELS = {
    "cdr": "IMEI CDR Analysis",
    "ipdr": "IMEI IPDR Analysis",
    "gprs": "IMEI GPRS Analysis",
    "unified": "Unified IMEI Analysis",
}

_MODE_HELP = {
    "cdr": (
        "Select the folder containing dedicated IMEI CDR reports. "
        "One analysis is created for every report-query identifier."
    ),
    "ipdr": (
        "Select the folder containing dedicated IMEI IPDR reports. "
        "Multiple detected identifiers also receive a common report."
    ),
    "gprs": (
        "Select the folder containing dedicated IMEI GPRS reports. "
        "Each detected report-query identifier is analyzed separately."
    ),
    "unified": (
        "Select the root folder containing CDR, IPDR and GPRS IMEI "
        "evidence. The sources remain separate in the combined review."
    ),
}


def _default_folder(mode: str) -> Path:
    resolvers = {
        "cdr": resolve_imei_cdr_input_folder,
        "ipdr": resolve_imei_ipdr_input_folder,
        "gprs": resolve_imei_gprs_input_folder,
        "unified": resolve_imei_unified_input_folder,
    }
    return resolvers[mode]("DEV-WORKSPACE")


class ImeiPage(QFrame):
    """Provide automatic CDR, IPDR, GPRS and unified IMEI controls."""

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageSurface")

        self._selected_folders = {
            mode: str(_default_folder(mode)) for mode in IMEI_MODES
        }
        self._report_paths_by_mode: dict[str, list[str]] = {
            mode: [] for mode in IMEI_MODES
        }
        self._identifiers_by_mode: dict[str, list[str]] = {
            mode: [] for mode in IMEI_MODES
        }
        self._thread: QThread | None = None
        self._worker: ImeiWorker | None = None

        self._mode_box = QComboBox()
        self._mode_box.setObjectName("inputControl")
        for mode in IMEI_MODES:
            self._mode_box.addItem(_MODE_LABELS[mode], mode)

        self._folder_edit = QLineEdit()
        self._folder_edit.setObjectName("inputControl")
        self._folder_edit.setReadOnly(True)
        self._folder_edit.setPlaceholderText(
            "Select a folder containing dedicated IMEI evidence"
        )

        self._browse_button = QPushButton("Select Folder")
        self._browse_button.setObjectName("secondaryButton")

        self._helper_label = QLabel()
        self._helper_label.setObjectName("cardText")
        self._helper_label.setWordWrap(True)

        self._automatic_note = QLabel(
            "Report-query identifiers are read automatically from evidence "
            "headers; no manual IMEI entry is required."
        )
        self._automatic_note.setObjectName("noticeText")
        self._automatic_note.setWordWrap(True)

        self._run_button = QPushButton("Run Automatic IMEI Analysis")
        self._run_button.setObjectName("primaryButton")

        self._open_report_button = QPushButton("Open Latest Report")
        self._open_report_button.setObjectName("secondaryButton")
        self._open_report_button.setEnabled(False)

        self._open_folder_button = QPushButton("Open Report Folder")
        self._open_folder_button.setObjectName("secondaryButton")
        self._open_folder_button.setEnabled(False)

        self._progress = QProgressBar()
        self._progress.setObjectName("analysisProgress")
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)

        self._status_label = QLabel("Ready")
        self._status_label.setObjectName("statusText")
        self._status_label.setWordWrap(True)

        self._identifier_label = QLabel(
            "Detected identifiers will appear after analysis."
        )
        self._identifier_label.setObjectName("cardText")
        self._identifier_label.setWordWrap(True)

        self._log = QPlainTextEdit()
        self._log.setObjectName("analysisLog")
        self._log.setReadOnly(True)
        self._log.document().setMaximumBlockCount(2200)
        self._log.setPlaceholderText(
            "IMEI detection and analysis progress will appear here."
        )

        self._build_layout()

        self._mode_box.currentIndexChanged.connect(self._mode_changed)
        self._browse_button.clicked.connect(self._browse_folder)
        self._run_button.clicked.connect(self._start_analysis)
        self._open_report_button.clicked.connect(self._open_latest_report)
        self._open_folder_button.clicked.connect(self._open_report_folder)

        self._mode_changed()

    @property
    def selected_mode(self) -> str:
        """Return the selected IMEI analysis mode."""

        return str(self._mode_box.currentData() or "")

    @property
    def selected_folder(self) -> str:
        """Return the selected evidence folder for the active mode."""

        return self._selected_folders.get(self.selected_mode, "")

    @property
    def is_running(self) -> bool:
        """Return True while an IMEI worker is active."""

        return self._thread is not None

    @property
    def report_paths(self) -> tuple[str, ...]:
        """Return generated report paths for the active mode."""

        return tuple(self._report_paths_by_mode.get(self.selected_mode, []))

    @property
    def detected_identifiers(self) -> tuple[str, ...]:
        """Return detected report-query identifiers for the active mode."""

        return tuple(self._identifiers_by_mode.get(self.selected_mode, []))

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(18)

        heading_row = QHBoxLayout()
        heading = QLabel("Run IMEI / Device Analysis")
        heading.setObjectName("moduleTitle")
        badge = QLabel("AUTOMATIC DETECTION")
        badge.setObjectName("statusBadge")
        heading_row.addWidget(heading)
        heading_row.addStretch()
        heading_row.addWidget(badge)

        description = QLabel(
            "Select dedicated IMEI evidence, let the software detect every "
            "query identifier, and create the required single-device and "
            "cross-device investigator reports."
        )
        description.setObjectName("moduleDescription")
        description.setWordWrap(True)

        controls = QFrame()
        controls.setObjectName("infoCard")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(20, 16, 20, 16)
        controls_layout.setSpacing(8)

        mode_label = QLabel("Analysis Type")
        mode_label.setObjectName("fieldLabel")
        mode_label.setFixedWidth(175)
        folder_label = QLabel("IMEI Evidence Folder")
        folder_label.setObjectName("fieldLabel")
        folder_label.setFixedWidth(175)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        mode_row.addWidget(mode_label)
        mode_row.addWidget(self._mode_box, stretch=1)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(10)
        folder_row.addWidget(folder_label)
        folder_row.addWidget(self._folder_edit, stretch=1)
        folder_row.addWidget(self._browse_button)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        action_row.addWidget(self._run_button)
        action_row.addWidget(self._open_report_button)
        action_row.addWidget(self._open_folder_button)
        action_row.addStretch()

        controls_layout.addLayout(mode_row)
        controls_layout.addLayout(folder_row)
        controls_layout.addWidget(self._helper_label)
        controls_layout.addWidget(self._automatic_note)
        controls_layout.addLayout(action_row)
        controls_layout.addWidget(self._progress)
        controls_layout.addWidget(self._status_label)

        result_card = QFrame()
        result_card.setObjectName("infoCard")
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(22, 18, 22, 20)
        result_layout.setSpacing(10)
        result_heading = QLabel("Detection and Analysis Progress")
        result_heading.setObjectName("cardHeading")
        result_layout.addWidget(result_heading)
        result_layout.addWidget(self._identifier_label)
        result_layout.addWidget(self._log, stretch=1)

        layout.addLayout(heading_row)
        layout.addWidget(description)
        layout.addWidget(controls)
        layout.addWidget(result_card, stretch=1)

    def set_mode(self, mode: str) -> None:
        """Select one stable IMEI mode."""

        index = self._mode_box.findData(str(mode).strip().casefold())
        if index < 0:
            raise ValueError(f"Unsupported IMEI mode: {mode}")
        self._mode_box.setCurrentIndex(index)

    def set_selected_folder(self, folder: str | Path) -> None:
        """Set the evidence folder for the active mode."""

        value = str(Path(folder).expanduser().resolve(strict=False))
        self._selected_folders[self.selected_mode] = value
        self._folder_edit.setText(value)
        self._update_folder_summary()

    def validation_error(self) -> str:
        """Return a simple validation error or an empty string."""

        if not self.selected_folder:
            return "Select an IMEI evidence folder."

        folder = Path(self.selected_folder)
        if not folder.is_dir():
            return "The selected IMEI evidence folder does not exist."

        if not self._supported_files(folder):
            return (
                "No supported CSV, TXT, TSV, XLSX or XLS IMEI evidence "
                "file was found in the selected folder."
            )

        return ""

    def refresh(self) -> None:
        """Refresh the selected-folder summary."""

        self._update_folder_summary()

    def _mode_changed(self) -> None:
        mode = self.selected_mode
        self._folder_edit.setText(self._selected_folders.get(mode, ""))
        self._helper_label.setText(_MODE_HELP.get(mode, ""))
        self._open_report_button.setEnabled(bool(self.report_paths))
        self._open_folder_button.setEnabled(bool(self.report_paths))
        self._update_identifier_summary()
        self._update_folder_summary()

    def _browse_folder(self) -> None:
        start = self.selected_folder or str(_default_folder(self.selected_mode))
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Dedicated IMEI Evidence Folder",
            start,
        )
        if selected:
            self.set_selected_folder(selected)

    @staticmethod
    def _supported_files(folder: Path) -> list[Path]:
        return sorted(
            path
            for path in folder.rglob("*")
            if path.is_file() and path.suffix.casefold() in IMEI_EVIDENCE_SUFFIXES
        )

    def _update_folder_summary(self) -> None:
        folder = Path(self.selected_folder) if self.selected_folder else None

        if folder is None or not folder.is_dir():
            self._status_label.setText(
                "Select an existing folder containing dedicated IMEI evidence."
            )
            return

        count = len(self._supported_files(folder))
        self._status_label.setText(f"Ready | Supported evidence files found: {count}")

    def _start_analysis(self) -> None:
        if self.is_running:
            return

        error = self.validation_error()
        if error:
            QMessageBox.warning(self, "IMEI Input Review", error)
            self._status_label.setText(error)
            return

        mode = self.selected_mode
        self._report_paths_by_mode[mode] = []
        self._identifiers_by_mode[mode] = []
        self._open_report_button.setEnabled(False)
        self._open_folder_button.setEnabled(False)
        self._log.clear()
        self._append_log("[+] Starting automatic IMEI detection and analysis.")
        self._set_running_state(True)

        thread = QThread(self)
        worker = ImeiWorker(
            mode=mode,
            input_folder=self.selected_folder,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.log.connect(self._append_log)
        worker.completed.connect(self._analysis_completed)
        worker.failed.connect(self._analysis_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _set_running_state(self, running: bool) -> None:
        self._mode_box.setEnabled(not running)
        self._browse_button.setEnabled(not running)
        self._run_button.setEnabled(not running)
        self._progress.setVisible(running)
        if running:
            self._status_label.setText(
                "IMEI analysis is running. Keep this window open."
            )

    def _append_log(self, message: str) -> None:
        text = str(message).strip()
        if text:
            self._log.appendPlainText(text)

    def _analysis_completed(self, payload: object) -> None:
        result = payload if isinstance(payload, dict) else {}
        mode = str(result.get("mode", self.selected_mode))
        identifiers = [
            str(value)
            for value in result.get("identifiers", []) or []
            if str(value).strip()
        ]
        paths = [
            str(value)
            for value in result.get("report_paths", []) or []
            if str(value).strip()
        ]
        self._identifiers_by_mode[mode] = identifiers
        self._report_paths_by_mode[mode] = paths
        self._update_identifier_summary()
        self._open_report_button.setEnabled(bool(self.report_paths))
        self._open_folder_button.setEnabled(bool(self.report_paths))

        if str(result.get("status", "")).upper() == "NO_IDENTIFIERS":
            message = str(result.get("message", "")).strip()
            self._status_label.setText(
                message or "No report-query IMEI or IMEISV was detected."
            )
            self._append_log("[!] No supported report-query identifier was detected.")
            return

        if paths:
            self._status_label.setText(
                f"IMEI analysis completed | Reports ready: {len(paths)}"
            )
            self._append_log("[+] IMEI analysis completed successfully.")
            for report_path in paths:
                self._append_log(f"[+] Report: {report_path}")
        else:
            self._status_label.setText(
                "Analysis completed, but no reportable matching evidence was found."
            )
            self._append_log("[=] No investigator workbook was created.")

    def _analysis_failed(self, message: str) -> None:
        self._status_label.setText("IMEI analysis failed. Review the progress log.")
        self._append_log(f"[-] {str(message).strip()}")

    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._set_running_state(False)

    def _update_identifier_summary(self) -> None:
        identifiers = self.detected_identifiers
        if identifiers:
            self._identifier_label.setText(
                "Detected report-query identifiers: " + ", ".join(identifiers)
            )
        else:
            self._identifier_label.setText(
                "Detected identifiers will appear after analysis."
            )

    def _open_latest_report(self) -> None:
        if not self.report_paths:
            return

        report_path = Path(self.report_paths[0])
        if not report_path.is_file():
            QMessageBox.warning(
                self,
                "Report Not Found",
                f"The report file is not available:\n{report_path}",
            )
            return

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(report_path))):
            QMessageBox.warning(
                self,
                "Open Report",
                "The operating system could not open the report.",
            )

    def _open_report_folder(self) -> None:
        if not self.report_paths:
            return

        folder = Path(self.report_paths[0]).parent
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            QMessageBox.warning(
                self,
                "Open Report Folder",
                "The operating system could not open the report folder.",
            )
