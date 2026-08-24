"""Application theme definitions."""

APP_STYLESHEET = """
QWidget {
    background-color: #0b1220;
    color: #e5e7eb;
    font-family: "DejaVu Sans";
    font-size: 13px;
}

QMainWindow {
    background-color: #0b1220;
}

QFrame#sidebar {
    background-color: #111827;
    border-right: 1px solid #243247;
}

QLabel#brandTitle {
    color: #f8fafc;
    font-size: 18px;
    font-weight: 700;
}

QLabel#brandSubtitle {
    color: #93a4b8;
    font-size: 11px;
}

QLabel#sectionLabel {
    color: #718096;
    font-size: 10px;
    font-weight: 700;
}

QPushButton#navButton {
    background-color: transparent;
    color: #cbd5e1;
    border: 0;
    border-radius: 8px;
    padding: 12px 14px;
    text-align: left;
    font-size: 13px;
    font-weight: 600;
}

QPushButton#navButton:hover {
    background-color: #1b2638;
    color: #ffffff;
}

QPushButton#navButton:checked {
    background-color: #1d4ed8;
    color: #ffffff;
}

QPushButton#closeButton {
    background-color: #1b2638;
    color: #fca5a5;
    border: 1px solid #374151;
    border-radius: 8px;
    padding: 11px 14px;
    text-align: left;
    font-weight: 600;
}

QPushButton#closeButton:hover {
    background-color: #7f1d1d;
    color: #ffffff;
    border-color: #991b1b;
}

QFrame#contentPanel {
    background-color: #0b1220;
}

QLabel#pageTitle {
    color: #f8fafc;
    font-size: 24px;
    font-weight: 700;
}

QLabel#pageSubtitle {
    color: #94a3b8;
    font-size: 12px;
}

QFrame#pageSurface {
    background-color: #111827;
    border: 1px solid #263449;
    border-radius: 12px;
}

QLabel#moduleTitle {
    color: #f8fafc;
    font-size: 22px;
    font-weight: 700;
}

QLabel#moduleDescription {
    color: #b8c3d1;
    font-size: 14px;
}

QLabel#statusBadge {
    background-color: #123826;
    color: #86efac;
    border: 1px solid #166534;
    border-radius: 10px;
    padding: 5px 10px;
    font-size: 10px;
    font-weight: 700;
}

QFrame#infoCard {
    background-color: #0f1a2b;
    border: 1px solid #2a394f;
    border-radius: 10px;
}

QLabel#cardHeading {
    color: #e2e8f0;
    font-size: 14px;
    font-weight: 700;
}

QLabel#cardText {
    color: #94a3b8;
    font-size: 12px;
}

QLabel#stepNumber {
    background-color: #1d4ed8;
    color: #ffffff;
    border-radius: 12px;
    min-width: 24px;
    max-width: 24px;
    min-height: 24px;
    max-height: 24px;
    font-weight: 700;
}

QStatusBar {
    background-color: #111827;
    color: #94a3b8;
    border-top: 1px solid #263449;
}

QToolTip {
    background-color: #111827;
    color: #f8fafc;
    border: 1px solid #475569;
}
QLabel#fieldLabel {
    color: #cbd5e1;
    font-size: 11px;
    font-weight: 700;
}

QLabel#statusText {
    color: #93c5fd;
    font-size: 12px;
}

QLineEdit#inputControl,
QComboBox#inputControl {
    background-color: #0b1220;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 10px 12px;
    min-height: 20px;
}

QLineEdit#inputControl:focus,
QComboBox#inputControl:focus {
    border-color: #3b82f6;
}

QComboBox#inputControl QAbstractItemView {
    background-color: #111827;
    color: #f8fafc;
    selection-background-color: #1d4ed8;
}

QPushButton#primaryButton {
    background-color: #2563eb;
    color: #ffffff;
    border: 0;
    border-radius: 8px;
    padding: 11px 18px;
    font-weight: 700;
}

QPushButton#primaryButton:hover {
    background-color: #1d4ed8;
}

QPushButton#primaryButton:disabled {
    background-color: #334155;
    color: #94a3b8;
}

QPushButton#secondaryButton {
    background-color: #172033;
    color: #dbeafe;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 10px 16px;
    font-weight: 600;
}

QPushButton#secondaryButton:hover {
    background-color: #1e293b;
    border-color: #475569;
}

QPushButton#secondaryButton:disabled {
    color: #64748b;
    background-color: #111827;
}

QPlainTextEdit#analysisLog {
    background-color: #08101d;
    color: #cbd5e1;
    border: 1px solid #263449;
    border-radius: 8px;
    padding: 10px;
    font-family: "DejaVu Sans Mono";
    font-size: 11px;
}

QProgressBar#analysisProgress {
    background-color: #0b1220;
    border: 1px solid #334155;
    border-radius: 6px;
    min-height: 10px;
    max-height: 10px;
    text-align: center;
}

QProgressBar#analysisProgress::chunk {
    background-color: #2563eb;
    border-radius: 5px;
}

QLabel#noticeText {
    background-color: #172554;
    color: #bfdbfe;
    border: 1px solid #1e40af;
    border-radius: 7px;
    padding: 8px 10px;
    font-size: 11px;
}

QLabel#warningBadge {
    background-color: #422006;
    color: #fde68a;
    border: 1px solid #a16207;
    border-radius: 10px;
    padding: 5px 10px;
    font-size: 10px;
    font-weight: 700;
}

QFrame#metricCard {
    background-color: #0f1a2b;
    border: 1px solid #2a394f;
    border-radius: 9px;
}

QLabel#metricValue {
    color: #f8fafc;
    font-size: 21px;
    font-weight: 700;
}

QLabel#metricLabel {
    color: #94a3b8;
    font-size: 11px;
}

QTabWidget#lookupTabs::pane {
    background-color: #0f1a2b;
    border: 1px solid #2a394f;
    border-radius: 8px;
    top: -1px;
}

QTabBar::tab {
    background-color: #111827;
    color: #94a3b8;
    border: 1px solid #2a394f;
    padding: 9px 14px;
    margin-right: 3px;
    min-width: 110px;
}

QTabBar::tab:selected {
    background-color: #1d4ed8;
    color: #ffffff;
    border-color: #2563eb;
}

QTabBar::tab:hover:!selected {
    background-color: #1e293b;
    color: #e2e8f0;
}

QTableWidget#dataTable {
    background-color: #08101d;
    alternate-background-color: #0d1726;
    color: #dbeafe;
    border: 1px solid #263449;
    border-radius: 7px;
    gridline-color: #263449;
    selection-background-color: #1d4ed8;
    selection-color: #ffffff;
}

QTableWidget#dataTable QHeaderView::section {
    background-color: #172033;
    color: #cbd5e1;
    border: 0;
    border-right: 1px solid #334155;
    border-bottom: 1px solid #334155;
    padding: 8px;
    font-weight: 700;
}

QTableWidget#dataTable::item {
    padding: 5px;
}

QScrollBar:vertical {
    background-color: #0b1220;
    width: 12px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #334155;
    border-radius: 6px;
    min-height: 28px;
}

QScrollBar::handle:vertical:hover {
    background-color: #475569;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}
"""
