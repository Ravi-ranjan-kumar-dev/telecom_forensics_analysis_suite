"""Optional reusable PySide6 dialog for analyst-approved unknown telecom formats.

This widget is deliberately NOT patched into every old importer. An integrator
opens it when load_universal_evidence() returns needs_review, then retries the
universal importer using the saved local profiles directory.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QLabel, QMessageBox, QPushButton, QScrollArea, QWidget,
    QHBoxLayout)

from modules.loader.universal_evidence import inspect_universal_evidence, approve_format_profile
from modules.loader.universal_schema import TYPES, ALIASES


class UniversalFormatReviewDialog(QDialog):
    def __init__(self, path: str | Path, *, profiles_dir: str | Path,
                 analyst_username: str = "", parent=None):
        super().__init__(parent)
        self.evidence_path = str(path)
        self.profiles_dir = str(profiles_dir)
        self.saved_profile = None
        self.setWindowTitle("EthicalArmor | Verify Unknown Telecom Format")
        self.resize(730, 610)
        root=QVBoxLayout(self)
        self.inspected=inspect_universal_evidence(path)
        if not self.inspected.get("ok"):
            root.addWidget(QLabel("Cannot inspect this file: " + "; ".join(self.inspected["errors"])))
            return
        root.addWidget(QLabel("Evidence: " + Path(self.evidence_path).name))
        root.addWidget(QLabel("Proposed module: " + self.inspected["suggested_module"] +
                              " | Type: " + self.inspected["suggested_type"] +
                              " | Operator: " + self.inspected["operator"]))
        root.addWidget(QLabel("IMPORTANT: Suggested fields are UNVERIFIED until you approve them. "
                              "Match each source header carefully."))
        form=QFormLayout()
        self.typ=QComboBox()
        self.typ.addItems(TYPES)
        if self.inspected["suggested_type"] in TYPES:
            self.typ.setCurrentText(self.inspected["suggested_type"])
        form.addRow("Evidence type (required)", self.typ)
        self.analyst=QLineEdit(analyst_username)
        form.addRow("Analyst ID (required)", self.analyst)
        self.operator=QLineEdit(self.inspected["operator"])
        form.addRow("Verified operator or Unknown",self.operator)
        self.time_format=QLineEdit()
        self.time_format.setPlaceholderText("e.g. %d/%m/%Y %H:%M:%S; leave blank only for IMEI_INVENTORY")
        form.addRow("Exact timestamp format",self.time_format)
        self.timezone=QLineEdit()
        self.timezone.setPlaceholderText("e.g. Asia/Kolkata (confirm from report)")
        form.addRow("Timestamp timezone",self.timezone)
        root.addLayout(form)
        root.addWidget(QLabel("Canonical field ← Original source column (blank means unmapped)"))
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        body=QWidget()
        mapping_form=QFormLayout(body)
        headers=self.inspected["metadata"]["headers"]
        suggested=self.inspected["column_mapping"]
        self.mappings={}
        for field in ALIASES:
            selector=QComboBox()
            selector.addItem("(not mapped)",None)
            for raw_header in headers:selector.addItem(raw_header,raw_header)
            if field in suggested:
                selector.setCurrentIndex(headers.index(suggested[field])+1)
            mapping_form.addRow(field,selector)
            self.mappings[field]=selector
        scroll.setWidget(body)
        root.addWidget(scroll)
        buttons=QHBoxLayout()
        cancel=QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        approve=QPushButton("Approve & Save Format Profile")
        approve.clicked.connect(self._approve)
        buttons.addWidget(cancel)
        buttons.addWidget(approve)
        root.addLayout(buttons)

    def _approve(self):
        mapping={key:combo.currentData() for key,combo in self.mappings.items() if combo.currentData() is not None}
        try:
            profile=approve_format_profile(self.evidence_path,evidence_type=self.typ.currentText(),
               field_mapping=mapping,approved_by=self.analyst.text(),
               operator=self.operator.text() or "Unknown",
               time_format=self.time_format.text() or None,
               timezone_name=self.timezone.text() or None,
               profile_dir=self.profiles_dir)
            self.saved_profile=profile
            self.accept()
        except Exception as exc:
            QMessageBox.warning(self,"Approval Failed",str(exc))
