from __future__ import annotations

import inspect

import duckdb

from modules.controllers import (
    tower_ipdr_controller,
)
from modules.staging import (
    tower_ipdr_staging,
)


def _create_test_database(
    database_path,
):
    connection = duckdb.connect(
        str(database_path)
    )

    try:
        connection.execute(
            """
            CREATE TABLE tower_ipdr_events (
                subscriber_number VARCHAR,
                searched_cell_id VARCHAR,
                imei VARCHAR,
                imsi VARCHAR,
                event_time TIMESTAMP,
                spot_id VARCHAR,
                spot_name VARCHAR
            )
            """
        )

        connection.executemany(
            """
            INSERT INTO tower_ipdr_events
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "A",
                    "CELL-A",
                    "IMEI-A",
                    "IMSI-A",
                    "2026-06-11 20:01:00",
                    "SPOT-01",
                    "spot_1",
                ),
                (
                    "A",
                    "CELL-X",
                    "IMEI-A",
                    "IMSI-A",
                    "2026-06-11 20:21:00",
                    "SPOT-02",
                    "spot_2",
                ),
                (
                    "B",
                    "CELL-A",
                    "IMEI-B",
                    "IMSI-B",
                    "2026-06-11 20:02:00",
                    "SPOT-01",
                    "spot_1",
                ),
                (
                    "C",
                    "CELL-A",
                    "IMEI-C",
                    "IMSI-C",
                    "2026-06-11 20:03:00",
                    "SPOT-01",
                    "spot_1",
                ),
                (
                    "C",
                    "CELL-A",
                    "IMEI-C",
                    "IMSI-C",
                    "2026-06-11 19:50:00",
                    "SPOT-01",
                    "spot_1",
                ),
                (
                    "D",
                    "CELL-A",
                    "IMEI-D",
                    "IMSI-D",
                    "2026-06-11 20:04:00",
                    "SPOT-01",
                    "spot_1",
                ),
                (
                    "D",
                    "CELL-Z",
                    "IMEI-D",
                    "IMSI-D",
                    "2026-06-11 20:45:00",
                    "SPOT-03",
                    "spot_3",
                ),
                (
                    "E",
                    "CELL-A",
                    "IMEI-E",
                    "IMSI-E",
                    "2026-06-11 20:05:00",
                    "SPOT-01",
                    "spot_1",
                ),
                (
                    "E",
                    "CELL-B",
                    "IMEI-E",
                    "IMSI-E",
                    "2026-06-11 20:06:00",
                    "SPOT-01",
                    "spot_1",
                ),
            ],
        )

    finally:
        connection.close()


def test_three_level_uncommon_classification(
    tmp_path,
    monkeypatch,
):
    database_path = (
        tmp_path
        / "tower_ipdr.duckdb"
    )

    _create_test_database(
        database_path
    )

    monkeypatch.setattr(
        tower_ipdr_staging,
        "tower_ipdr_database_path",
        lambda _case_id: database_path,
    )

    parts = [
        {
            "part_no": 1,
            "start_time": (
                "2026-06-11 20:00:00"
            ),
            "end_time": (
                "2026-06-11 20:10:00"
            ),
            "spot_id": "SPOT-01",
            "spot_name": "spot_1",
        },
        {
            "part_no": 2,
            "start_time": (
                "2026-06-11 20:20:00"
            ),
            "end_time": (
                "2026-06-11 20:30:00"
            ),
            "spot_id": "SPOT-02",
            "spot_name": "spot_2",
        },
    ]

    result = (
        tower_ipdr_staging
        .tower_ipdr_range_investigation_summary(
            "TEST-CASE",
            "2026-06-11 20:00:00",
            "2026-06-11 20:10:00",
            spot_id="SPOT-01",
            spot_name="spot_1",
            comparison_parts=parts,
            current_part_no=1,
            lead_limit=50,
        )
    )

    summary = result["summary"].iloc[0]

    assert summary["spot_id"] == "SPOT-01"
    assert (
        summary["spot_scope_mode"]
        == "SELECTED_SPOT_ONLY"
    )
    assert int(summary["records_found"]) == 6
    assert int(summary["numbers_found"]) == 5
    assert int(summary["cells_involved"]) == 2

    classification = (
        result[
            "uncommon_classification"
        ]
        .set_index(
            "mobile_number"
        )
    )

    assert (
        classification.loc[
            "A",
            "part_status",
        ]
        == "SEEN_IN_OTHER_PART"
    )

    assert (
        classification.loc[
            "A",
            "spot_status",
        ]
        == "NEW_IN_SPOT"
    )

    assert (
        classification.loc[
            "B",
            "global_status",
        ]
        == "GLOBAL_UNCOMMON"
    )

    assert (
        classification.loc[
            "C",
            "part_status",
        ]
        == "PART_ONLY"
    )

    assert (
        classification.loc[
            "C",
            "spot_status",
        ]
        == "SEEN_IN_SPOT_OUTSIDE_PART"
    )

    assert (
        classification.loc[
            "D",
            "spot_status",
        ]
        == "NEW_IN_SPOT"
    )

    assert (
        classification.loc[
            "D",
            "global_status",
        ]
        == "SEEN_ELSEWHERE"
    )

    global_numbers = set(
        result[
            "global_uncommon_numbers"
        ]["mobile_number"]
    )

    assert global_numbers == {
        "B",
        "E",
    }

    multi_cell_numbers = set(
        result[
            "multi_cell_presence"
        ]["mobile_number"]
    )

    assert "E" in multi_cell_numbers


def test_partwise_controller_passes_spot_scope():
    source = inspect.getsource(
        tower_ipdr_controller
        ._run_partwise_analysis
    )

    for token in (
        "spot_id=",
        "spot_name=",
        "comparison_parts=parts",
        "current_part_no=",
    ):
        assert token in source
