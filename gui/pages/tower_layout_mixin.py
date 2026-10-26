"""Tower Dump layout mixin, safely extracted from the page.
The original _build_layout body has not been rewritten.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout


class TowerLayoutMixin:
    """Preserves the Tower Dump widget-construction method."""

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
