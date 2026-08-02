from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault(
    "QT_QPA_PLATFORM",
    "offscreen",
)

from gui.app import build_application
from gui.main_window import MainWindow, NAVIGATION_ITEMS
from gui.pages.case_reports_page import (
    CaseReportEntry,
    CaseReportsPage,
    build_case_report_entries,
)


def test_report_entries_find_existing_map_sidecars(
    tmp_path: Path,
):
    report = (
        tmp_path
        / (
            "8210021561_cdr_report_20260730T100459_"
            "sample.xlsx"
        )
    )
    report.touch()
    contact = report.with_name(
        f"{report.stem}_contact_map.html"
    )
    route = report.with_name(
        f"{report.stem}_movement_route.html"
    )
    contact.write_text(
        "<html></html>",
        encoding="utf-8",
    )
    route.write_text(
        "<html></html>",
        encoding="utf-8",
    )

    entries = build_case_report_entries(
        [
            {
                "report_type": "MULTIPLE_CDR_INDIVIDUAL",
                "report_path": str(
                    report
                ),
            },
            {
                "report_type": "DUPLICATE",
                "report_path": str(
                    report
                ),
            },
        ]
    )

    assert len(
        entries
    ) == 1
    assert entries[
        0
    ].target == "8210021561"
    assert entries[
        0
    ].created_at == "30-07-2026 15:34:59 IST"
    assert entries[
        0
    ].contact_map_path == contact
    assert entries[
        0
    ].movement_route_path == route


def test_relative_registry_path_resolves_from_case_directory(
    tmp_path: Path,
):
    case_directory = (
        tmp_path
        / "cases"
        / "active"
        / "DEV-WORKSPACE"
    )
    report = (
        case_directory
        / "reports"
        / "cdr"
        / "single"
        / (
            "7209062997_cdr_report_20260730T155617_"
            "044839Z_0cdb023c.xlsx"
        )
    )
    report.parent.mkdir(
        parents=True
    )
    report.touch()
    contact = report.with_name(
        f"{report.stem}_contact_map.html"
    )
    route = report.with_name(
        f"{report.stem}_movement_route.html"
    )
    contact.touch()
    route.touch()

    entries = build_case_report_entries(
        [
            {
                "report_type": "SINGLE_CDR",
                "report_path": (
                    "reports/cdr/single/"
                    f"{report.name}"
                ),
            },
        ],
        base_directory=case_directory,
    )

    assert len(
        entries
    ) == 1
    assert entries[
        0
    ].report_path == report
    assert entries[
        0
    ].contact_map_path == contact
    assert entries[
        0
    ].movement_route_path == route


def test_common_report_has_no_incorrect_map_actions(
    tmp_path: Path,
):
    report = tmp_path / "multiple_common_report.xlsx"
    report.touch()

    entries = build_case_report_entries(
        [
            {
                "report_type": "MULTIPLE_CDR_COMMON",
                "report_path": str(
                    report
                ),
            },
        ]
    )

    assert len(
        entries
    ) == 1
    assert entries[
        0
    ].contact_map_path is None
    assert entries[
        0
    ].movement_route_path is None


def test_stored_iso_timestamp_is_compact(
    tmp_path: Path,
):
    report = tmp_path / "target_report.xlsx"
    report.touch()

    entries = build_case_report_entries(
        [
            {
                "report_type": "SINGLE_CDR",
                "report_path": str(
                    report
                ),
                "created_at": "2026-07-30T11:30:21.752053+00:00",
            },
        ]
    )

    assert entries[
        0
    ].report_type == "Single CDR"
    assert entries[
        0
    ].created_at == "30-07-2026 17:00:21 IST"


def test_case_reports_page_builds_available_actions(
    tmp_path: Path,
):
    build_application(
        [
            "case-reports-test",
        ]
    )

    report = tmp_path / "target_report.xlsx"
    contact = tmp_path / "target_report_contact_map.html"
    route = tmp_path / "target_report_movement_route.html"
    report.touch()
    contact.touch()
    route.touch()

    entry = CaseReportEntry(
        report_type="Single Cdr",
        target="9000000001",
        created_at="30-07-2026 10:00:00",
        report_path=report,
        contact_map_path=contact,
        movement_route_path=route,
    )
    page = CaseReportsPage(
        case_id="TEST-CASE",
        loader=lambda case_id: [
            entry
        ],
    )

    assert page.entries == (
        entry,
    )
    assert page._table.rowCount() == 1
    assert page._table.cellWidget(
        0,
        4,
    ).isEnabled()
    assert page._table.cellWidget(
        0,
        5,
    ).isEnabled()
    assert page._table.cellWidget(
        0,
        6,
    ).isEnabled()
    page.close()


def test_case_reports_page_hides_missing_history_by_default(
    tmp_path: Path,
):
    build_application(
        [
            "case-reports-filter-test",
        ]
    )

    available = tmp_path / "available.xlsx"
    missing = tmp_path / "missing.xlsx"
    available.touch()

    entries = [
        CaseReportEntry(
            report_type="Single CDR",
            target="9000000001",
            created_at="30-07-2026 10:00:00",
            report_path=available,
            contact_map_path=None,
            movement_route_path=None,
        ),
        CaseReportEntry(
            report_type="Single CDR",
            target="9000000002",
            created_at="30-07-2026 11:00:00",
            report_path=missing,
            contact_map_path=None,
            movement_route_path=None,
        ),
    ]
    page = CaseReportsPage(
        case_id="TEST-CASE",
        loader=lambda case_id: entries,
    )

    assert len(
        page.entries
    ) == 1
    assert page._table.rowCount() == 1

    page._show_missing.setChecked(
        True
    )

    assert len(
        page.entries
    ) == 2
    assert page._table.rowCount() == 2
    assert page._table.cellWidget(
        0,
        4,
    ).text() == "Missing"
    assert page._table.cellWidget(
        0,
        5,
    ).text() == "—"
    page.close()


def test_case_reports_table_supports_target_and_date_sorting(tmp_path: Path):
    build_application(["case-reports-sort-test"])
    first = tmp_path / "first.xlsx"
    second = tmp_path / "second.xlsx"
    first.touch()
    second.touch()
    entries = [
        CaseReportEntry(
            report_type="Single CDR",
            target="9000000002",
            created_at="29-07-2026 10:00:00 IST",
            report_path=first,
            contact_map_path=None,
            movement_route_path=None,
        ),
        CaseReportEntry(
            report_type="Tower CDR",
            target="9000000001",
            created_at="30-07-2026 10:00:00 IST",
            report_path=second,
            contact_map_path=None,
            movement_route_path=None,
        ),
    ]
    page = CaseReportsPage(case_id="TEST-CASE", loader=lambda case_id: entries)

    assert page._table.item(0, 2).text() == "30-07-2026 10:00:00 IST"

    page._table.sortItems(1)
    assert page._table.item(0, 1).text() == "9000000001"

    page._table.sortItems(2)
    assert page._table.item(0, 2).text() == "29-07-2026 10:00:00 IST"
    page.close()


def test_main_window_uses_real_case_reports_page():
    build_application(
        [
            "case-reports-window-test",
        ]
    )
    window = MainWindow()
    window.select_page_by_key(
        "case_reports"
    )

    assert isinstance(
        window._page_stack.currentWidget(),
        CaseReportsPage,
    )
    assert next(
        item.title
        for item in NAVIGATION_ITEMS
        if item.key == "case_reports"
    ) == "View Case Reports"
    window.close()
