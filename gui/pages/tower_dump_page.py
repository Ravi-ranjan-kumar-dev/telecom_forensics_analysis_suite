"""Tower Dump analysis page for the desktop GUI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.workers.tower_dump_worker import TowerDumpWorker
from gui.widgets.date_time_partition_dialog import (
    DateTimePartitionDialog,
)
from modules.controllers.tower_dump_controller import (
    TOWER_DUMP_SOURCE_SUFFIXES,
    TOWER_DUMP_SOURCE_TYPES,
)
from modules.core.paths import PROJECT_ROOT
from modules.loader.tower_spot_layout import (
    build_tower_spot_layout,
)


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
        self._spot_layouts: dict[str, dict[str, object]] = {
            source_type: {}
            for source_type in TOWER_DUMP_SOURCE_TYPES
        }
        self._selected_spots: dict[
            str,
            set[str] | None,
        ] = {
            source_type: None
            for source_type in TOWER_DUMP_SOURCE_TYPES
        }
        self._partition_parts_by_source: dict[
            str,
            list[dict[str, object]] | None,
        ] = {
            source_type: None
            for source_type in TOWER_DUMP_SOURCE_TYPES
        }
        self._thread: QThread | None = None
        self._worker: TowerDumpWorker | None = None
        self._running_analysis_mode = ""

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
            False
        )
        self._folder_edit.editingFinished.connect(lambda: self.set_selected_folder(self._folder_edit.text().strip()) if self._folder_edit.text().strip() else None)
        self._folder_edit.setPlaceholderText(
            "Select the parent folder containing all Spot folders"
        )

        self._browse_button = QPushButton(
            "Select Parent Folder"
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

        self._spot_summary_label = QLabel(
            "Spot folders will be detected automatically."
        )
        self._spot_summary_label.setObjectName(
            "cardText"
        )
        self._spot_summary_label.setWordWrap(
            True
        )

        self._spot_selection_label = QLabel(
            "Select Spot Folders"
        )
        self._spot_selection_label.setObjectName(
            "fieldLabel"
        )
        self._spot_selection_label.setVisible(
            False
        )

        self._spot_list = QListWidget()
        self._spot_list.setObjectName(
            "inputControl"
        )
        self._spot_list.setMaximumHeight(
            125
        )
        self._spot_list.setVisible(
            False
        )

        self._select_all_spots_button = QPushButton(
            "Select All Spots"
        )
        self._select_all_spots_button.setObjectName(
            "secondaryButton"
        )
        self._select_all_spots_button.setVisible(
            False
        )

        self._clear_spots_button = QPushButton(
            "Clear Selection"
        )
        self._clear_spots_button.setObjectName(
            "secondaryButton"
        )
        self._clear_spots_button.setVisible(
            False
        )

        self._manage_parts_button = QPushButton(
            "Create / Manage Date-Time Parts"
        )
        self._manage_parts_button.setObjectName(
            "secondaryButton"
        )

        self._run_parts_button = QPushButton(
            "Analyze Parts"
        )
        self._run_parts_button.setObjectName(
            "primaryButton"
        )

        self._parts_summary_label = QLabel(
            "Open Date-Time Parts to load or create saved Parts."
        )
        self._parts_summary_label.setObjectName(
            "cardText"
        )
        self._parts_summary_label.setWordWrap(
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

        self._open_viewer_button = QPushButton(
            "View Results"
        )
        self._open_viewer_button.setObjectName(
            "secondaryButton"
        )
        self._open_viewer_button.setEnabled(
            False
        )

        self._search_input = QLineEdit()
        self._search_input.setObjectName(
            "inputControl"
        )
        self._search_input.setPlaceholderText(
            "Enter suspected mobile number(s) (comma-separated) to search 100% full dump & B-Parties..."
        )
        self._search_input.setClearButtonEnabled(True)

        self._search_dump_button = QPushButton(
            "Search Numbers"
        )
        self._search_dump_button.setObjectName(
            "secondaryButton"
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

        self._browse_files_button = QPushButton("Select File(s)")
        self._browse_files_button.setObjectName("secondaryButton")
        self._browse_files_button.clicked.connect(self._browse_files_anywhere)

        self._build_layout()

        self._mode_box.currentIndexChanged.connect(
            self._mode_changed
        )
        self._browse_button.clicked.connect(
            self._browse_folder
        )
        self._spot_list.itemChanged.connect(
            self._spot_selection_changed
        )
        self._select_all_spots_button.clicked.connect(
            self._select_all_spots
        )
        self._clear_spots_button.clicked.connect(
            self._clear_spot_selection
        )
        self._run_button.clicked.connect(
            self._start_complete_analysis
        )
        self._manage_parts_button.clicked.connect(
            self._manage_date_time_parts
        )
        self._run_parts_button.clicked.connect(
            self._start_partition_analysis
        )
        self._open_report_button.clicked.connect(
            self._open_latest_report
        )
        self._open_viewer_button.clicked.connect(
            self._open_internal_viewer
        )
        self._search_dump_button.clicked.connect(
            self._search_full_dump_suspect
        )
        self._search_input.returnPressed.connect(
            self._search_full_dump_suspect
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

    @property
    def detected_spot_names(
        self,
    ) -> tuple[str, ...]:
        """Return canonical Spot folder names for the active source."""

        layout = self._spot_layouts.get(
            self.selected_mode,
            {},
        )

        names = layout.get(
            "spot_names",
            [],
        )

        if not isinstance(
            names,
            list,
        ):
            return ()

        return tuple(
            str(name)
            for name in names
            if str(name).strip()
        )

    @property
    def selected_spot_names(
        self,
    ) -> tuple[str, ...]:
        """Return checked Spot folder names for the active source."""

        selected: list[str] = []

        for index in range(
            self._spot_list.count()
        ):
            item = self._spot_list.item(
                index
            )

            if (
                item.checkState()
                != Qt.CheckState.Checked
            ):
                continue

            name = str(
                item.data(
                    Qt.ItemDataRole.UserRole
                )
                or ""
            ).strip()

            if name:
                selected.append(
                    name
                )

        return tuple(
            selected
        )

    def set_selected_spots(
        self,
        spot_names: tuple[str, ...] | list[str],
    ) -> None:
        """Set checked Spot folders using detected canonical names."""

        requested = {
            str(name)
            for name in spot_names
            if str(name).strip()
        }
        available = set(
            self.detected_spot_names
        )
        unknown = requested.difference(
            available
        )

        if unknown:
            raise ValueError(
                "Unknown Spot folder(s): "
                + ", ".join(
                    sorted(
                        unknown
                    )
                )
            )

        self._spot_list.blockSignals(
            True
        )

        try:
            for index in range(
                self._spot_list.count()
            ):
                item = self._spot_list.item(
                    index
                )
                name = str(
                    item.data(
                        Qt.ItemDataRole.UserRole
                    )
                    or ""
                )
                item.setCheckState(
                    Qt.CheckState.Checked
                    if name in requested
                    else Qt.CheckState.Unchecked
                )
        finally:
            self._spot_list.blockSignals(
                False
            )

        self._selected_spots[
            self.selected_mode
        ] = set(
            requested
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
        folder_row.addWidget(
            self._browse_files_button
        )

        spot_action_row = QHBoxLayout()
        spot_action_row.setSpacing(
            10
        )
        spot_action_row.addWidget(
            self._select_all_spots_button
        )
        spot_action_row.addWidget(
            self._clear_spots_button
        )
        spot_action_row.addStretch()

        partition_heading = QLabel(
            "Date-Time Parts"
        )
        partition_heading.setObjectName(
            "fieldLabel"
        )

        partition_action_row = QHBoxLayout()
        partition_action_row.setSpacing(
            10
        )
        partition_action_row.addWidget(
            self._manage_parts_button
        )
        partition_action_row.addWidget(
            self._run_parts_button
        )
        partition_action_row.addStretch()

        search_heading = QLabel(
            "Search Numbers in Full Dump"
        )
        search_heading.setObjectName(
            "fieldLabel"
        )
        search_row = QHBoxLayout()
        search_row.setSpacing(
            10
        )
        search_row.addWidget(
            self._search_input,
            stretch=1,
        )
        search_row.addWidget(
            self._search_dump_button
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
            self._open_viewer_button
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
        # Selected source type is visible in the type dropdown.
        controls_layout.addWidget(
            self._spot_summary_label
        )
        controls_layout.addWidget(
            self._spot_selection_label
        )
        controls_layout.addWidget(
            self._spot_list
        )
        controls_layout.addLayout(
            spot_action_row
        )
        controls_layout.addWidget(
            partition_heading
        )
        # Date-Time Parts controls explain their own action.
        controls_layout.addLayout(
            partition_action_row
        )
        # The status line shows the active Parts selection when needed.
        controls_layout.addWidget(
            search_heading
        )
        controls_layout.addLayout(
            search_row
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

        source_type = self.selected_mode
        previous_folder = self._selected_folders.get(
            source_type,
            "",
        )

        if previous_folder != str(
            path
        ):
            self._selected_spots[
                source_type
            ] = None
            self._partition_parts_by_source[
                source_type
            ] = None

        self._selected_folders[
            source_type
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
            if (
                self.detected_spot_names
                and not self.selected_spot_names
            ):
                return (
                    "Select at least one Spot folder "
                    "before running analysis."
                )

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
        self._open_viewer_button.setEnabled(
            bool(
                self.report_paths
            )
        )
        self._show_cached_partition_summary()

        if self.selected_folder:
            self._update_folder_summary()
        else:
            self._spot_layouts[
                source_type
            ] = {}
            self._spot_summary_label.setText(
                "Spot folders will be detected automatically."
            )
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
            "Select Parent Folder Containing Tower Dump Spots",
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
        source_type = self.selected_mode

        if not folder_text:
            self._spot_layouts[
                source_type
            ] = {}
            self._spot_summary_label.setText(
                "Spot folders will be detected automatically."
            )
            return

        folder = Path(
            folder_text
        )

        if not folder.is_dir():
            self._spot_layouts[
                source_type
            ] = {}
            self._spot_summary_label.setText(
                "Spot layout is unavailable."
            )
            self._status_label.setText(
                "Selected folder is not available."
            )
            return

        files = self._evidence_files(
            folder,
            source_type,
        )
        layout = build_tower_spot_layout(
            folder,
            files,
        )
        self._spot_layouts[
            source_type
        ] = layout

        self._status_label.setText(
            f"Selected folder contains {len(files)} supported file(s)."
        )

        summary = layout.get(
            "spot_summary",
            [],
        )
        folder_spots = [
            item
            for item in summary
            if (
                isinstance(item, dict)
                and str(
                    item.get(
                        "spot_id",
                        "",
                    )
                )
                != "UNASSIGNED-ROOT"
            )
        ]

        if folder_spots:
            details = ", ".join(
                (
                    f"{item.get('spot_name', item.get('spot_id', 'Spot'))} "
                    f"({int(item.get('files_found', 0))} file(s))"
                )
                for item in folder_spots
            )
            message = (
                f"Detected {len(folder_spots)} Spot folder(s): "
                f"{details}."
            )
        else:
            message = (
                "No Spot subfolders were detected. Root-level files "
                "will be analyzed as unassigned evidence."
            )

        root_file_count = int(
            layout.get(
                "root_level_file_count",
                0,
            )
            or 0
        )

        if root_file_count:
            message += (
                f" {root_file_count} root-level file(s) will be "
                "excluded from selected-Spot analysis."
            )

        self._spot_summary_label.setText(
            message
        )
        self._populate_spot_selection(
            folder_spots
        )

    def _populate_spot_selection(
        self,
        folder_spots: list[dict[str, object]],
    ) -> None:
        """Populate checked Spot folders without including root files."""

        source_type = self.selected_mode
        available = {
            str(
                item.get(
                    "spot_name",
                    "",
                )
            ): int(
                item.get(
                    "files_found",
                    0,
                )
                or 0
            )
            for item in folder_spots
            if str(
                item.get(
                    "spot_name",
                    "",
                )
            ).strip()
        }
        stored = self._selected_spots.get(
            source_type
        )
        selected = (
            set(
                available
            )
            if stored is None
            else set(
                stored
            ).intersection(
                available
            )
        )

        self._selected_spots[
            source_type
        ] = selected
        self._spot_list.blockSignals(
            True
        )

        try:
            self._spot_list.clear()

            for name in sorted(
                available,
                key=lambda value: (
                    value.casefold(),
                    value,
                ),
            ):
                item = QListWidgetItem(
                    f"{name} ({available[name]} file(s))"
                )
                item.setData(
                    Qt.ItemDataRole.UserRole,
                    name,
                )
                item.setFlags(
                    item.flags()
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(
                    Qt.CheckState.Checked
                    if name in selected
                    else Qt.CheckState.Unchecked
                )
                self._spot_list.addItem(
                    item
                )
        finally:
            self._spot_list.blockSignals(
                False
            )

        visible = bool(
            available
        )

        for widget in (
            self._spot_selection_label,
            self._spot_list,
            self._select_all_spots_button,
            self._clear_spots_button,
        ):
            widget.setVisible(
                visible
            )

    def _spot_selection_changed(
        self,
        _item: QListWidgetItem,
    ) -> None:
        self._selected_spots[
            self.selected_mode
        ] = set(
            self.selected_spot_names
        )

    def _select_all_spots(
        self,
    ) -> None:
        self.set_selected_spots(
            list(
                self.detected_spot_names
            )
        )

    def _clear_spot_selection(
        self,
    ) -> None:
        self.set_selected_spots(
            []
        )

    def _show_cached_partition_summary(
        self,
    ) -> None:
        parts = self._partition_parts_by_source.get(
            self.selected_mode
        )

        if parts is None:
            self._parts_summary_label.setText(
                "Open Date-Time Parts to load or create saved Parts."
            )
            return

        if not parts:
            self._parts_summary_label.setText(
                "No Date-Time Parts are saved for this Tower Dump type."
            )
            return

        spot_names = {
            str(
                part.get(
                    "spot_name",
                    "",
                )
                or part.get(
                    "spot_id",
                    "",
                )
            ).strip()
            for part in parts
            if str(
                part.get(
                    "spot_name",
                    "",
                )
                or part.get(
                    "spot_id",
                    "",
                )
            ).strip()
        }
        self._parts_summary_label.setText(
            f"Saved Parts: {len(parts)} | Spots: {len(spot_names)} | "
            "Rule: Start included, End excluded."
        )

    def _available_partition_spots(
        self,
    ) -> list[dict[str, object]]:
        layout = self._spot_layouts.get(
            self.selected_mode,
            {},
        )
        summary = [
            dict(item)
            for item in layout.get(
                "spot_summary",
                [],
            )
            if isinstance(
                item,
                dict,
            )
        ]

        if not self.detected_spot_names:
            return summary

        selected_names = set(
            self.selected_spot_names
        )
        return [
            item
            for item in summary
            if (
                str(
                    item.get(
                        "spot_id",
                        "",
                    )
                )
                != "UNASSIGNED-ROOT"
                and str(
                    item.get(
                        "spot_name",
                        "",
                    )
                )
                in selected_names
            )
        ]

    def _partition_input_error(
        self,
    ) -> str:
        error = self.validation_error()

        if error:
            return error

        if not self._available_partition_spots():
            return (
                "No selected investigation Spot is available for "
                "Date-Time Partitioning."
            )

        return ""

    @staticmethod
    def _active_case() -> dict[str, object]:
        from modules.controllers.app_controller import (
            get_direct_analysis_workspace,
        )

        return get_direct_analysis_workspace()

    def _load_partition_parts(
        self,
    ) -> list[dict[str, object]]:
        from modules.controllers.tower_dump_controller import (
            list_tower_dump_date_time_parts,
        )

        parts = [
            dict(part)
            for part in list_tower_dump_date_time_parts(
                self._active_case(),
                source_type=self.selected_mode,
            )
        ]
        self._partition_parts_by_source[
            self.selected_mode
        ] = parts
        self._show_cached_partition_summary()
        return parts

    def _manage_date_time_parts(
        self,
    ) -> None:
        if self.is_running:
            return

        error = self._partition_input_error()

        if error:
            QMessageBox.warning(
                self,
                "Date-Time Part Input Review",
                error,
            )
            self._status_label.setText(
                error
            )
            return

        try:
            case = self._active_case()
            existing_parts = self._load_partition_parts()
            dialog = DateTimePartitionDialog(
                source_type=self.selected_mode,
                spots=self._available_partition_spots(),
                existing_parts=existing_parts,
                parent=self,
            )

            if not dialog.exec():
                return

            from modules.controllers.tower_dump_controller import (
                save_tower_dump_date_time_parts,
            )

            payload = save_tower_dump_date_time_parts(
                case,
                source_type=self.selected_mode,
                part_specs=dialog.part_specs(),
            )
            saved_parts = [
                dict(part)
                for part in payload.get(
                    "parts",
                    [],
                )
            ]
            self._partition_parts_by_source[
                self.selected_mode
            ] = saved_parts
            self._show_cached_partition_summary()

            overlap_warnings = list(
                payload.get(
                    "overlap_warnings",
                    [],
                )
            )
            self._status_label.setText(
                f"Saved {len(saved_parts)} Date-Time Part(s)."
            )

            if overlap_warnings:
                QMessageBox.warning(
                    self,
                    "Date-Time Parts Saved",
                    (
                        f"{len(saved_parts)} Part(s) were saved. "
                        f"{len(overlap_warnings)} overlap warning(s) "
                        "were found. Overlap is allowed, but some records "
                        "may appear in more than one Part."
                    ),
                )
            else:
                QMessageBox.information(
                    self,
                    "Date-Time Parts Saved",
                    f"{len(saved_parts)} Date-Time Part(s) were saved.",
                )

        except Exception as error:
            # EA_HANDLED_DIAGNOSTICS_V1
            try:
                from modules.core.diagnostic_events import record_handled_exception as _ea_record_handled_exception
                _ea_record_handled_exception()
            except Exception:
                pass
            message = f"{type(error).__name__}: {error}"
            QMessageBox.warning(
                self,
                "Date-Time Part Review",
                message,
            )
            self._status_label.setText(
                "Date-Time Parts could not be saved."
            )

    def _start_complete_analysis(
        self,
    ) -> None:
        self._start_analysis(
            "complete"
        )

    def _start_partition_analysis(
        self,
    ) -> None:
        if self.is_running:
            return

        error = self._partition_input_error()

        if error:
            QMessageBox.warning(
                self,
                "Date-Time Part Input Review",
                error,
            )
            self._status_label.setText(
                error
            )
            return

        try:
            parts = self._load_partition_parts()
        except Exception as error:
            # EA_HANDLED_DIAGNOSTICS_V1
            try:
                from modules.core.diagnostic_events import record_handled_exception as _ea_record_handled_exception
                _ea_record_handled_exception()
            except Exception:
                pass
            QMessageBox.warning(
                self,
                "Date-Time Part Review",
                f"{type(error).__name__}: {error}",
            )
            return

        if not parts:
            message = (
                "Create and save at least one Date-Time Part before "
                "running Part-wise Analysis."
            )
            QMessageBox.warning(
                self,
                "No Date-Time Parts",
                message,
            )
            self._status_label.setText(
                message
            )
            return

        self._start_analysis(
            "partition"
        )

    def _start_analysis(
        self,
        analysis_mode: str = "complete",
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
        mode_title = (
            "Part-wise Date-Time Analysis"
            if analysis_mode == "partition"
            else "Complete Analysis"
        )
        self._append_log(
            f"[+] Starting {mode_title}: {_MODE_LABELS[source_type]}."
        )
        self._running_analysis_mode = analysis_mode
        self._set_running_state(
            True
        )

        thread = QThread(
            self
        )
        has_spot_folders = bool(
            self.detected_spot_names
        )
        selected_spots = (
            self.selected_spot_names
            if has_spot_folders
            else None
        )
        include_root_files = not has_spot_folders

        self._append_log(
            (
                "[+] Selected Spots: "
                + ", ".join(
                    selected_spots
                    or ()
                )
            )
            if selected_spots
            else "[+] Legacy root-file input mode."
        )

        worker = TowerDumpWorker(
            source_type=source_type,
            input_folder=self.selected_folder,
            analysis_mode=analysis_mode,
            selected_spot_folders=selected_spots,
            include_root_files=include_root_files,
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
        self._spot_list.setEnabled(
            not running
        )
        self._select_all_spots_button.setEnabled(
            not running
        )
        self._clear_spots_button.setEnabled(
            not running
        )
        self._run_button.setEnabled(
            not running
        )
        self._manage_parts_button.setEnabled(
            not running
        )
        self._run_parts_button.setEnabled(
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
        source_type = str(
            result.get(
                "source_type",
                self.selected_mode,
            )
        )

        if source_type not in TOWER_DUMP_SOURCE_TYPES:
            source_type = self.selected_mode

        analysis_mode = str(
            result.get(
                "analysis_mode",
                self._running_analysis_mode,
            )
            or self._running_analysis_mode
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
        self._report_paths_by_source[
            source_type
        ] = paths
        self._open_report_button.setEnabled(
            bool(
                self.report_paths
            )
        )
        self._open_viewer_button.setEnabled(
            bool(
                self.report_paths
            )
        )

        if paths:
            self._status_label.setText(
                (
                    "Part-wise analysis completed. "
                    "The investigator report is ready."
                    if analysis_mode == "partition"
                    else (
                        "Analysis completed. The investigator report "
                        "is ready."
                    )
                )
            )
            self._append_log(
                (
                    "[+] Part-wise analysis completed successfully."
                    if analysis_mode == "partition"
                    else "[+] Analysis completed successfully."
                )
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
        self._running_analysis_mode = ""
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


    def _open_internal_viewer(
        self,
    ) -> None:
        if not self.report_paths:
            return
        report_path = Path(
            self.report_paths[0]
        )
        if not report_path.is_file():
            QMessageBox.warning(
                self,
                "Report Not Found",
                f"The report file is not available:\n{report_path}",
            )
            return
        from gui.widgets.report_viewer_dialog import ReportViewerDialog
        ReportViewerDialog(report_path, self).exec()

    def _search_full_dump_suspect(self) -> None:
        # Avoid running the full-dump load/search on the Qt UI thread.
        if self.is_running or getattr(self, "_ea_search_busy", False):
            return
        error = self.validation_error()
        if error:
            QMessageBox.warning(self, "Tower Dump Input Review", error)
            self._status_label.setText(error)
            return
        query = self._search_input.text().strip()
        if not query:
            QMessageBox.warning(self, "Number Required", "Enter one or more mobile numbers to search.")
            return

        from PySide6.QtCore import QThread
        from gui.workers.full_dump_search_worker import FullDumpSearchWorker
        case = self._active_case()
        has_spot_folders = bool(self.detected_spot_names)
        selected_spots = list(self.selected_spot_names) if has_spot_folders else None
        self._ea_search_busy = True
        self._search_dump_button.setEnabled(False)
        self._status_label.setText("Searching full dump in background...")
        self._append_log("[+] Full dump search started (background): " + query)

        thread = QThread(self)
        worker = FullDumpSearchWorker(
            case_id=str(case.get("case_id", "DEV-WORKSPACE")),
            source_type=self.selected_mode,
            input_folder=self.selected_folder,
            selected_spots=selected_spots,
            include_root_files=not has_spot_folders,
            query=query,
        )
        worker.moveToThread(thread)
        self._ea_search_thread = thread
        self._ea_search_worker = worker

        def completed(payload):
            if payload.get("empty"):
                self._status_label.setText("No valid dump records found.")
                QMessageBox.information(self, "No Dump Records", "No valid records found in the selected folder.")
                return
            from gui.widgets.tower_search_dialog import TowerDumpSearchDialog
            result = payload["result"]
            count = int(result.get("matched_count", 0) or 0)
            parties = len(result.get("counterparty_summary", []))
            self._status_label.setText(
                f"Search complete: {count:,} records, {parties:,} B-Parties"
            )
            self._append_log(
                f"[+] Search completed: {count:,} matches in {payload['total']:,} records."
            )
            TowerDumpSearchDialog(result, self).exec()

        def failed(message):
            self._status_label.setText("Full dump search failed.")
            QMessageBox.warning(self, "Full Dump Search Error", message)

        def reset():
            self._ea_search_busy = False
            self._search_dump_button.setEnabled(True)

        thread.started.connect(worker.run)
        worker.completed.connect(completed)
        worker.failed.connect(failed)
        worker.finished.connect(thread.quit)
        thread.finished.connect(reset)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

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
            "Tower Dump Files (*.csv *.txt *.tsv *.xlsx *.xls);;All Files (*)",
        )
        if not files:
            return
        try:
            staged_folder = stage_selected_files_as_folder(
                files,
                workflow="tower_dump",
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
_ORIG_TowerDumpPage_COMPLETED = TowerDumpPage._analysis_completed


def _enhanced_TowerDumpPage_completed(self, payload: object) -> None:
    from gui.utils.thread_dispatcher import _is_main_thread, run_on_main_thread
    if not _is_main_thread():
        run_on_main_thread(lambda p=payload: _enhanced_TowerDumpPage_completed(self, p))
        return
    from pathlib import Path as _Path
    from modules.reporting.gui_result_store import get_latest_gui_meta, get_latest_gui_sheets
    from gui.dialogs.fullscreen_results_window import open_fullscreen_results_window

    result = payload if isinstance(payload, dict) else {}
    sheets = result.get("gui_sheets") if isinstance(result.get("gui_sheets"), dict) and result.get("gui_sheets") else get_latest_gui_sheets()
    meta = get_latest_gui_meta()
    win_title = str(meta.get("title") or "Tower Dump Analysis Results")

    report_paths = [
        _Path(p) for p in (result.get("report_paths") or []) if p
    ]

    if report_paths:
        _ORIG_TowerDumpPage_COMPLETED(self, payload)
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

    _ORIG_TowerDumpPage_COMPLETED(self, payload)


TowerDumpPage._analysis_completed = _enhanced_TowerDumpPage_completed

if hasattr(TowerDumpPage, "_open_latest_report"):
    _ORIG_TowerDumpPage_OPEN_REPORT = TowerDumpPage._open_latest_report

    def _enhanced_TowerDumpPage_open_report(self) -> None:
        from modules.reporting.gui_result_store import get_latest_gui_meta, get_latest_gui_sheets
        from gui.dialogs.fullscreen_results_window import open_fullscreen_results_window

        sheets = get_latest_gui_sheets()
        if sheets and not getattr(self, "_latest_report_paths", None):
            meta = get_latest_gui_meta()
            open_fullscreen_results_window(
                self,
                sheets,
                title=str(meta.get("title") or "Tower Dump Analysis Results"),
            )
            return
        _ORIG_TowerDumpPage_OPEN_REPORT(self)

    TowerDumpPage._open_latest_report = _enhanced_TowerDumpPage_open_report

# === GUI-FIRST TOWER CDR EXCEL EXPORT (on-demand) ===
_ORIG_LAZY_TOWER_COMPLETED = TowerDumpPage._analysis_completed
_ORIG_LAZY_TOWER_OPEN = TowerDumpPage._open_latest_report
_ORIG_LAZY_TOWER_START = TowerDumpPage._start_analysis


def _lazy_tower_start(self, *args, **kwargs):
    self._lazy_export_result = None
    if hasattr(self, "_open_report_button"):
        self._open_report_button.setText("Open Latest Report")
    return _ORIG_LAZY_TOWER_START(self, *args, **kwargs)


def _lazy_tower_completed(self, payload):
    data = payload if isinstance(payload, dict) else {}
    nested = data.get("result")
    lazy = isinstance(nested, dict) and nested.get("gui_export_only") is True
    _ORIG_LAZY_TOWER_COMPLETED(self, payload)
    if lazy:
        self._lazy_export_result = nested
        self._open_report_button.setText("Export Full Excel Report...")
        self._open_report_button.setEnabled(True)
        self._status_label.setText("Analysis ready in GUI. Excel export is optional.")
        self._append_log("[+] Full formatted Excel report will be created only if Export is clicked.")


def _lazy_tower_open_report(self):
    source = getattr(self, "_lazy_export_result", None)
    if not isinstance(source, dict) or not source.get("gui_export_only"):
        return _ORIG_LAZY_TOWER_OPEN(self)

    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from gui.workers.lazy_excel_export_worker import TowerExcelExportWorker

    if getattr(self, "_lazy_excel_thread", None) is not None:
        QMessageBox.information(self, "Export", "A full Excel export is already running.")
        return

    path, _ = QFileDialog.getSaveFileName(
        self,
        "Export Full Tower CDR Forensic Report",
        "Tower_CDR_Forensic_Report.xlsx",
        "Excel Files (*.xlsx)",
    )
    if not path:
        return
    if not path.lower().endswith(".xlsx"):
        path += ".xlsx"
    thread = QThread(self)
    worker = TowerExcelExportWorker(
        source, path, case_id=str(source.get("export_case_id") or "")
    )
    worker.moveToThread(thread)
    self._lazy_excel_thread = thread
    self._lazy_excel_worker = worker
    self._open_report_button.setEnabled(False)
    self._status_label.setText("Exporting Excel in background; analysis remains available.")
    thread.started.connect(worker.run)

    def success(output):
        self._append_log(f"[+] User-exported Excel: {output}")
        QMessageBox.information(self, "Export Complete", f"Excel saved to:\n{output}")

    def failure(message):
        self._append_log(f"[-] Excel export failed: {message}")
        QMessageBox.warning(self, "Excel Export Failed", message)

    def cleanup():
        self._lazy_excel_thread = None
        self._lazy_excel_worker = None
        self._open_report_button.setEnabled(True)
        self._status_label.setText("Analysis ready in GUI. Excel export is optional.")

    worker.completed.connect(success)
    worker.failed.connect(failure)
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(cleanup)
    thread.finished.connect(thread.deleteLater)
    thread.start()


TowerDumpPage._start_analysis = _lazy_tower_start
TowerDumpPage._analysis_completed = _lazy_tower_completed
TowerDumpPage._open_latest_report = _lazy_tower_open_report
