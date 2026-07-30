"""CDR analysis page for the desktop GUI."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.contact_map_dialog import ContactMapDialog
from gui.workers.cdr_worker import CdrWorker
from modules.core.paths import PROJECT_ROOT


_CONTACT_MAP_NAME_PATTERN = re.compile(
    r"^(?P<target>\d{10,15})_cdr_report_"
    r"(?P<created>\d{8}T\d{6})(?:_|$)"
)


def contact_map_choices(
    map_paths: list[str] | tuple[str, ...],
) -> list[tuple[str, str]]:
    """Return unique investigator-friendly labels and map paths."""

    choices: list[tuple[str, str]] = []
    label_counts: dict[str, int] = {}

    for value in map_paths:
        path_text = str(
            value or ""
        ).strip()

        if not path_text:
            continue

        stem = Path(
            path_text
        ).stem

        if stem.endswith(
            "_contact_map"
        ):
            stem = stem[
                : -len(
                    "_contact_map"
                )
            ]

        match = _CONTACT_MAP_NAME_PATTERN.match(
            stem
        )

        if match:
            target = match.group(
                "target"
            )
            created_text = match.group(
                "created"
            )

            try:
                created = datetime.strptime(
                    created_text,
                    "%Y%m%dT%H%M%S",
                )
                label = (
                    f"Target {target} — "
                    f"{created:%d-%m-%Y %H:%M:%S}"
                )
            except ValueError:
                label = f"Target {target}"
        else:
            clean_name = stem.replace(
                "_",
                " ",
            ).strip()
            label = clean_name or "Contact Map"

        label_counts[
            label
        ] = (
            label_counts.get(
                label,
                0,
            )
            + 1
        )
        count = label_counts[
            label
        ]

        if count > 1:
            label = (
                f"{label} ({count})"
            )

        choices.append(
            (
                label,
                path_text,
            )
        )

    return choices


class CdrPage(QFrame):
    """Provide Single and Multiple CDR analysis controls."""

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
            "single": "",
            "multiple": "",
        }
        self._report_paths: list[str] = []
        self._map_paths: list[str] = []
        self._route_paths: list[str] = []
        self._thread: QThread | None = None
        self._worker: CdrWorker | None = None

        self._mode_box = QComboBox()
        self._mode_box.setObjectName(
            "inputControl"
        )
        self._mode_box.addItem(
            "Single CDR Analysis",
            "single",
        )
        self._mode_box.addItem(
            "Multiple CDR Analysis",
            "multiple",
        )

        self._folder_edit = QLineEdit()
        self._folder_edit.setObjectName(
            "inputControl"
        )
        self._folder_edit.setReadOnly(
            True
        )
        self._folder_edit.setPlaceholderText(
            "Select a folder containing CDR CSV files"
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
            "Run CDR Analysis"
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

        self._open_map_button = QPushButton(
            "Open Contact Map"
        )
        self._open_map_button.setObjectName(
            "secondaryButton"
        )
        self._open_map_button.setEnabled(
            False
        )

        self._open_route_button = QPushButton(
            "Open Movement Route"
        )
        self._open_route_button.setObjectName(
            "secondaryButton"
        )
        self._open_route_button.setEnabled(
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
            1500
        )
        self._log.setPlaceholderText(
            "Analysis progress will appear here."
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
        self._open_map_button.clicked.connect(
            self._open_contact_map
        )
        self._open_route_button.clicked.connect(
            self._open_movement_route
        )

        self._mode_changed()

    @property
    def selected_mode(
        self,
    ) -> str:
        """Return the active CDR mode."""

        return str(
            self._mode_box.currentData()
            or ""
        )

    @property
    def selected_folder(
        self,
    ) -> str:
        """Return the selected evidence folder."""

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
        """Return generated report paths."""

        return tuple(
            self._report_paths
        )

    @property
    def map_paths(
        self,
    ) -> tuple[str, ...]:
        """Return generated contact map paths."""

        return tuple(
            self._map_paths
        )

    @property
    def route_paths(
        self,
    ) -> tuple[str, ...]:
        """Return generated movement-route paths."""

        return tuple(
            self._route_paths
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
            "Run CDR Analysis"
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
            "Select an evidence folder, run the existing case-aware "
            "CDR workflow in the background, and open the generated "
            "investigator report."
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
        action_row.addWidget(
            self._open_map_button
        )
        action_row.addWidget(
            self._open_route_button
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
        mode: str,
    ) -> None:
        """Select one analysis mode."""

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
            f"Unsupported CDR mode: {mode}"
        )

    def set_selected_folder(
        self,
        folder: str | Path,
    ) -> None:
        """Set the current evidence folder."""

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

        csv_files = self._csv_files(
            folder
        )

        if self.selected_mode == "single":
            if len(
                csv_files
            ) != 1:
                return (
                    "Single CDR Analysis requires exactly one CSV "
                    f"file. Found: {len(csv_files)}."
                )

        elif len(
            csv_files
        ) < 2:
            return (
                "Multiple CDR Analysis requires at least two CSV "
                f"files. Found: {len(csv_files)}."
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

        if mode == "single":
            self._helper_label.setText(
                "Select a folder containing exactly one CDR CSV file. "
                "The original file remains unchanged."
            )
        else:
            self._helper_label.setText(
                "Select a folder containing two or more CDR CSV files. "
                "Individual and common-analysis reports will be created."
            )

        self._report_paths = []
        self._map_paths = []
        self._route_paths = []
        self._open_report_button.setEnabled(
            False
        )
        self._open_map_button.setEnabled(
            False
        )
        self._open_route_button.setEnabled(
            False
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
            / "cdr"
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
            "Select CDR Evidence Folder",
            str(
                start_folder
            ),
        )

        if selected:
            self.set_selected_folder(
                selected
            )

    @staticmethod
    def _csv_files(
        folder: Path,
    ) -> list[Path]:
        return sorted(
            path
            for path in folder.iterdir()
            if (
                path.is_file()
                and path.suffix.casefold()
                == ".csv"
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
            self._csv_files(
                folder
            )
        )

        self._status_label.setText(
            f"Selected folder contains {file_count} CSV file(s)."
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
                "CDR Input Review",
                error,
            )
            self._status_label.setText(
                error
            )
            return

        self._report_paths = []
        self._map_paths = []
        self._route_paths = []
        self._open_report_button.setEnabled(
            False
        )
        self._open_map_button.setEnabled(
            False
        )
        self._open_route_button.setEnabled(
            False
        )
        self._log.clear()
        self._append_log(
            "[+] Starting CDR analysis."
        )

        self._set_running_state(
            True
        )

        thread = QThread(
            self
        )
        worker = CdrWorker(
            mode=self.selected_mode,
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

        self._status_label.setText(
            "Analysis is running. Keep this window open."
            if running
            else self._status_label.text()
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

        paths = result.get(
            "report_paths",
            [],
        )

        self._report_paths = [
            str(
                path
            )
            for path in paths
            if str(
                path
            ).strip()
        ]

        map_paths = result.get(
            "map_paths",
            [],
        )
        self._map_paths = [
            str(
                path
            )
            for path in map_paths
            if str(
                path
            ).strip()
        ]

        route_paths = result.get(
            "route_paths",
            [],
        )
        self._route_paths = [
            str(
                path
            )
            for path in route_paths
            if str(
                path
            ).strip()
        ]

        self._open_report_button.setEnabled(
            bool(
                self._report_paths
            )
        )
        self._open_map_button.setEnabled(
            bool(
                self._map_paths
            )
        )
        self._open_route_button.setEnabled(
            bool(
                self._route_paths
            )
        )

        if self._report_paths:
            self._status_label.setText(
                f"Analysis completed. Reports created: "
                f"{len(self._report_paths)}."
            )
            self._append_log(
                "[+] Analysis completed successfully."
            )

            for report_path in self._report_paths:
                self._append_log(
                    f"[+] Report: {report_path}"
                )

            for map_path in self._map_paths:
                self._append_log(
                    f"[+] Contact map: {map_path}"
                )

            for route_path in self._route_paths:
                self._append_log(
                    f"[+] Movement route: {route_path}"
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

    def _open_contact_map(
        self,
    ) -> None:
        if not self._map_paths:
            return

        map_path_text = self._map_paths[
            0
        ]

        if len(
            self._map_paths
        ) > 1:
            choices = contact_map_choices(
                self._map_paths
            )
            labels = [
                label
                for label, _ in choices
            ]
            selected, accepted = QInputDialog.getItem(
                self,
                "Select Contact Map",
                "Choose the target map to review:",
                labels,
                0,
                False,
            )

            if not accepted:
                return

            map_path_text = choices[
                labels.index(
                    selected
                )
            ][
                1
            ]

        map_path = Path(
            map_path_text
        )

        if not map_path.is_file():
            QMessageBox.warning(
                self,
                "Map Not Found",
                f"The contact map file is not available:\n{map_path}",
            )
            return

        dialog = ContactMapDialog(
            map_path,
            self,
        )
        dialog.exec()

    def _open_movement_route(
        self,
    ) -> None:
        if not self._route_paths:
            return

        route_path_text = self._route_paths[
            0
        ]

        if len(
            self._route_paths
        ) > 1:
            choices = contact_map_choices(
                self._route_paths
            )
            labels = [
                label
                for label, _ in choices
            ]
            selected, accepted = QInputDialog.getItem(
                self,
                "Select Movement Route",
                "Choose the target route to review:",
                labels,
                0,
                False,
            )

            if not accepted:
                return

            route_path_text = choices[
                labels.index(
                    selected
                )
            ][
                1
            ]

        route_path = Path(
            route_path_text
        )

        if not route_path.is_file():
            QMessageBox.warning(
                self,
                "Route Not Found",
                f"The movement route file is not available:\n{route_path}",
            )
            return

        dialog = ContactMapDialog(
            route_path,
            self,
            window_title="CDR Target Movement Route",
            heading="Target Movement Route",
            caution=(
                "The line connects serving towers in chronological order. "
                "It does not prove the exact road or exact handset location."
            ),
        )
        dialog.exec()

    def _open_latest_report(
        self,
    ) -> None:
        if not self._report_paths:
            return

        report_path = Path(
            self._report_paths[
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
