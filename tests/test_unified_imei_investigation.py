from __future__ import annotations

import pandas as pd

from modules.analysis.device.imei_unified import (
    build_unified_imei_investigation,
)


IMEI_15 = "862518054878650"
IMEISV_16 = "8625180548786512"


def _cdr_frame(
    imei: str = IMEI_15,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "imei": [
                imei
            ],
            "imsi": [
                "405520123456789"
            ],
            "b_party": [
                "8002310903"
            ],
            "call_type": [
                "outgoing"
            ],
            "call_duration": [
                30
            ],
            "call_date": [
                "01-01-2026"
            ],
            "call_time": [
                "10:00:00"
            ],
            "first_cell_id": [
                "405-52-3347-232803094"
            ],
            "last_cell_id": [
                "405-52-3347-232803095"
            ],
            "source_row_number": [
                2
            ],
        }
    )


def _ipdr_frame(
    imei: str = IMEI_15,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "subscriber_number": [
                "9000000001"
            ],
            "subscriber_identifier_type": [
                "MSISDN"
            ],
            "imei": [
                imei
            ],
            "imsi": [
                "405520123456789"
            ],
            "event_time": pd.to_datetime(
                [
                    "2026-01-01 11:00:00"
                ]
            ),
            "allocation_end": pd.to_datetime(
                [
                    "2026-01-01 11:05:00"
                ]
            ),
            "session_duration_seconds": [
                300
            ],
            "source_ip": [
                "10.0.0.1"
            ],
            "destination_ip": [
                "8.8.8.8"
            ],
            "destination_port": [
                "443"
            ],
            "protocol": [
                "TCP"
            ],
            "cgi": [
                "405-52-3347-232803094"
            ],
            "source_file": [
                "ipdr.csv"
            ],
            "source_row_number": [
                3
            ],
        }
    )


def _gprs_frame(
    imei: str = IMEI_15,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "subscriber_number_raw": [
                "9000000001"
            ],
            "subscriber_number": [
                "9000000001"
            ],
            "identifier_type": [
                "MSISDN"
            ],
            "imei_raw": [
                imei
            ],
            "imei": [
                imei
            ],
            "imsi_raw": [
                "405520123456789"
            ],
            "imsi": [
                "405520123456789"
            ],
            "session_start": pd.to_datetime(
                [
                    "2026-01-01 12:00:00"
                ]
            ),
            "session_end": pd.to_datetime(
                [
                    "2026-01-01 12:10:00"
                ]
            ),
            "session_duration_seconds": [
                600
            ],
            "session_time_valid": [
                True
            ],
            "ipv4_address": [
                "10.0.0.2"
            ],
            "ipv6_address": [
                ""
            ],
            "downlink_volume": [
                100.0
            ],
            "uplink_volume": [
                50.0
            ],
            "total_volume": [
                150.0
            ],
            "volume_fields_present": [
                True
            ],
            "volume_mismatch": [
                False
            ],
            "is_zero_volume": [
                False
            ],
            "technology": [
                "4G"
            ],
            "searched_cell_id": [
                "405-52-3347-232803094"
            ],
            "source_file": [
                "gprs.csv"
            ],
            "source_row_number": [
                4
            ],
        }
    )


def _all_sources(
    imei: str = IMEI_15,
):
    cdr = _cdr_frame(
        imei
    )

    ipdr = _ipdr_frame(
        imei
    )

    gprs = _gprs_frame(
        imei
    )

    return cdr, ipdr, gprs


def test_unified_imei_found_in_all_sources():
    cdr, ipdr, gprs = _all_sources()

    result = build_unified_imei_investigation(
        IMEI_15,
        loaded_cdrs={
            "9000000001": {
                "df": cdr,
                "source_file": "cdr.csv",
            }
        },
        ipdr_dataframe=ipdr,
        gprs_dataframe=gprs,
    )

    assert result[
        "overall_status"
    ] == "FOUND"

    source_summary = result[
        "source_summary"
    ].set_index(
        "Evidence Source"
    )

    assert source_summary.loc[
        "CDR",
        "Matched Count",
    ] == 1

    assert source_summary.loc[
        "IPDR",
        "Matched Count",
    ] == 1

    assert source_summary.loc[
        "GPRS",
        "Matched Count",
    ] == 1

    assert list(
        result[
            "cross_source_timeline"
        ][
            "Evidence Source"
        ]
    ) == [
        "CDR",
        "IPDR",
        "GPRS",
    ]


def test_unified_counts_remain_source_specific():
    cdr, ipdr, gprs = _all_sources()

    result = build_unified_imei_investigation(
        IMEI_15,
        loaded_cdrs={
            "9000000001": {
                "df": cdr,
            }
        },
        ipdr_dataframe=ipdr,
        gprs_dataframe=gprs,
    )

    assert "Total Events" not in set(
        result[
            "source_summary"
        ][
            "Evidence Unit"
        ]
    )

    assert set(
        result[
            "source_summary"
        ][
            "Evidence Unit"
        ]
    ) == {
        "CDR records",
        "IPDR records",
        "GPRS sessions",
    }


def test_unified_can_run_with_only_cdr_input():
    cdr = _cdr_frame()

    result = build_unified_imei_investigation(
        IMEI_15,
        loaded_cdrs={
            "9000000001": {
                "df": cdr,
            }
        },
    )

    assert result[
        "overall_status"
    ] == "FOUND"

    statuses = result[
        "source_summary"
    ].set_index(
        "Evidence Source"
    )[
        "Status"
    ].to_dict()

    assert statuses == {
        "CDR": "FOUND",
        "IPDR": "NO_INPUT",
        "GPRS": "NO_INPUT",
    }


def test_unified_exact_16_digit_identifier_is_preserved():
    cdr, ipdr, gprs = _all_sources(
        IMEISV_16
    )

    result = build_unified_imei_investigation(
        IMEISV_16,
        loaded_cdrs={
            "9000000001": {
                "df": cdr,
            }
        },
        ipdr_dataframe=ipdr,
        gprs_dataframe=gprs,
    )

    assert result[
        "requested_imei"
    ] == IMEISV_16

    assert set(
        result[
            "cross_source_timeline"
        ][
            "Evidence Source"
        ]
    ) == {
        "CDR",
        "IPDR",
        "GPRS",
    }


def test_unified_valid_imei_not_found():
    cdr, ipdr, gprs = _all_sources()

    result = build_unified_imei_investigation(
        "111111111111111",
        loaded_cdrs={
            "9000000001": {
                "df": cdr,
            }
        },
        ipdr_dataframe=ipdr,
        gprs_dataframe=gprs,
    )

    assert result[
        "overall_status"
    ] == "NOT_FOUND"

    assert result[
        "cross_source_timeline"
    ].empty


def test_unified_no_input_and_invalid_imei():
    no_input = build_unified_imei_investigation(
        IMEI_15
    )

    assert no_input[
        "overall_status"
    ] == "NO_INPUT"

    invalid = build_unified_imei_investigation(
        "12345"
    )

    assert invalid[
        "overall_status"
    ] == "INVALID_IMEI"

    assert invalid[
        "cross_source_timeline"
    ].empty


def test_unified_source_dataframes_are_not_modified():
    cdr, ipdr, gprs = _all_sources()

    original_cdr = cdr.copy(
        deep=True
    )

    original_ipdr = ipdr.copy(
        deep=True
    )

    original_gprs = gprs.copy(
        deep=True
    )

    build_unified_imei_investigation(
        IMEI_15,
        loaded_cdrs={
            "9000000001": {
                "df": cdr,
            }
        },
        ipdr_dataframe=ipdr,
        gprs_dataframe=gprs,
    )

    pd.testing.assert_frame_equal(
        cdr,
        original_cdr,
    )

    pd.testing.assert_frame_equal(
        ipdr,
        original_ipdr,
    )

    pd.testing.assert_frame_equal(
        gprs,
        original_gprs,
    )
