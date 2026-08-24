"""Read-only active case details page for the desktop GUI."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from modules.cases import get_case_overview

_CASE_FIELDS = (
    ("case_id", "Case ID"),
    ("case_name", "Case Name"),
    ("fir_number", "FIR / Reference Number"),
    ("incident_date", "Incident Date"),
    ("incident_location", "Incident Location"),
    ("investigator", "Investigator"),
    ("unit_name", "Police Unit"),
    ("status", "Case Status"),
    ("source_timezone", "Evidence Time Zone"),
    ("created_at", "Created At"),
    ("updated_at", "Last Updated"),
    ("description", "Description"),
)


def load_active_case_overview() -> dict[str, Any]:
    """Load the direct-analysis case through the public case service."""

    from modules.controllers.app_controller import (
        get_direct_analysis_workspace,
    )

    case = get_direct_analysis_workspace()
    return get_case_overview(str(case.get("case_id", "")))


def _display_value(value: object) -> str:
    text = str(value if value is not None else "").strip()
    return text or "-"


def _format_bytes(value: object) -> str:
    try:
        size = max(int(str(value or 0)), 0)
    except (TypeError, ValueError):
        return "-"

    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(size)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{int(amount):,} {unit}" if unit == "B" else f"{amount:,.1f} {unit}"
        amount /= 1024
    return f"{size:,} B"


def _format_timestamp(value: object, timezone_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return text

    if parsed.tzinfo is None:
        return parsed.strftime("%d-%m-%Y %H:%M:%S")

    try:
        target_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        target_timezone = ZoneInfo("UTC")

    return parsed.astimezone(target_timezone).strftime("%d-%m-%Y %H:%M:%S %Z")


class CaseDetailsPage(QFrame):
    """Display active case metadata, evidence and activity summaries."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        loader: Callable[[], dict[str, Any]] = load_active_case_overview,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageSurface")
        self._loader = loader
        self._overview: dict[str, Any] = {}

        self._audit_badge = QLabel("CHECKING")
        self._audit_badge.setObjectName("statusBadge")

        self._refresh_button = QPushButton("Refresh Case Details")
        self._refresh_button.setObjectName("secondaryButton")

        self._status_label = QLabel("Loading active case details...")
        self._status_label.setObjectName("statusText")
        self._status_label.setWordWrap(True)

        self._metric_values = {
            key: QLabel("0")
            for key in (
                "target_count",
                "evidence_file_count",
                "report_count",
                "analysis_run_count",
            )
        }
        for label in self._metric_values.values():
            label.setObjectName("metricValue")

        self._case_table = self._key_value_table()
        self._targets_table = self._table(("Type", "Target", "Description"))
        self._evidence_table = self._table(
            (
                "Evidence File",
                "Type",
                "Current Status",
                "Size",
                "Registered",
                "Source Reference",
            )
        )
        self._runs_table = self._table(
            (
                "Analysis",
                "Status",
                "Input Records",
                "Output Records",
                "Recorded",
            )
        )

        self._tabs = QTabWidget()
        self._tabs.setObjectName("lookupTabs")
        self._tabs.addTab(self._case_table, "Case Information")
        self._tabs.addTab(self._targets_table, "Targets")
        self._tabs.addTab(self._evidence_table, "Evidence")
        self._tabs.addTab(self._runs_table, "Recent Analyses")

        self._build_layout()
        self._refresh_button.clicked.connect(self.refresh)
        self.refresh()

    @property
    def overview(self) -> dict[str, Any]:
        """Return a shallow copy of the current case overview."""

        return dict(self._overview)

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(16)

        heading_row = QHBoxLayout()
        heading = QLabel("Active Investigation Case")
        heading.setObjectName("moduleTitle")
        heading_row.addWidget(heading)
        heading_row.addStretch()
        heading_row.addWidget(self._audit_badge)
        heading_row.addWidget(self._refresh_button)

        description = QLabel(
            "Review the active case identity, registered targets, current "
            "evidence files and recent analysis activity. This screen is "
            "read-only and does not modify case records."
        )
        description.setObjectName("moduleDescription")
        description.setWordWrap(True)

        metric_row = QHBoxLayout()
        metric_row.setSpacing(12)
        metric_labels = (
            ("target_count", "Registered Targets"),
            ("evidence_file_count", "Evidence Files"),
            ("report_count", "Reports Created"),
            ("analysis_run_count", "Analysis Runs"),
        )
        for key, label in metric_labels:
            metric_row.addWidget(
                self._metric_card(self._metric_values[key], label),
                stretch=1,
            )

        layout.addLayout(heading_row)
        layout.addWidget(description)
        layout.addLayout(metric_row)
        layout.addWidget(self._status_label)
        layout.addWidget(self._tabs, stretch=1)

    @staticmethod
    def _metric_card(value_label: QLabel, label: str) -> QFrame:
        card = QFrame()
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(3)
        title = QLabel(label)
        title.setObjectName("metricLabel")
        layout.addWidget(value_label)
        layout.addWidget(title)
        return card

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.setObjectName("dataTable")
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setWordWrap(False)

    @classmethod
    def _key_value_table(cls) -> QTableWidget:
        table = QTableWidget(0, 2)
        cls._configure_table(table)
        table.setHorizontalHeaderLabels(["Field", "Value"])
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        return table

    @classmethod
    def _table(cls, headers: tuple[str, ...]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        cls._configure_table(table)
        table.setHorizontalHeaderLabels(list(headers))
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        return table

    def refresh(self) -> None:
        """Reload active case details from the read-only case service."""

        try:
            overview = self._loader()
            if not isinstance(overview, dict):
                raise TypeError("Case overview is not a valid mapping.")
        except Exception as error:  # noqa: BLE001 - keep the GUI responsive.
            self._overview = {}
            self._clear_tables()
            self._audit_badge.setText("UNAVAILABLE")
            self._audit_badge.setObjectName("warningBadge")
            self._refresh_style(self._audit_badge)
            self._status_label.setText(
                f"Case details could not be loaded. {type(error).__name__}: {error}"
            )
            return

        self._overview = overview
        self._populate_overview()

    def _populate_overview(self) -> None:
        case = self._mapping(self._overview.get("case"))
        summary = self._mapping(self._overview.get("summary"))
        audit = self._mapping(self._overview.get("audit"))
        timezone_name = str(case.get("source_timezone", "Asia/Kolkata"))

        for key, label in self._metric_values.items():
            try:
                count = int(summary.get(key, 0) or 0)
            except (TypeError, ValueError):
                count = 0
            label.setText(f"{count:,}")

        self._populate_case_table(case, timezone_name)
        self._populate_targets()
        self._populate_evidence(timezone_name)
        self._populate_runs(timezone_name)

        audit_valid = bool(audit.get("valid"))
        event_count = int(audit.get("event_count", 0) or 0)
        self._audit_badge.setText(
            "AUDIT VERIFIED" if audit_valid else "AUDIT REVIEW NEEDED"
        )
        self._audit_badge.setObjectName(
            "statusBadge" if audit_valid else "warningBadge"
        )
        self._refresh_style(self._audit_badge)
        self._status_label.setText(
            f"Case: {_display_value(case.get('case_id'))} | "
            f"Status: {_display_value(case.get('status')).title()} | "
            f"Verified audit events: {event_count:,}"
        )

    def _populate_case_table(
        self,
        case: dict[str, Any],
        timezone_name: str,
    ) -> None:
        self._case_table.setRowCount(len(_CASE_FIELDS))
        for row, (key, label) in enumerate(_CASE_FIELDS):
            value = case.get(key)
            if key in {"created_at", "updated_at"}:
                value = _format_timestamp(value, timezone_name)
            self._set_item(self._case_table, row, 0, label)
            self._set_item(
                self._case_table,
                row,
                1,
                _display_value(value),
            )

    def _populate_targets(self) -> None:
        targets = self._records(self._overview.get("targets"))
        self._targets_table.setRowCount(len(targets))
        for row, record in enumerate(targets):
            values = (
                record.get("target_type"),
                record.get("target_value"),
                record.get("description"),
            )
            for column, value in enumerate(values):
                self._set_item(
                    self._targets_table,
                    row,
                    column,
                    _display_value(value),
                )

    def _populate_evidence(self, timezone_name: str) -> None:
        evidence = self._records(self._overview.get("evidence"))
        self._evidence_table.setRowCount(len(evidence))
        for row, record in enumerate(evidence):
            values = (
                record.get("file_name"),
                record.get("evidence_type"),
                record.get("change_status"),
                _format_bytes(record.get("file_size_bytes")),
                _format_timestamp(record.get("registered_at"), timezone_name),
                record.get("source_file"),
            )
            for column, value in enumerate(values):
                self._set_item(
                    self._evidence_table,
                    row,
                    column,
                    _display_value(value),
                )

    def _populate_runs(self, timezone_name: str) -> None:
        runs = self._records(self._overview.get("analysis_runs"))[:100]
        self._runs_table.setRowCount(len(runs))
        for row, record in enumerate(runs):
            values = (
                record.get("analysis_type"),
                record.get("status"),
                self._integer_text(record.get("input_records")),
                self._integer_text(record.get("output_records")),
                _format_timestamp(record.get("recorded_at"), timezone_name),
            )
            for column, value in enumerate(values):
                self._set_item(
                    self._runs_table,
                    row,
                    column,
                    _display_value(value),
                )

    def _clear_tables(self) -> None:
        for table in (
            self._case_table,
            self._targets_table,
            self._evidence_table,
            self._runs_table,
        ):
            table.setRowCount(0)
        for label in self._metric_values.values():
            label.setText("0")

    @staticmethod
    def _mapping(value: object) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _records(value: object) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [dict(item) for item in value if isinstance(item, dict)]

    @staticmethod
    def _integer_text(value: object) -> str:
        try:
            return f"{int(str(value or 0)):,}"
        except (TypeError, ValueError):
            return "0"

    @staticmethod
    def _set_item(
        table: QTableWidget,
        row: int,
        column: int,
        text: str,
    ) -> None:
        item = QTableWidgetItem(text)
        item.setToolTip(text)
        table.setItem(row, column, item)

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
