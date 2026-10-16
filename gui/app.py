# gui/app.py
"""Application bootstrap for the desktop GUI."""

from __future__ import annotations

# === GUI_NON_BLOCKING_STDIN_GUARD ===
import builtins as _builtins
import os as _os
import threading as _threading

_os.environ["TELECOM_GUI_MODE"] = "1"
_THREAD_INPUT_COUNTS: dict[int, int] = {}


def _gui_safe_input(prompt: object = "") -> str:
    tid = _threading.get_ident()
    cnt = _THREAD_INPUT_COUNTS.get(tid, 0) + 1
    _THREAD_INPUT_COUNTS[tid] = cnt
    prompt_str = str(prompt or "").strip()
    if prompt_str:
        print(f"[GUI Auto-Continue] {prompt_str}", flush=True)
    if cnt > 3:
        _THREAD_INPUT_COUNTS[tid] = 0
        raise EOFError("GUI mode: interactive CLI prompt skipped.")
    if any(k in prompt_str.lower() for k in ("choose", "select", "enter number", "choice", "[1")):
        return "1"
    return ""


_builtins.input = _gui_safe_input


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
        "EthicalArmor - Telecom Forensics Suite"
    )
    application.setApplicationDisplayName(
        "EthicalArmor - Telecom Forensics Suite"
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