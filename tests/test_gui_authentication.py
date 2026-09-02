"""GUI behavior tests for login, first-time setup and password reset."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QDialog, QMessageBox

from gui.api_client import (
    AuthenticationError,
    ServiceUnavailableError,
)
from gui.app import build_application
from gui.login_dialog import (
    FirstAdminDialog,
    LoginDialog,
    PasswordResetDialog,
)


class FakeAuthClient:
    def __init__(self) -> None:
        self.login_error: Exception | None = None
        self.login_calls: list[tuple[str, str]] = []
        self.setup_calls: list[tuple[str, str]] = []
        self.reset_calls: list[dict[str, str]] = []

    def login(self, username: str, password: str) -> bool:
        self.login_calls.append((username, password))
        if self.login_error is not None:
            raise self.login_error
        return True

    def setup_status(self) -> bool:
        return True

    def setup_first_admin(
        self,
        username: str,
        password: str,
    ) -> dict[str, object]:
        self.setup_calls.append((username, password))
        return {
            "id": 1,
            "username": username,
            "role": "admin",
            "is_active": True,
        }

    def reset_password(
        self,
        *,
        username: str,
        token: str,
        new_password: str,
    ) -> bool:
        self.reset_calls.append(
            {
                "username": username,
                "token": token,
                "new_password": new_password,
            }
        )
        return True


@pytest.fixture(scope="module", autouse=True)
def application():
    return build_application(["gui-auth-test"])


def test_login_exposes_setup_and_forgot_password_actions() -> None:
    dialog = LoginDialog(api_client=FakeAuthClient())

    assert dialog.setup_button.text() == "First-time Setup"
    assert (
        dialog.forgot_password_button.text()
        == "Forgot Password?"
    )
    dialog.close()


@pytest.mark.parametrize(
    ("error", "expected_text"),
    [
        (
            AuthenticationError("invalid"),
            "Invalid application username or password",
        ),
        (
            ServiceUnavailableError("down"),
            "Backend service is unavailable",
        ),
    ],
    ids=["wrong-password", "backend-down"],
)
def test_login_error_messages_are_distinct(
    monkeypatch,
    error: Exception,
    expected_text: str,
) -> None:
    client = FakeAuthClient()
    client.login_error = error
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, message: messages.append(
            (title, message)
        ),
    )
    dialog = LoginDialog(api_client=client)
    dialog.username_input.setText("case_admin")
    dialog.password_input.setText("Entered Password")

    dialog.attempt_login()

    assert expected_text in messages[0][1]
    dialog.close()


def test_login_does_not_strip_password_characters() -> None:
    client = FakeAuthClient()
    dialog = LoginDialog(api_client=client)
    dialog.username_input.setText(" case_admin ")
    dialog.password_input.setText("  exact password value  ")

    dialog.attempt_login()

    assert client.login_calls == [
        ("case_admin", "  exact password value  ")
    ]
    assert dialog.result() == QDialog.DialogCode.Accepted
    dialog.close()


def test_first_admin_dialog_creates_admin_without_default_password(
    monkeypatch,
) -> None:
    client = FakeAuthClient()
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args: None,
    )
    dialog = FirstAdminDialog(
        api_client=client,
        suggested_username="case_admin",
    )
    dialog.password_input.setText(
        "Correct Horse Battery Staple"
    )
    dialog.confirm_input.setText(
        "Correct Horse Battery Staple"
    )

    dialog.attempt_setup()

    assert client.setup_calls == [
        ("case_admin", "Correct Horse Battery Staple")
    ]
    assert dialog.result() == QDialog.DialogCode.Accepted
    dialog.close()


def test_password_reset_dialog_submits_host_issued_token(
    monkeypatch,
) -> None:
    client = FakeAuthClient()
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args: None,
    )
    dialog = PasswordResetDialog(
        api_client=client,
        suggested_username="case_admin",
    )
    dialog.token_input.setPlainText(
        "host-issued-token-value-that-is-long-enough"
    )
    dialog.password_input.setText(
        "A Different Long Password 2026"
    )
    dialog.confirm_input.setText(
        "A Different Long Password 2026"
    )

    dialog.attempt_reset()

    assert client.reset_calls == [
        {
            "username": "case_admin",
            "token": "host-issued-token-value-that-is-long-enough",
            "new_password": "A Different Long Password 2026",
        }
    ]
    assert dialog.result() == QDialog.DialogCode.Accepted
    dialog.close()
