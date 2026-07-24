from __future__ import annotations

import inspect

import pandas as pd

from modules.analysis.gprsdump.analysis import (
    create_gprs_partitions,
)
from modules.controllers import (
    tower_gprs_controller,
)


def test_parts_convert_to_spot_scoped_sightings():
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
            "spot_id": "SPOT-02",
            "spot_name": "spot_2",
            "spot_folder": "spot_2",
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

    assert len(sightings) == 1

    sighting = sightings[0]

    assert sighting["window_start"] == (
        "2026-06-11 19:00:00"
    )
    assert sighting["window_end"] == (
        "2026-06-11 20:00:00"
    )
    assert sighting["spot_id"] == "SPOT-02"
    assert sighting["cgi_group_id"] == "AUTO_ALL"


def test_collector_uses_start_end_and_spot(
    monkeypatch,
):
    answers = iter(
        [
            "11-06-2026",
            "19:00",
            "",
            "20:00",
            "2",
            "",
        ]
    )

    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt="": next(answers),
    )

    spots = [
        {
            "spot_id": "SPOT-01",
            "spot_name": "spot_1",
            "spot_folder": "spot_1",
            "file_count": 10,
        },
        {
            "spot_id": "SPOT-02",
            "spot_name": "spot_2",
            "spot_folder": "spot_2",
            "file_count": 13,
        },
    ]

    parts = (
        tower_gprs_controller
        ._collect_date_time_pairs(
            spots
        )
    )

    assert len(parts) == 1
    assert parts[0]["start_time"] == (
        "2026-06-11 19:00:00"
    )
    assert parts[0]["end_time"] == (
        "2026-06-11 20:00:00"
    )
    assert parts[0]["spot_id"] == "SPOT-02"
    assert parts[0]["spot_scope_mode"] == (
        "SELECTED_SPOT_ONLY"
    )


def test_partition_applies_spot_and_half_open_overlap():
    dataframe = pd.DataFrame(
        [
            {
                "subscriber_number": "9000000001",
                "session_start": "2026-06-11 19:10:00",
                "session_end": "2026-06-11 19:20:00",
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
            },
            {
                "subscriber_number": "9000000002",
                "session_start": "2026-06-11 19:10:00",
                "session_end": "2026-06-11 19:30:00",
                "spot_id": "SPOT-02",
                "spot_name": "spot_2",
                "spot_folder": "spot_2",
                "searched_cell_id": "CELL-B",
                "imei": "222222222222222",
                "imsi": "405222222222222",
                "ipv4_address": "10.0.0.2",
                "ipv6_address": "",
                "total_volume": 200.0,
                "operator": "Airtel",
                "technology": "5G",
            },
            {
                "subscriber_number": "9000000003",
                "session_start": "2026-06-11 18:30:00",
                "session_end": "2026-06-11 19:00:00",
                "spot_id": "SPOT-02",
                "spot_name": "spot_2",
                "spot_folder": "spot_2",
                "searched_cell_id": "CELL-B",
                "imei": "333333333333333",
                "imsi": "405333333333333",
                "ipv4_address": "10.0.0.3",
                "ipv6_address": "",
                "total_volume": 300.0,
                "operator": "Airtel",
                "technology": "4G",
            },
        ]
    )

    parts = [
        {
            "part_no": 1,
            "part_name": "Part 1",
            "start_time": "2026-06-11 19:00:00",
            "end_time": "2026-06-11 20:00:00",
            "spot_id": "SPOT-02",
            "spot_name": "spot_2",
            "spot_folder": "spot_2",
            "spot_scope_mode": "SELECTED_SPOT_ONLY",
        }
    ]

    sightings = (
        tower_gprs_controller
        ._parts_to_gprs_sightings(parts)
    )

    result = create_gprs_partitions(
        dataframe,
        sightings=sightings,
        cgi_groups=[],
    )

    partition = result["partitions"]["P1"]

    assert list(
        partition["subscriber_number"]
    ) == ["9000000002"]

    summary = result[
        "partition_summary"
    ].iloc[0]

    assert summary["spot_id"] == "SPOT-02"
    assert summary["sessions"] == 1
    assert summary["unique_subscribers"] == 1

    assert result["overlap_rule"] == (
        "session_start < window_end "
        "AND session_end > window_start"
    )



def test_controller_no_longer_uses_zero_window_storage():
    new_partition_source = inspect.getsource(
        tower_gprs_controller
        ._new_partition
    )

    execute_source = inspect.getsource(
        tower_gprs_controller
        ._execute
    )

    assert (
        "replace_simple_sightings"
        not in new_partition_source
    )
    assert (
        "save_date_time_parts"
        in new_partition_source
    )
    assert (
        "list_date_time_parts"
        in execute_source
    )
    assert (
        "_parts_to_gprs_sightings"
        in execute_source
    )
