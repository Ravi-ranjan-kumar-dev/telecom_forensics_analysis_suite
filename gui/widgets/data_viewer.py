"""High-speed interactive forensic data viewer with cross-sheet search and on-demand Excel export."""

from __future__ import annotations

from typing import Any
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from modules.reporting.report_sanitizer import clean_report_dataframe


class FastPandasTableModel(QAbstractTableModel):
    """Virtual Qt Table Model backed directly by a pandas DataFrame for instant rendering."""

    def __init__(self, df: pd.DataFrame | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._df = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
        self._headers = [str(c) for c in self._df.columns]
        if not self._df.empty:
            safe_df = self._df.copy()
            for col in safe_df.columns:
                safe_df[col] = safe_df[col].apply(
                    lambda v: "" if pd.isna(v) else str(v)
                )
            self._matrix = safe_df.to_numpy()
        else:
            self._matrix = None

    def set_dataframe(self, df: pd.DataFrame) -> None:
        self.beginResetModel()
        self._df = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
        self._headers = [str(c) for c in self._df.columns]
        if not self._df.empty:
            safe_df = self._df.copy()
            for col in safe_df.columns:
                safe_df[col] = safe_df[col].apply(
                    lambda v: "" if pd.isna(v) else str(v)
                )
            self._matrix = safe_df.to_numpy()
        else:
            self._matrix = None
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid() or self._matrix is None:
            return 0
        return int(self._matrix.shape[0])

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or self._matrix is None:
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return str(self._matrix[index.row(), index.column()])
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self._headers):
            return self._headers[section]
        if orientation == Qt.Orientation.Vertical:
            return str(section + 1)
        return None


class ForensicDataViewer(QWidget):
    """Interactive multi-sheet forensic viewer with instant search and on-demand .xlsx export."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.datasets: dict[str, pd.DataFrame] = {}
        self.current_df = pd.DataFrame()

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.sheet_combo = QComboBox()
        self.sheet_combo.setObjectName("inputControl")
        self.sheet_combo.setMinimumWidth(250)
        self.sheet_combo.currentIndexChanged.connect(self._on_sheet_changed)

        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("inputControl")
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.setPlaceholderText(
            "Search Mobile No., IP, Port, App, IMEI, Cell ID or Name..."
        )
        self.search_bar.textChanged.connect(self._apply_filter)
        self.search_bar.returnPressed.connect(self.search_across_all_sheets)

        self.search_all_btn = QPushButton("Search All Sheets")
        self.search_all_btn.setObjectName("secondaryButton")
        self.search_all_btn.clicked.connect(self.search_across_all_sheets)

        self.export_btn = QPushButton("Export Current View (.xlsx)")
        self.export_btn.setObjectName("primaryButton")
        self.export_btn.clicked.connect(self.export_to_excel)

        self.export_all_btn = QPushButton("Export All Sheets (.xlsx)")
        self.export_all_btn.setObjectName("secondaryButton")
        self.export_all_btn.clicked.connect(self.export_all_sheets_to_excel)

        toolbar.addWidget(QLabel("Analyzed Table:"))
        toolbar.addWidget(self.sheet_combo)
        toolbar.addWidget(self.search_bar, stretch=1)
        toolbar.addWidget(self.search_all_btn)
        toolbar.addWidget(self.export_btn)
        toolbar.addWidget(self.export_all_btn)

        self.layout.addLayout(toolbar)

        self.row_count_label = QLabel("Run analysis to view interactive results here.")
        self.row_count_label.setObjectName("cardText")
        self.layout.addWidget(self.row_count_label)

        self.table_view = QTableView()
        self.table_view.setObjectName("dataTable")
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSortingEnabled(True)
        self.table_view.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.layout.addWidget(self.table_view, stretch=1)

        self.fast_model = FastPandasTableModel(pd.DataFrame(), self)
        self.model = QStandardItemModel()
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.fast_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)
        self.table_view.setModel(self.proxy_model)

    def load_dataframe(
        self,
        data: pd.DataFrame | dict[str, pd.DataFrame],
        dataset_name: str = "Analyzed Data",
    ) -> None:
        self.sheet_combo.blockSignals(True)
        self.sheet_combo.clear()

        if isinstance(data, dict):
            cleaned_dict: dict[str, pd.DataFrame] = {}
            for name, frame in data.items():
                if isinstance(frame, pd.DataFrame) and not frame.empty:
                    cleaned_dict[str(name)] = frame
            self.datasets = cleaned_dict
        elif isinstance(data, pd.DataFrame):
            cleaned = clean_report_dataframe(data, clean_headers=False)
            self.datasets = {dataset_name: cleaned if not cleaned.empty else data}
        else:
            self.datasets = {}

        for name, frame in self.datasets.items():
            self.sheet_combo.addItem(f"{name} ({len(frame):,})", name)
        self.sheet_combo.blockSignals(False)

        if self.datasets:
            self.sheet_combo.setCurrentIndex(0)
            self._on_sheet_changed()
        else:
            self.current_df = pd.DataFrame()
            self.fast_model.set_dataframe(self.current_df)
            self.row_count_label.setText("No records available.")

    def _on_sheet_changed(self) -> None:
        sheet_key = self.sheet_combo.currentData() or self.sheet_combo.currentText()
        if not sheet_key or sheet_key not in self.datasets:
            return

        self.current_df = self.datasets[sheet_key]
        self.search_bar.blockSignals(True)
        self.search_bar.clear()
        self.search_bar.blockSignals(False)
        self.proxy_model.setFilterFixedString("")

        self.fast_model.set_dataframe(self.current_df)
        self.table_view.resizeColumnsToContents()
        self._update_row_count_label()

    def _apply_filter(self, text: str) -> None:
        self.proxy_model.setFilterFixedString(text.strip())
        self._update_row_count_label()

    def _update_row_count_label(self) -> None:
        total = len(self.current_df)
        visible = self.proxy_model.rowCount()
        sheet_key = self.sheet_combo.currentData() or self.sheet_combo.currentText()
        if total == 0:
            self.row_count_label.setText(f"Table: {sheet_key} | 0 records")
        elif visible == total:
            self.row_count_label.setText(
                f"Table: {sheet_key} | Showing all {total:,} record(s) across {len(self.current_df.columns)} column(s)."
            )
        else:
            self.row_count_label.setText(
                f"Table: {sheet_key} | Filtered matches: {visible:,} of {total:,} record(s)."
            )

    def search_across_all_sheets(self) -> None:
        query = self.search_bar.text().strip()
        if not query or not self.datasets:
            return

        q_low = query.casefold()
        matched_frames: list[pd.DataFrame] = []

        for sheet_name, df in self.datasets.items():
            if sheet_name.startswith("Search Hits:") or df.empty:
                continue
            str_df = df.astype("object").fillna("").astype(str)
            mask = str_df.apply(
                lambda col: col.str.casefold().str.contains(q_low, regex=False, na=False)
            ).any(axis=1)
            hits = df.loc[mask].copy()
            if not hits.empty:
                hits.insert(0, "Matched Table", sheet_name)
                matched_frames.append(hits)

        if not matched_frames:
            QMessageBox.information(
                self,
                "Global Search",
                f"No records matching '{query}' were found across loaded tables.",
            )
            return

        combined_hits = pd.concat(matched_frames, ignore_index=True, sort=False)
        hit_sheet_name = f"Search Hits: {query[:20]}"
        self.datasets[hit_sheet_name] = combined_hits

        existing_idx = self.sheet_combo.findData(hit_sheet_name)
        self.sheet_combo.blockSignals(True)
        if existing_idx >= 0:
            self.sheet_combo.setItemText(
                existing_idx, f"{hit_sheet_name} ({len(combined_hits):,})"
            )
            self.sheet_combo.setCurrentIndex(existing_idx)
        else:
            self.sheet_combo.insertItem(
                0, f"{hit_sheet_name} ({len(combined_hits):,})", hit_sheet_name
            )
            self.sheet_combo.setCurrentIndex(0)
        self.sheet_combo.blockSignals(False)
        self._on_sheet_changed()

    def _current_filtered_dataframe(self) -> pd.DataFrame:
        if self.current_df.empty:
            return pd.DataFrame()
        rows = self.proxy_model.rowCount()
        if rows == len(self.current_df) and not self.search_bar.text().strip():
            return self.current_df.copy()
        source_indices = [
            self.proxy_model.mapToSource(self.proxy_model.index(r, 0)).row()
            for r in range(rows)
        ]
        return self.current_df.iloc[source_indices].reset_index(drop=True)

    def export_to_excel(self) -> None:
        filtered_df = self._current_filtered_dataframe()
        if filtered_df.empty:
            QMessageBox.warning(self, "No Data", "There are no visible rows to export.")
            return

        sheet_key = str(self.sheet_combo.currentData() or "Analyzed_View")
        safe_default = "".join(c if c.isalnum() or c in "-_" else "_" for c in sheet_key)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Current Filtered View",
            f"{safe_default}.xlsx",
            "Excel Files (*.xlsx);;CSV Files (*.csv)",
        )
        if not path:
            return

        try:
            if path.lower().endswith(".csv"):
                filtered_df.to_csv(path, index=False)
            else:
                if not path.lower().endswith(".xlsx"):
                    path += ".xlsx"
                filtered_df.to_excel(path, index=False)
            QMessageBox.information(
                self,
                "Export Complete",
                f"Exported {len(filtered_df):,} row(s) successfully to:\n{path}",
            )
        except Exception as error:
            QMessageBox.critical(self, "Export Error", f"Failed to export data:\n{error}")

    def export_all_sheets_to_excel(self) -> None:
        if not self.datasets:
            QMessageBox.warning(self, "No Data", "No analyzed tables are loaded to export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export All Analyzed Tables to Excel",
            "Complete_Analyzed_Report.xlsx",
            "Excel Workbook (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                used_names: set[str] = set()
                for idx, (sheet_title, df) in enumerate(self.datasets.items(), start=1):
                    if df is None or df.empty:
                        continue
                    clean_name = "".join(
                        " " if c in "[]:*?/\\" else c for c in f"{idx}. {sheet_title}"
                    ).strip()[:31]
                    if clean_name.lower() in used_names:
                        clean_name = f"{clean_name[:28]}_{idx}"
                    used_names.add(clean_name.lower())
                    df.head(100_000).to_excel(writer, sheet_name=clean_name, index=False)
            QMessageBox.information(
                self,
                "Workbook Exported",
                f"All {len(self.datasets)} analyzed table(s) exported to:\n{path}",
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to export multi-sheet workbook:\n{error}",
            )
