"""Visual polish for report-history table actions; no business logic changes."""
from PySide6.QtCore import QTimer, QSize
from PySide6.QtWidgets import QPushButton, QTableWidget, QStyle, QSizePolicy

_ACTIONS = {
    "Open Report": ("Report", "SP_FileIcon"),
    "Open Map": ("Map", "SP_DirIcon"),
    "Open Route": ("Route", "SP_ArrowRight"),
}


def _polish_actions(page):
    from shiboken6 import isValid
    if not isValid(page) or not page.isVisible():
        return
    for table in page.findChildren(QTableWidget):
        header = table.horizontalHeader()
        action_columns = []
        for col in range(table.columnCount()):
            label = table.horizontalHeaderItem(col)
            title = label.text().strip().lower() if label else ""
            if title in {"report", "contact map", "movement route"}:
                action_columns.append(col)
        if not action_columns:
            continue
        table.verticalHeader().setDefaultSectionSize(46)
        for col in action_columns:
            table.setColumnWidth(col, max(table.columnWidth(col), 132))
        for row in range(min(table.rowCount(), 1000)):
            if table.rowHeight(row) < 46:
                table.setRowHeight(row, 46)
            for col in action_columns:
                widget = table.cellWidget(row, col)
                if widget is None:
                    continue
                buttons = ([widget] if isinstance(widget, QPushButton) else widget.findChildren(QPushButton))
                for button in buttons:
                    text = button.text().strip()
                    info = _ACTIONS.get(text)
                    if not info:
                        continue
                    short, icon_name = info
                    button.setText(short)
                    button.setToolTip(text)
                    button.setIcon(button.style().standardIcon(getattr(QStyle.StandardPixmap, icon_name)))
                    button.setIconSize(QSize(17, 17))
                    button.setMinimumHeight(34)
                    button.setMinimumWidth(110)
                    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                    button.setStyleSheet("QPushButton { padding: 5px 9px; font-weight: 600; border-radius: 7px; }")
                    button.setProperty("ea_report_polished", True)


def install_report_history_polish(page):
    """Lightweight cosmetic refresh for dynamically populated history rows."""
    timer = QTimer(page)
    timer.setInterval(1300)
    timer.timeout.connect(lambda: _polish_actions(page))
    timer.start()
    QTimer.singleShot(100, lambda: _polish_actions(page))
    page._ea_report_polish_timer = timer
