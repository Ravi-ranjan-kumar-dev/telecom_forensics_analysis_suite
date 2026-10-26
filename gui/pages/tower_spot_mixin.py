"""Spot folder detection and selection for TowerDumpPage.

Extracted without changing method implementations.
Do not import TowerDumpPage here (avoids circular imports).
"""

from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem
from modules.controllers.tower_dump_controller import TOWER_DUMP_SOURCE_SUFFIXES
from modules.loader.tower_spot_layout import build_tower_spot_layout


class TowerSpotMixin:
    """Reusable Spot-selection behavior; page owns the widgets and state."""

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
