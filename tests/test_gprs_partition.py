import pandas as pd

from modules.analysis.gprsdump import create_gprs_partitions


def test_true_session_overlap():
    dataframe = pd.DataFrame(
        {
            "subscriber_number": [
                    "9000000001",
                    "9000000002",
                    "9000000001",
                ],
            "imei": ["I1", "I2", "I1"],
            "imsi": ["S1", "S2", "S1"],
            "ipv4_address": ["10.0.0.1", "10.0.0.2", "10.0.0.1"],
            "ipv6_address": ["", "", ""],
            "operator": ["Airtel", "Airtel", "Airtel"],
            "total_volume": [100, 200, 300],
            "session_start": pd.to_datetime(
                [
                    "2026-06-11 12:45:00",
                    "2026-06-11 13:30:00",
                    "2026-06-11 13:55:00",
                ]
            ),
            "session_end": pd.to_datetime(
                [
                    "2026-06-11 13:05:00",
                    "2026-06-11 13:40:00",
                    "2026-06-11 14:05:00",
                ]
            ),
        }
    )

    sightings = [
        {
            "sighting_id": "S1",
            "cctv_timestamp": "2026-06-11 13:00:00",
            "window_start": "2026-06-11 12:50:00",
            "window_end": "2026-06-11 13:10:00",
            "minutes_before": 10,
            "minutes_after": 10,
        },
        {
            "sighting_id": "S2",
            "cctv_timestamp": "2026-06-11 14:00:00",
            "window_start": "2026-06-11 13:50:00",
            "window_end": "2026-06-11 14:10:00",
            "minutes_before": 10,
            "minutes_after": 10,
        },
    ]

    result = create_gprs_partitions(
        dataframe,
        sightings=sightings,
    )

    assert len(result["partitions"]["P1"]) == 1
    assert len(result["partitions"]["P2"]) == 1
    assert len(result["strict_common_candidates"]) == 1
    assert (
        result["strict_common_candidates"]
        .iloc[0]["subscriber_number"]
        == "9000000001"
    )
