from __future__ import annotations

import pandas as pd

from modules.analysis.ipdr.imei_investigation import (
    build_ipdr_imei_investigation,
)


IMEI_15 = "862518054878650"
IMEISV_16 = "8625180548786512"


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "subscriber_number": [
                "9000000001",
                "9000000002",
                "9000000001",
            ],
            "subscriber_identifier_type": [
                "MSISDN",
                "MSISDN",
                "MSISDN",
            ],
            "imei": [
                IMEI_15,
                IMEI_15,
                IMEISV_16,
            ],
            "imsi": [
                "405520123456789",
                "405520123456780",
                "405520123456789",
            ],
            "event_time": pd.to_datetime(
                [
                    "2026-01-01 10:00:00",
                    "2026-01-02 11:00:00",
                    "2026-01-03 12:00:00",
                ]
            ),
            "allocation_end": pd.to_datetime(
                [
                    "2026-01-01 10:05:00",
                    "2026-01-02 11:10:00",
                    "2026-01-03 12:15:00",
                ]
            ),
            "session_duration_seconds": [
                300,
                600,
                900,
            ],
            "source_ip": [
                "10.0.0.1",
                "10.0.0.2",
                "10.0.0.3",
            ],
            "source_port": [
                "1000",
                "1001",
                "1002",
            ],
            "translated_ip": [
                "100.64.0.1",
                "100.64.0.2",
                "100.64.0.3",
            ],
            "translated_port": [
                "2000",
                "2001",
                "2002",
            ],
            "destination_ip": [
                "8.8.8.8",
                "1.1.1.1",
                "8.8.4.4",
            ],
            "destination_port": [
                "443",
                "53",
                "443",
            ],
            "protocol": [
                "TCP",
                "UDP",
                "TCP",
            ],
            "apn": [
                "airtelgprs.com",
                "airtelgprs.com",
                "airtelgprs.com",
            ],
            "technology": [
                "4G",
                "4G",
                "4G",
            ],
            "cgi": [
                "405-52-3347-232803094",
                "",
                "405-52-3347-232803095",
            ],
            "first_cell_id": [
                "",
                "405-52-3347-232803096",
                "",
            ],
            "last_cell_id": [
                "",
                "405-52-3347-232803097",
                "",
            ],
            "charging_id": [
                "A",
                "B",
                "C",
            ],
            "source_file": [
                "first.csv",
                "second.csv",
                "third.csv",
            ],
            "source_row_number": [
                2,
                3,
                4,
            ],
        }
    )


def test_exact_15_digit_ipdr_search():
    result = build_ipdr_imei_investigation(
        _sample_frame(),
        IMEI_15,
    )

    assert result["status"] == "FOUND"
    assert result["record_count"] == 2

    assert set(
        result["timeline"]["Normalized IMEI"]
    ) == {
        IMEI_15,
    }

    assert set(
        result[
            "associated_subscribers"
        ][
            "Subscriber / User ID"
        ]
    ) == {
        "9000000001",
        "9000000002",
    }

    assert len(
        result["associated_sims"]
    ) == 2

    assert len(
        result["destination_endpoints"]
    ) == 2

    assert set(
        result["cells"]["Cell ID"]
    ) == {
        "405-52-3347-232803094",
        "405-52-3347-232803096",
        "405-52-3347-232803097",
    }


def test_exact_16_digit_ipdr_identifier_is_not_truncated():
    result = build_ipdr_imei_investigation(
        _sample_frame(),
        IMEISV_16,
    )

    assert result["status"] == "FOUND"
    assert result["record_count"] == 1

    assert (
        result["timeline"].loc[
            0,
            "Normalized IMEI",
        ]
        == IMEISV_16
    )

    observations = " ".join(
        result[
            "review_indicators"
        ][
            "Observation"
        ].astype(str)
    )

    assert "16-digit" in observations


def test_invalid_ipdr_imei_is_rejected():
    result = build_ipdr_imei_investigation(
        _sample_frame(),
        "12345",
    )

    assert result["status"] == "INVALID_IMEI"
    assert result["timeline"].empty


def test_ipdr_imei_not_found_returns_empty_bundle():
    result = build_ipdr_imei_investigation(
        _sample_frame(),
        "111111111111111",
    )

    assert result["status"] == "NOT_FOUND"
    assert result["record_count"] == 0
    assert result["summary"].empty


def test_ipdr_source_dataframe_is_not_modified():
    frame = _sample_frame()
    original = frame.copy(
        deep=True
    )

    build_ipdr_imei_investigation(
        frame,
        IMEI_15,
    )

    pd.testing.assert_frame_equal(
        frame,
        original,
    )

def test_dedicated_query_scope_preserves_observed_imeisv():
    """Match the exact report query without merging IMEI and IMEISV."""

    frame = _sample_frame().iloc[
        [
            2
        ]
    ].copy()

    frame[
        "query_identifier_raw"
    ] = IMEI_15

    frame[
        "query_identifier_normalized"
    ] = IMEI_15

    frame[
        "query_identifier_type"
    ] = "IMEI15"

    frame[
        "observed_imei_raw"
    ] = IMEISV_16

    frame[
        "observed_imei_normalized"
    ] = IMEISV_16

    frame[
        "match_relation"
    ] = "SAME_BASE14"

    original = frame.copy(
        deep=True
    )

    query_result = build_ipdr_imei_investigation(
        frame,
        IMEI_15,
    )

    assert query_result[
        "status"
    ] == "FOUND"

    assert query_result[
        "record_count"
    ] == 1

    query_record = query_result[
        "timeline"
    ].iloc[
        0
    ]

    assert query_record[
        "Query Identifier"
    ] == IMEI_15

    assert query_record[
        "Normalized IMEI"
    ] == IMEISV_16

    assert query_record[
        "Match Basis"
    ] == "QUERY_SCOPE"

    assert query_record[
        "Match Relation"
    ] == "SAME_BASE14"

    indicators = " ".join(
        query_result[
            "review_indicators"
        ][
            "Observation"
        ].astype(str)
    )

    assert (
        "dedicated report query"
        in indicators.lower()
    )

    exact_result = build_ipdr_imei_investigation(
        frame,
        IMEISV_16,
    )

    assert exact_result[
        "status"
    ] == "FOUND"

    exact_record = exact_result[
        "timeline"
    ].iloc[
        0
    ]

    assert exact_record[
        "Match Basis"
    ] == "EXACT_OBSERVED"

    # The relation still describes the report query versus observation.
    assert exact_record[
        "Match Relation"
    ] == "SAME_BASE14"

    unrelated_result = build_ipdr_imei_investigation(
        frame,
        "111111111111111",
    )

    assert unrelated_result[
        "status"
    ] == "NOT_FOUND"

    pd.testing.assert_frame_equal(
        frame,
        original,
    )

