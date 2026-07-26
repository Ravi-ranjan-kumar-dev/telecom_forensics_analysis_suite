from __future__ import annotations

import pandas as pd

from modules.analysis.gprsdump.imei_investigation import (
    build_gprs_imei_investigation,
)


IMEI_15 = "862518054878650"
IMEISV_16 = "8625180548786512"


def _sample_frame() -> pd.DataFrame:
    starts = pd.to_datetime(
        [
            "2026-06-11 19:10:00",
            "2026-06-11 20:10:00",
            "2026-06-11 21:10:00",
        ]
    )

    ends = pd.to_datetime(
        [
            "2026-06-11 19:15:00",
            "2026-06-11 20:20:00",
            "2026-06-11 21:25:00",
        ]
    )

    return pd.DataFrame(
        {
            "record_type": [
                "GPRS_SESSION",
                "GPRS_SESSION",
                "GPRS_SESSION",
            ],
            "source_format": [
                "AIRTEL_GPRS_SESSION",
                "AIRTEL_GPRS_SESSION",
                "AIRTEL_GPRS_SESSION",
            ],
            "operator": [
                "Airtel",
                "Airtel",
                "Airtel",
            ],
            "subscriber_number_raw": [
                "9000000001",
                "9000000002",
                "9000000001",
            ],
            "subscriber_number": [
                "9000000001",
                "9000000002",
                "9000000001",
            ],
            "identifier_type": [
                "MSISDN",
                "MSISDN",
                "MSISDN",
            ],
            "ipv4_address_raw": [
                "10.0.0.1",
                "",
                "10.0.0.3",
            ],
            "ipv4_address": [
                "10.0.0.1",
                "",
                "10.0.0.3",
            ],
            "ipv6_address_raw": [
                "",
                "2001:db8::1",
                "",
            ],
            "ipv6_address": [
                "",
                "2001:db8::1",
                "",
            ],
            "imei_raw": [
                IMEI_15,
                IMEI_15,
                IMEISV_16,
            ],
            "imei": [
                IMEI_15,
                IMEI_15,
                IMEISV_16,
            ],
            "imsi_raw": [
                "405520123456789",
                "405520123456780",
                "405520123456789",
            ],
            "imsi": [
                "405520123456789",
                "405520123456780",
                "405520123456789",
            ],
            "downlink_volume": [
                100.0,
                200.0,
                300.0,
            ],
            "uplink_volume": [
                50.0,
                100.0,
                150.0,
            ],
            "total_volume": [
                150.0,
                300.0,
                450.0,
            ],
            "session_start": starts,
            "session_end": ends,
            "session_duration_seconds": [
                300.0,
                600.0,
                900.0,
            ],
            "session_time_valid": [
                True,
                True,
                True,
            ],
            "pre_post": [
                "PREPAID",
                "POSTPAID",
                "PREPAID",
            ],
            "roaming_circle": [
                "",
                "DELHI",
                "",
            ],
            "technology": [
                "4G",
                "5G",
                "4G",
            ],
            "icr_operator": [
                "",
                "JIO",
                "",
            ],
            "home_circle": [
                "BIHAR",
                "BIHAR",
                "BIHAR",
            ],
            "searched_cell_id": [
                "405-52-3347-232803094",
                "405-52-3347-232803095",
                "405-52-3347-232803096",
            ],
            "cgi_latitude": [
                24.1,
                24.2,
                24.3,
            ],
            "cgi_longitude": [
                86.1,
                86.2,
                86.3,
            ],
            "volume_fields_present": [
                True,
                True,
                True,
            ],
            "volume_mismatch": [
                False,
                False,
                False,
            ],
            "is_zero_volume": [
                False,
                False,
                False,
            ],
            "source_file": [
                "/evidence/first.csv",
                "/evidence/second.csv",
                "/evidence/third.csv",
            ],
            "source_relative_path": [
                "SPOT-A/first.csv",
                "SPOT-B/second.csv",
                "SPOT-C/third.csv",
            ],
            "spot_id": [
                "SPOT-A",
                "SPOT-B",
                "SPOT-C",
            ],
            "spot_name": [
                "Tower A",
                "Tower B",
                "Tower C",
            ],
            "spot_folder": [
                "SPOT-A",
                "SPOT-B",
                "SPOT-C",
            ],
            "source_row_number": [
                2,
                3,
                4,
            ],
        }
    )


def test_exact_15_digit_gprs_search():
    result = build_gprs_imei_investigation(
        _sample_frame(),
        IMEI_15,
    )

    assert result["status"] == "FOUND"
    assert result["session_count"] == 2

    assert set(
        result["timeline"]["Normalized IMEI"]
    ) == {
        IMEI_15,
    }

    assert set(
        result[
            "associated_subscribers"
        ][
            "Subscriber Number"
        ]
    ) == {
        "9000000001",
        "9000000002",
    }

    assert len(
        result["associated_sims"]
    ) == 2

    assert set(
        result["ip_addresses"]["IP Address"]
    ) == {
        "10.0.0.1",
        "2001:db8::1",
    }

    assert set(
        result["cells"]["Cell ID"]
    ) == {
        "405-52-3347-232803094",
        "405-52-3347-232803095",
    }


def test_exact_16_digit_gprs_identifier_is_not_truncated():
    result = build_gprs_imei_investigation(
        _sample_frame(),
        IMEISV_16,
    )

    assert result["status"] == "FOUND"
    assert result["session_count"] == 1

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


def test_invalid_gprs_imei_is_rejected():
    result = build_gprs_imei_investigation(
        _sample_frame(),
        "12345",
    )

    assert result["status"] == "INVALID_IMEI"
    assert result["timeline"].empty


def test_gprs_imei_not_found_returns_empty_bundle():
    result = build_gprs_imei_investigation(
        _sample_frame(),
        "111111111111111",
    )

    assert result["status"] == "NOT_FOUND"
    assert result["session_count"] == 0
    assert result["summary"].empty


def test_gprs_source_dataframe_is_not_modified():
    frame = _sample_frame()
    original = frame.copy(
        deep=True
    )

    build_gprs_imei_investigation(
        frame,
        IMEI_15,
    )

    pd.testing.assert_frame_equal(
        frame,
        original,
    )
