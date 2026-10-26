"""Tower Dump input controls and folder selection.

Phase-2 extracted methods: method implementations are unchanged.
Keep this module independent of TowerDumpPage to prevent circular imports.
"""

from __future__ import annotations

from pathlib import Path
from PySide6.QtWidgets import QFileDialog
from modules.core.paths import PROJECT_ROOT


class TowerInputMixin:
    """Input methods; TowerDumpPage provides widgets and state."""

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
