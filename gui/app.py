# gui/app.py
"""Application bootstrap for the desktop GUI."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from gui.login_dialog import LoginDialog
from gui.main_window import MainWindow
from gui.theme import APP_STYLESHEET


def build_application(
    arguments: Sequence[str] | None = None,
) -> QApplication:
    """Create or reuse the Qt application object."""

    application = QApplication.instance()

    if application is None:
        application = QApplication(
            list(
                arguments
                if arguments is not None
                else sys.argv
            )
        )

    application.setApplicationName(
        "Telecom Forensics Analysis Suite"
    )
    application.setApplicationDisplayName(
        "Telecom Forensics Analysis Suite"
    )
    application.setOrganizationName(
        "Telecom Forensics"
    )
    application.setStyle(
        "Fusion"
    )
    application.setStyleSheet(
        APP_STYLESHEET
    )

    return application


def main() -> int:
    """Start the desktop application after successful login."""

    application = build_application()

    # Show login dialog first
    login_dialog = LoginDialog()

    if login_dialog.exec() != LoginDialog.DialogCode.Accepted:
        return 0  # User cancelled login, exit

    # Create main window and pass the api_client
    window = MainWindow(api_client=login_dialog.api)

    # Keep a strong reference for the complete application lifetime.
    application.main_window = window

    window.show()

    return application.exec()