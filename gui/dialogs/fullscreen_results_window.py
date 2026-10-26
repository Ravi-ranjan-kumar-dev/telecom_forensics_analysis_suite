# Full-screen interactive forensic results viewer window for EthicalArmor
from __future__ import annotations

import os
import pandas as pd
from PySide6.QtCore import Qt
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
from gui.utils.thread_dispatcher import run_on_main_thread
from modules.utils.cdr_column_sanitizer import sanitize_sheets_dict

_ACTIVE_WINDOWS: list[QDialog] = []


class FullScreenResultsWindow(QDialog):
    def __init__(
        self,
        sheets: dict[str, pd.DataFrame],
        *,
        title: str = 'EthicalArmor Forensic Analysis Workspace',
        parent: QWidget | None = None,
        case_id: str | None = None,
        source_id: str = "",
    ) -> None:
        super().__init__(None)
        display_title = f"{title} — Case: {case_id}" if case_id else title
        self.setWindowTitle(display_title)
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

        header_frame = QFrame(self)
        header_frame.setObjectName('infoCard')
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(12)

        title_label = QLabel(display_title, header_frame)
        title_label.setObjectName('moduleTitle')

        total_rows = sum(len(df) for df in sheets.values() if isinstance(df, pd.DataFrame))
        badge_label = QLabel(f'{len(sheets)} TABLES | {total_rows:,} TOTAL ROWS', header_frame)
        badge_label.setObjectName('statusBadge')

        close_btn = QPushButton('<- Back to Module Setup', header_frame)
        close_btn.setObjectName('secondaryButton')
        close_btn.clicked.connect(self.close)

        header_layout.addWidget(title_label)
        header_layout.addWidget(badge_label)
        header_layout.addStretch()
        header_layout.addWidget(close_btn)

        root.addWidget(header_frame)

        self.viewer = ForensicDataViewer(self,case_id=case_id,source_id=source_id)
        self.viewer.load_dataframe(sheets)
        root.addWidget(self.viewer, stretch=1)


def open_fullscreen_results_window(
    parent: QWidget | None,
    sheets: dict[str, pd.DataFrame],
    *,
    title: str = 'EthicalArmor Forensic Analysis Workspace',
    case_id: str | None = None,
    source_id: str = "",
) -> None:
    if not sheets:
        return
    if 'PYTEST_CURRENT_TEST' in os.environ or os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
        return

    from modules.controllers.app_controller import get_active_gui_case_id
    case_id = case_id or getattr(parent,"_result_case_id",None) or get_active_gui_case_id()
    safe_sheets = {
        str(k): (v.copy() if isinstance(v, pd.DataFrame) else pd.DataFrame(v))
        for k, v in sheets.items()
        if v is not None
    }


    def _show_window() -> None:
        try:
            win = FullScreenResultsWindow(safe_sheets, title=title, parent=None,case_id=case_id,source_id=source_id)
            _ACTIVE_WINDOWS.append(win)
            if len(_ACTIVE_WINDOWS) > 3:
                old_win = _ACTIVE_WINDOWS.pop(0)
                old_win.close()
                old_win.deleteLater()
            win.showMaximized()
            win.raise_()
            win.activateWindow()
        except Exception as err:
            # EA_RESULTS_ERROR_CAPTURE_V1
            try:
                from modules.core.diagnostic_events import record_handled_exception as _ea_record_results_error
                _ea_record_results_error()
            except Exception:
                pass
            import traceback
            print(f'[!] Error opening results window: {err}', flush=True)
            traceback.print_exc()

    run_on_main_thread(_show_window)


