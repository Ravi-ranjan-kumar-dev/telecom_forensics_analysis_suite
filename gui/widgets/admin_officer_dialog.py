"""GUI Admin Panel for creating and managing Police Officer accounts across districts/states."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.api_client import ApiClient, ApiError, get_active_api_client


class AdminOfficerDialog(QDialog):
    """Manage multi-district/state police officer accounts, roles, status & passwords."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        api_client: ApiClient | None = None,
    ) -> None:
        super().__init__(parent)
        self.api = api_client or get_active_api_client() or ApiClient()
        self.setWindowTitle("EthicalArmor - Telecom & Digital Forensics Suite")
        self.setModal(True)
        self.resize(1180, 720)
        self._users: list[dict[str, Any]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        header_row = QHBoxLayout()
        title = QLabel("Multi-State / District Police Officer Management")
        title.setObjectName("moduleTitle")
        refresh_btn = QPushButton("Refresh Officers")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self.refresh_users)
        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(refresh_btn)
        layout.addLayout(header_row)

        # Create Officer Card
        create_card = QFrame()
        create_card.setObjectName("infoCard")
        create_layout = QVBoxLayout(create_card)
        create_layout.setContentsMargins(18, 14, 18, 14)
        create_layout.setSpacing(10)

        create_heading = QLabel("Create New Police Officer Account")
        create_heading.setObjectName("cardHeading")
        create_layout.addWidget(create_heading)

        row1 = QHBoxLayout()
        self.username_edit = QLineEdit()
        self.username_edit.setObjectName("inputControl")
        self.username_edit.setPlaceholderText("Username * (e.g. patna_stf_01)")

        self.password_edit = QLineEdit()
        self.password_edit.setObjectName("inputControl")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Password * (12+ chars)")

        self.role_box = QComboBox()
        self.role_box.setObjectName("inputControl")
        self.role_box.addItems(["investigator", "viewer", "admin"])

        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("inputControl")
        self.name_edit.setPlaceholderText("Officer Name (e.g. Insp. R. Kumar)")

        row1.addWidget(self.username_edit, stretch=1)
        row1.addWidget(self.password_edit, stretch=1)
        row1.addWidget(self.role_box)
        row1.addWidget(self.name_edit, stretch=1)

        row2 = QHBoxLayout()
        self.unit_edit = QLineEdit()
        self.unit_edit.setObjectName("inputControl")
        self.unit_edit.setPlaceholderText("Police Unit / PS (e.g. Cyber Cell / STF)")

        self.district_edit = QLineEdit()
        self.district_edit.setObjectName("inputControl")
        self.district_edit.setPlaceholderText("District (e.g. Patna)")

        self.state_edit = QLineEdit()
        self.state_edit.setObjectName("inputControl")
        self.state_edit.setPlaceholderText("State (e.g. Bihar)")

        self.mobile_edit = QLineEdit()
        self.mobile_edit.setObjectName("inputControl")
        self.mobile_edit.setPlaceholderText("Mobile Number")

        self.expiry_edit = QLineEdit()
        self.expiry_edit.setObjectName("inputControl")
        self.expiry_edit.setPlaceholderText("Expiry YYYY-MM-DD (optional)")

        create_btn = QPushButton("Create Officer")
        create_btn.setObjectName("primaryButton")
        create_btn.clicked.connect(self._create_officer)

        row2.addWidget(self.unit_edit, stretch=1)
        row2.addWidget(self.district_edit, stretch=1)
        row2.addWidget(self.state_edit, stretch=1)
        row2.addWidget(self.mobile_edit, stretch=1)
        row2.addWidget(self.expiry_edit, stretch=1)
        row2.addWidget(create_btn)

        create_layout.addLayout(row1)
        create_layout.addLayout(row2)
        layout.addWidget(create_card)

        # Officers Table
        self.table = QTableWidget(0, 9)
        self.table.setObjectName("dataTable")
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setHorizontalHeaderLabels(
            [
                "Username",
                "Officer Name",
                "Role",
                "Status",
                "Police Unit",
                "District",
                "State",
                "Mobile",
                "Expiry Date",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, stretch=1)

        # Action Buttons for Selected Officer
        action_row = QHBoxLayout()
        toggle_btn = QPushButton("Activate / Block Selected Officer")
        toggle_btn.setObjectName("secondaryButton")
        toggle_btn.clicked.connect(self._toggle_selected_status)

        reset_pw_btn = QPushButton("Reset Selected Officer Password")
        reset_pw_btn.setObjectName("secondaryButton")
        reset_pw_btn.clicked.connect(self._reset_selected_password)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.accept)

        action_row.addWidget(toggle_btn)
        action_row.addWidget(reset_pw_btn)
        action_row.addStretch()
        action_row.addWidget(close_btn)
        layout.addLayout(action_row)

        self.refresh_users()

    def refresh_users(self) -> None:
        if not self.api or not self.api.token:
            return
        try:
            self._users = self.api.list_users()
        except ApiError as error:
            QMessageBox.warning(self, "Admin Panel", str(error))
            return

        self.table.setRowCount(len(self._users))
        for r_idx, user in enumerate(self._users):
            vals = (
                user.get("username", ""),
                user.get("full_name", "") or "-",
                user.get("role", "viewer"),
                "ACTIVE" if user.get("is_active") else "BLOCKED",
                user.get("police_unit", "") or "-",
                user.get("district", "") or "-",
                user.get("state", "") or "-",
                user.get("mobile_number", "") or "-",
                user.get("expires_at", "") or "No Expiry",
            )
            for c_idx, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                self.table.setItem(r_idx, c_idx, item)
        self.table.resizeColumnsToContents()

    def _create_officer(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not username or len(password) < 12:
            QMessageBox.warning(
                self,
                "Create Officer",
                "Enter a valid username and a password with at least 12 characters.",
            )
            return
        payload = {
            "username": username,
            "password": password,
            "role": self.role_box.currentText(),
            "full_name": self.name_edit.text().strip(),
            "police_unit": self.unit_edit.text().strip(),
            "district": self.district_edit.text().strip(),
            "state": self.state_edit.text().strip(),
            "mobile_number": self.mobile_edit.text().strip(),
            "expires_at": self.expiry_edit.text().strip(),
        }
        try:
            self.api.create_officer_user(payload)
            QMessageBox.information(
                self,
                "Officer Created",
                f"Account '{username}' created successfully.",
            )
            self.username_edit.clear()
            self.password_edit.clear()
            self.name_edit.clear()
            self.refresh_users()
        except ApiError as error:
            QMessageBox.critical(self, "Create Officer Failed", str(error))

    def _selected_user(self) -> dict[str, Any] | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._users):
            QMessageBox.warning(
                self,
                "Select Officer",
                "Select an officer row in the table first.",
            )
            return None
        return self._users[row]

    def _toggle_selected_status(self) -> None:
        user = self._selected_user()
        if not user:
            return
        username = str(user.get("username", ""))
        new_active = not bool(user.get("is_active"))
        try:
            self.api.update_user_status(username, is_active=new_active)
            self.refresh_users()
        except ApiError as error:
            QMessageBox.critical(self, "Status Update Failed", str(error))

    def _reset_selected_password(self) -> None:
        user = self._selected_user()
        if not user:
            return
        username = str(user.get("username", ""))
        new_pw, ok = QInputDialog.getText(
            self,
            f"Reset Password — {username}",
            "Enter new password (12+ characters):",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not new_pw:
            return
        try:
            self.api.admin_reset_password(username, new_pw)
            QMessageBox.information(
                self,
                "Password Reset",
                f"Password updated for '{username}'.",
            )
        except ApiError as error:
            QMessageBox.critical(self, "Password Reset Failed", str(error))
