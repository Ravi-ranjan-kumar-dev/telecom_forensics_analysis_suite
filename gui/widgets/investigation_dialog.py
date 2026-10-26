"""Searchable case-number and bookmark lists available without rerunning analysis."""

from __future__ import annotations

from pathlib import Path
import pandas as pd
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableView,
    QVBoxLayout,
)
from .data_viewer import FastPandasTableModel, _ExportJob


class InvestigationDialog(QDialog):
    def __init__(self, case_id, *, parent=None, initial="bookmarks"):
        super().__init__(parent)
        self.case_id = str(case_id)
        self.setWindowTitle(f"Case Leads & Numbers — {self.case_id}")
        self.resize(1180, 720)
        self.frames = {}
        self.models = {}
        self._jobs = []
        self._closed = False
        root = QVBoxLayout(self)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.search = QLineEdit(self)
        self.search.setObjectName("inputControl")
        self.search.setPlaceholderText(
            "Search the current list by number, source, or any displayed value"
        )
        root.addWidget(self.search)
        self.scope = QComboBox(self)
        self.scope.setObjectName("inputControl")
        self.scope.addItem("Number scope: This case", "case")
        self.scope.addItem("Number scope: All saved cases (active + archived)", "all")
        self.scope.currentIndexChanged.connect(self._scope_changed)
        root.addWidget(self.scope)
        self.tabs = QTabWidget(self)
        self.tables = {}
        for key, title in [("bookmarks", "Saved Bookmarks"), ("numbers", "Case Numbers")]:
            table = QTableView(self)
            table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
            table.setSortingEnabled(True)
            table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
            self.tables[key] = table
            self.tabs.addTab(table, title)
        root.addWidget(self.tabs, 1)
        row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh Lists", self)
        self.remove_btn = QPushButton("Remove Selected Bookmarks", self)
        self.copy_btn = QPushButton("Copy Selected Row(s)", self)
        self.export_btn = QPushButton("Export Visible List (CSV)", self)
        self.close_btn = QPushButton("Close", self)
        for button in [
            self.refresh_btn,
            self.remove_btn,
            self.copy_btn,
            self.export_btn,
            self.close_btn,
        ]:
            button.setObjectName("secondaryButton")
            row.addWidget(button)
        root.addLayout(row)
        self.search.textChanged.connect(self._filter)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.refresh_btn.clicked.connect(self.refresh)
        self.remove_btn.clicked.connect(self._remove)
        self.copy_btn.clicked.connect(self._copy)
        self.export_btn.clicked.connect(self._export)
        self.close_btn.clicked.connect(self.close)
        self.tabs.setCurrentIndex(1 if initial == "numbers" else 0)
        self.refresh()

    def closeEvent(self, event):
        self._closed = True
        super().closeEvent(event)

    def _key(self):
        return "bookmarks" if self.tabs.currentIndex() == 0 else "numbers"

    def _tab_changed(self, *_):
        self.remove_btn.setEnabled(self._key() == "bookmarks")
        self.scope.setEnabled(self._key() == "numbers" and not self._jobs)
        self._filter()

    def refresh(self):
        from modules.cases.investigation import bookmarks_frame, numbers_frame

        try:
            self.frames = {
                "bookmarks": bookmarks_frame(self.case_id),
                "numbers": numbers_frame(self.case_id),
            }
            self.status.setText(
                f"Case: {self.case_id} · {len(self.frames['bookmarks'])} saved bookmarks · {len(self.frames['numbers'])} numbers. Counts are field appearances in indexed analysis runs; repeated analyses may overlap. Older GUI-only sessions must be rerun if no source snapshot was saved."
            )
            for key in self.tables:
                self._set_table(key, self.frames[key])
            self._tab_changed()
            if self.scope.currentData() == "all":
                self._scope_changed()
        except Exception as error:
            self.status.setText(f"Could not load this case: {type(error).__name__}: {error}")

    def _scope_changed(self, *_):
        if self.scope.currentData() != "all":
            from modules.cases.investigation import numbers_frame

            self.frames["numbers"] = numbers_frame(self.case_id)
            self._filter()
            return
        from modules.cases.investigation import all_case_numbers_frame

        job = _ExportJob(all_case_numbers_frame)
        self._jobs.append(job)
        self.scope.setEnabled(False)
        self.status.setText("Loading number indexes and registered targets across saved cases…")

        def finish():
            if job in self._jobs:
                self._jobs.remove(job)
            if not self._closed:
                self.scope.setEnabled(self._key() == "numbers")

        def ready(result):
            finish()
            if self._closed:
                return
            frame, errors = result
            self.frames["numbers"] = frame
            self._filter()
            self.status.setText(
                f"All saved cases: {len(frame)} case-number entries. Includes registered targets and indexed analysis sources; older unindexed evidence is not included. "
                + ("Unavailable cases: " + "; ".join(errors) if errors else "")
            )

        def failed(message):
            finish()
            if self._closed:
                return
            self.status.setText("Could not read all case indexes: " + message)

        job.signals.completed.connect(ready, Qt.ConnectionType.QueuedConnection)
        job.signals.failed.connect(failed, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(job)

    def _set_table(self, key, frame):
        model = FastPandasTableModel(frame, self.tables[key])
        old = self.models.get(key)
        self.models[key] = model
        self.tables[key].setModel(model)
        if old is not None:
            old.deleteLater()
        self.tables[key].horizontalHeader().setStretchLastSection(True)
        self.tables[key].resizeColumnsToContents()
        if "Bookmark ID" in frame.columns:
            self.tables[key].hideColumn(frame.columns.get_loc("Bookmark ID"))

    def _filter(self, *_):
        key = self._key()
        frame = self.frames.get(key, pd.DataFrame())
        q = self.search.text().strip().casefold()
        if q and not frame.empty:
            mask = (
                frame.fillna("")
                .astype(str)
                .apply(lambda c: c.str.casefold().str.contains(q, regex=False))
                .any(axis=1)
            )
            frame = frame.loc[mask]
        self._set_table(key, frame)

    def _selected(self):
        key = self._key()
        model = self.models.get(key)
        selection = self.tables[key].selectionModel()
        rows = [i.row() for i in selection.selectedRows()] if selection else []
        return model._frame.iloc[rows] if rows and model else pd.DataFrame()

    def _remove(self):
        from modules.cases.investigation import remove_bookmarks

        selected = self._selected()
        if self._key() != "bookmarks" or selected.empty:
            return
        try:
            remove_bookmarks(self.case_id, selected["Bookmark ID"].tolist())
            self.refresh()
        except Exception as error:
            QMessageBox.warning(self, "Remove Bookmarks", str(error))

    def _copy(self):
        selected = self._selected()
        if not selected.empty:
            QApplication.clipboard().setText(selected.to_csv(index=False, sep="\t"))

    def _export(self):
        model = self.models.get(self._key())
        if model is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Visible List",
            str(Path.home() / f"{self.case_id}_{self._key()}.csv"),
            "CSV (*.csv)",
        )
        if path:
            try:
                model._frame.to_csv(path, index=False, encoding="utf-8-sig")
            except Exception as error:
                QMessageBox.warning(self, "Export List", str(error))
