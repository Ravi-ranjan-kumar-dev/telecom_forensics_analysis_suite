
from pathlib import Path

import pandas as pd

from modules.analysis.ipdr.imei_investigation import (
    build_ipdr_imei_investigation,
)
from modules.reporting.imei_device_excel import (
    IPDR_EVIDENCE_COLUMNS,
)


QUERY_IMEI = "862261072892730"
OBSERVED_IMEISV = "8622610728927300"


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "imei": OBSERVED_IMEISV,
                "query_identifier_normalized": QUERY_IMEI,
                "match_relation": "SAME_BASE14",
                "event_time": "2025-10-05 08:14:24",
                "allocation_end": "2025-10-05 08:15:56",
                "subscriber_number": "5754021077243",
                "subscriber_identifier_type": (
                    "NUMERIC_SUBSCRIBER_ID"
                ),
                "imsi": "405523214527244",
                "source_ip": "2401:4900:8339:2dbc::2",
                "destination_ip": (
                    "2a03:2880:f288:ca:face:b00c:0:7260"
                ),
                "destination_port": 5222.0,
                "first_cell_id": (
                    "404-10-2330-158187265"
                ),
                "source_file": "source.csv",
                "source_row_number": 8,
            }
        ]
    )


def test_ipdr_port_is_rendered_without_decimal_suffix():
    result = build_ipdr_imei_investigation(
        _frame(),
        QUERY_IMEI,
    )

    timeline = result[
        "timeline"
    ]

    assert timeline.loc[
        0,
        "Destination Port",
    ] == "5222"


def test_ipdr_timeline_retains_query_and_match_provenance():
    result = build_ipdr_imei_investigation(
        _frame(),
        QUERY_IMEI,
    )

    timeline = result[
        "timeline"
    ]

    assert timeline.loc[
        0,
        "Query Identifier",
    ] == QUERY_IMEI

    assert timeline.loc[
        0,
        "Normalized IMEI",
    ] == OBSERVED_IMEISV

    assert timeline.loc[
        0,
        "Match Basis",
    ] == "QUERY_SCOPE"

    assert timeline.loc[
        0,
        "Match Relation",
    ] == "SAME_BASE14"

    # These fields remain in the source analysis. They are omitted only
    # from the compact investigator-facing IPDR Evidence projection.
    assert timeline.loc[
        0,
        "Identifier Type",
    ] == "NUMERIC_SUBSCRIBER_ID"

    assert timeline.loc[
        0,
        "First Cell ID",
    ] == "404-10-2330-158187265"


def test_ipdr_report_columns_preserve_matching_context():
    assert IPDR_EVIDENCE_COLUMNS == [
        "Event Time",
        "Allocation End",
        "Subscriber / User ID",
        "IMSI",
        "Source IP",
        "Destination IP",
        "Destination Port",
        "Protocol",
        "Cell ID",
        "Source File",
        "Source Row Number",
        "Query Identifier",
        "Normalized IMEI",
        "Match Basis",
        "Match Relation",
    ]

    assert len(
        IPDR_EVIDENCE_COLUMNS
    ) == 15
