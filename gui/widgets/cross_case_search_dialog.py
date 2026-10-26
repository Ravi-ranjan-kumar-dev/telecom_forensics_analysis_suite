"""Interactive Cross-Case Mobile / IMEI / CGI Search Dialog for EthicalArmor."""

from __future__ import annotations

from typing import Callable
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.reporting.cross_case_intelligence import search_across_all_cases


class CrossCaseSearchDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        initial_query: str = "",
        on_send_to_viewer: Callable[[dict[str, pd.DataFrame]], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cross-Case Intelligence Search (All Cases, Reports & Evidence)")
        self.resize(1120, 680)
        self._results: dict[str, pd.DataFrame] = {}
        self._on_send_to_viewer = on_send_to_viewer

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Cross-Case Mobile Number / IMEI / IMSI / CGI / IP Search")
        title.setObjectName("moduleTitle")
        layout.addWidget(title)

        sub = QLabel(
            "Enter one or more comma-separated Mobile Numbers, IMEIs, IMSIs, Cell IDs, or IPs to scan across all saved cases, "
            "staged Parquet/DuckDB stores, raw CSV evidence, and Excel reports."
        )
        sub.setWordWrap(True)
        layout.addWidget(sub)

        search_row = QHBoxLayout()
        self.query_input = QLineEdit(self)
        self.query_input.setPlaceholderText("e.g. 9876543210, 864201098765432, 404-10-1234-56789")
        self.query_input.setText(initial_query)
        self.query_input.returnPressed.connect(self.run_search)
        search_row.addWidget(self.query_input, stretch=1)

        self.search_btn = QPushButton("Scan All Cases", self)
        self.search_btn.setObjectName("primaryButton")
        self.search_btn.clicked.connect(self.run_search)
        search_row.addWidget(self.search_btn)

        self.send_viewer_btn = QPushButton("Load into Main Viewer", self)
        self.send_viewer_btn.setObjectName("secondaryButton")
        self.send_viewer_btn.setEnabled(False)
        self.send_viewer_btn.clicked.connect(self._send_to_viewer)
        search_row.addWidget(self.send_viewer_btn)

        self.export_btn = QPushButton("Export Cross-Case Excel", self)
        self.export_btn.setObjectName("secondaryButton")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_excel)
        search_row.addWidget(self.export_btn)

        layout.addLayout(search_row)

        self.status_label = QLabel("Ready to scan all cases.")
        self.status_label.setObjectName("statusBadge")
        layout.addWidget(self.status_label)

        self.tabs = QTabWidget(self)
        self.summary_table = QTableWidget(self)
        self.detail_table = QTableWidget(self)
        self.tabs.addTab(self.summary_table, "Case Match Summary")
        self.tabs.addTab(self.detail_table, "Detailed Matched Records")
        layout.addWidget(self.tabs, stretch=1)

        if initial_query.strip():
            self.run_search()

    def _populate_table(self, table: QTableWidget, df: pd.DataFrame) -> None:
        table.clear()
        if df is None or df.empty:
            table.setRowCount(1)
            table.setColumnCount(1)
            table.setHorizontalHeaderLabels(["Info"])
            table.setItem(0, 0, QTableWidgetItem("No matching records found across saved cases."))
            return

        cols = [str(c) for c in df.columns]
        table.setColumnCount(len(cols))
        table.setRowCount(len(df))
        table.setHorizontalHeaderLabels(cols)

        for r_idx, row in enumerate(df.itertuples(index=False)):
            for c_idx, val in enumerate(row):
                item = QTableWidgetItem("" if val is None else str(val))
                item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                table.setItem(r_idx, c_idx, item)

        header = table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setStretchLastSection(True)

    def run_search(self) -> None:
        q = self.query_input.text().strip()
        if not q:
            QMessageBox.information(self, "Cross-Case Search", "Enter at least one Mobile Number, IMEI, IMSI, or CGI.")
            return

        self.status_label.setText(f"Scanning all cases and reports for: {q} ...")
        self.search_btn.setEnabled(False)
        try:
            self._results = search_across_all_cases(q)
            sum_df = self._results.get("Cross-Case Summary", pd.DataFrame())
            det_df = self._results.get("Cross-Case Detailed Hits", pd.DataFrame())

            self._populate_table(self.summary_table, sum_df)
            self._populate_table(self.detail_table, det_df)

            total_files = len(sum_df)
            total_hits = int(sum_df["Total Matches"].sum()) if not sum_df.empty and "Total Matches" in sum_df.columns else 0
            unique_cases = sum_df["Case ID / Folder"].nunique() if not sum_df.empty and "Case ID / Folder" in sum_df.columns else 0

            self.status_label.setText(
                f"Scan Complete | Matched Cases: {unique_cases} | Matched Files/Sheets: {total_files} | Total Record Hits: {total_hits:,}"
            )
            has_hits = not sum_df.empty
            self.export_btn.setEnabled(has_hits)
            self.send_viewer_btn.setEnabled(has_hits and self._on_send_to_viewer is not None)
        except Exception as err:
            QMessageBox.warning(self, "Cross-Case Search Error", str(err))
            self.status_label.setText("Search failed.")
        finally:
            self.search_btn.setEnabled(True)

    def _send_to_viewer(self) -> None:
        if self._on_send_to_viewer and self._results:
            self._on_send_to_viewer(self._results)
            QMessageBox.information(
                self,
                "Loaded into Viewer",
                "Cross-Case Summary and Detailed Hits tabs have been added to your current Interactive Viewer dropdown.",
            )

    def _export_excel(self) -> None:
        sum_df = self._results.get("Cross-Case Summary", pd.DataFrame())
        det_df = self._results.get("Cross-Case Detailed Hits", pd.DataFrame())
        if sum_df.empty and det_df.empty:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Cross-Case Intelligence Report",
            "Cross_Case_Intelligence_Report.xlsx",
            "Excel Files (*.xlsx)",
        )
        if not file_path:
            return
        try:
            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                sum_out = sum_df.copy()
                sum_out.attrs = {}
                det_out = det_df.copy()
                det_out.attrs = {}
                sum_out.to_excel(writer, sheet_name="Cross_Case_Summary", index=False)
                det_out.to_excel(writer, sheet_name="Detailed_Matched_Records", index=False)
            QMessageBox.information(self, "Export Complete", f"Saved Cross-Case Report to:\n{file_path}")
        except Exception as err:
            QMessageBox.warning(self, "Export Error", str(err))
