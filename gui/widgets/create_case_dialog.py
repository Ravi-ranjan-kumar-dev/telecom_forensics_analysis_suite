"""Dialog for creating a new FIR / Investigation Case from the desktop GUI."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from modules.cases import CaseError, create_case


class CreateCaseDialog(QDialog):
    """Collect FIR / Case metadata and create an audited case workspace."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.created_case: dict[str, Any] | None = None
        self.setWindowTitle("EthicalArmor - Telecom & Digital Forensics Suite")
        self.setModal(True)
        self.setMinimumSize(520, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        title = QLabel("Create New Investigation Case")
        title.setObjectName("moduleTitle")
        layout.addWidget(title)

        note = QLabel(
            "Enter the Case Name and optional FIR / Police Unit details. "
            "Leave Case ID blank to generate an automatic ID (e.g. CASE-YYYYMMDD-001)."
        )
        note.setObjectName("cardText")
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QFormLayout()
        form.setSpacing(10)

        self.case_name_edit = QLineEdit()
        self.case_name_edit.setObjectName("inputControl")
        self.case_name_edit.setPlaceholderText("Required — e.g. Patna Cyber Fraud / Murder Case")

        self.case_id_edit = QLineEdit()
        self.case_id_edit.setObjectName("inputControl")
        self.case_id_edit.setPlaceholderText("Optional — e.g. FIR-102-2026 (auto-generated if blank)")

        self.fir_edit = QLineEdit()
        self.fir_edit.setObjectName("inputControl")
        self.fir_edit.setPlaceholderText("e.g. FIR No. 102/2026 u/s 318 BNS")

        self.date_edit = QLineEdit()
        self.date_edit.setObjectName("inputControl")
        self.date_edit.setPlaceholderText("e.g. 15-10-2026")

        self.location_edit = QLineEdit()
        self.location_edit.setObjectName("inputControl")
        self.location_edit.setPlaceholderText("e.g. Gandhi Maidan PS, Patna")

        self.investigator_edit = QLineEdit()
        self.investigator_edit.setObjectName("inputControl")
        self.investigator_edit.setPlaceholderText("e.g. Insp. Ravi Ranjan")

        self.unit_edit = QLineEdit()
        self.unit_edit.setObjectName("inputControl")
        self.unit_edit.setPlaceholderText("e.g. Bihar STF / Cyber Cell Patna")

        self.description_edit = QPlainTextEdit()
        self.description_edit.setObjectName("analysisLog")
        self.description_edit.setMaximumHeight(80)
        self.description_edit.setPlaceholderText("Brief case summary or investigation notes...")

        form.addRow("Case Name *:", self.case_name_edit)
        form.addRow("Custom Case ID:", self.case_id_edit)
        form.addRow("FIR / Reference No.:", self.fir_edit)
        form.addRow("Incident Date:", self.date_edit)
        form.addRow("Incident Location:", self.location_edit)
        form.addRow("Investigator:", self.investigator_edit)
        form.addRow("Police Unit / District:", self.unit_edit)
        form.addRow("Description:", self.description_edit)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        create_btn = QPushButton("Create & Activate Case")
        create_btn.setObjectName("primaryButton")
        create_btn.clicked.connect(self._create_case)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self.reject)

        btn_row.addWidget(create_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _create_case(self) -> None:
        case_name = self.case_name_edit.text().strip()
        if not case_name:
            QMessageBox.warning(self, "Case Name Required", "Please enter a Case Name.")
            return

        custom_id = self.case_id_edit.text().strip() or None
        try:
            created = create_case(
                case_name=case_name,
                case_id=custom_id,
                fir_number=self.fir_edit.text().strip(),
                incident_date=self.date_edit.text().strip(),
                incident_location=self.location_edit.text().strip(),
                investigator=self.investigator_edit.text().strip(),
                unit_name=self.unit_edit.text().strip(),
                description=self.description_edit.toPlainText().strip(),
            )
        except (CaseError, ValueError) as error:
            QMessageBox.critical(self, "Case Creation Error", str(error))
            return
        except Exception as error:
            QMessageBox.critical(
                self,
                "Case Creation Error",
                f"{type(error).__name__}: {error}",
            )
            return

        self.created_case = created
        self.accept()
