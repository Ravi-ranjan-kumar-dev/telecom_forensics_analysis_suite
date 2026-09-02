"""Authentication dialogs for the Telecom Forensics desktop application."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.api_client import (
    ApiClient,
    ApiError,
    AuthenticationError,
    BackendConfigurationError,
    PasswordResetError,
    ServiceUnavailableError,
    SetupAlreadyCompletedError,
)

MINIMUM_PASSWORD_LENGTH = 12


def _password_edit(
    placeholder: str,
) -> QLineEdit:
    edit = QLineEdit()
    edit.setPlaceholderText(placeholder)
    edit.setEchoMode(QLineEdit.EchoMode.Password)
    return edit


class FirstAdminDialog(QDialog):
    """Create the first administrator when no application users exist."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        api_client: ApiClient,
        suggested_username: str = "",
    ) -> None:
        super().__init__(parent)
        self.api = api_client
        self.created_username = ""
        self.setWindowTitle("First-time Administrator Setup")
        self.setModal(True)
        self.setMinimumSize(460, 330)

        layout = QVBoxLayout(self)

        title = QLabel("Create the First Application Administrator")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 17px; font-weight: bold;")
        layout.addWidget(title)

        note = QLabel(
            "Use this only once, before any application user exists. "
            "There is no default username or password. Database/PostgreSQL "
            "credentials are not application login credentials."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        layout.addWidget(QLabel("Administrator Username:"))
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText(
            "3-64 letters, numbers, dot, underscore or hyphen"
        )
        self.username_input.setText(suggested_username)
        layout.addWidget(self.username_input)

        layout.addWidget(QLabel("Password:"))
        self.password_input = _password_edit(
            f"At least {MINIMUM_PASSWORD_LENGTH} characters"
        )
        layout.addWidget(self.password_input)

        layout.addWidget(QLabel("Confirm Password:"))
        self.confirm_input = _password_edit(
            "Enter the same password again"
        )
        layout.addWidget(self.confirm_input)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.create_button = QPushButton("Create Administrator")
        self.create_button.clicked.connect(self.attempt_setup)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.create_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.confirm_input.returnPressed.connect(
            self.attempt_setup
        )

    def attempt_setup(self) -> None:
        username = self.username_input.text().strip()
        password = self.password_input.text()
        confirmation = self.confirm_input.text()

        if not username or not password or not confirmation:
            QMessageBox.warning(
                self,
                "First-time Setup",
                "Enter the username, password and confirmation.",
            )
            return
        if password != confirmation:
            QMessageBox.warning(
                self,
                "First-time Setup",
                "The two passwords do not match.",
            )
            return
        if len(password) < MINIMUM_PASSWORD_LENGTH:
            QMessageBox.warning(
                self,
                "First-time Setup",
                (
                    "Use a password containing at least "
                    f"{MINIMUM_PASSWORD_LENGTH} characters."
                ),
            )
            return

        try:
            if not self.api.setup_status():
                raise SetupAlreadyCompletedError(
                    "First-time setup has already been completed."
                )
            self.api.setup_first_admin(username, password)
        except SetupAlreadyCompletedError:
            QMessageBox.information(
                self,
                "First-time Setup",
                (
                    "An application user already exists. Use Login or "
                    "Forgot Password instead."
                ),
            )
            return
        except ServiceUnavailableError:
            QMessageBox.critical(
                self,
                "First-time Setup",
                (
                    "Backend service is unavailable. Start or check the "
                    "backend, then try again."
                ),
            )
            return
        except ApiError as error:
            QMessageBox.critical(
                self,
                "First-time Setup",
                str(error),
            )
            return

        self.created_username = username
        QMessageBox.information(
            self,
            "First-time Setup",
            "Administrator created. You can now log in.",
        )
        self.accept()


class PasswordResetDialog(QDialog):
    """Reset a password with a short-lived host-issued token."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        api_client: ApiClient,
        suggested_username: str = "",
    ) -> None:
        super().__init__(parent)
        self.api = api_client
        self.reset_username = ""
        self.setWindowTitle("Forgot Password")
        self.setModal(True)
        self.setMinimumSize(560, 460)

        layout = QVBoxLayout(self)

        title = QLabel("Reset Application Password")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 17px; font-weight: bold;")
        layout.addWidget(title)

        note = QLabel(
            "For security, the GUI never generates or displays reset tokens. "
            "On the backend host, issue a short-lived token with:\n"
            "docker compose -f backend/docker-compose.yml exec api "
            "python -m app.cli reset-token USERNAME\n\n"
            "Paste that private token below."
        )
        note.setWordWrap(True)
        note.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(note)

        layout.addWidget(QLabel("Username:"))
        self.username_input = QLineEdit()
        self.username_input.setText(suggested_username)
        self.username_input.setPlaceholderText("Application username")
        layout.addWidget(self.username_input)

        layout.addWidget(QLabel("Password-reset Token:"))
        self.token_input = QPlainTextEdit()
        self.token_input.setPlaceholderText(
            "Paste the complete short-lived token"
        )
        self.token_input.setMaximumHeight(90)
        layout.addWidget(self.token_input)

        layout.addWidget(QLabel("New Password:"))
        self.password_input = _password_edit(
            f"At least {MINIMUM_PASSWORD_LENGTH} characters"
        )
        layout.addWidget(self.password_input)

        layout.addWidget(QLabel("Confirm New Password:"))
        self.confirm_input = _password_edit(
            "Enter the same password again"
        )
        layout.addWidget(self.confirm_input)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.reset_button = QPushButton("Reset Password")
        self.reset_button.clicked.connect(self.attempt_reset)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.reset_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.confirm_input.returnPressed.connect(
            self.attempt_reset
        )

    def attempt_reset(self) -> None:
        username = self.username_input.text().strip()
        token = self.token_input.toPlainText().strip()
        password = self.password_input.text()
        confirmation = self.confirm_input.text()

        if not username or not token or not password or not confirmation:
            QMessageBox.warning(
                self,
                "Forgot Password",
                "Enter the username, reset token and new password twice.",
            )
            return
        if password != confirmation:
            QMessageBox.warning(
                self,
                "Forgot Password",
                "The two new passwords do not match.",
            )
            return
        if len(password) < MINIMUM_PASSWORD_LENGTH:
            QMessageBox.warning(
                self,
                "Forgot Password",
                (
                    "Use a password containing at least "
                    f"{MINIMUM_PASSWORD_LENGTH} characters."
                ),
            )
            return

        try:
            self.api.reset_password(
                username=username,
                token=token,
                new_password=password,
            )
        except PasswordResetError:
            QMessageBox.critical(
                self,
                "Forgot Password",
                (
                    "The reset token is invalid or expired. Issue a new "
                    "token on the backend host and try again."
                ),
            )
            return
        except ServiceUnavailableError:
            QMessageBox.critical(
                self,
                "Forgot Password",
                (
                    "Backend service is unavailable. Start or check the "
                    "backend, then try again."
                ),
            )
            return
        except ApiError as error:
            QMessageBox.critical(
                self,
                "Forgot Password",
                str(error),
            )
            return

        self.reset_username = username
        QMessageBox.information(
            self,
            "Forgot Password",
            "Password reset completed. Log in with the new password.",
        )
        self.accept()


class LoginDialog(QDialog):
    """Authenticate an application user through the backend API."""

    def __init__(
        self,
        parent: QWidget | None = None,
        api_client: ApiClient | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Login - Telecom Forensics")
        self.setModal(True)
        self.setMinimumSize(460, 270)
        self.api = api_client or ApiClient()

        layout = QVBoxLayout(self)

        title_label = QLabel("Telecom Forensics Suite")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(
            "font-size: 18px; font-weight: bold;"
        )
        layout.addWidget(title_label)

        layout.addWidget(QLabel("Application Username:"))
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText(
            "Enter application username"
        )
        layout.addWidget(self.username_input)

        layout.addWidget(QLabel("Password:"))
        self.password_input = _password_edit(
            "Enter application password"
        )
        layout.addWidget(self.password_input)

        help_row = QHBoxLayout()
        self.setup_button = QPushButton("First-time Setup")
        self.setup_button.clicked.connect(
            self.open_first_admin_setup
        )
        self.forgot_password_button = QPushButton(
            "Forgot Password?"
        )
        self.forgot_password_button.clicked.connect(
            self.open_password_reset
        )
        help_row.addWidget(self.setup_button)
        help_row.addWidget(self.forgot_password_button)
        help_row.addStretch()
        layout.addLayout(help_row)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.login_button = QPushButton("Login")
        self.login_button.clicked.connect(self.attempt_login)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.login_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

        self.password_input.returnPressed.connect(
            self.attempt_login
        )

    def open_first_admin_setup(self) -> None:
        dialog = FirstAdminDialog(
            self,
            api_client=self.api,
            suggested_username=self.username_input.text().strip(),
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.username_input.setText(
                dialog.created_username
            )
            self.password_input.clear()
            self.password_input.setFocus()

    def open_password_reset(self) -> None:
        dialog = PasswordResetDialog(
            self,
            api_client=self.api,
            suggested_username=self.username_input.text().strip(),
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.username_input.setText(
                dialog.reset_username
            )
            self.password_input.clear()
            self.password_input.setFocus()

    def attempt_login(self) -> None:
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(
                self,
                "Login",
                "Please enter both username and password.",
            )
            return

        try:
            self.api.login(username, password)
            self.accept()
        except AuthenticationError:
            QMessageBox.critical(
                self,
                "Login Failed",
                (
                    "Invalid application username or password. "
                    "Database/PostgreSQL credentials cannot be used here."
                ),
            )
        except BackendConfigurationError:
            QMessageBox.critical(
                self,
                "Login Failed",
                (
                    "Backend authentication is not configured. Set a strong "
                    "SECRET_KEY and restart the backend."
                ),
            )
        except ServiceUnavailableError:
            QMessageBox.critical(
                self,
                "Login Failed",
                (
                    "Backend service is unavailable. Start or check the "
                    "backend, then try again."
                ),
            )
        except ApiError as error:
            QMessageBox.critical(
                self,
                "Login Failed",
                str(error),
            )
