
from __future__ import annotations

from pathlib import Path

import pandas as pd

from modules.enrichment import (
    sdr_subscriber_enrichment,
)
from modules.reporting import (
    single_cdr_excel,
)


def _base_rows() -> pd.DataFrame:
    """
    Build a minimal canonical Single CDR frame.

    The fixture includes every column required by the report
    summary and contact aggregation functions.
    """

    return pd.DataFrame(
        [
            {
                "call_type": "outgoing",
                "call_direction": "OUTGOING",
                "call_duration": 30,
                "other_party": "9000000001",
                "imei": "111111111111111",
                "imsi": "405001111111111",
                "first_cell_id": (
                    "405-52-3347-232803094"
                ),
                "tower_address": "Tower One",
                "datetime": pd.Timestamp(
                    "2026-01-01 10:00:00"
                ),
                "level_code": "human_mobile",
                "contact_name": "",
                "contact_address": "",
            },
            {
                "call_type": "dsm",
                "call_direction": "OUTGOING",
                "call_duration": 50,
                "other_party": "SERVICE",
                "imei": "111111111111111",
                "imsi": "405001111111111",
                "first_cell_id": "INVALID",
                "tower_address": "",
                "datetime": pd.Timestamp(
                    "2026-01-01 10:05:00"
                ),
                "level_code": "service_sender_id",
                "contact_name": "",
                "contact_address": "",
            },
            {
                "call_type": "incoming",
                "call_direction": "INCOMING",
                "call_duration": 20,
                "other_party": "9000000002",
                "imei": "111111111111111",
                "imsi": "405001111111111",
                "first_cell_id": "",
                "tower_address": "",
                "datetime": pd.Timestamp(
                    "2026-01-01 10:10:00"
                ),
                "level_code": "human_mobile",
                "contact_name": "",
                "contact_address": "",
            },
            {
                "call_type": "smsout",
                "call_direction": "OUTGOING",
                "call_duration": 0,
                "other_party": "9000000003",
                "imei": "111111111111111",
                "imsi": "405001111111111",
                "first_cell_id": None,
                "tower_address": "",
                "datetime": pd.Timestamp(
                    "2026-01-01 10:15:00"
                ),
                "level_code": "human_mobile",
                "contact_name": "",
                "contact_address": "",
            },
            {
                "call_type": "smsin",
                "call_direction": "INCOMING",
                "call_duration": 0,
                "other_party": "9000000004",
                "imei": "111111111111111",
                "imsi": "405001111111111",
                "first_cell_id": (
                    "405-52-3347-232803094"
                ),
                "tower_address": "Tower One",
                "datetime": pd.Timestamp(
                    "2026-01-01 10:20:00"
                ),
                "level_code": "human_mobile",
                "contact_name": "",
                "contact_address": "",
            },
        ]
    )



def test_voice_masks_exclude_unknown_directional_records():
    data = _base_rows()

    assert int(
        single_cdr_excel
        ._voice_out_mask(
            data
        )
        .sum()
    ) == 1

    assert int(
        single_cdr_excel
        ._voice_in_mask(
            data
        )
        .sum()
    ) == 1

    assert int(
        single_cdr_excel
        ._sms_out_mask(
            data
        )
        .sum()
    ) == 1

    assert int(
        single_cdr_excel
        ._sms_in_mask(
            data
        )
        .sum()
    ) == 1


def test_cell_summary_and_extract_share_valid_cgi_rule():
    data = _base_rows()

    summary = (
        single_cdr_excel
        ._cell_summary(
            data
        )
    )

    assert len(
        summary
    ) == 1

    assert summary.loc[
        0,
        "Total Calls",
    ] == 2

    extract = (
        single_cdr_excel
        ._extract_table(
            data,
            {},
        )
    )

    values = dict(
        zip(
            extract[
                "Header"
            ],
            extract[
                "Details"
            ],
        )
    )

    assert values[
        "Outgoing Calls"
    ] == 1

    assert values[
        "Incoming Calls"
    ] == 1

    assert values[
        "Unique Cell IDs"
    ] == 1

    assert values[
        "Total Call Duration (Sec)"
    ] == 50


def test_contact_report_reuses_common_enrichment(
    monkeypatch,
):
    def forbidden_lookup(
        *args,
        **kwargs,
    ):
        raise AssertionError(
            "Excel attempted a duplicate SDR lookup."
        )

    monkeypatch.setattr(
        sdr_subscriber_enrichment,
        "lookup_sdr_subscribers",
        forbidden_lookup,
    )

    frame = pd.DataFrame(
        [
            {
                "Contact": "9000000001",
                "Total Calls": 10,
                "contact_sdr_subscriber_name": (
                    "Test Person"
                ),
                "contact_sdr_father_name": (
                    "Test Parent"
                ),
                "contact_sdr_address": (
                    "Test Address"
                ),
                "contact_sdr_operator": (
                    "TEST OPERATOR"
                ),
                "contact_sdr_circle": (
                    "TEST CIRCLE"
                ),
                "contact_sdr_activation_date": (
                    "2020-01-01"
                ),
                "contact_sdr_caf_number": (
                    "CAF-1"
                ),
                "contact_sdr_found": "Yes",
                "contact_sdr_lookup_status": (
                    "FOUND"
                ),
                "contact_sdr_match_confidence": (
                    "DIRECT_NORMALIZED_MSISDN"
                ),
            }
        ]
    )

    result = (
        single_cdr_excel
        ._enrich_contact_report_dataframe(
            "16. Top Human Contacts",
            frame,
        )
    )

    assert result.loc[
        0,
        "Name",
    ] == "Test Person"

    assert result.loc[
        0,
        "SDR Lookup Status",
    ] == "FOUND"

    assert not any(
        str(
            column
        ).startswith(
            "contact_sdr_"
        )
        for column in result.columns
    )


def test_report_paths_are_portable():
    absolute = (
        "/home/example/Desktop/"
        "telecom_forensics_analysis_suite/"
        "data/cdr/single/sample.csv"
    )

    assert (
        single_cdr_excel
        ._portable_report_path(
            absolute
        )
        == "data/cdr/single/sample.csv"
    )

    frame = pd.DataFrame(
        [
            {
                "source_file": absolute,
                "source_row_number": 10,
            }
        ]
    )

    sanitized = (
        single_cdr_excel
        ._sanitize_report_paths(
            frame
        )
    )

    assert sanitized.loc[
        0,
        "source_file",
    ] == "data/cdr/single/sample.csv"


def test_target_not_found_message_and_sheet_name(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        sdr_subscriber_enrichment,
        "lookup_sdr_subscribers",
        lambda values: pd.DataFrame(
            [
                {
                    "lookup_mobile": (
                        "9000000001"
                    ),
                    "sdr_found": "No",
                    "subscriber_name": "",
                    "subscriber_address": "",
                    "source_file": "",
                }
            ]
        ),
    )

    result = (
        single_cdr_excel
        ._enrich_target_metadata_with_sdr(
            {},
            "9000000001",
        )
    )

    output = capsys.readouterr().out

    assert result[
        "target_sdr_found"
    ] == "No"

    assert (
        "Target SDR profile not found"
        in output
    )

    sheet_names = [
        sheet_name
        for (
            sheet_name,
            _
        ) in single_cdr_excel.MODULE_RESULT_SHEETS
    ]

    assert (
        "32A. Master Enrichment"
        in sheet_names
    )

    assert (
        "43A. Master Enrichment"
        not in sheet_names
    )

def test_social_network_hides_internal_sdr_columns():
    frame = pd.DataFrame(
        [
            {
                "Contact": "9000000001",
                "Total_Events": 5,
                "Strength": 25,
                "contact_sdr_lookup_mobile": (
                    "9000000001"
                ),
                "contact_sdr_subscriber_name": (
                    "Test Person"
                ),
                "contact_sdr_father_name": (
                    "Test Parent"
                ),
                "contact_sdr_address": (
                    "Test Address"
                ),
                "contact_sdr_operator": (
                    "TEST OPERATOR"
                ),
                "contact_sdr_circle": (
                    "TEST CIRCLE"
                ),
                "contact_sdr_activation_date": (
                    "2020-01-01"
                ),
                "contact_sdr_caf_number": (
                    "CAF-1"
                ),
                "contact_sdr_found": "Yes",
                "contact_sdr_lookup_status": (
                    "FOUND"
                ),
                "contact_sdr_match_confidence": (
                    "DIRECT_NORMALIZED_MSISDN"
                ),
            }
        ]
    )

    result = (
        single_cdr_excel
        ._enrich_contact_report_dataframe(
            "23. Social Network",
            frame,
        )
    )

    assert result.loc[
        0,
        "Name",
    ] == "Test Person"

    assert result.loc[
        0,
        "SDR Lookup Status",
    ] == "FOUND"

    assert result.loc[
        0,
        "Match Confidence",
    ] == "DIRECT_NORMALIZED_MSISDN"

    assert not any(
        str(column).startswith(
            "contact_sdr_"
        )
        for column in result.columns
    )

