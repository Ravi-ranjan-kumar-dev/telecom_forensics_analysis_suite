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
"""
