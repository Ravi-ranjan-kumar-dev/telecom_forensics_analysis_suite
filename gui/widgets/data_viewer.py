# Crash-proof interactive forensic data viewer for EthicalArmor
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
from typing import Any
import webbrowser
import pandas as pd
from PySide6.QtGui import QColor
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QThread, QRunnable, QThreadPool, QObject, Signal, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QDialog,
    QPlainTextEdit,
    QProgressBar,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from gui.utils.thread_dispatcher import run_on_main_thread
from modules.utils.cdr_column_sanitizer import sanitize_sheets_dict


def _safe_str_dataframe(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or (df.empty and len(df.columns) == 0):
        return pd.DataFrame()
    clean = df.copy()
    clean.attrs = {}
    if clean.columns.duplicated().any():
        clean = clean.loc[:, ~clean.columns.duplicated()]
    obj_df = clean.astype(object)
    obj_df = obj_df.where(pd.notna(obj_df), "")
    return obj_df.astype(str).replace({"<NA>": "", "nan": "", "None": "", "NaT": ""})


class _ExportSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)


class _ExportJob(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = _ExportSignals()

    def run(self):
        try:
            self.signals.completed.emit(self.function())
        except Exception as error:
            # EA_HANDLED_DIAGNOSTICS_V1
            try:
                from modules.core.diagnostic_events import record_handled_exception as _ea_record_handled_exception
                _ea_record_handled_exception()
            except Exception:
                pass
            self.signals.failed.emit(f"{type(error).__name__}: {error}")


class FastPandasTableModel(QAbstractTableModel):
    def __init__(self, df: pd.DataFrame | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._frame = df.copy(deep=False) if isinstance(df, pd.DataFrame) else pd.DataFrame()
        if df is None or (df.empty and len(df.columns) == 0):
            self._headers: list[str] = []
            self._rows: list[list[str]] = []
        else:
            safe_df = _safe_str_dataframe(df)
            self._headers = [str(c) for c in safe_df.columns]
            self._rows = [
                [str(cell) if cell is not None else "" for cell in row]
                for row in safe_df.to_numpy().tolist()
            ]

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        if column < 0 or column >= len(self._frame.columns) or self._frame.empty:
            return
        values = self._frame.iloc[:, column]
        numeric = pd.to_numeric(values, errors="coerce")
        key = numeric if numeric.notna().sum() == values.notna().sum() else values.fillna("").astype(str).str.casefold()
        positions = pd.DataFrame({"key": key.to_numpy(), "position": range(len(values))}).sort_values(
            "key", ascending=order == Qt.SortOrder.AscendingOrder, kind="stable", na_position="last"
        )["position"].tolist()
        self.layoutAboutToBeChanged.emit()
        self._frame = self._frame.iloc[positions].copy(deep=False)
        self._rows = _safe_str_dataframe(self._frame).to_numpy().tolist()
        parent = self.parent()
        if parent is not None and hasattr(parent, "_current_df"):
            parent._current_df = self._frame
            parent._bookmark_key_cache = {}
        self.layoutChanged.emit()
        if parent is not None and hasattr(parent,"_bookmark_selection_changed"):
            parent._bookmark_selection_changed()


    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.ToolTipRole):
            viewer = self.parent()
            if hasattr(viewer, "_is_row_bookmarked") and viewer._is_row_bookmarked(index.row()):
                return QColor("#384c38") if role == Qt.ItemDataRole.BackgroundRole else "Already bookmarked in this case"
        if role == Qt.ItemDataRole.DisplayRole:
            r = index.row()
            c = index.column()
            if 0 <= r < len(self._rows):
                row_vals = self._rows[r]
                if 0 <= c < len(row_vals):
                    return row_vals[c]
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._headers):
                return self._headers[section]
            return ""
        return str(section + 1)


class ForensicDataViewer(QWidget):
    def __init__(self, parent: QWidget | None = None, *, case_id=None, source_id="") -> None:
        super().__init__(parent)
        from modules.controllers.app_controller import get_active_gui_case_id
        self.case_id = str(case_id or get_active_gui_case_id())
        self.source_id = str(source_id)
        self._explicit_source_id = str(source_id)
        self._bookmark_ids = set()
        self._bookmark_key_cache = {}
        self._dialogs = []
        self._sheets: dict[str, pd.DataFrame] = {}
        self._analysis_sheets: dict[str, pd.DataFrame] = {}
        self._export_jobs = []
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(180)
        self._filter_timer.timeout.connect(lambda: self._apply_filter(self.search_input.text()))
        self._active_sheet_df: pd.DataFrame = pd.DataFrame()
        self._current_df: pd.DataFrame = pd.DataFrame()
        self._bookmarked_rows: list[dict[str, Any]] = []
        self._current_model: FastPandasTableModel | None = None
        self._retired_models: list[FastPandasTableModel] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # Primary Navigation & Search Toolbar
        toolbar = QFrame(self)
        toolbar.setObjectName("infoCard")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(10, 8, 10, 8)
        tb_layout.setSpacing(8)

        tb_layout.addWidget(QLabel("Sheet:", self))
        self.sheet_combo = QComboBox(self)
        self.sheet_combo.setMinimumWidth(230)
        self.sheet_combo.currentTextChanged.connect(self._on_sheet_changed)
        tb_layout.addWidget(self.sheet_combo)

        self.section_label = QLabel("Section:", self)
        self.section_label.setVisible(False)
        tb_layout.addWidget(self.section_label)

        self.section_combo = QComboBox(self)
        self.section_combo.setMinimumWidth(210)
        self.section_combo.setVisible(False)
        self.section_combo.currentTextChanged.connect(self._on_section_changed)
        tb_layout.addWidget(self.section_combo)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Filter rows in current sheet or search across all sheets...")
        self.search_input.textChanged.connect(lambda: self._filter_timer.start())
        self.search_input.setClearButtonEnabled(True)
        tb_layout.addWidget(self.search_input, stretch=1)
        self.filter_column = QComboBox(self)
        self.filter_column.addItem("All columns")
        self.filter_column.setMaximumWidth(180)
        self.filter_column.currentTextChanged.connect(lambda: self._apply_filter(self.search_input.text()))
        tb_layout.addWidget(self.filter_column)
        export_row = QHBoxLayout()

        self.global_search_btn = QPushButton("Search All Sheets", self)
        self.global_search_btn.setObjectName("secondaryButton")
        self.global_search_btn.clicked.connect(self._search_all_sheets)
        export_row.addWidget(self.global_search_btn)

        self.export_current_btn = QPushButton("Export Current View", self)
        self.export_current_btn.setObjectName("secondaryButton")
        self.export_current_btn.clicked.connect(self._export_current_view)
        export_row.addWidget(self.export_current_btn)

        self.export_all_btn = QPushButton("Export All Sheets (Excel)", self)
        self.export_all_btn.setObjectName("primaryButton")
        self.export_all_btn.clicked.connect(self._export_all_sheets)
        export_row.addWidget(self.export_all_btn)
        self.search_loaded_numbers_btn = QPushButton("Find Numbers · Loaded Sheets", self)
        self.search_loaded_numbers_btn.clicked.connect(self._search_loaded_numbers)
        export_row.addWidget(self.search_loaded_numbers_btn)

        root.addWidget(toolbar)
        root.addLayout(export_row)

        # Secondary Forensic Intelligence Bar (Bookmarks, Map, Link Graph, Court Brief)
        intel_bar = QFrame(self)
        intel_bar.setObjectName("infoCard")
        ib_layout = QGridLayout(intel_bar)
        ib_layout.setContentsMargins(10, 5, 10, 5)
        ib_layout.setSpacing(8)

        self.stats_label = QLabel("No data loaded.", self)
        self.stats_label.setObjectName("statusBadge")
        ib_layout.addWidget(self.stats_label, 0, 0, 1, 6)

        self.bookmark_btn = QPushButton("Bookmark Selected Row", self)
        self.bookmark_btn.setObjectName("secondaryButton")
        self.bookmark_btn.clicked.connect(self._bookmark_selected_rows)
        ib_layout.addWidget(self.bookmark_btn, 1, 0)

        self.view_bookmarks_btn = QPushButton("View Bookmarks (0)", self)
        self.view_bookmarks_btn.setObjectName("secondaryButton")
        self.view_bookmarks_btn.clicked.connect(lambda: self._open_case_lists("bookmarks"))
        ib_layout.addWidget(self.view_bookmarks_btn, 2, 0, 1, 2)
        self.case_numbers_btn = QPushButton("View Case Numbers", self)
        self.case_numbers_btn.setObjectName("secondaryButton")
        self.case_numbers_btn.clicked.connect(lambda: self._open_case_lists("numbers"))
        ib_layout.addWidget(self.case_numbers_btn, 2, 2, 1, 2)
        self.bookmark_status = QLabel(f"Case: {self.case_id} · Saved bookmarks are retained with this case.", self)
        self.bookmark_status.setWordWrap(True)
        ib_layout.addWidget(self.bookmark_status, 3, 0, 1, 6)

        self.map_btn = QPushButton("Tower Map (HTML)", self)
        self.map_btn.setObjectName("secondaryButton")
        self.map_btn.clicked.connect(self._open_interactive_map)
        ib_layout.addWidget(self.map_btn, 1, 1)

        self.graph_btn = QPushButton("Call Link Graph", self)
        self.graph_btn.setObjectName("secondaryButton")
        self.graph_btn.clicked.connect(self._open_call_link_graph)
        ib_layout.addWidget(self.graph_btn, 1, 2)

        self.court_brief_btn = QPushButton("Court Brief && SHA-256", self)
        self.court_brief_btn.setObjectName("secondaryButton")
        self.court_brief_btn.clicked.connect(self._open_court_forensic_brief)
        ib_layout.addWidget(self.court_brief_btn, 1, 3)

        self.cross_case_btn = QPushButton("Cross-Case Search", self)
        self.cross_case_btn.setObjectName("primaryButton")
        self.cross_case_btn.clicked.connect(self._open_cross_case_search)
        ib_layout.addWidget(self.cross_case_btn, 1, 4)

        self.database_btn = QPushButton("Database Status", self)
        self.database_btn.setObjectName("secondaryButton")
        self.database_btn.clicked.connect(self._show_database_status)
        ib_layout.addWidget(self.database_btn, 1, 5)
        self.export_progress = QProgressBar(self)
        self.export_progress.setRange(0, 0)
        self.export_progress.setMaximumHeight(5)
        self.export_progress.hide()
        root.addWidget(intel_bar)
        root.addWidget(self.export_progress)

        self.table_view = QTableView(self)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSortingEnabled(True)
        self.table_view.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        header = self.table_view.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setStretchLastSection(True)
        root.addWidget(self.table_view, stretch=1)

    def _set_table_dataframe(self, df: pd.DataFrame) -> None:
        self._current_df = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
        self._bookmark_key_cache = {}
        new_model = FastPandasTableModel(self._current_df, parent=self)
        old_model = self._current_model
        self._current_model = new_model
        self.table_view.setModel(new_model)
        self.table_view.selectionModel().selectionChanged.connect(self._bookmark_selection_changed)
        if "_Source_Row" in self._current_df:
            self.table_view.hideColumn(self._current_df.columns.get_loc("_Source_Row"))
        if old_model is not None:
            self._retired_models.append(old_model)
            if len(self._retired_models) > 5:
                retired = self._retired_models.pop(0)
                retired.deleteLater()

    def load_dataframe(self, data: pd.DataFrame | dict[str, pd.DataFrame]) -> None:
        app = QApplication.instance()
        if app is not None and QThread.currentThread() != app.thread():
            run_on_main_thread(lambda: self.load_dataframe(data))
            return

        if isinstance(data, pd.DataFrame):
            sheets = {"Results": data}
        elif isinstance(data, dict):
            sheets = {
                str(k): (v if isinstance(v, pd.DataFrame) else pd.DataFrame(v))
                for k, v in data.items()
                if v is not None
            }
        else:
            sheets = {}

        if not self._explicit_source_id:
            from uuid import uuid4
            identities = [str(f.attrs.get("analysis_run_id") or f.attrs.get("gui_snapshot_id")) for f in sheets.values()
                          if f.attrs.get("analysis_run_id") or f.attrs.get("gui_snapshot_id")]
            self.source_id = identities[0] if identities else "snapshot-" + uuid4().hex
            for frame in sheets.values():
                frame.attrs.setdefault("gui_snapshot_id", self.source_id)
        self._analysis_sheets = dict(sheets)
        self._reload_bookmarks()
        self._sheets = sanitize_sheets_dict(sheets)
        self.sheet_combo.blockSignals(True)
        self.sheet_combo.clear()
        for name in self._sheets.keys():
            self.sheet_combo.addItem(name)
        self.sheet_combo.blockSignals(False)

        if self._sheets:
            first_key = next(iter(self._sheets.keys()))
            self._on_sheet_changed(first_key)
        else:
            self._set_table_dataframe(pd.DataFrame())
            self.stats_label.setText("No rows available.")

    def _on_sheet_changed(self, sheet_name: str) -> None:
        if not sheet_name or sheet_name not in self._sheets:
            return
        df = self._sheets[sheet_name]
        sections = getattr(df, "attrs", {}).get("sections") if hasattr(df, "attrs") else None

        if isinstance(sections, dict) and len(sections) > 1:
            self.section_combo.blockSignals(True)
            self.section_combo.clear()
            for sec_name in sections.keys():
                self.section_combo.addItem(sec_name)
            default_sec = getattr(df, "attrs", {}).get("default_section")
            if default_sec and default_sec in sections:
                self.section_combo.setCurrentText(default_sec)
            self.section_combo.blockSignals(False)
            self.section_label.setVisible(True)
            self.section_combo.setVisible(True)
            active_sec = self.section_combo.currentText()
            self._active_sheet_df = sections.get(active_sec, df)
        else:
            self.section_label.setVisible(False)
            self.section_combo.setVisible(False)
            self._active_sheet_df = df

        self._refresh_active_view()

    def _on_section_changed(self, section_name: str) -> None:
        sheet_name = self.sheet_combo.currentText()
        if not sheet_name or sheet_name not in self._sheets:
            return
        df = self._sheets[sheet_name]
        sections = getattr(df, "attrs", {}).get("sections") if hasattr(df, "attrs") else None
        if isinstance(sections, dict) and section_name in sections:
            self._active_sheet_df = sections[section_name]
            self._refresh_active_view()

    def _refresh_active_view(self) -> None:
        sheet_name = self.sheet_combo.currentText()
        df = self._active_sheet_df
        previous = self.filter_column.currentText()
        self.filter_column.blockSignals(True)
        self.filter_column.clear()
        self.filter_column.addItem("All columns")
        self.filter_column.addItems([str(c) for c in df.columns])
        if previous in [str(c) for c in df.columns]:
            self.filter_column.setCurrentText(previous)
        self.filter_column.blockSignals(False)
        query = self.search_input.text().strip()
        if query:
            self._apply_filter(query)
        else:
            self._set_table_dataframe(df)
            sec_suffix = f" ({self.section_combo.currentText()})" if self.section_combo.isVisible() else ""
            self.stats_label.setText(
                f"Sheet: {sheet_name}{sec_suffix} | Rows: {len(df):,} | Columns: {len(df.columns)}"
            )

    def _apply_filter(self, text: str) -> None:
        sheet_name = self.sheet_combo.currentText()
        if not sheet_name or sheet_name not in self._sheets:
            return
        df = self._active_sheet_df if isinstance(self._active_sheet_df, pd.DataFrame) else self._sheets[sheet_name]
        q = text.strip().lower()
        sec_suffix = f" ({self.section_combo.currentText()})" if self.section_combo.isVisible() else ""
        if not q or df.empty:
            self._set_table_dataframe(df)
            self.stats_label.setText(
                f"Sheet: {sheet_name}{sec_suffix} | Rows: {len(df):,} | Columns: {len(df.columns)}"
            )
            return
        column = self.filter_column.currentText()
        searchable = df[[column]] if column != "All columns" and column in df.columns else df
        _clean_df = _safe_str_dataframe(searchable)
        mask = _clean_df.apply(lambda col: col.str.lower().str.contains(q, na=False, regex=False)).any(axis=1)
        filtered = df.loc[mask]
        self._set_table_dataframe(filtered)
        self.stats_label.setText(
            f"Sheet: {sheet_name}{sec_suffix} | Matches: {len(filtered):,} (Searched all {len(df):,} rows)"
        )

    def _search_all_sheets(self) -> None:
        q = self.search_input.text().strip().lower()
        if not q or not self._sheets:
            return
        combined_rows: list[pd.DataFrame] = []
        for s_name, df in self._sheets.items():
            if df is None:
                continue
            sections = getattr(df, "attrs", {}).get("sections") if hasattr(df, "attrs") else None
            if isinstance(sections, dict) and len(sections) > 1:
                for sec_name, sec_df in sections.items():
                    if sec_df is None or sec_df.empty:
                        continue
                    _clean_df = _safe_str_dataframe(sec_df)
                    mask = _clean_df.apply(lambda col: col.str.lower().str.contains(q, na=False, regex=False)).any(axis=1)
                    matched = _safe_str_dataframe(sec_df.loc[mask])
                    if not matched.empty:
                        matched.attrs = {}
                        matched.insert(0, "_Source_Row", [str(i) for i in matched.index])
                        matched.insert(0, "_Source_Sheet", f"{s_name} [{sec_name}]")
                        combined_rows.append(matched)
            else:
                if df.empty:
                    continue
                _clean_df = _safe_str_dataframe(df)
                mask = _clean_df.apply(lambda col: col.str.lower().str.contains(q, na=False, regex=False)).any(axis=1)
                matched = _safe_str_dataframe(df.loc[mask])
                if not matched.empty:
                    matched.attrs = {}
                    matched.insert(0, "_Source_Row", [str(i) for i in matched.index])
                    matched.insert(0, "_Source_Sheet", s_name)
                    combined_rows.append(matched)

        if combined_rows:
            merged = pd.concat(combined_rows, ignore_index=True)
            self._set_table_dataframe(merged)
            self.stats_label.setText(
                f"Global Search '{q}' | Total Matches Across All Sheets & Sections: {len(merged):,}"
            )
        else:
            self._set_table_dataframe(pd.DataFrame())
            self.stats_label.setText(f"Global Search '{q}' | 0 matches found.")

    def set_case_context(self, case_id, source_id=""):
        if case_id:
            self.case_id = str(case_id)
        self.source_id = str(source_id)
        self._explicit_source_id = str(source_id)
        self._bookmark_key_cache = {}
        self._reload_bookmarks()

    def _reload_bookmarks(self):
        from modules.cases.investigation import bookmarks_frame
        try:
            frame = bookmarks_frame(self.case_id)
            self._bookmarked_rows = frame.to_dict(orient="records")
            self._bookmark_ids = set(frame["Bookmark ID"]) if not frame.empty else set()
            self.view_bookmarks_btn.setText(f"View Bookmarks ({len(frame)})")
        except Exception as error:
            # EA_HANDLED_DIAGNOSTICS_V1
            try:
                from modules.core.diagnostic_events import record_handled_exception as _ea_record_handled_exception
                _ea_record_handled_exception()
            except Exception:
                pass
            self._bookmarked_rows = []
            self._bookmark_ids = set()
            self.bookmark_status.setText(f"Case {self.case_id}: bookmarks unavailable — {error}")
        self._bookmark_key_cache = {}
        if hasattr(self,"table_view"):
            self.table_view.viewport().update()

    def _bookmark_entry(self, position):
        from modules.cases.investigation import bookmark_id, text
        row = self._current_df.iloc[position].to_dict()
        if row.get("Bookmark ID"):
            return {"bookmark_id": str(row["Bookmark ID"])}
        sheet = text(row.pop("_Source_Sheet", self.sheet_combo.currentText()))
        if not self.section_combo.isHidden() and "_Source_Sheet" not in self._current_df:
            sheet += f" [{self.section_combo.currentText()}]"
        source_row = str(row.pop("_Source_Row", self._current_df.index[position]))
        return {"bookmark_id":bookmark_id(self.source_id,sheet,row,source_row),
                "source_id":self.source_id,"sheet":sheet,"source_row":source_row,"row_data":row}

    def _is_row_bookmarked(self, position):
        if position < 0 or position >= len(self._current_df):return False
        if position not in self._bookmark_key_cache:
            self._bookmark_key_cache[position] = self._bookmark_entry(position)["bookmark_id"]
        return self._bookmark_key_cache[position] in self._bookmark_ids

    def _bookmark_selection_changed(self,*_):
        selection = self.table_view.selectionModel()
        rows = selection.selectedRows() if selection else []
        already = bool(rows) and all(self._is_row_bookmarked(i.row()) for i in rows)
        self.bookmark_btn.setText("Already Bookmarked" if already else "Bookmark Selected Row")

    def _bookmark_selected_rows(self):
        selection = self.table_view.selectionModel()
        rows = selection.selectedRows() if selection else []
        if not rows:
            QMessageBox.information(self,"Bookmark Lead","Select one or more rows in the table first.")
            return
        from modules.cases.investigation import add_bookmarks
        self._reload_bookmarks()
        entries = [self._bookmark_entry(i.row()) for i in rows]
        existing = sum(e["bookmark_id"] in self._bookmark_ids for e in entries)
        fresh = [e for e in entries if e["bookmark_id"] not in self._bookmark_ids and "row_data" in e]
        try:
            from modules.controllers.app_controller import DIRECT_ANALYSIS_CASE_ID, _direct_analysis_workspace
            if self.case_id == DIRECT_ANALYSIS_CASE_ID:
                _direct_analysis_workspace()
            added, duplicate = add_bookmarks(self.case_id,fresh) if fresh else (0,0)
        except Exception as error:
            # EA_HANDLED_DIAGNOSTICS_V1
            try:
                from modules.core.diagnostic_events import record_handled_exception as _ea_record_handled_exception
                _ea_record_handled_exception()
            except Exception:
                pass
            QMessageBox.warning(self,"Save Bookmark",f"Bookmark was not saved: {error}")
            return
        self._reload_bookmarks()
        self._bookmark_selection_changed()
        message = f"Case {self.case_id}: {added} bookmark(s) saved; {existing+duplicate} already bookmarked. Total: {len(self._bookmarked_rows)}. Use View Bookmarks to review or export."
        self.bookmark_status.setText(message)
        self.stats_label.setText(message)
        if self._current_model and self._current_model.rowCount():
            self._current_model.dataChanged.emit(self._current_model.index(0,0),self._current_model.index(self._current_model.rowCount()-1,self._current_model.columnCount()-1),[Qt.ItemDataRole.BackgroundRole,Qt.ItemDataRole.ToolTipRole])

    def _open_case_lists(self, initial):
        from modules.cases.investigation import backfill_saved_numbers,index_case_numbers,indexed_runs
        from modules.reporting.cdr_gui_artifacts import event_frames
        case_id, source_id = self.case_id,self.source_id
        frames = event_frames(self._analysis_sheets)
        def prepare():
            errors = backfill_saved_numbers(case_id) if initial=="numbers" else []
            if initial=="numbers" and frames and source_id not in indexed_runs(case_id):
                index_case_numbers(case_id,source_id,frames)
            return errors
        def opened(errors):
            from gui.widgets.investigation_dialog import InvestigationDialog
            dialog=InvestigationDialog(case_id,parent=self,initial=initial)
            if errors:
                dialog.status.setText(dialog.status.text()+" Some saved sources could not be indexed: "+"; ".join(errors))
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            self._dialogs.append(dialog)
            def done(*_):
                from shiboken6 import isValid
                if not isValid(self):return
                self._reload_bookmarks()
                self._bookmark_selection_changed()
                if dialog in self._dialogs:self._dialogs.remove(dialog)
            dialog.finished.connect(done)
            dialog.show()
        button = self.case_numbers_btn if initial=="numbers" else self.view_bookmarks_btn
        self._run_export(button,prepare,opened)

    def _run_export(self, button, function, finished):
        button.setEnabled(False)
        self.export_progress.show()
        self.stats_label.setText("Preparing analysis preview…")
        job = _ExportJob(function)
        self._export_jobs.append(job)
        def cleanup():
            from shiboken6 import isValid
            if job in self._export_jobs:
                self._export_jobs.remove(job)
            if not isValid(self):return False
            if isValid(button):button.setEnabled(True)
            if not self._export_jobs:
                self.export_progress.hide()
            return True
        def completed(result):
            if not cleanup():return
            try:
                finished(result)
            except Exception as error:
                # EA_HANDLED_DIAGNOSTICS_V1
                try:
                    from modules.core.diagnostic_events import record_handled_exception as _ea_record_handled_exception
                    _ea_record_handled_exception()
                except Exception:
                    pass
                QMessageBox.warning(self, "Open Preview", str(error))
        def failed(message):
            if not cleanup():return
            QMessageBox.warning(self, "Export Error", message)
        job.signals.completed.connect(completed, Qt.ConnectionType.QueuedConnection)
        job.signals.failed.connect(failed, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(job)

    def _preview_destination(self, name):
        from uuid import uuid4
        from modules.core.paths import REPORT_DIR
        directory = REPORT_DIR / "interactive"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{name}_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}.html"

    def _open_interactive_map(self) -> None:
        if not self._sheets:
            return
        from modules.reporting.forensic_intelligence_suite import export_interactive_map_html
        path = self._preview_destination("tower_map")
        sheets = dict(self._analysis_sheets or self._sheets)
        def opened(result):
            from gui.utils.local_preview import open_preview
            file, count = result
            open_preview(file)
            self.stats_label.setText(f"Tower coordinate explorer: {count} verified points · {file.name}")
        self._run_export(self.map_btn, lambda: export_interactive_map_html(sheets, path), opened)

    def _open_call_link_graph(self) -> None:
        if not self._sheets:
            return
        from modules.reporting.forensic_intelligence_suite import export_call_link_graph_html
        path = self._preview_destination("call_links")
        sheets = dict(self._analysis_sheets or self._sheets)
        def opened(result):
            from gui.utils.local_preview import open_preview
            file, nodes, links = result
            open_preview(file)
            self.stats_label.setText(f"Link explorer: {nodes} entities · {links} aggregated links · {file.name}")
        self._run_export(self.graph_btn, lambda: export_call_link_graph_html(sheets, path), opened)

    def _open_court_forensic_brief(self) -> None:
        if not self._sheets:
            return
        from modules.reporting.forensic_intelligence_suite import export_court_forensic_brief_html
        from modules.core.paths import REPORT_DIR
        selected, _ = QFileDialog.getSaveFileName(self, "Save Analytical Brief", str(REPORT_DIR / "analytical_brief.html"), "HTML brief (*.html)")
        if not selected:
            return
        path = Path(selected).with_suffix(".html")
        sheets = dict(self._sheets)
        def opened(result):
            from gui.utils.local_preview import open_preview
            file, digest = result
            self.stats_label.setText(f"Brief saved with SHA-256 sidecars · {file.name}")
            open_preview(file)
        self._run_export(self.court_brief_btn, lambda: export_court_forensic_brief_html(sheets, path), opened)

    def _show_database_status(self):
        import json
        from modules.database.diagnostics import database_diagnostics
        def show(result):
            dialog = QDialog(self)
            dialog.setWindowTitle("Read-only Database Status")
            dialog.resize(850, 550)
            layout = QVBoxLayout(dialog)
            view = QPlainTextEdit(dialog)
            view.setReadOnly(True)
            view.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
            layout.addWidget(view)
            close = QPushButton("Close", dialog)
            close.clicked.connect(dialog.accept)
            layout.addWidget(close)
            dialog.exec()
        self._run_export(self.database_btn, database_diagnostics, show)

    def _open_cross_case_search(self) -> None:
        initial_q = self.search_input.text().strip()
        if not initial_q and self._current_df is not None and not self._current_df.empty:
            sel_model = self.table_view.selectionModel()
            idxs = sel_model.selectedIndexes() if sel_model is not None else []
            if idxs:
                r = idxs[0].row()
                c = idxs[0].column()
                if 0 <= r < len(self._current_df) and 0 <= c < len(self._current_df.columns):
                    cell_val = str(self._current_df.iloc[r, c]).strip()
                    if cell_val and len(cell_val) <= 32:
                        initial_q = cell_val

        def _inject_cross_case_sheets(cc_sheets: dict[str, pd.DataFrame]) -> None:
            for k, df in cc_sheets.items():
                if isinstance(df, pd.DataFrame) and not df.empty:
                    df.attrs["preserve_excel_columns"] = True
                    self._sheets[k] = df
                    existing = [self.sheet_combo.itemText(i) for i in range(self.sheet_combo.count())]
                    if k not in existing:
                        self.sheet_combo.addItem(k)
            if "Cross-Case Summary" in self._sheets:
                self.sheet_combo.setCurrentText("Cross-Case Summary")

        from gui.widgets.cross_case_search_dialog import CrossCaseSearchDialog
        dlg = CrossCaseSearchDialog(
            self,
            initial_query=initial_q,
            on_send_to_viewer=_inject_cross_case_sheets,
        )
        dlg.exec()

    def _export_current_view(self) -> None:
        if self._current_df is None or self._current_df.empty:
            QMessageBox.information(self, "Export", "No rows in current view to export.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Current View",
            "ethicalarmor_current_view.xlsx",
            "Excel Files (*.xlsx);;CSV Files (*.csv)",
        )
        if not file_path:
            return
        try:
            out_df = self._current_df.copy()
            out_df.attrs = {}
            if file_path.lower().endswith(".csv"):
                out_df.to_csv(file_path, index=False)
            else:
                out_df.to_excel(file_path, index=False)
            QMessageBox.information(self, "Export Complete", f"Saved to:\n{file_path}")
        except Exception as err:
            # EA_HANDLED_DIAGNOSTICS_V1
            try:
                from modules.core.diagnostic_events import record_handled_exception as _ea_record_handled_exception
                _ea_record_handled_exception()
            except Exception:
                pass
            QMessageBox.warning(self, "Export Failed", str(err))

    def _export_all_sheets(self) -> None:
        if not self._sheets:
            QMessageBox.information(self, "Export", "No sheets available to export.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export All Forensic Sheets", "ethicalarmor_full_report.xlsx", "Excel Files (*.xlsx)"
        )
        if not file_path:
            return
        try:
            from modules.reporting.compact_excel_export import export_sheets_xlsx
            info = export_sheets_xlsx(file_path, self._sheets)
            QMessageBox.information(self, "Export Complete",
                f"Exported {info['sheets']} sheets and {info['rows']:,} GUI-loaded rows to:\n"
                f"{info['path']}\n\nSHA-256 (exported file): {info['sha256']}\n"
                "Preview tabs may not contain all backend records.")
        except Exception as exc:
            # EA_HANDLED_DIAGNOSTICS_V1
            try:
                from modules.core.diagnostic_events import record_handled_exception as _ea_record_handled_exception
                _ea_record_handled_exception()
            except Exception:
                pass
            import traceback
            QMessageBox.warning(self, "Export Failed",
                f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}")


    def _search_loaded_numbers(self) -> None:
        """Search loaded GUI frames. This is not a database-wide search."""
        import re
        from PySide6.QtWidgets import QInputDialog

        raw, ok = QInputDialog.getMultiLineText(
            self, "Find Numbers in Loaded Sheets",
            "Enter mobile numbers, IMEI or IMSI (one per line or comma separated):"
        )
        if not ok or not raw.strip():
            return
        tokens = [re.sub(r"\D", "", x) for x in re.split(r"[,;\n]+", raw)]
        needles = list(dict.fromkeys(x for x in tokens if len(x) >= 5))
        if not needles:
            QMessageBox.warning(self, "Number Search", "Enter at least one identifier (5+ digits).")
            return
        # For mobile numbers, match optional Indian country/trunk prefixes only.
        # No arbitrary substring matching: avoids accidental leads.
        variants = set(needles)
        for number in needles:
            if len(number) == 10:
                variants.update(("91" + number, "0" + number, "0091" + number))
        target = frozenset(variants)
        number_columns = re.compile(
            r"msisdn|imsi|imei|iccid|subscriber|mobile|phone|number|"
            r"caller|callee|calling|called|a[ _-]?party|b[ _-]?party|"
            r"target|contact|sim[ _-]?(?:id|number)", re.I
        )
        def cell_hit(value):
            if value is None:
                return False
            s = str(value).strip()
            if not s or s.lower() in ("nan", "none", "<na>"):
                return False
            # ID fields may contain +91, spaces, hyphens or multiple IDs.
            pieces = re.split(r"[,;/\n]+", s)
            for piece in pieces:
                digits = re.sub(r"\D", "", piece)
                if digits in target:
                    return True
            return False

        matches = []
        matched_count = 0
        limit = 5000  # Avoid injecting giant secondary tables into the GUI.
        searched_rows = 0
        searched_sheets = 0
        for title, frame in list(self._sheets.items()):
            if (not isinstance(frame, pd.DataFrame) or frame.empty or
                    str(title) == "Number Search Results"):
                continue
            searched_sheets += 1
            searched_rows += len(frame)
            ids = [c for c in frame.columns if number_columns.search(str(c))]
            # Fall back to textual columns for heterogeneous evidence imports.
            if not ids:
                ids = [c for c in frame.columns
                       if pd.api.types.is_object_dtype(frame[c].dtype)
                       or pd.api.types.is_string_dtype(frame[c].dtype)]
            if not ids:
                continue
            mask = pd.Series(False, index=frame.index)
            for c in ids:
                # Per-column mask, no giant concatenated intermediate table.
                try:
                    col_mask = frame[c].map(cell_hit).fillna(False)
                    mask = mask | col_mask
                except (TypeError, ValueError):
                    continue
            count = int(mask.sum())
            matched_count += count
            if count and sum(len(f) for f in matches) < limit:
                allowance = limit - sum(len(f) for f in matches)
                selected = frame.loc[mask].head(allowance).copy()
                selected.insert(0, "Source Sheet", str(title))
                matches.append(selected)
        if not matches:
            QMessageBox.information(
                self, "Number Search", "No match in currently loaded GUI rows.\n"
                f"Searched {searched_rows:,} rows across {searched_sheets} sheets.\n"
                "This does NOT search raw rows held only in DuckDB/Parquet."
            )
            return
        result = pd.concat(matches, ignore_index=True, sort=False)
        name = "Number Search Results"
        self._sheets[name] = result
        if self.sheet_combo.findText(name) == -1:
            self.sheet_combo.addItem(name)
        self.sheet_combo.setCurrentText(name)
        QMessageBox.information(
            self, "Number Search Results",
            f"Matched {matched_count:,} rows; showing {len(result):,}.\n"
            f"Scanned {searched_rows:,} GUI rows across {searched_sheets} sheets.\n"
            "For a complete tower dump search, backend DuckDB search is required."
        )





