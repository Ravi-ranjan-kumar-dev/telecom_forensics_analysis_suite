# gui/login_dialog.py
"""Login dialog for the Telecom Forensics desktop application."""

import sys
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
)
from PySide6.QtCore import Qt

from gui.api_client import ApiClient


class LoginDialog(QDialog):
    """Dialog that authenticates the user via the backend API."""

    def __init__(self, parent=None, api_client: ApiClient | None = None):
        super().__init__(parent)
        self.setWindowTitle("Login - Telecom Forensics")
        self.setModal(True)
        self.setMinimumSize(400, 200)
        self.api = api_client or ApiClient()

        # UI widgets
        layout = QVBoxLayout(self)

        title_label = QLabel("Telecom Forensics Suite")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title_label)

        username_label = QLabel("Username:")
        layout.addWidget(username_label)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter username")
        layout.addWidget(self.username_input)

        password_label = QLabel("Password:")
        layout.addWidget(password_label)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.password_input)

        # Buttons
        button_row = QHBoxLayout()
        self.login_button = QPushButton("Login")
        self.login_button.clicked.connect(self.attempt_login)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.login_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

        # Enter key triggers login
        self.password_input.returnPressed.connect(self.attempt_login)

    def attempt_login(self):
        """Try to login using the provided credentials."""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "Login", "Please enter both username and password.")
            return

        success = self.api.login(username, password)
        if success:
            self.accept()
        else:
            QMessageBox.critical(self, "Login Failed", "Invalid username or password.")