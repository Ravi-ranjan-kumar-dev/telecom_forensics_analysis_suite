"""Unified format preflight for all four evidence modules (no case mutation)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
                              QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from modules.loader.universal_workspace import DEFAULT_PROFILES_DIR, run_universal_preflight


class _PreflightWorker(QThread):
    finished_result = Signal(object)
    def __init__(self, path: str, module: str | None):
        super().__init__()
        self.path, self.module = path, module

    def run(self):
        try:
            result=run_universal_preflight(self.path,module=self.module)
        except Exception as exc:
            result={"ok":False,"files":[],"analysis":[],"needs_review":False,
                    "errors":[f"{type(exc).__name__}: {exc}"]}
        self.finished_result.emit(result)


class UniversalEvidencePage(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._path=""
        self._worker=None
        self._last_result=None
        root=QVBoxLayout(self)
        intro=QLabel("Inspect CDR, Tower CDR/GPRS/IPDR, Subscriber IPDR and IMEI formats. "
                     "This is a preflight only: it does not save evidence into a case or make forensic findings.")
        intro.setWordWrap(True)
        root.addWidget(intro)
        controls=QHBoxLayout()
        self.module=QComboBox()
        self.module.addItem("Auto detect",None)
        for key in ("CDR","TOWER_DUMP","IPDR","IMEI"):
            self.module.addItem(key,key)
        self.choose=QPushButton("Select evidence file")
        self.choose.clicked.connect(self._select_file)
        self.run_button=QPushButton("Inspect / Validate")
        self.run_button.clicked.connect(self._run)
        self.review_button=QPushButton("Review unknown format")
        self.review_button.setEnabled(False)
        self.review_button.clicked.connect(self._review)
        controls.addWidget(self.module)
        controls.addWidget(self.choose)
        controls.addWidget(self.run_button)
        controls.addWidget(self.review_button)
        root.addLayout(controls)
        self.file_label=QLabel("No evidence selected")
        self.file_label.setWordWrap(True)
        root.addWidget(self.file_label)
        self.output=QPlainTextEdit()
        self.output.setReadOnly(True)
        root.addWidget(self.output)
        self._running=False

    @property
    def is_running(self) -> bool:
        return self._running

    def _select_file(self):
        path,_=QFileDialog.getOpenFileName(
            self,"Choose telecom evidence","",
            "Telecom evidence (*.csv *.txt *.tsv *.xlsx *.xls *.zip *.gz);;All files (*)")
        if path:
            self._path=path
            self.file_label.setText(path)
            self.review_button.setEnabled(False)

    def _run(self):
        if not self._path:
            QMessageBox.information(self,"Select file","Choose a telecom evidence file first.")
            return
        self._running=True
        self.run_button.setEnabled(False)
        self.review_button.setEnabled(False)
        self.output.setPlainText("Inspecting input (read-only)...")
        self._worker=_PreflightWorker(self._path,self.module.currentData())
        self._worker.finished_result.connect(self._display)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _display(self, result):
        self._running=False
        self.run_button.setEnabled(True)
        self._last_result=result
        statuses = {f.get("status") for f in result.get("files", [])}
        overall = ("OK" if result.get("ok") else
                   "NO DATA — report contains zero evidence rows" if statuses == {"no_data"} else
                   "NEEDS REVIEW / ERROR")
        lines=["Import status: "+overall,
               "Source SHA-256: "+str(result.get("source_sha256") or "not available"),""]
        for item in result.get("files",[]):
            lines.append(f"Module: {item['module']} | Type: {item['evidence_type']} | Status: {item['status']}")
            lines.append(f"Operator: {item['operator']} | Confidence: {item['operator_confidence']}")
            lines.append(f"Accepted: {item['accepted_rows']} | Rejected: {item['rejected_rows']}")
            for msg in item.get("warnings",[]):lines.append("Warning: "+msg)
            for msg in item.get("errors",[]):lines.append("Error: "+msg)
            lines.append("")
        for report in result.get("analysis",[]):
            lines.append(f"Descriptive only: {report['module']} has {report['rows']} rows across {report['files']} member(s)")
        lines.extend("Error: "+e for e in result.get("errors",[]))
        lines.append("\nNo case evidence was registered and no investigative report was created.")
        self.output.setPlainText("\n".join(lines))
        can_review = (bool(result.get("needs_review"))
                      and any(f.get("status") in ("needs_review", "rejected") for f in result.get("files", []))) and self._path.lower().endswith(
            (".csv",".tsv",".txt",".xlsx",".xls"))
        self.review_button.setEnabled(can_review)

    def _review(self):
        if not self._path:return
        from gui.widgets.universal_format_review_dialog import UniversalFormatReviewDialog
        dialog=UniversalFormatReviewDialog(self._path,profiles_dir=DEFAULT_PROFILES_DIR,parent=self)
        if dialog.exec() and dialog.saved_profile:
            self._run()
