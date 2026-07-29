from __future__ import annotations

import pandas as pd

from modules.loader.imei_evidence_loader import (
    _parse_imei_gprs_session_start,
)


def test_mixed_imei_gprs_datetime_formats():
    dates = pd.Series(
        [
            "01/02/2025",
            "01-Feb-2025",
            "invalid-date",
            "",
        ],
        dtype="string",
    )

    times = pd.Series(
        [
            "03:04:05",
            "03:04:05",
            "03:04:05",
            "",
        ],
        dtype="string",
    )

    parsed = _parse_imei_gprs_session_start(
        dates,
        times,
    )

    expected = pd.Timestamp(
        "2025-02-01 03:04:05"
    )

    assert parsed.iloc[0] == expected
    assert parsed.iloc[1] == expected
    assert pd.isna(parsed.iloc[2])
    assert pd.isna(parsed.iloc[3])


def test_imei_gprs_datetime_parser_preserves_index():
    dates = pd.Series(
        ["09-Oct-2025"],
        index=[17],
        dtype="string",
    )

    times = pd.Series(
        ["23:59:59"],
        index=[17],
        dtype="string",
    )

    parsed = _parse_imei_gprs_session_start(
        dates,
        times,
    )

    assert parsed.index.tolist() == [17]
    assert parsed.loc[17] == pd.Timestamp(
        "2025-10-09 23:59:59"
    )
