"""Interactive dialog to inspect full-dump suspect & B-Party search results."""

from __future__ import annotations

from typing import Any

import pandas as pd
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class TowerDumpSearchDialog(QDialog):
    """Display Suspect Role, Linked B-Parties (with SDR) and 100% Matched Dump Rows."""

    def __init__(
        self,
        search_result: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._result = search_result
        targets = ", ".join(search_result.get("targets", []))
        self.setWindowTitle(f"Full Tower Dump Search — {targets}")
        self.resize(1320, 780)
        self.setModal(True)

        self._suspect_df: pd.DataFrame = search_result.get(
            "suspect_summary", pd.DataFrame()
        )
        self._counterparty_df: pd.DataFrame = search_result.get(
            "counterparty_summary", pd.DataFrame()
        )
        self._records_df: pd.DataFrame = search_result.get(
            "matched_records", pd.DataFrame()
        )

        title = QLabel(f"Full Tower Dump Suspect & B-Party Search: {targets}")
        title.setObjectName("moduleTitle")

        total_dump = int(search_result.get("total_dump_records", 0) or 0)
        matched_count = int(search_result.get("matched_count", 0) or 0)
        summary = QLabel(
            f"Scanned 100% Full Tower Dump: {total_dump:,} total records | "
            f"Matched records: {matched_count:,} | "
            f"Linked B-Parties / Endpoints: {len(self._counterparty_df):,}"
        )
        summary.setObjectName("cardText")
        summary.setWordWrap(True)

        filter_row = QHBoxLayout()
        self._filter_edit = QLineEdit()
        self._filter_edit.setObjectName("inputControl")
        self._filter_edit.setPlaceholderText(
            "Filter current tab by B-Party number, Cell ID, Spot, IMEI, or SDR Name..."
        )
        self._filter_edit.setClearButtonEnabled(True)
        self._filter_edit.textChanged.connect(self._apply_filter)

        export_btn = QPushButton("Export Search Report to Excel (.xlsx)")
        export_btn.setObjectName("primaryButton")
        export_btn.clicked.connect(self._export_excel)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.accept)

        filter_row.addWidget(QLabel("Quick Filter:"))
        filter_row.addWidget(self._filter_edit, stretch=1)
        filter_row.addWidget(export_btn)
        filter_row.addWidget(close_btn)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("lookupTabs")

        self._suspect_table = self._build_table(self._suspect_df)
        self._counterparty_table = self._build_table(self._counterparty_df)
        self._records_table = self._build_table(self._records_df.head(5000))

        self._tabs.addTab(
            self._suspect_table,
            f"1. Suspect Role & Overview ({len(self._suspect_df)})",
        )
        self._tabs.addTab(
            self._counterparty_table,
            f"2. Linked B-Party / Counterparties ({len(self._counterparty_df)})",
        )
        self._tabs.addTab(
            self._records_table,
            f"3. All Matched Dump Records ({len(self._records_df):,})",
        )
        self._tabs.currentChanged.connect(lambda _idx: self._apply_filter())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(summary)
        layout.addLayout(filter_row)
        layout.addWidget(self._tabs, stretch=1)

    @staticmethod
    def _build_table(df: pd.DataFrame) -> QTableWidget:
        if df is None or df.empty:
            table = QTableWidget(0, 1)
            table.setHorizontalHeaderLabels(["Info"])
            return table

        cols = [str(c) for c in df.columns]
        table = QTableWidget(len(df), len(cols))
        table.setObjectName("dataTable")
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setHorizontalHeaderLabels(cols)

        for r_idx, row in enumerate(df.itertuples(index=False, name=None)):
            for c_idx, val in enumerate(row):
                text = "" if val is None or pd.isna(val) else str(val).strip()
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                table.setItem(r_idx, c_idx, item)

        table.setSortingEnabled(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.resizeColumnsToContents()
        return table

    def _apply_filter(self) -> None:
        query = self._filter_edit.text().strip().casefold()
        current_widget = self._tabs.currentWidget()
        if not isinstance(current_widget, QTableWidget):
            return
        for row in range(current_widget.rowCount()):
            if not query:
                current_widget.setRowHidden(row, False)
                continue
            matched = False
            for col in range(current_widget.columnCount()):
                item = current_widget.item(row, col)
                if item is not None and query in item.text().casefold():
                    matched = True
                    break
            current_widget.setRowHidden(row, not matched)

    def _export_excel(self) -> None:
        targets_slug = "_".join(self._result.get("targets", ["suspect"]))[:40]
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Full Dump Suspect Search Report",
            f"Tower_Dump_Search_{targets_slug}.xlsx",
            "Excel Workbook (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                self._suspect_df.to_excel(
                    writer, sheet_name="1_Suspect_Overview", index=False
                )
                self._counterparty_df.to_excel(
                    writer, sheet_name="2_Linked_B_Parties", index=False
                )
                self._records_df.head(100000).to_excel(
                    writer, sheet_name="3_Matched_Dump_Records", index=False
                )
            QMessageBox.information(
                self,
                "Export Completed",
                f"Full-dump search report saved:\n{path}",
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Could not save Excel report:\n{error}",
            )
