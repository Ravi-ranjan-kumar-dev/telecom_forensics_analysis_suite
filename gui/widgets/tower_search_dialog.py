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

        title = QLabel(f"Full Tower Dump Search: {targets}")
        title.setObjectName("moduleTitle")

        total_dump = int(search_result.get("total_dump_records", 0) or 0)
        matched_count = int(search_result.get("matched_count", 0) or 0)
        summary = QLabel(
            f"Scanned 100% Full Tower Dump: {total_dump:,} total records | "
            f"Matched records: {matched_count:,} | Displayed preview: {len(self._records_df):,} | "
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

        export_btn = QPushButton("Export Search Preview (.xlsx)")
        export_btn.setObjectName("primaryButton")
        export_btn.clicked.connect(self._export_excel)
        self._ea_export_running = False
        self._full_export_btn = QPushButton("Export All Matches")
        self._full_export_btn.setObjectName("primaryButton")
        self._full_export_btn.setToolTip("Export all staged-SQL matches, not GUI preview")
        self._full_export_btn.setEnabled(bool(search_result.get("full_export_request")))
        self._full_export_btn.clicked.connect(self._export_full_matches)
        self._full_export_status = QLabel("Full matching records: use Export All Matches (CSV/Excel).")

        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.accept)

        filter_row.addWidget(QLabel("Quick Filter:"))
        filter_row.addWidget(self._filter_edit, stretch=1)
        filter_row.addWidget(export_btn)
        filter_row.addWidget(self._full_export_btn)
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
            f"2. {search_result.get('endpoint_description', 'Linked B-Party / Counterparties')} ({len(self._counterparty_df)})",
        )
        self._tabs.addTab(
            self._records_table,
            f"3. Matched Records Preview ({len(self._records_df):,})",
        )
        self._tabs.currentChanged.connect(lambda _idx: self._apply_filter())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(summary)
        layout.addWidget(self._full_export_status)
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

    def _export_full_matches(self) -> None:
        """Export the entire staged-SQL result, not the dialog's bounded DataFrame."""
        if getattr(self, "_ea_export_running", False):
            return
        request = self._result.get("full_export_request")
        if not isinstance(request, dict):
            QMessageBox.warning(self, "Export unavailable", "Rerun Full Dump Search to enable complete export.")
            return
        from pathlib import Path
        from PySide6.QtCore import QThread
        from gui.workers.full_match_export_worker import FullMatchExportWorker

        file_path, chosen_filter = QFileDialog.getSaveFileName(
            self, "Export ALL Matching Records", "Tower_Dump_Matched_Records.csv",
            "CSV (recommended for large data) (*.csv);;Excel Workbook (*.xlsx)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith((".csv", ".xlsx")):
            file_path += ".xlsx" if "xlsx" in chosen_filter else ".csv"
        destination = Path(file_path).expanduser()
        if destination.exists():
            answer = QMessageBox.question(
                self, "Confirm overwrite", f"Replace existing file?\n{destination}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self._ea_export_running = True
        self._full_export_btn.setEnabled(False)
        self._full_export_status.setText("Exporting all matching rows in background...")
        thread = QThread(self)
        worker = FullMatchExportWorker(request, str(destination))
        worker.moveToThread(thread)
        self._ea_export_thread = thread
        self._ea_export_worker = worker

        def update_progress(row_count: int):
            self._full_export_status.setText(f"Exporting all matches: {row_count:,} rows written...")

        def complete(info: dict):
            self._full_export_status.setText(
                f"Exported {info['rows']:,} matching records ({info['columns']} columns)."
            )
            QMessageBox.information(
                self, "Export Complete",
                f"Saved: {info['path']}\nRows: {info['rows']:,}\n"
                f"Source records: {info['total_records']:,}\nSHA-256: {info['sha256']}",
            )

        def failed(message: str):
            self._full_export_status.setText("Export failed. No incomplete report published.")
            QMessageBox.warning(self, "Full Export Failed", message)

        def finished():
            self._ea_export_running = False
            self._full_export_btn.setEnabled(True)
            self._ea_export_thread = None
            self._ea_export_worker = None

        thread.started.connect(worker.run)
        worker.progress.connect(update_progress)
        worker.completed.connect(complete)
        worker.failed.connect(failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def accept(self) -> None:
        if getattr(self, "_ea_export_running", False):
            QMessageBox.information(self, "Export active", "Export is running; keep this window open.")
            return
        super().accept()

    def reject(self) -> None:
        if getattr(self, "_ea_export_running", False):
            QMessageBox.information(self, "Export active", "Export is running; keep this window open.")
            return
        super().reject()

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
            # EA_HANDLED_DIAGNOSTICS_V1
            try:
                from modules.core.diagnostic_events import record_handled_exception as _ea_record_handled_exception
                _ea_record_handled_exception()
            except Exception:
                pass
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Could not save Excel report:\n{error}",
            )
