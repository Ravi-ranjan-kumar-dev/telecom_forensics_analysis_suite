"""Case report browser for the desktop GUI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
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

from gui.widgets.contact_map_dialog import ContactMapDialog
from gui.widgets.report_viewer_dialog import ReportViewerDialog
from modules.core.paths import PROJECT_ROOT
from modules.reporting.cdr_contact_map import contact_map_path
from modules.reporting.cdr_movement_route import movement_route_path


_REPORT_TIME_PATTERN = re.compile(
    r"_cdr_report_(?P<created>\d{8}T\d{6})(?:_|$)"
)
_TARGET_PATTERN = re.compile(
    r"^(?P<target>\d{10,15})(?:_|$)"
)
_BACKEND_MARKERS = (
    ".duckdb",
    ".parquet",
    "manifest.json",
    "latest_pipeline.json",
    "/staging/",
    "/configuration/",
    "backend_state",
)
_DISPLAY_TIME_ZONE = ZoneInfo(
    "Asia/Kolkata"
)


@dataclass(frozen=True)
class CaseReportEntry:
    """Describe one investigator-facing case report."""

    report_type: str
    target: str
    created_at: str
    report_path: Path
    contact_map_path: Path | None
    movement_route_path: Path | None


class _ReportSortItem(QTableWidgetItem):
    """Sort a report cell using its normalized value."""

    def __init__(self, text: str, sort_value: object) -> None:
        super().__init__(text)
        self._sort_value = sort_value

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, _ReportSortItem):
            return self._sort_value < other._sort_value
        return super().__lt__(other)


def _text(
    value: Any,
) -> str:
    """Return one clean text value."""

    return str(
        value or ""
    ).strip()


def _report_path(
    report: dict[str, Any],
) -> str:
    """Return the first supported report path field."""

    return (
        _text(
            report.get(
                "report_path"
            )
        )
        or _text(
            report.get(
                "path"
            )
        )
        or _text(
            report.get(
                "file"
            )
        )
    )


def _report_type(
    report: dict[str, Any],
) -> str:
    """Return one investigator-friendly report type."""

    value = (
        _text(
            report.get(
                "title"
            )
        )
        or _text(
            report.get(
                "report_type"
            )
        )
        or _text(
            report.get(
                "type"
            )
        )
        or _text(
            report.get(
                "analysis_type"
            )
        )
        or "Investigation Report"
    )

    label = value.replace(
        "_",
        " ",
    ).title()

    replacements = {
        "Cdr": "CDR",
        "Ipdr": "IPDR",
        "Gprs": "GPRS",
        "Imei": "IMEI",
    }

    for source, replacement in replacements.items():
        label = label.replace(
            source,
            replacement,
        )

    return label


def _format_created_at(
    value: str,
) -> str:
    """Return one compact investigator-friendly timestamp."""

    text = _text(
        value
    )

    if not text:
        return ""

    normalized = text.replace(
        "Z",
        "+00:00",
    )

    try:
        created = datetime.fromisoformat(
            normalized
        )
    except ValueError:
        return text

    if created.tzinfo is not None:
        created = created.astimezone(
            _DISPLAY_TIME_ZONE
        )

    return created.strftime(
        "%d-%m-%Y %H:%M:%S IST"
    )



def _target(
    report: dict[str, Any],
    path: Path,
) -> str:
    """Return target metadata or a target parsed from the filename."""

    metadata = report.get(
        "metadata",
        {},
    )
    metadata = (
        metadata
        if isinstance(
            metadata,
            dict,
        )
        else {}
    )

    for key in (
        "target",
        "target_number",
        "msisdn",
        "subscriber",
    ):
        value = (
            _text(
                metadata.get(
                    key
                )
            )
            or _text(
                report.get(
                    key
                )
            )
        )

        if value:
            return value

    match = _TARGET_PATTERN.match(
        path.stem
    )

    return (
        match.group(
            "target"
        )
        if match
        else "—"
    )


def _created_at(
    report: dict[str, Any],
    path: Path,
) -> str:
    """Return stored creation time or a time parsed from the filename."""

    value = (
        _text(
            report.get(
                "generated_at"
            )
        )
        or _text(
            report.get(
                "created_at"
            )
        )
        or _text(
            report.get(
                "timestamp"
            )
        )
    )

    if value:
        return _format_created_at(
            value
        )

    match = _REPORT_TIME_PATTERN.search(
        path.stem
    )

    if not match:
        return "—"

    try:
        created = datetime.strptime(
            match.group(
                "created"
            ),
            "%Y%m%dT%H%M%S",
        )
    except ValueError:
        return "—"

    created = (
        created.replace(
            tzinfo=timezone.utc
        )
        .astimezone(
            _DISPLAY_TIME_ZONE
        )
    )

    return created.strftime(
        "%d-%m-%Y %H:%M:%S IST"
    )


def build_case_report_entries(
    reports: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    base_directory: str | Path | None = None,
) -> list[CaseReportEntry]:
    """Normalize and deduplicate user-facing report records."""

    entries: list[CaseReportEntry] = []
    seen_paths: set[str] = set()
    base_path = (
        Path(
            base_directory
        ).expanduser().resolve(
            strict=False
        )
        if base_directory is not None
        else None
    )

    for report in reports:
        if not isinstance(
            report,
            dict,
        ):
            continue

        path_text = _report_path(
            report
        )

        if not path_text:
            continue

        normalized = path_text.replace(
            "\\",
            "/",
        ).casefold()

        if any(
            marker in normalized
            for marker in _BACKEND_MARKERS
        ):
            continue

        path = Path(
            path_text
        ).expanduser()

        if (
            not path.is_absolute()
            and base_path is not None
        ):
            path = (
                base_path
                / path
            )

        path = path.resolve(
            strict=False
        )
        path_key = str(
            path
        )

        if path_key in seen_paths:
            continue

        seen_paths.add(
            path_key
        )

        contact = contact_map_path(
            path
        )
        route = movement_route_path(
            path
        )

        entries.append(
            CaseReportEntry(
                report_type=_report_type(
                    report
                ),
                target=_target(
                    report,
                    path,
                ),
                created_at=_created_at(
                    report,
                    path,
                ),
                report_path=path,
                contact_map_path=(
                    contact
                    if contact.is_file()
                    else None
                ),
                movement_route_path=(
                    route
                    if route.is_file()
                    else None
                ),
            )
        )

    return entries


def load_case_report_entries(
    case_id: str,
) -> list[CaseReportEntry]:
    """Load latest and registered reports for one case."""

    from modules.cases import list_case_reports
    from modules.cases.latest_reports import list_latest_reports

    latest: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []

    try:
        value = list_latest_reports(
            str(
                case_id
            )
        )
        if isinstance(
            value,
            (
                list,
                tuple,
            ),
        ):
            latest = list(
                value
            )
    except Exception:
        latest = []

    try:
        value = list_case_reports(
            str(
                case_id
            )
        )
        if isinstance(
            value,
            (
                list,
                tuple,
            ),
        ):
            history = list(
                value
            )
    except Exception:
        history = []

    active_case_directory = (
        PROJECT_ROOT
        / "cases"
        / "active"
        / str(
            case_id
        )
    )
    archived_case_directory = (
        PROJECT_ROOT
        / "cases"
        / "archived"
        / str(
            case_id
        )
    )
    case_directory = (
        active_case_directory
        if active_case_directory.is_dir()
        or not archived_case_directory.is_dir()
        else archived_case_directory
    )

    return build_case_report_entries(
        [
            *latest,
            *reversed(
                history
            ),
        ],
        base_directory=case_directory,
    )


class CaseReportsPage(QFrame):
    """Display reports and their available CDR map sidecars."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        case_id: str = "DEV-WORKSPACE",
        loader: Callable[
            [str],
            list[CaseReportEntry],
        ] = load_case_report_entries,
    ) -> None:
        super().__init__(
            parent
        )

        self._case_id = str(
            case_id
        ).strip() or "DEV-WORKSPACE"
        self._loader = loader
        self._entries: list[
            CaseReportEntry
        ] = []
        self._all_entries: list[
            CaseReportEntry
        ] = []

        self.setObjectName(
            "pageSurface"
        )

        self._summary = QLabel()
        self._summary.setObjectName(
            "cardText"
        )
        self._summary.setWordWrap(
            True
        )

        self._refresh_button = QPushButton(
            "Refresh Reports"
        )
        self._refresh_button.setObjectName(
            "secondaryButton"
        )
        self._refresh_button.clicked.connect(
            self.refresh
        )

        self._show_missing = QCheckBox(
            "Show Missing History"
        )
        self._show_missing.setObjectName(
            "cardText"
        )
        self._show_missing.setChecked(
            False
        )
        self._show_missing.toggled.connect(
            self._apply_filter
        )

        self._table = QTableWidget(
            0,
            7,
        )
        self._table.setObjectName(
            "reportTable"
        )
        self._table.setHorizontalHeaderLabels(
            [
                "Report Type",
                "Target",
                "Created",
                "Status",
                "Report",
                "Contact Map",
                "Movement Route",
            ]
        )
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setAlternatingRowColors(
            True
        )
        self._table.setSortingEnabled(
            True
        )
        self._table.verticalHeader().setVisible(
            False
        )
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(80)

        # Report Type uses the remaining available width.
        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )

        # Keep information columns within practical screen-safe widths.
        information_column_widths = {
            1: 150,  # Target
            2: 180,  # Created
            3: 110,  # Status
        }

        for column, width in information_column_widths.items():
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Interactive,
            )
            self._table.setColumnWidth(
                column,
                width,
            )

        # Action columns must always reserve enough space for buttons.
        action_column_widths = {
            4: 132,  # Open Report
            5: 112,  # Open Map
            6: 120,  # Open Route
        }

        for column, width in action_column_widths.items():
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Fixed,
            )
            self._table.setColumnWidth(
                column,
                width,
            )

        self._build_layout()
        self.refresh()

    @property
    def entries(
        self,
    ) -> tuple[CaseReportEntry, ...]:
        """Return currently displayed report entries."""

        return tuple(
            self._entries
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
            16
        )

        heading_row = QHBoxLayout()
        heading = QLabel(
            "Case Investigation Reports"
        )
        heading.setObjectName(
            "moduleTitle"
        )

        heading_row.addWidget(
            heading
        )
        heading_row.addStretch()
        heading_row.addWidget(
            self._show_missing
        )
        heading_row.addWidget(
            self._refresh_button
        )

        layout.addLayout(
            heading_row
        )
        layout.addWidget(
            self._summary
        )
        layout.addWidget(
            self._table,
            stretch=1,
        )

    def refresh(
        self,
    ) -> None:
        """Reload case reports and rebuild available actions."""

        try:
            self._all_entries = list(
                self._loader(
                    self._case_id
                )
            )
        except Exception as error:
            self._all_entries = []
            QMessageBox.warning(
                self,
                "Case Reports",
                (
                    "Case reports could not be loaded.\n"
                    f"{type(error).__name__}: {error}"
                ),
            )

        self._apply_filter()

    @staticmethod
    def _has_available_artifact(
        entry: CaseReportEntry,
    ) -> bool:
        """Return True when at least one user-facing artifact exists."""

        return any(
            path is not None
            and path.is_file()
            for path in (
                entry.report_path,
                entry.contact_map_path,
                entry.movement_route_path,
            )
        )

    def _apply_filter(
        self,
        checked: bool | None = None,
    ) -> None:
        """Apply the normal or missing-history report view."""

        del checked

        if self._show_missing.isChecked():
            self._entries = list(
                self._all_entries
            )
        else:
            self._entries = [
                entry
                for entry in self._all_entries
                if self._has_available_artifact(
                    entry
                )
            ]

        self._populate_table()

    def _populate_table(
        self,
    ) -> None:
        """Populate the report table from currently visible entries."""

        sorting_enabled = self._table.isSortingEnabled()
        self._table.setSortingEnabled(
            False
        )
        self._table.setRowCount(
            len(
                self._entries
            )
        )

        for row, entry in enumerate(
            self._entries
        ):
            values = (
                entry.report_type,
                entry.target,
                entry.created_at,
                (
                    "Available"
                    if entry.report_path.is_file()
                    else "File Missing"
                ),
            )

            for column, value in enumerate(
                values
            ):
                self._table.setItem(
                    row,
                    column,
                    self._sortable_item(
                        value,
                        column=column,
                    ),
                )

            self._table.setCellWidget(
                row,
                4,
                self._action_button(
                    "Open Report",
                    entry.report_path,
                    self._open_report,
                    unavailable_label="Missing",
                ),
            )
            self._table.setCellWidget(
                row,
                5,
                self._action_button(
                    "Open Map",
                    entry.contact_map_path,
                    self._open_contact_map,
                    unavailable_label="—",
                ),
            )
            self._table.setCellWidget(
                row,
                6,
                self._action_button(
                    "Open Route",
                    entry.movement_route_path,
                    self._open_movement_route,
                    unavailable_label="—",
                ),
            )

        self._table.setSortingEnabled(
            sorting_enabled
        )
        if sorting_enabled:
            self._table.sortItems(
                2,
                Qt.SortOrder.DescendingOrder,
            )

        available_entries = sum(
            self._has_available_artifact(
                entry
            )
            for entry in self._all_entries
        )
        hidden_count = (
            len(
                self._all_entries
            )
            - len(
                self._entries
            )
        )

    @staticmethod
    def _sortable_item(
        value: str,
        *,
        column: int,
    ) -> QTableWidgetItem:
        """Create an item with a stable investigator-friendly sort value."""

        sort_value: object = value.casefold()

        if column == 1:
            digits = re.sub(r"\D", "", value)
            sort_value = int(digits) if digits else -1
        elif column == 2:
            try:
                sort_value = datetime.strptime(
                    value.removesuffix(" IST").strip(),
                    "%d-%m-%Y %H:%M:%S",
                ).timestamp()
            except ValueError:
                sort_value = -1.0

        return _ReportSortItem(value, sort_value)
        self._summary.setText(
            (
                f"Case: {self._case_id} | "
                f"Available report groups: {available_entries} | "
                f"Rows shown: {len(self._entries)}"
                + (
                    f" | Missing history hidden: {hidden_count}"
                    if hidden_count
                    else ""
                )
                + ". Map and route actions appear only when their files exist."
            )
        )

    def _action_button(
        self,
        label: str,
        path: Path | None,
        action: Callable[
            [Path],
            None,
        ],
        *,
        unavailable_label: str,
    ) -> QPushButton:
        """Create one path-bound table action."""

        button = QPushButton(
            (
                label
                if path is not None
                and path.is_file()
                else unavailable_label
            )
        )
        button.setObjectName(
            "secondaryButton"
        )
        button.setMinimumHeight(32)
        button.setToolTip(
    (
        f"{label}: {path.name}"
        if path is not None
        else unavailable_label
    )
)
        button.setEnabled(
            bool(
                path
                and path.is_file()
            )
        )

        if path is not None:
            button.clicked.connect(
                lambda checked=False, selected=path: action(
                    selected
                )
            )

        return button

    def _open_report(
        self,
        path: Path,
    ) -> None:
        """Open one supported report inside the investigation GUI."""

        if not path.is_file():
            QMessageBox.warning(
                self,
                "Report Not Found",
                f"The report file is not available:\n{path}",
            )
            return

        if path.suffix.casefold() not in {".xlsx", ".xlsm"}:
            QMessageBox.warning(
                self,
                "Open Report",
                "Internal viewing currently supports Excel .xlsx and .xlsm reports.",
            )
            return

        ReportViewerDialog(
            path,
            self,
        ).exec()

    def _open_contact_map(
        self,
        path: Path,
    ) -> None:
        """Open one saved Contact Tower Map."""

        ContactMapDialog(
            path,
            self,
        ).exec()

    def _open_movement_route(
        self,
        path: Path,
    ) -> None:
        """Open one saved Target Movement Route."""

        ContactMapDialog(
            path,
            self,
            window_title="CDR Target Movement Route",
            heading="Target Movement Route",
            caution=(
                "The line connects serving towers in chronological order. "
                "It does not prove the exact road or exact handset location."
            ),
        ).exec()
