"""Investigator-facing editor for Tower Dump Date-Time Parts."""

from __future__ import annotations

from typing import Any, Iterable

from PySide6.QtCore import QDate, QDateTime, Qt, QTime
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


DISPLAY_FORMAT = "dd-MM-yyyy HH:mm:ss"
CANONICAL_FORMAT = "yyyy-MM-dd HH:mm:ss"
EMPTY_DATE_TIME = QDateTime(QDate(1970, 1, 1), QTime(0, 0, 0))
SOURCE_RECORD_TYPES = {
    "cdr": "NORMAL_CDR",
    "gprs": "GPRS",
    "ipdr": "TOWER_IPDR",
}


class DateTimePartitionDialog(QDialog):
    """Create and edit exact Spot-aware Start/End Date-Time Parts."""

    def __init__(
        self,
        *,
        source_type: str,
        spots: Iterable[dict[str, Any]],
        existing_parts: Iterable[dict[str, Any]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.source_type = str(source_type).strip().casefold()
        if self.source_type not in SOURCE_RECORD_TYPES:
            raise ValueError(
                f"Unsupported Tower Dump source type: {source_type}"
            )

        self._spots = [
            dict(spot)
            for spot in spots
            if isinstance(spot, dict)
            and str(spot.get("spot_id", "")).strip()
        ]
        if not self._spots:
            raise ValueError(
                "No investigation Spot is available for Date-Time Parts."
            )

        self.setWindowTitle("Create / Manage Date-Time Parts")
        self.setModal(True)
        self.resize(980, 520)

        self._table = QTableWidget(0, 4)
        self._table.setObjectName("inputControl")
        self._table.setHorizontalHeaderLabels(
            (
                "Part",
                "Investigation Spot",
                "Start Date-Time",
                "End Date-Time",
            )
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)

        self._add_button = QPushButton("Add Part")
        self._add_button.setObjectName("secondaryButton")
        self._remove_button = QPushButton("Remove Selected Part")
        self._remove_button.setObjectName("secondaryButton")
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )

        self._build_layout()
        self._add_button.clicked.connect(lambda: self.add_part())
        self._remove_button.clicked.connect(self.remove_selected_part)
        self._buttons.accepted.connect(self._validate_and_accept)
        self._buttons.rejected.connect(self.reject)

        parts = [
            dict(part)
            for part in (existing_parts or [])
            if isinstance(part, dict)
        ]
        for part in parts or [None]:
            self.add_part(part)

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 20)
        layout.setSpacing(14)

        title = QLabel("Date-Time Partitioning")
        title.setObjectName("moduleTitle")

        guidance = QLabel(
            "Create one row for each Part. Select one Spot and enter the "
            "exact Start and End Date-Time. Start is included; End is "
            "excluded, so boundary records are not duplicated."
        )
        guidance.setObjectName("cardText")
        guidance.setWordWrap(True)

        overlap_note = QLabel(
            "Overlapping Parts are allowed. The software will show a "
            "warning when the same Spot scopes overlap."
        )
        overlap_note.setObjectName("statusText")
        overlap_note.setWordWrap(True)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        action_row.addWidget(self._add_button)
        action_row.addWidget(self._remove_button)
        action_row.addStretch()

        layout.addWidget(title)
        layout.addWidget(guidance)
        layout.addWidget(overlap_note)
        layout.addLayout(action_row)
        layout.addWidget(self._table, stretch=1)
        layout.addWidget(self._buttons)

    @property
    def row_count(self) -> int:
        """Return the number of Part rows currently shown."""

        return self._table.rowCount()

    @staticmethod
    def _text(value: object) -> str:
        return str(value or "").strip()

    def _new_spot_box(self, part: dict[str, Any]) -> QComboBox:
        box = QComboBox()
        box.setObjectName("inputControl")
        box.addItem("Select Spot for this Part", None)

        for spot in self._spots:
            spot_id = self._text(spot.get("spot_id"))
            spot_name = self._text(spot.get("spot_name")) or spot_id
            box.addItem(f"{spot_id} | {spot_name}", dict(spot))

        requested_id = self._text(part.get("spot_id"))
        requested_name = self._text(part.get("spot_name"))
        selected_index = -1

        for index in range(1, box.count()):
            data = box.itemData(index)
            if not isinstance(data, dict):
                continue

            data_id = self._text(data.get("spot_id"))
            data_name = self._text(data.get("spot_name"))
            id_match = requested_id and data_id == requested_id
            name_match = not requested_name or data_name == requested_name

            if (id_match and name_match) or (
                not requested_id
                and requested_name
                and data_name == requested_name
            ):
                selected_index = index
                break

        if selected_index >= 0:
            box.setCurrentIndex(selected_index)
        elif requested_id or requested_name:
            unavailable = dict(part)
            unavailable["unavailable"] = True
            box.addItem(
                f"{requested_id or 'UNKNOWN'} | "
                f"{requested_name or 'Saved Spot'} "
                "(not in selected evidence)",
                unavailable,
            )
            box.setCurrentIndex(box.count() - 1)
        elif len(self._spots) == 1:
            box.setCurrentIndex(1)

        return box

    @staticmethod
    def _new_date_time_edit(value: object = "") -> QDateTimeEdit:
        edit = QDateTimeEdit()
        edit.setObjectName("inputControl")
        edit.setCalendarPopup(True)
        edit.setDisplayFormat(DISPLAY_FORMAT)
        edit.setMinimumDateTime(EMPTY_DATE_TIME)
        edit.setSpecialValueText("Select date and time")
        edit.setDateTime(EMPTY_DATE_TIME)
        edit.setProperty("partitionEmpty", True)

        parsed = QDateTime.fromString(
            DateTimePartitionDialog._text(value),
            CANONICAL_FORMAT,
        )
        if parsed.isValid():
            edit.setDateTime(parsed)
            edit.setProperty("partitionEmpty", False)

        edit.dateTimeChanged.connect(
            lambda _value: edit.setProperty("partitionEmpty", False)
        )
        return edit

    def add_part(self, part: dict[str, Any] | None = None) -> None:
        """Append one editable Part row."""

        specification = dict(part or {})
        row = self._table.rowCount()
        self._table.insertRow(row)

        part_item = QTableWidgetItem(f"Part {row + 1}")
        part_item.setFlags(
            part_item.flags() & ~Qt.ItemFlag.ItemIsEditable
        )
        self._table.setItem(row, 0, part_item)
        self._table.setCellWidget(row, 1, self._new_spot_box(specification))
        self._table.setCellWidget(
            row,
            2,
            self._new_date_time_edit(specification.get("start_time", "")),
        )
        self._table.setCellWidget(
            row,
            3,
            self._new_date_time_edit(specification.get("end_time", "")),
        )
        self._table.setRowHeight(row, 42)

    def remove_selected_part(self) -> None:
        """Remove the currently selected Part row."""

        row = self._table.currentRow()
        if row < 0:
            return

        self._table.removeRow(row)
        for current_row in range(self._table.rowCount()):
            item = self._table.item(current_row, 0)
            if item is not None:
                item.setText(f"Part {current_row + 1}")

    @staticmethod
    def _required_date_time(
        widget: QWidget | None,
        *,
        part_number: int,
        field_name: str,
    ) -> QDateTime:
        if not isinstance(widget, QDateTimeEdit):
            raise ValueError(
                f"Part {part_number}: {field_name} Date-Time is required."
            )

        value = widget.dateTime()
        if bool(widget.property("partitionEmpty")) or value == EMPTY_DATE_TIME:
            raise ValueError(
                f"Part {part_number}: {field_name} Date-Time is required."
            )

        return value

    def part_specs(self) -> list[dict[str, Any]]:
        """Return validated canonical Part specifications."""

        if self._table.rowCount() <= 0:
            raise ValueError(
                "Add at least one Date-Time Part before saving."
            )

        specifications: list[dict[str, Any]] = []

        for row in range(self._table.rowCount()):
            part_number = row + 1
            spot_box = self._table.cellWidget(row, 1)
            if not isinstance(spot_box, QComboBox):
                raise ValueError(
                    f"Part {part_number}: Select one investigation Spot."
                )

            spot = spot_box.currentData()
            if not isinstance(spot, dict):
                raise ValueError(
                    f"Part {part_number}: Select one investigation Spot."
                )
            if spot.get("unavailable"):
                raise ValueError(
                    f"Part {part_number}: The saved Spot is not available "
                    "in the selected evidence folder. Select another Spot."
                )

            start_value = self._required_date_time(
                self._table.cellWidget(row, 2),
                part_number=part_number,
                field_name="Start",
            )
            end_value = self._required_date_time(
                self._table.cellWidget(row, 3),
                part_number=part_number,
                field_name="End",
            )
            if end_value.toSecsSinceEpoch() <= start_value.toSecsSinceEpoch():
                raise ValueError(
                    f"Part {part_number}: End Date-Time must be later "
                    "than Start Date-Time."
                )

            spot_id = self._text(spot.get("spot_id"))
            spot_name = self._text(spot.get("spot_name")) or spot_id
            specifications.append(
                {
                    "part_name": f"Part {part_number}",
                    "spot_part_no": part_number,
                    "spot_scope_mode": "SELECTED_SPOT_ONLY",
                    "spot_id": spot_id,
                    "spot_name": spot_name,
                    "spot_folder": (
                        self._text(spot.get("spot_folder")) or spot_name
                    ),
                    "start_time": start_value.toString(CANONICAL_FORMAT),
                    "end_time": end_value.toString(CANONICAL_FORMAT),
                    "source_type": SOURCE_RECORD_TYPES[self.source_type],
                }
            )

        return specifications

    def _validate_and_accept(self) -> None:
        try:
            self.part_specs()
        except ValueError as error:
            QMessageBox.warning(
                self,
                "Date-Time Part Review",
                str(error),
            )
            return

        self.accept()


__all__ = ["DateTimePartitionDialog"]
