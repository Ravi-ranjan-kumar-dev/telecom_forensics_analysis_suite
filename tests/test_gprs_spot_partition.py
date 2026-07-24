import pandas as pd

from modules.analysis.gprsdump.analysis import (
    create_gprs_partitions,
)


def _gprs_row(
    *,
    subscriber_number: str,
    session_start: str,
    session_end: str,
    searched_cell_id: str,
    spot_id: str,
    spot_name: str,
    operator: str,
    source_row_number: int,
) -> dict:
    start = pd.Timestamp(
        session_start
    )
    end = pd.Timestamp(
        session_end
    )

    downlink_volume = (
        source_row_number * 700
    )
    uplink_volume = (
        source_row_number * 300
    )

    return {
        "subscriber_number": subscriber_number,
        "subscriber_number_raw": subscriber_number,
        "identifier_type": "MSISDN",
        "imei": str(
            source_row_number
        ) * 15,
        "imei_raw": str(
            source_row_number
        ) * 15,
        "imsi": (
            "405"
            + str(
                source_row_number
            ) * 12
        ),
        "imsi_raw": (
            "405"
            + str(
                source_row_number
            ) * 12
        ),
        "ipv4_address": (
            f"10.0.0.{source_row_number}"
        ),
        "ipv4_address_raw": (
            f"10.0.0.{source_row_number}"
        ),
        "ipv6_address": "",
        "ipv6_address_raw": "",
        "session_start": start,
        "session_end": end,
        "session_duration_seconds": int(
            (
                end
                - start
            ).total_seconds()
        ),
        "session_time_valid": True,
        "downlink_volume": downlink_volume,
        "uplink_volume": uplink_volume,
        "total_volume": (
            downlink_volume
            + uplink_volume
        ),
        "volume_expected_total": (
            downlink_volume
            + uplink_volume
        ),
        "volume_difference": 0,
        "volume_tolerance": 0,
        "volume_fields_present": True,
        "volume_consistent": True,
        "volume_mismatch": False,
        "is_zero_volume": False,
        "searched_cell_id": searched_cell_id,
        "operator": operator,
        "spot_id": spot_id,
        "spot_name": spot_name,
        "spot_folder": spot_name,
        "source_file": (
            "synthetic_gprs_test.csv"
        ),
        "source_relative_path": (
            f"{spot_name}/"
            "synthetic_gprs_test.csv"
        ),
        "source_format": (
            "SYNTHETIC_TEST"
        ),
        "source_row_number": (
            source_row_number
        ),
        "_source_row_number": (
            source_row_number
        ),
        "input_mode": "TEST_FIXTURE",
    }


def test_gprs_partition_is_spot_aware_and_half_open():
    dataframe = pd.DataFrame(
        [
            _gprs_row(
                # Overlaps selected Part.
                subscriber_number=(
                    "9000000001"
                ),
                session_start=(
                    "2026-06-11 19:55:00"
                ),
                session_end=(
                    "2026-06-11 20:05:00"
                ),
                searched_cell_id=(
                    "CELL-A1"
                ),
                spot_id="SPOT-01",
                spot_name=(
                    "MURDER SPOT"
                ),
                operator="Airtel",
                source_row_number=1,
            ),
            _gprs_row(
                # Starts exactly at Part end.
                # Must be excluded.
                subscriber_number=(
                    "9000000002"
                ),
                session_start=(
                    "2026-06-11 20:10:00"
                ),
                session_end=(
                    "2026-06-11 20:20:00"
                ),
                searched_cell_id=(
                    "CELL-A2"
                ),
                spot_id="SPOT-01",
                spot_name=(
                    "MURDER SPOT"
                ),
                operator="Airtel",
                source_row_number=2,
            ),
            _gprs_row(
                # Overlaps in time but belongs
                # to another Spot.
                subscriber_number=(
                    "9000000003"
                ),
                session_start=(
                    "2026-06-11 20:01:00"
                ),
                session_end=(
                    "2026-06-11 20:06:00"
                ),
                searched_cell_id=(
                    "CELL-B1"
                ),
                spot_id="SPOT-02",
                spot_name=(
                    "PETROL PUMP"
                ),
                operator="Airtel",
                source_row_number=3,
            ),
        ]
    )

    sightings = [
        {
            "sighting_id": "P1",
            "partition_id": "P1",
            "location_name": (
                "Murder Spot Part 1"
            ),
            "window_start": (
                "2026-06-11 20:00:00"
            ),
            "window_end": (
                "2026-06-11 20:10:00"
            ),
            "cgi_group_id": "AUTO_ALL",
            "source_types": [
                "GPRS",
            ],
            "spot_scope_mode": (
                "SELECTED_SPOT_ONLY"
            ),
            "spot_id": "SPOT-01",
            "spot_name": (
                "MURDER SPOT"
            ),
            "spot_folder": (
                "MURDER SPOT"
            ),
        }
    ]

    result = create_gprs_partitions(
        dataframe,
        sightings=sightings,
        cgi_groups=[],
    )

    assert (
        result["overlap_rule"]
        == (
            "session_start < window_end "
            "AND session_end > window_start"
        )
    )

    part = result[
        "partitions"
    ]["P1"]

    assert (
        part[
            "subscriber_number"
        ]
        .astype(str)
        .tolist()
        == [
            "9000000001",
        ]
    )

    assert (
        part[
            "spot_id"
        ]
        .astype(str)
        .unique()
        .tolist()
        == [
            "SPOT-01",
        ]
    )

    assert (
        part[
            "partition_spot_id"
        ]
        .astype(str)
        .unique()
        .tolist()
        == [
            "SPOT-01",
        ]
    )

    assert (
        part[
            "partition_spot_scope_mode"
        ]
        .astype(str)
        .unique()
        .tolist()
        == [
            "SELECTED_SPOT_ONLY",
        ]
    )

    summary = result[
        "partition_summary"
    ]

    assert not summary.empty

    assert {
        "spot_id",
        "spot_name",
        "spot_scope_mode",
        "spot_scope_status",
    }.issubset(
        summary.columns
    )

    summary_row = (
        summary.iloc[0]
    )

    assert (
        summary_row["spot_id"]
        == "SPOT-01"
    )

    assert (
        summary_row[
            "spot_scope_status"
        ]
        == "VALID_SELECTED_SPOT"
    )

    assert (
        int(
            summary_row["sessions"]
        )
        == 1
    )

    presence = result[
        "subscriber_presence"
    ]

    assert not presence.empty

    assert {
        "operators",
        "total_volume",
        "total_overlap_seconds",
    }.issubset(
        presence.columns
    )

    assert (
        presence[
            "subscriber_number"
        ]
        .astype(str)
        .tolist()
        == [
            "9000000001",
        ]
    )

    assert (
        presence.iloc[0][
            "operators"
        ]
        == "Airtel"
    )

    excluded = result.get(
        "time_only_excluded_by_location",
        pd.DataFrame(),
    )

    if (
        isinstance(
            excluded,
            pd.DataFrame,
        )
        and not excluded.empty
        and "spot_id" in excluded.columns
    ):
        assert not (
            excluded[
                "spot_id"
            ]
            .astype(str)
            .eq("SPOT-02")
            .any()
        )
