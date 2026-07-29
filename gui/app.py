"""Application bootstrap for the desktop GUI."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

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
    """Start the desktop application."""

    application = build_application()

    window = MainWindow()
    window.show()

    return application.exec()
