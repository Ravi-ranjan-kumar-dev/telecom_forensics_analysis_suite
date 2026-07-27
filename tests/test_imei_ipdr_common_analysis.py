
from __future__ import annotations

import pandas as pd

from modules.analysis.device.imei_ipdr_common import (
    build_common_imei_ipdr_analysis,
)


FIRST_IMEI = "862261072892730"
SECOND_IMEI = "862286069717070"


def _frame(
    *,
    query_identifier: str,
    observed_imei: str,
    subscriber: str = "5754021077243",
    imsi: str = "405523214527244",
    source_ip: str = "2401:4900:8339:2dbc::2",
    destination_ip: str = "203.0.113.10",
    destination_port: float = 443.0,
    cell_id: str = "404-10-2330-158187265",
    event_time: str = "2025-10-05 08:14:24",
    source_file: str = "source.csv",
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "event_time": event_time,
                "allocation_end": "2025-10-05 08:15:56",
                "subscriber_number": subscriber,
                "imsi": imsi,
                "source_ip": source_ip,
                "destination_ip": destination_ip,
                "destination_port": destination_port,
                "protocol": "TCP",
                "first_cell_id": cell_id,
                "query_identifier_normalized": (
                    query_identifier
                ),
                "observed_imei_normalized": observed_imei,
                "match_relation": "SAME_BASE14",
                "source_file": source_file,
                "source_row_number": 8,
            }
        ]
    )


def _manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Relative Path": "first.csv",
                "SHA-256": "a" * 64,
                "Source Type": "IPDR",
                "Query Identifier": FIRST_IMEI,
                "Inspection Status": "HAS_DATA",
                "Analysis Content Role": "PRIMARY_CONTENT",
            },
            {
                "Relative Path": "second.csv",
                "SHA-256": "b" * 64,
                "Source Type": "IPDR",
                "Query Identifier": SECOND_IMEI,
                "Inspection Status": "HAS_DATA",
                "Analysis Content Role": "PRIMARY_CONTENT",
            },
        ]
    )


def test_common_ipdr_analysis_finds_shared_evidence():
    first = _frame(
        query_identifier=FIRST_IMEI,
        observed_imei="8622610728927300",
        source_file="first.csv",
    )

    second = _frame(
        query_identifier=SECOND_IMEI,
        observed_imei="8622860697170700",
        source_file="second.csv",
    )

    first_original = first.copy(
        deep=True
    )

    second_original = second.copy(
        deep=True
    )

    result = build_common_imei_ipdr_analysis(
        {
            FIRST_IMEI: first,
            SECOND_IMEI: second,
        },
        _manifest(),
    )

    assert result[
        "status"
    ] == "FOUND"

    assert result[
        "query_identifier_count"
    ] == 2

    assert result[
        "device_family_count"
    ] == 2

    assert result[
        "data_bearing_device_count"
    ] == 2

    assert set(
        result[
            "common_subscribers"
        ][
            "Subscriber / User ID"
        ]
    ) == {
        "5754021077243"
    }

    assert set(
        result[
            "common_imsis"
        ][
            "IMSI"
        ]
    ) == {
        "405523214527244"
    }

    assert set(
        result[
            "common_source_ips"
        ][
            "Source IP"
        ]
    ) == {
        "2401:4900:8339:2dbc::2"
    }

    assert set(
        result[
            "common_destination_endpoints"
        ][
            "Destination Endpoint"
        ]
    ) == {
        "203.0.113.10:443"
    }

    assert set(
        result[
            "common_cells"
        ][
            "Cell ID"
        ]
    ) == {
        "404-10-2330-158187265"
    }

    assert len(
        result[
            "cross_device_timeline"
        ]
    ) == 2

    pd.testing.assert_frame_equal(
        first,
        first_original,
    )

    pd.testing.assert_frame_equal(
        second,
        second_original,
    )


def test_shared_values_require_distinct_device_families():
    imei15 = "862261072892730"
    imeisv16 = "8622610728927300"

    result = build_common_imei_ipdr_analysis(
        {
            imei15: _frame(
                query_identifier=imei15,
                observed_imei=imeisv16,
                source_file="imei15.csv",
            ),
            imeisv16: _frame(
                query_identifier=imeisv16,
                observed_imei=imeisv16,
                source_file="imeisv16.csv",
            ),
        }
    )

    assert result[
        "status"
    ] == "FOUND"

    assert result[
        "query_identifier_count"
    ] == 2

    assert result[
        "device_family_count"
    ] == 1

    assert result[
        "common_subscribers"
    ].empty

    assert result[
        "common_imsis"
    ].empty

    assert result[
        "common_destination_endpoints"
    ].empty

    assert result[
        "common_source_ips"
    ].empty

    assert result[
        "common_cells"
    ].empty


def test_valid_empty_ipdr_identifier_is_retained():
    manifest = pd.DataFrame(
        [
            {
                "Relative Path": "data.csv",
                "SHA-256": "a" * 64,
                "Source Type": "IPDR",
                "Query Identifier": FIRST_IMEI,
                "Inspection Status": "HAS_DATA",
                "Analysis Content Role": "PRIMARY_CONTENT",
            },
            {
                "Relative Path": "empty.csv",
                "SHA-256": "b" * 64,
                "Source Type": "IPDR",
                "Query Identifier": SECOND_IMEI,
                "Inspection Status": "EMPTY_NO_DATA",
                "Analysis Content Role": "PRIMARY_CONTENT",
            },
            {
                "Relative Path": "excluded-gprs.csv",
                "SHA-256": "c" * 64,
                "Source Type": "GPRS",
                "Query Identifier": FIRST_IMEI,
                "Inspection Status": "EMPTY_NO_DATA",
                "Analysis Content Role": "EXCLUDED_NON_IPDR",
            },
        ]
    )

    result = build_common_imei_ipdr_analysis(
        {
            FIRST_IMEI: _frame(
                query_identifier=FIRST_IMEI,
                observed_imei="8622610728927300",
            ),
            SECOND_IMEI: pd.DataFrame(),
        },
        manifest,
    )

    assert result[
        "status"
    ] == "FOUND"

    assert result[
        "query_identifier_count"
    ] == 2

    assert result[
        "data_bearing_device_count"
    ] == 1

    assert result[
        "empty_report_count"
    ] == 1

    overview = result[
        "device_overview"
    ].set_index(
        "Query Identifier"
    )

    assert overview.loc[
        FIRST_IMEI,
        "Analysis Status",
    ] == "FOUND"

    assert overview.loc[
        SECOND_IMEI,
        "Analysis Status",
    ] == "EMPTY_NO_DATA"

    assert overview.loc[
        SECOND_IMEI,
        "IPDR Records",
    ] == 0

    quality = result[
        "data_quality"
    ].set_index(
        "Check"
    )

    assert quality.loc[
        "Physical acquisitions",
        "Count",
    ] == 3

    assert quality.loc[
        "All acquisition SHA-256 groups",
        "Count",
    ] == 3

    assert quality.loc[
        "Supported IPDR analytical content groups",
        "Count",
    ] == 2

    assert quality.loc[
        "Non-IPDR acquisitions excluded",
        "Count",
    ] == 1

    assert len(
        result[
            "cross_device_timeline"
        ]
    ) == 1


def test_common_ipdr_analysis_excludes_plmn_only_cells():
    first = _frame(
        query_identifier=FIRST_IMEI,
        observed_imei="8622610728927300",
        cell_id="404-10-2330-158187265",
        source_file="first.csv",
    )

    first[
        "cgi"
    ] = "405856"

    second = _frame(
        query_identifier=SECOND_IMEI,
        observed_imei="8622860697170700",
        cell_id="404-10-2330-158187265",
        source_file="second.csv",
    )

    second[
        "cgi"
    ] = "405856"

    result = build_common_imei_ipdr_analysis(
        {
            FIRST_IMEI: first,
            SECOND_IMEI: second,
        },
        _manifest(),
    )

    assert set(
        result[
            "common_cells"
        ][
            "Cell ID"
        ]
    ) == {
        "404-10-2330-158187265"
    }

    assert "405856" not in set(
        result[
            "common_cells"
        ][
            "Cell ID"
        ]
    )

    quality = result[
        "data_quality"
    ].set_index(
        "Check"
    )

    assert quality.loc[
        "Invalid or incomplete Cell IDs excluded",
        "Count",
    ] == 2


def test_common_ipdr_analysis_requires_multiple_identifiers():
    result = build_common_imei_ipdr_analysis(
        {
            FIRST_IMEI: pd.DataFrame(),
        }
    )

    assert result[
        "status"
    ] == "NOT_APPLICABLE"

    assert result[
        "query_identifier_count"
    ] == 1

    assert result[
        "device_family_count"
    ] == 1

    assert result[
        "device_overview"
    ].loc[
        0,
        "Analysis Status",
    ] == "NO_DATA"

    assert result[
        "cross_device_timeline"
    ].empty
