from __future__ import annotations

from pathlib import Path

import pandas as pd


def test_jio_dayfirst_parser_keeps_dd_mm_order():
    from modules.loader.ipdr_loader import _combine_datetime, _parse_jio_datetime

    event = _parse_jio_datetime(pd.Series(["11/06/2026 19:40:00"]))
    allocation = _combine_datetime(
        pd.Series(["11/06/2026"]),
        pd.Series(["19:40:00"]),
    )

    assert event.iloc[0] == pd.Timestamp("2026-06-11 19:40:00")
    assert allocation.iloc[0] == pd.Timestamp("2026-06-11 19:40:00")


def test_gprs_partition_requires_resolved_cgi_match():
    from modules.analysis.gprsdump import create_gprs_partitions

    dataframe = pd.DataFrame(
        {
            "subscriber_number": ["111", "222"],
            "imei": ["I1", "I2"],
            "imsi": ["S1", "S2"],
            "ipv4_address": ["10.0.0.1", "10.0.0.2"],
            "ipv6_address": ["", ""],
            "operator": ["Airtel", "Airtel"],
            "total_volume": [100, 200],
            "searched_cell_id": ["405-01-A", "405-01-B"],
            "session_start": pd.to_datetime(["2026-06-11 12:55:00"] * 2),
            "session_end": pd.to_datetime(["2026-06-11 13:05:00"] * 2),
        }
    )
    sightings = [
        {
            "sighting_id": "S1",
            "location_name": "Camera A",
            "cctv_timestamp": "2026-06-11 13:00:00",
            "window_start": "2026-06-11 12:50:00",
            "window_end": "2026-06-11 13:10:00",
            "cgi_group_id": "G1",
            "source_types": ["GPRS"],
        }
    ]
    groups = [{"group_id": "G1", "cgi_values": ["40501A"]}]

    result = create_gprs_partitions(
        dataframe,
        sightings=sightings,
        cgi_groups=groups,
    )

    assert result["partitions"]["P1"]["subscriber_number"].tolist() == ["111"]
    assert len(result["time_only_excluded_by_location"]) == 1
    assert result["partition_status"].iloc[0]["status"] == "VALID_LOCATION_SCOPED"


def test_tower_ipdr_partition_requires_resolved_cgi_match():
    from modules.analysis.toweripdr import create_tower_ipdr_partitions

    dataframe = pd.DataFrame(
        {
            "subscriber_number": ["111", "222"],
            "imei": ["I1", "I2"],
            "imsi": ["S1", "S2"],
            "searched_cell_id": ["CELL-A", "CELL-B"],
            "event_time": pd.to_datetime(["2026-06-11 13:00:00"] * 2),
            "allocation_start": pd.to_datetime(["2026-06-11 12:00:00"] * 2),
            "allocation_end": pd.to_datetime(["2026-06-11 14:00:00"] * 2),
            "allocation_key": ["A1", "A2"],
            "allocation_volume_key": ["AV1", "AV2"],
        }
    )
    sightings = [
        {
            "sighting_id": "S1",
            "location_name": "Camera A",
            "cctv_timestamp": "2026-06-11 13:00:00",
            "window_start": "2026-06-11 12:50:00",
            "window_end": "2026-06-11 13:10:00",
            "cgi_group_id": "G1",
            "source_types": ["IPDR"],
        }
    ]
    groups = [{"group_id": "G1", "cgi_values": ["CELLA"]}]

    result = create_tower_ipdr_partitions(
        dataframe,
        sightings=sightings,
        cgi_groups=groups,
    )

    assert result["actual_event_hits"]["subscriber_number"].tolist() == ["111"]
    assert result["allocation_overlap_hits"]["subscriber_number"].tolist() == ["111"]
    assert len(result["actual_time_only_excluded_by_location"]) == 1
    assert len(result["allocation_time_only_excluded_by_location"]) == 1


def test_activity_does_not_merge_same_week_or_month_across_years():
    from modules.analysis.cdr.activity import monthly_activity, weekly_activity

    dataframe = pd.DataFrame(
        {
            "datetime": pd.to_datetime(
                [
                    "2025-01-02 10:00:00",
                    "2026-01-02 10:00:00",
                ]
            )
        }
    )

    weekly = weekly_activity(dataframe)
    monthly = monthly_activity(dataframe)

    assert len(weekly) == 2
    assert set(weekly["ISO Year"].astype(int)) == {2025, 2026}
    assert len(monthly) == 2
    assert set(monthly["Year-Month"]) == {"2025-01", "2026-01"}


def test_potential_duplicates_are_flagged_and_retained():
    from modules.loader.duplicate_flags import flag_potential_duplicates

    dataframe = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-01-01 10:00:00"] * 2),
            "a_party": ["999", "999"],
            "b_party": ["888", "888"],
            "call_type": ["outgoing", "outgoing"],
            "call_duration": [30, 30],
            "source_file": ["part1.csv", "part2.csv"],
            "source_row_number": [10, 20],
        }
    )

    output = flag_potential_duplicates(dataframe)

    assert len(output) == 2
    assert output["is_potential_duplicate"].all()
    assert output["potential_duplicate_count"].tolist() == [2, 2]


def test_csv_reader_quarantines_extra_nonempty_fields(tmp_path: Path):
    from modules.loader.evidence_csv import read_csv_with_quarantine

    source = tmp_path / "sample.csv"
    source.write_text(
        "a,b,c\n"
        "1,2,3\n"
        "4,5,6,UNEXPECTED\n"
        "7,8\n",
        encoding="utf-8",
    )

    accepted, rejected, metadata = read_csv_with_quarantine(source)

    assert len(accepted) == 2
    assert accepted["_source_row_number"].tolist() == [2, 4]
    assert accepted.iloc[1]["c"] == ""
    assert len(rejected) == 1
    assert rejected.iloc[0]["source_row_number"] == 3
    assert "FIELD_COUNT_MISMATCH" in rejected.iloc[0]["rejection_reason"]
    assert metadata["adjusted_rows"] == 1


def test_jio_loader_preserves_physical_rows_and_quarantines_invalid(tmp_path: Path):
    from modules.loader.ipdr_loader import FORMAT_JIO, load_ipdr_file

    source = tmp_path / "jio_target_ipdr.csv"
    source.write_text(
        "Source IP Address,Destination IP Address,Landline/MSISDN/MDN/Leased Circuit ID for Internet Access,TIME1 (dd/MM/yyyy HH:mm:ss),Source Port,Destination Port,First CELL ID,Last CELL ID\n"
        "10.0.0.1,8.8.8.8,9876543210,11/06/2026 19:40:00,1234,53,CELL-A,CELL-A\n"
        "10.0.0.2,1.1.1.1,9876543210,INVALID,1235,443,CELL-B,CELL-B\n",
        encoding="utf-8",
    )

    result = load_ipdr_file(source)

    assert result["ok"] is True
    assert result["metadata"]["source_format"] == FORMAT_JIO
    assert len(result["data"]) == 1
    assert result["data"].iloc[0]["event_time"] == pd.Timestamp("2026-06-11 19:40:00")
    assert int(result["data"].iloc[0]["source_row_number"]) == 2
    assert len(result["rejected_rows"]) == 1
    assert int(result["rejected_rows"].iloc[0]["source_row_number"]) == 3


def test_multi_cdr_merge_preserves_rejected_row_ledger():
    from modules.loader.multi_loader import merge_same_target_cdrs

    rejected_one = pd.DataFrame({"source_file": ["one.csv"], "source_row_number": [9]})
    rejected_two = pd.DataFrame({"source_file": ["two.csv"], "source_row_number": [12]})
    base = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-01-01 10:00:00"]),
            "a_party": ["999"],
            "b_party": ["888"],
            "call_type": ["outgoing"],
            "call_duration": [30],
        }
    )

    merged = merge_same_target_cdrs(
        [
            {"file": "one.csv", "target": "9999999999", "target_method": "test", "df": base.copy(), "rejected_rows": rejected_one},
            {"file": "two.csv", "target": "9999999999", "target_method": "test", "df": base.copy(), "rejected_rows": rejected_two},
        ]
    )

    assert len(merged) == 1
    assert len(merged[0]["df"]) == 2
    assert len(merged[0]["rejected_rows"]) == 2
    assert len(merged[0]["df"].attrs["rejected_rows"]) == 2


def test_tower_cdr_partition_rejects_nonmatching_cgi_group():
    from modules.analysis.towerdump.window_partition import create_sighting_partitions

    dataframe = pd.DataFrame(
        {
            "subscriber_number": ["111", "222"],
            "searched_cell_id": ["CELL-A", "CELL-B"],
            "first_cell_id": ["CELL-A", "CELL-B"],
            "last_cell_id": ["CELL-A", "CELL-B"],
            "call_datetime": pd.to_datetime(["2026-06-11 13:00:00"] * 2),
        }
    )
    sighting = {
        "sighting_id": "S1",
        "location_name": "Camera A",
        "cctv_timestamp": "2026-06-11 13:00:00",
        "window_start": "2026-06-11 12:50:00",
        "window_end": "2026-06-11 13:10:00",
        "cgi_group_id": "G1",
        "source_types": ["NORMAL_CDR"],
    }

    valid = create_sighting_partitions(
        dataframe,
        sightings=[sighting],
        cgi_groups=[{"group_id": "G1", "cgi_values": ["CELL-A"]}],
    )
    invalid = create_sighting_partitions(
        dataframe,
        sightings=[sighting],
        cgi_groups=[{"group_id": "G1", "cgi_values": ["CELL-X"]}],
    )

    assert valid["partitions"]["S1"]["subscriber_number"].tolist() == ["111"]
    assert valid["partition_status"].iloc[0]["status"] == "VALID_LOCATION_SCOPED"
    assert invalid["total_sightings"] == 0
    assert invalid["partition_status"].iloc[0]["status"] == "NO_MATCHING_LOADED_CGI"
