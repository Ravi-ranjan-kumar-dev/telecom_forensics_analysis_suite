from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

os.environ.setdefault(
    "QT_QPA_PLATFORM",
    "offscreen",
)

from gui.app import build_application
from gui.pages.cdr_page import (
    CdrPage,
    contact_map_choices,
)
from gui.workers.cdr_worker import (
    collect_cdr_map_paths,
)
from modules.reporting.cdr_contact_map import (
    build_contact_map_points,
    contact_map_path,
    generate_cdr_contact_map,
)


def _contact_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Other Party": "8000000001",
                "Name": "First Contact",
                "SDR Lookup Status": "FOUND",
                "Most Used Target CGI": "404-55-113-12101",
                "Most Used CGI Events": 5,
                "Most Used CGI Lookup Status": "FOUND",
                "Most Used Site Name": "Test Site",
                "Most Used Tower Address": "Test Tower Address",
                "Most Used Latitude": 25.61,
                "Most Used Longitude": 85.14,
                "Last Interaction CGI": "404-55-113-12101",
                "Last Interaction CGI Lookup Status": "FOUND",
                "Last Interaction Site Name": "Test Site",
                "Last Interaction Tower Address": "Test Tower Address",
                "Last Interaction Latitude": 25.61,
                "Last Interaction Longitude": 85.14,
                "Last Call Time": "17-03-2026 11:00:00",
            },
            {
                "Other Party": "8000000002",
                "Name": "Second Contact",
                "SDR Lookup Status": "NOT_FOUND",
                "Most Used Target CGI": "404-55-113-12101",
                "Most Used CGI Events": 3,
                "Most Used CGI Lookup Status": "FOUND",
                "Most Used Site Name": "Test Site",
                "Most Used Tower Address": "Test Tower Address",
                "Most Used Latitude": 25.61,
                "Most Used Longitude": 85.14,
                "Last Interaction CGI": "404-55-113-12102",
                "Last Interaction CGI Lookup Status": "NOT_FOUND",
                "Last Interaction Latitude": pd.NA,
                "Last Interaction Longitude": pd.NA,
                "Last Call Time": "18-03-2026 13:00:00",
            },
        ]
    )


def test_contact_map_path_is_deterministic(
    tmp_path: Path,
):
    report = tmp_path / "target_report.xlsx"

    assert contact_map_path(
        report
    ) == (
        tmp_path
        / "target_report_contact_map.html"
    )


def test_contact_map_choices_show_target_and_created_time(
    tmp_path: Path,
):
    map_path = (
        tmp_path
        / (
            "8210021561_cdr_report_20260730T100459_"
            "94625752_8c8df97c_contact_map.html"
        )
    )

    assert contact_map_choices(
        [
            str(
                map_path
            ),
        ]
    ) == [
        (
            "Target 8210021561 — 30-07-2026 10:04:59",
            str(
                map_path
            ),
        )
    ]


def test_contact_map_choices_keep_duplicate_labels_unique(
    tmp_path: Path,
):
    first = (
        tmp_path
        / "a"
        / (
            "8210021561_cdr_report_20260730T100459_"
            "first_contact_map.html"
        )
    )
    second = (
        tmp_path
        / "b"
        / (
            "8210021561_cdr_report_20260730T100459_"
            "second_contact_map.html"
        )
    )

    choices = contact_map_choices(
        [
            str(
                first
            ),
            str(
                second
            ),
        ]
    )

    assert [
        label
        for label, _ in choices
    ] == [
        "Target 8210021561 — 30-07-2026 10:04:59",
        "Target 8210021561 — 30-07-2026 10:04:59 (2)",
    ]
    assert [
        path
        for _, path in choices
    ] == [
        str(
            first
        ),
        str(
            second
        ),
    ]


def test_contact_map_points_group_same_tower_contacts():
    points = build_contact_map_points(
        _contact_frame(),
        target="9000000001",
    )

    most_used = next(
        point
        for point in points
        if point[
            "type"
        ] == "Most Used Tower"
    )

    assert most_used[
        "contact_count"
    ] == 2
    assert most_used[
        "event_count"
    ] == 8

    last_points = [
        point
        for point in points
        if point[
            "type"
        ] == "Last Interaction Tower"
    ]

    assert len(
        last_points
    ) == 1


def test_contact_map_html_is_safe_and_has_fallback(
    tmp_path: Path,
):
    frame = _contact_frame()
    frame.loc[
        0,
        "Name",
    ] = "<img src=x onerror=alert(1)>"

    report = tmp_path / "target_report.xlsx"
    map_path = generate_cdr_contact_map(
        frame,
        target="9000000001",
        report_path=report,
    )
    text = map_path.read_text(
        encoding="utf-8"
    )

    assert map_path.is_file()
    assert "OpenStreetMap" in text
    assert "Interactive basemap resources could not be loaded" in text
    assert "<img src=x onerror=alert(1)>" not in text
    assert "\\u003cimg" in text


def test_collect_cdr_map_paths_ignores_missing_sidecars(
    tmp_path: Path,
):
    first_report = tmp_path / "first.xlsx"
    second_report = tmp_path / "second.xlsx"

    first_report.touch()
    second_report.touch()

    first_map = contact_map_path(
        first_report
    )
    first_map.write_text(
        "<html></html>",
        encoding="utf-8",
    )

    assert collect_cdr_map_paths(
        [
            str(
                first_report
            ),
            str(
                second_report
            ),
        ]
    ) == [
        str(
            first_map
        )
    ]


def test_cdr_page_accepts_generated_map_paths(
    tmp_path: Path,
):
    build_application(
        [
            "cdr-map-test",
        ]
    )

    map_path = tmp_path / "target_contact_map.html"
    map_path.write_text(
        "<html></html>",
        encoding="utf-8",
    )

    page = CdrPage()
    page._analysis_completed(
        {
            "report_paths": [],
            "map_paths": [
                str(
                    map_path
                ),
            ],
        }
    )

    assert page.map_paths == (
        str(
            map_path
        ),
    )
    assert page._open_map_button.isEnabled()

    page.close()
