from __future__ import annotations

from pathlib import Path

import pandas as pd

from gui.app import build_application
from gui.pages.cdr_page import CdrPage
from gui.workers.cdr_worker import (
    collect_cdr_route_paths,
)
from modules.reporting.cdr_movement_route import (
    build_movement_route_points,
    generate_cdr_movement_route,
    movement_route_path,
)


def _movement_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "call_date": "30-07-2026",
                "call_time": "10:10:00",
                "first_cell_id": "404-55-102",
                "first_cell_latitude": 25.62,
                "first_cell_longitude": 85.15,
                "first_cell_site_name": "Second Site",
                "first_cell_address": "Second Address",
                "b_party": "8000000002",
                "call_type": "Outgoing",
            },
            {
                "call_date": "30-07-2026",
                "call_time": "10:00:00",
                "first_cell_id": "404-55-101",
                "first_cell_latitude": 25.61,
                "first_cell_longitude": 85.14,
                "first_cell_site_name": "First Site",
                "first_cell_address": "First Address",
                "b_party": "8000000001",
                "call_type": "Incoming",
            },
            {
                "call_date": "30-07-2026",
                "call_time": "10:05:00",
                "first_cell_id": "404-55-101",
                "first_cell_latitude": 25.61,
                "first_cell_longitude": 85.14,
                "first_cell_site_name": "First Site",
                "first_cell_address": "First Address",
                "b_party": "8000000003",
                "call_type": "SMS",
            },
        ]
    )


def test_movement_route_path_is_deterministic(
    tmp_path: Path,
):
    report = tmp_path / "target_report.xlsx"

    assert movement_route_path(
        report
    ) == (
        tmp_path
        / "target_report_movement_route.html"
    )


def test_route_points_are_chronological_and_suppress_stationary_rows():
    points = build_movement_route_points(
        _movement_frame(),
        target="9000000001",
    )

    assert [
        point[
            "cgi"
        ]
        for point in points
    ] == [
        "404-55-101",
        "404-55-102",
    ]
    assert [
        point[
            "sequence"
        ]
        for point in points
    ] == [
        1,
        2,
    ]
    assert points[
        0
    ][
        "timestamp"
    ] == "30-07-2026 10:00:00"


def test_route_ignores_rows_without_valid_coordinates():
    frame = _movement_frame()
    frame.loc[
        0,
        "first_cell_latitude",
    ] = 999

    points = build_movement_route_points(
        frame
    )

    assert len(
        points
    ) == 1
    assert points[
        0
    ][
        "cgi"
    ] == "404-55-101"


def test_movement_route_html_is_safe_and_has_fallback(
    tmp_path: Path,
):
    frame = _movement_frame()
    frame.loc[
        0,
        "first_cell_site_name",
    ] = "<img src=x onerror=alert(1)>"
    report = tmp_path / "target_report.xlsx"

    route_path = generate_cdr_movement_route(
        frame,
        target="9000000001",
        report_path=report,
    )

    assert route_path is not None
    text = route_path.read_text(
        encoding="utf-8"
    )
    assert "OpenStreetMap" in text
    assert "Interactive basemap resources could not be loaded" in text
    assert "<img src=x onerror=alert(1)>" not in text
    assert "\\u003cimg" in text
    assert "exact road travelled" in text


def test_collect_route_paths_and_enable_gui_button(
    tmp_path: Path,
):
    report = tmp_path / "target_report.xlsx"
    report.touch()
    route = movement_route_path(
        report
    )
    route.write_text(
        "<html></html>",
        encoding="utf-8",
    )

    assert collect_cdr_route_paths(
        [
            str(
                report
            ),
        ]
    ) == [
        str(
            route
        )
    ]

    build_application(
        [
            "cdr-route-test",
        ]
    )
    page = CdrPage()
    page._analysis_completed(
        {
            "report_paths": [
                str(
                    report
                ),
            ],
            "map_paths": [],
            "route_paths": [
                str(
                    route
                ),
            ],
        }
    )

    assert page.route_paths == (
        str(
            route
        ),
    )
    assert page._open_route_button.isEnabled()
    page.close()
