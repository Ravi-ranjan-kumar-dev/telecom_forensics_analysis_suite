from __future__ import annotations

import pandas as pd
import pytest

from modules.database import lookup_service


@pytest.fixture(autouse=True)
def clear_sdr_profile_cache():
    lookup_service._lookup_sdr_profile_cached.cache_clear()
    yield
    lookup_service._lookup_sdr_profile_cached.cache_clear()


def _mock_large_sdr_row(
    operator: str,
) -> dict[str, object]:
    return {
        "lookup_mobile": "6000369727",
        "mobile_number": "6000369727",
        "subscriber_name": "TEST SUBSCRIBER",
        "father_name": "TEST FATHER",
        "subscriber_address": "TEST ADDRESS",
        "raw_address": "TEST ADDRESS",
        "operator": operator,
        "circle": None,
        "connection_type": None,
        "source_file": "sdr_master_export.csv",
    }


def test_verified_large_sdr_operator_is_exposed(
    monkeypatch,
):
    monkeypatch.setattr(
        lookup_service,
        "lookup_sdr_subscribers",
        lambda *args, **kwargs: pd.DataFrame(
            [
                _mock_large_sdr_row(
                    "AIRTEL"
                )
            ]
        ),
    )

    result = lookup_service.lookup_sdr_profile(
        "6000369727"
    )

    assert result["found"] is True
    assert result["status"] == "MATCHED"

    record = result["record"]

    assert record["operator"] == "AIRTEL"
    assert (
        record["operator_or_source_category"]
        == "AIRTEL"
    )


def test_unverified_source_category_is_not_operator(
    monkeypatch,
):
    monkeypatch.setattr(
        lookup_service,
        "lookup_sdr_subscribers",
        lambda *args, **kwargs: pd.DataFrame(
            [
                _mock_large_sdr_row(
                    "SDR MASTER"
                )
            ]
        ),
    )

    result = lookup_service.lookup_sdr_profile(
        "6000369727"
    )

    record = result["record"]

    assert record["operator"] == ""
    assert (
        record["operator_or_source_category"]
        == "SDR MASTER"
    )
