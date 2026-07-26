from __future__ import annotations

import pandas as pd

from modules.analysis.cdr.imei_investigation import (
    build_imei_investigation,
)


IMEI_15 = "862518054878650"
IMEISV_16 = "8625180548786512"


def _sample_frame(
    imeis: list[str],
    *,
    target: str,
) -> pd.DataFrame:
    size = len(
        imeis
    )

    return pd.DataFrame(
        {
            "a_party": [
                target
            ]
            * size,
            "b_party": [
                "8002310903",
                "8927873436",
                "AD-AIRTEL-S",
            ][
                :size
            ],
            "imei": imeis,
            "imsi": [
                "405520123456789",
                "405520123456780",
                "405520123456789",
            ][
                :size
            ],
            "call_type": [
                "outgoing",
                "incoming",
                "smsin",
            ][
                :size
            ],
            "call_duration": [
                30,
                60,
                0,
            ][
                :size
            ],
            "call_date": [
                "01-01-2026",
                "02-01-2026",
                "03-01-2026",
            ][
                :size
            ],
            "call_time": [
                "10:00:00",
                "11:00:00",
                "12:00:00",
            ][
                :size
            ],
            "first_cell_id": [
                "405-52-3347-232803094",
                "405-52-3347-232803095",
                "",
            ][
                :size
            ],
            "last_cell_id": [
                "405-52-3347-232803095",
                "405-52-3347-232803094",
                "",
            ][
                :size
            ],
            "source_row_number": list(
                range(
                    2,
                    2 + size,
                )
            ),
        }
    )


def test_exact_imei_search_across_targets():
    first = _sample_frame(
        [
            IMEI_15,
            IMEISV_16,
        ],
        target="9000000001",
    )

    second = _sample_frame(
        [
            IMEI_15,
        ],
        target="9000000002",
    )

    loaded = {
        "9000000001": {
            "df": first,
            "source_file": "first.csv",
        },
        "9000000002": {
            "df": second,
            "source_file": "second.csv",
        },
    }

    result = build_imei_investigation(
        loaded,
        IMEI_15,
    )

    assert result[
        "status"
    ] == "FOUND"

    assert len(
        result[
            "timeline"
        ]
    ) == 2

    assert set(
        result[
            "timeline"
        ][
            "Target Number"
        ]
    ) == {
        "9000000001",
        "9000000002",
    }

    assert set(
        result[
            "timeline"
        ][
            "Normalized IMEI"
        ]
    ) == {
        IMEI_15,
    }

    assert IMEISV_16 not in set(
        result[
            "timeline"
        ][
            "Normalized IMEI"
        ]
    )

    assert len(
        result[
            "associated_targets"
        ]
    ) == 2


def test_exact_16_digit_identifier_is_not_truncated():
    frame = _sample_frame(
        [
            IMEI_15,
            IMEISV_16,
        ],
        target="9000000001",
    )

    result = build_imei_investigation(
        {
            "9000000001": {
                "df": frame,
            }
        },
        IMEISV_16,
    )

    assert result[
        "status"
    ] == "FOUND"

    assert len(
        result[
            "timeline"
        ]
    ) == 1

    assert result[
        "timeline"
    ].loc[
        0,
        "Normalized IMEI",
    ] == IMEISV_16

    indicators = " ".join(
        result[
            "review_indicators"
        ][
            "Observation"
        ].astype(
            str
        )
    )

    assert "16-digit" in indicators


def test_invalid_imei_is_rejected():
    result = build_imei_investigation(
        {},
        "12345",
    )

    assert result[
        "status"
    ] == "INVALID_IMEI"

    assert result[
        "timeline"
    ].empty

    assert result[
        "associated_targets"
    ].empty


def test_not_found_returns_valid_empty_bundle():
    frame = _sample_frame(
        [
            IMEI_15,
        ],
        target="9000000001",
    )

    result = build_imei_investigation(
        {
            "9000000001": {
                "df": frame,
            }
        },
        "111111111111111",
    )

    assert result[
        "status"
    ] == "NOT_FOUND"

    assert result[
        "summary"
    ].empty

    assert result[
        "timeline"
    ].empty


def test_source_dataframes_are_not_modified():
    frame = _sample_frame(
        [
            IMEI_15,
            IMEI_15,
        ],
        target="9000000001",
    )

    original = frame.copy(
        deep=True
    )

    build_imei_investigation(
        {
            "9000000001": {
                "df": frame,
            }
        },
        IMEI_15,
    )

    pd.testing.assert_frame_equal(
        frame,
        original,
    )
