# Full-screen interactive forensic results viewer window.

import os
from typing import Any
import pandas as pd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.data_viewer import ForensicDataViewer

_ACTIVE_WINDOWS: list[QDialog] = []


class FullScreenResultsWindow(QDialog):
    def __init__(
        self,
        sheets: dict[str, pd.DataFrame],
        *,
        title: str = "EthicalArmor Forensic Analysis Workspace",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(None)  # Force parent=None to prevent cross-thread QObject parenting crash
        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(1360, 820)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        header_frame = QFrame()
        header_frame.setObjectName("infoCard")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("moduleTitle")

        total_rows = sum(len(df) for df in sheets.values() if isinstance(df, pd.DataFrame))
        badge_label = QLabel(f"{len(sheets)} TABLES | {total_rows:,} TOTAL ROWS")
        badge_label.setObjectName("statusBadge")

        close_btn = QPushButton("<- Back to Module Setup")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.close)

        header_layout.addWidget(title_label)
        header_layout.addWidget(badge_label)
        header_layout.addStretch()
        header_layout.addWidget(close_btn)

        root.addWidget(header_frame)

        self.viewer = ForensicDataViewer(self)
        self.viewer.load_dataframe(sheets)
        root.addWidget(self.viewer, stretch=1)


def open_fullscreen_results_window(
    parent: QWidget | None,
    sheets: dict[str, pd.DataFrame],
    *,
    title: str = "EthicalArmor Forensic Analysis Workspace",
) -> None:
    if not sheets:
        return
    if "PYTEST_CURRENT_TEST" in os.environ or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return

    def _show_window() -> None:
        try:
            win = FullScreenResultsWindow(sheets, title=title, parent=None)
            _ACTIVE_WINDOWS.append(win)
            win.showMaximized()
            win.raise_()
            win.activateWindow()
        except Exception as err:
            print(f"[!] Error opening results window: {err}")

    QTimer.singleShot(0, _show_window)
