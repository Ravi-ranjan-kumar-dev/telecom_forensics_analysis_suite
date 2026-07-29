from __future__ import annotations

import os

os.environ.setdefault(
    "QT_QPA_PLATFORM",
    "offscreen",
)

from gui.app import build_application
from gui.main_window import (
    MainWindow,
    NAVIGATION_ITEMS,
)


def test_gui_application_metadata():
    application = build_application(
        [
            "gui-test",
        ]
    )

    assert application.applicationName() == (
        "Telecom Forensics Analysis Suite"
    )


def test_gui_navigation_matches_workspace():
    build_application(
        [
            "gui-test",
        ]
    )

    window = MainWindow()

    assert window.navigation_keys == tuple(
        item.key
        for item in NAVIGATION_ITEMS
    )

    assert window.navigation_keys == (
        "cdr",
        "tower_dump",
        "ipdr",
        "imei",
        "lookup",
        "case_details",
        "case_reports",
    )

    assert window.active_page_key == "cdr"

    window.close()


def test_gui_can_switch_pages_by_stable_key():
    build_application(
        [
            "gui-test",
        ]
    )

    window = MainWindow()

    window.select_page_by_key(
        "lookup"
    )
    assert window.active_page_key == "lookup"

    window.select_page_by_key(
        "case_reports"
    )
    assert window.active_page_key == "case_reports"

    window.close()
