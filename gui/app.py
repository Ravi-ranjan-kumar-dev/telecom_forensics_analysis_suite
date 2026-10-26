"""Application bootstrap for the desktop GUI - Professional Edition."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from gui.login_dialog import LoginDialog
from gui.main_window import MainWindow
from gui.theme import APP_STYLESHEET

os.environ["TELECOM_GUI_MODE"] = "1"

def build_application(
    arguments: Sequence[str] | None = None,
) -> QApplication:
    application = QApplication.instance()
    if application is None:
        application = QApplication(
            list(arguments if arguments is not None else sys.argv)
        )
    application.setApplicationName("EthicalArmor - Telecom & Digital Forensics Suite")
    application.setApplicationDisplayName("EthicalArmor - Telecom & Digital Forensics Suite")
    application.setOrganizationName("EthicalArmor")
    application.setStyle("Fusion")
    application.setStyleSheet(APP_STYLESHEET)
    return application

def main() -> int:
    try:
        from modules.core.logger import setup_global_logging, get_logger
        setup_global_logging()
        logger = get_logger("gui.app")
        logger.info("Starting EthicalArmor GUI")
    except Exception:
        import logging
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger("gui.app")

    application = build_application()
    login_dialog = LoginDialog()
    if login_dialog.exec() != LoginDialog.DialogCode.Accepted:
        return 0
    window = MainWindow(api_client=login_dialog.api)
    application.main_window = window
    window.show()
    exit_code = application.exec()
    # Release clipboard ownership while QApplication and fonts are still alive.
    # A clipboard manager asking for rich text during shutdown otherwise
    # aborts Qt ("Must construct a QGuiApplication before accessing QFontDatabase").
    try:
        application.clipboard().clear()
        window.close()
        window.deleteLater()
        application.processEvents()
    except Exception:
        logger.exception("GUI shutdown cleanup failed")
    return exit_code
