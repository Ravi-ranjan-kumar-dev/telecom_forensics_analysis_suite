from __future__ import annotations

import pandas as pd

from modules.analysis.gprsdump.analysis import (
    create_gprs_partitions,
)
from modules.controllers import (
    tower_gprs_controller,
)
from modules.reporting.tower_gprs_excel import (
    _non_standard_identifier_row_count,
    _portable_report_path,
    _sanitize_gprs_report_frame,
)


def _row(
    *,
    subscriber_number: str,
    session_start: str,
    session_end: str,
) -> dict[str, object]:
    return {
        "subscriber_number": subscriber_number,
        "session_start": session_start,
        "session_end": session_end,
        "spot_id": "SPOT-01",
        "spot_name": "spot_1",
        "spot_folder": "spot_1",
        "searched_cell_id": "CELL-A",
        "imei": "111111111111111",
        "imsi": "405111111111111",
        "ipv4_address": "10.0.0.1",
        "ipv6_address": "",
        "total_volume": 100.0,
        "operator": "Airtel",
        "technology": "4G",
    }


def test_identifier_leads_are_separated():
    analysis = {
        "gprs_common_numbers": pd.DataFrame(
            [
                {
                    "subscriber_number": "9000000001",
                    "session_count": 5,
                },
                {
                    "subscriber_number": "5754027685869",
                    "session_count": 8,
                },
            ]
        )
    }

    result = (
        tower_gprs_controller
        ._separate_gprs_identifier_leads(
            analysis
        )
    )

    assert list(
        result[
            "gprs_common_numbers"
        ][
            "subscriber_number"
        ]
    ) == [
        "9000000001"
    ]

    assert list(
        result[
            "gprs_non_standard_leads"
        ][
            "subscriber_number"
        ]
    ) == [
        "5754027685869"
    ]


def test_spot_menu_file_counts_are_accurate(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "input"

    spot_1 = root / "spot_1"
    spot_2 = root / "spot_2"

    spot_1.mkdir(
        parents=True
    )
    spot_2.mkdir(
        parents=True
    )

    (spot_1 / "a.csv").write_text(
        "a",
        encoding="utf-8",
    )
    (spot_1 / "b.txt").write_text(
        "b",
        encoding="utf-8",
    )
    (spot_2 / "c.csv").write_text(
        "c",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        tower_gprs_controller,
        "_input_folder",
        lambda _case_id: root,
    )

    spots = (
        tower_gprs_controller
        ._available_gprs_spots(
            "CASE"
        )
    )

    counts = {
        item["spot_id"]: item["file_count"]
        for item in spots
    }

    assert counts == {
        "SPOT-01": 2,
        "SPOT-02": 1,
    }


def test_partition_mobile_and_nonstandard_are_separate():
    dataframe = pd.DataFrame(
        [
            _row(
                subscriber_number="9000000001",
                session_start="2026-06-11 19:10:00",
                session_end="2026-06-11 19:20:00",
            ),
            _row(
                subscriber_number="5754027685869",
                session_start="2026-06-11 19:15:00",
                session_end="2026-06-11 19:25:00",
            ),
            _row(
                subscriber_number="9000000001",
                session_start="2026-06-11 20:10:00",
                session_end="2026-06-11 20:20:00",
            ),
            _row(
                subscriber_number="5754027685869",
                session_start="2026-06-11 20:15:00",
                session_end="2026-06-11 20:25:00",
            ),
        ]
    )

    parts = [
        {
            "part_no": 1,
            "part_name": "Part 1",
            "start_time": "2026-06-11 19:00:00",
            "end_time": "2026-06-11 20:00:00",
            "spot_id": "SPOT-01",
            "spot_name": "spot_1",
            "spot_folder": "spot_1",
            "spot_scope_mode": "SELECTED_SPOT_ONLY",
        },
        {
            "part_no": 2,
            "part_name": "Part 2",
            "start_time": "2026-06-11 20:00:00",
            "end_time": "2026-06-11 21:00:00",
            "spot_id": "SPOT-01",
            "spot_name": "spot_1",
            "spot_folder": "spot_1",
            "spot_scope_mode": "SELECTED_SPOT_ONLY",
        },
    ]

    sightings = (
        tower_gprs_controller
        ._parts_to_gprs_sightings(
            parts
        )
    )

    result = create_gprs_partitions(
        dataframe,
        sightings=sightings,
        cgi_groups=[],
    )

    assert list(
        result[
            "strict_common_candidates"
        ][
            "subscriber_number"
        ]
    ) == [
        "9000000001"
    ]

    non_standard = result[
        "non_standard_subscriber_presence"
    ]

    assert list(
        non_standard[
            "subscriber_number"
        ]
    ) == [
        "5754027685869"
    ]

    assert (
        non_standard.iloc[0][
            "presence_class"
        ]
        == "STRICT_COMMON_NON_STANDARD"
    )


def test_report_paths_are_portable_and_ids_are_text():
    absolute = (
        "/home/user/project/"
        "data/tower_dump/gprs/input/spot_1/a.csv"
    )

    assert _portable_report_path(
        absolute
    ) == (
        "data/tower_dump/gprs/"
        "input/spot_1/a.csv"
    )

    frame = pd.DataFrame(
        [
            {
                "source_file": absolute,
                "source_relative_path": (
                    "spot_1/a.csv"
                ),
                "subscriber_number": (
                    5754027685869
                ),
            }
        ]
    )

    cleaned = (
        _sanitize_gprs_report_frame(
            frame
        )
    )

    assert (
        cleaned.iloc[0][
            "source_file"
        ]
        == "spot_1/a.csv"
    )

    assert isinstance(
        cleaned.iloc[0][
            "subscriber_number"
        ],
        str,
    )

def test_partition_report_drops_legacy_cctv_column():
    frame = pd.DataFrame(
        [
            {
                "partition_id": "P1",
                "cctv_timestamp": (
                    "2026-06-11 19:00:00"
                ),
                "window_start": (
                    "2026-06-11 19:00:00"
                ),
                "window_end": (
                    "2026-06-11 20:00:00"
                ),
            }
        ]
    )

    cleaned = _sanitize_gprs_report_frame(
        frame
    )

    assert (
        "cctv_timestamp"
        not in cleaned.columns
    )
    assert (
        "window_start"
        in cleaned.columns
    )
    assert (
        "window_end"
        in cleaned.columns
    )


def test_partition_status_has_no_hinglish():
    dataframe = pd.DataFrame(
        [
            _row(
                subscriber_number="9000000001",
                session_start=(
                    "2026-06-11 19:10:00"
                ),
                session_end=(
                    "2026-06-11 19:20:00"
                ),
            )
        ]
    )

    parts = [
        {
            "part_no": 1,
            "part_name": "Part 1",
            "start_time": (
                "2026-06-11 19:00:00"
            ),
            "end_time": (
                "2026-06-11 20:00:00"
            ),
            "spot_id": "SPOT-01",
            "spot_name": "spot_1",
            "spot_folder": "spot_1",
            "spot_scope_mode": (
                "SELECTED_SPOT_ONLY"
            ),
        }
    ]

    sightings = (
        tower_gprs_controller
        ._parts_to_gprs_sightings(
            parts
        )
    )

    result = create_gprs_partitions(
        dataframe,
        sightings=sightings,
        cgi_groups=[],
    )

    message = str(
        result[
            "partition_status"
        ].iloc[0][
            "message"
        ]
    ).lower()

    assert message.strip()
    assert "nahi" not in message
    assert "na maana" not in message

def test_non_standard_identifier_count_uses_analysis_rows():
    analysis = {
        "non_standard_identifiers": pd.DataFrame(
            [
                {
                    "subscriber_number": (
                        "5754027685869"
                    ),
                },
                {
                    "subscriber_number": (
                        "5754024644000"
                    ),
                },
            ]
        )
    }

    metadata = {
        "non_standard_identifier_rows": 0,
    }

    assert (
        _non_standard_identifier_row_count(
            analysis,
            metadata,
        )
        == 2
    )
