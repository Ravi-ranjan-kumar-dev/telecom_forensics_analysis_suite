from __future__ import annotations

import inspect

from modules.cases import (
    date_time_partitions,
)
from modules.controllers import (
    tower_ipdr_controller,
)


def test_spot_metadata_is_preserved(
    tmp_path,
    monkeypatch,
):
    target = (
        tmp_path
        / "tower_ipdr_date_time_parts.json"
    )

    monkeypatch.setattr(
        date_time_partitions,
        "date_time_partition_path",
        lambda _case_id, _workflow: target,
    )

    payload = (
        date_time_partitions
        .save_date_time_parts(
            "TEST-CASE",
            "tower_ipdr",
            [
                {
                    "start_time": (
                        "2026-06-11 20:00:00"
                    ),
                    "end_time": (
                        "2026-06-11 20:20:00"
                    ),
                    "spot_id": "SPOT-01",
                    "spot_name": "spot_1",
                    "spot_folder": "spot_1",
                },
                {
                    "start_time": (
                        "2026-06-11 20:20:00"
                    ),
                    "end_time": (
                        "2026-06-11 20:40:00"
                    ),
                    "spot_id": "SPOT-02",
                    "spot_name": "spot_2",
                    "spot_folder": "spot_2",
                },
            ],
        )
    )

    assert payload["schema_version"] == 2
    assert payload["parts_count"] == 2

    first = payload["parts"][0]
    second = payload["parts"][1]

    assert first["spot_id"] == "SPOT-01"
    assert first["spot_name"] == "spot_1"
    assert (
        first["spot_scope_mode"]
        == "SELECTED_SPOT_ONLY"
    )
    assert (
        first["spot_scope_status"]
        == "VALID_SELECTED_SPOT"
    )

    assert second["spot_id"] == "SPOT-02"

    assert (
        first["start_time"]
        == "2026-06-11 20:00:00"
    )
    assert (
        first["end_time"]
        == "2026-06-11 20:20:00"
    )


def test_legacy_range_remains_readable(
    tmp_path,
    monkeypatch,
):
    target = (
        tmp_path
        / "legacy_parts.json"
    )

    monkeypatch.setattr(
        date_time_partitions,
        "date_time_partition_path",
        lambda _case_id, _workflow: target,
    )

    payload = (
        date_time_partitions
        .save_date_time_parts(
            "TEST-CASE",
            "tower_ipdr",
            [
                (
                    "2026-06-11 20:00:00",
                    "2026-06-11 20:10:00",
                )
            ],
        )
    )

    part = payload["parts"][0]

    assert part["spot_id"] == ""
    assert (
        part["spot_scope_mode"]
        == "LEGACY_ALL_SPOTS"
    )


def test_controller_requires_spot_selection():
    source = inspect.getsource(
        tower_ipdr_controller
        ._create_date_time_parts
    )

    assert (
        "_tower_ipdr_available_spots"
        in source
    )
    assert (
        "_select_tower_ipdr_spot"
        in source
    )
    assert "scoped_ranges" in source
    assert '"spot_id"' in source
