
from __future__ import annotations

import pandas as pd

from modules.analysis.gprsdump.imei_investigation import (
    _prepare_matches,
)


QUERY_IMEI = "861679062132757"
OBSERVED_IMEI = "405704526326453"


def test_report_scope_matches_query_when_observed_imei_differs():
    dataframe = pd.DataFrame(
        [
            {
                "imei": OBSERVED_IMEI,
                "observed_imei_raw": OBSERVED_IMEI,
                "observed_imei_normalized": OBSERVED_IMEI,
                "query_identifier_raw": QUERY_IMEI,
                "query_identifier_normalized": QUERY_IMEI,
                "query_identifier_type": "IMEI15",
                "match_basis": "REPORT_QUERY",
                "match_relation": "REPORT_SCOPE",
                "source_row_number": 7,
            },
            {
                "imei": "999999999999999",
                "observed_imei_normalized": "999999999999999",
                "query_identifier_normalized": "888888888888888",
                "match_relation": "REPORT_SCOPE",
                "source_row_number": 8,
            },
        ]
    )

    matches = _prepare_matches(
        dataframe,
        QUERY_IMEI,
    )

    assert len(
        matches
    ) == 1

    assert matches.iloc[
        0
    ][
        "query_identifier_normalized"
    ] == QUERY_IMEI

    assert matches.iloc[
        0
    ][
        "observed_imei_normalized"
    ] == OBSERVED_IMEI

    assert matches.iloc[
        0
    ][
        "match_relation"
    ] == "REPORT_SCOPE"


    assert "_session_start" in matches.columns
    assert "_session_end" in matches.columns
    assert "_imei" in matches.columns

    # The selected report query must not replace
    # the observed device identifier.
    assert matches.iloc[
        0
    ][
        "imei"
    ] == OBSERVED_IMEI

    assert matches.iloc[
        0
    ][
        "_imei"
    ] == OBSERVED_IMEI


def test_observed_imei_match_remains_supported():
    dataframe = pd.DataFrame(
        [
            {
                "imei": QUERY_IMEI,
                "observed_imei_raw": QUERY_IMEI,
                "observed_imei_normalized": QUERY_IMEI,
                "query_identifier_normalized": "777777777777777",
                "match_relation": "EXACT",
                "source_row_number": 10,
            }
        ]
    )

    matches = _prepare_matches(
        dataframe,
        QUERY_IMEI,
    )

    assert len(
        matches
    ) == 1

    assert matches.iloc[
        0
    ][
        "observed_imei_normalized"
    ] == QUERY_IMEI


def test_query_identifier_without_report_scope_does_not_match():
    dataframe = pd.DataFrame(
        [
            {
                "imei": OBSERVED_IMEI,
                "observed_imei_normalized": OBSERVED_IMEI,
                "query_identifier_normalized": QUERY_IMEI,
                "match_relation": "SAME_BASE14",
                "source_row_number": 11,
            }
        ]
    )

    matches = _prepare_matches(
        dataframe,
        QUERY_IMEI,
    )

    assert matches.empty
