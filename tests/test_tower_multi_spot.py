from __future__ import annotations

import pandas as pd

from modules.analysis.towerdump.multi_spot import (
    build_multi_spot_analysis,
    filter_multi_spot_time_range,
)


def _sample_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "subscriber_number": "9000000001",
                "spot_id": "SPOT-01",
                "spot_name": "Murder Spot",
                "call_datetime": "2026-06-29 21:50:00",
                "operator": "airtel",
                "searched_cell_id": "CELL-A",
                "imei": "IMEI-A",
                "imsi": "IMSI-A",
                "source_relative_path": "Murder Spot/a.csv",
            },
            {
                "subscriber_number": "9000000001",
                "spot_id": "SPOT-02",
                "spot_name": "Petrol Pump",
                "call_datetime": "2026-06-29 22:00:00",
                "operator": "airtel",
                "searched_cell_id": "CELL-B",
                "imei": "IMEI-A",
                "imsi": "IMSI-A",
                "source_relative_path": "Petrol Pump/b.csv",
            },
            {
                "subscriber_number": "9000000002",
                "spot_id": "SPOT-01",
                "spot_name": "Murder Spot",
                "call_datetime": "2026-06-29 21:55:00",
                "operator": "jio",
                "searched_cell_id": "CELL-A",
                "imei": "IMEI-B",
                "imsi": "IMSI-B",
                "source_relative_path": "Murder Spot/jio.csv",
            },
            {
                "subscriber_number": "9000000003",
                "spot_id": "SPOT-02",
                "spot_name": "Petrol Pump",
                "call_datetime": "2026-06-29 22:05:00",
                "operator": "vi",
                "searched_cell_id": "CELL-B",
                "imei": "IMEI-C",
                "imsi": "IMSI-C",
                "source_relative_path": "Petrol Pump/vi.csv",
            },
            {
                "subscriber_number": "9000000004",
                "spot_id": "SPOT-01",
                "spot_name": "Murder Spot",
                "call_datetime": "2026-06-29 21:52:00",
                "operator": "airtel",
                "searched_cell_id": "CELL-A",
                "imei": "IMEI-D1",
                "imsi": "IMSI-D",
                "source_relative_path": "Murder Spot/d1.csv",
            },
            {
                "subscriber_number": "9000000004",
                "spot_id": "SPOT-02",
                "spot_name": "Petrol Pump",
                "call_datetime": "2026-06-29 22:02:00",
                "operator": "airtel",
                "searched_cell_id": "CELL-B",
                "imei": "IMEI-D2",
                "imsi": "IMSI-D",
                "source_relative_path": "Petrol Pump/d2.csv",
            },
            {
                "subscriber_number": "9000000005",
                "spot_id": "SPOT-01",
                "spot_name": "Murder Spot",
                "call_datetime": "2026-06-29 21:53:00",
                "operator": "jio",
                "searched_cell_id": "CELL-A",
                "imei": "IMEI-SHARED",
                "imsi": "IMSI-E",
                "source_relative_path": "Murder Spot/e.csv",
            },
            {
                "subscriber_number": "9000000006",
                "spot_id": "SPOT-02",
                "spot_name": "Petrol Pump",
                "call_datetime": "2026-06-29 22:03:00",
                "operator": "jio",
                "searched_cell_id": "CELL-B",
                "imei": "IMEI-SHARED",
                "imsi": "IMSI-F",
                "source_relative_path": "Petrol Pump/f.csv",
            },
        ]
    )


def test_multi_spot_common_and_exclusive_numbers():
    result = build_multi_spot_analysis(
        _sample_dataframe()
    )

    assert result["total_spots"] == 2

    common_numbers = set(
        result[
            "all_spot_common_numbers"
        ]["subscriber_number"]
    )

    assert common_numbers == {
        "9000000001",
        "9000000004",
    }

    exclusive_numbers = set(
        result[
            "spot_exclusive_numbers"
        ]["subscriber_number"]
    )

    assert exclusive_numbers == {
        "9000000002",
        "9000000003",
        "9000000005",
        "9000000006",
    }


def test_multi_spot_device_and_identifier_continuity():
    result = build_multi_spot_analysis(
        _sample_dataframe()
    )

    continuity = result[
        "cross_spot_device_continuity"
    ].set_index(
        "subscriber_number"
    )

    assert (
        continuity.loc[
            "9000000001",
            "imei_continuity",
        ]
        == "SAME IMEI ACROSS SPOTS"
    )

    assert (
        continuity.loc[
            "9000000004",
            "imei_continuity",
        ]
        == "MULTIPLE IMEI ACROSS SPOTS"
    )

    shared_imei = result[
        "shared_imei_across_spots"
    ]

    assert "IMEI-SHARED" in set(
        shared_imei["imei"]
    )


def test_cross_spot_sequence_is_time_ordered():
    result = build_multi_spot_analysis(
        _sample_dataframe()
    )

    sequence = result[
        "cross_spot_sequence"
    ]

    subscriber_sequence = sequence.loc[
        sequence[
            "subscriber_number"
        ].eq(
            "9000000001"
        )
    ]

    assert len(
        subscriber_sequence
    ) == 1

    row = subscriber_sequence.iloc[0]

    assert row["from_spot_id"] == "SPOT-01"
    assert row["to_spot_id"] == "SPOT-02"
    assert row["time_gap_minutes"] == 10.0


def test_multi_spot_time_range_is_half_open():
    dataframe = _sample_dataframe()

    filtered = filter_multi_spot_time_range(
        dataframe,
        start_time="2026-06-29 21:50:00",
        end_time="2026-06-29 22:00:00",
    )

    assert pd.Timestamp(
        "2026-06-29 21:50:00"
    ) in set(
        filtered["call_datetime"]
    )

    assert pd.Timestamp(
        "2026-06-29 22:00:00"
    ) not in set(
        filtered["call_datetime"]
    )
