
from __future__ import annotations

import pandas as pd

from modules.enrichment import (
    telecom_master_enrichment,
)
from modules.enrichment.telecom_master_enrichment import (
    CDR_TABLE_SPECS,
    TOWER_GPRS_TABLE_SPECS,
    enrich_analysis_bundle,
)
from modules.reporting import (
    analysis_bundle,
    single_cdr_excel,
)


def test_cdr_bundle_uses_one_common_batch_lookup(
    monkeypatch,
):
    sdr_calls = []
    cgi_calls = []

    def fake_sdr_lookup(
        values,
    ):
        sdr_calls.append(
            list(
                values
            )
        )

        return pd.DataFrame(
            [
                {
                    "lookup_mobile": "9000000001",
                    "subscriber_name": "Person One",
                    "subscriber_address": "Address One",
                    "sdr_found": "Yes",
                }
            ]
        )

    def fake_cgi_lookup(
        values,
    ):
        cgi_calls.append(
            list(
                values
            )
        )

        return pd.DataFrame(
            [
                {
                    "cgi": (
                        telecom_master_enrichment
                        .normalize_cgi(
                            "405-52-100-200"
                        )
                    ),
                    "address": "Tower Address One",
                }
            ]
        )

    monkeypatch.setattr(
        telecom_master_enrichment,
        "lookup_sdr_subscribers",
        fake_sdr_lookup,
    )

    monkeypatch.setattr(
        telecom_master_enrichment,
        "lookup_cgi_addresses",
        fake_cgi_lookup,
    )

    bundle = {
        "results": {
            "top_contacts": pd.DataFrame(
                [
                    {
                        "Contact": "9000000001",
                        "Total Calls": 12,
                    },
                    {
                        "Contact": "405123456789012",
                        "Total Calls": 2,
                    },
                ]
            ),
            "tower_movement": pd.DataFrame(
                [
                    {
                        "first_cell_id": (
                            "405-52-100-200"
                        ),
                        "records": 4,
                    }
                ]
            ),
        },
        "errors": {},
        "status": pd.DataFrame(),
    }

    result = (
        analysis_bundle
        ._apply_cgi_address_enrichment(
            bundle
        )
    )

    assert sdr_calls == [
        [
            "9000000001",
        ]
    ]

    assert len(
        cgi_calls
    ) == 1

    contacts = result[
        "results"
    ][
        "top_contacts"
    ]

    assert contacts.loc[
        0,
        "contact_sdr_lookup_status",
    ] == "FOUND"

    assert contacts.loc[
        1,
        "contact_sdr_lookup_status",
    ] == "NOT_ELIGIBLE"

    movement = result[
        "results"
    ][
        "tower_movement"
    ]

    assert movement.loc[
        0,
        "first_cell_lookup_status",
    ] == "FOUND"

    assert (
        "master_enrichment_summary"
        in result[
            "results"
        ]
    )


def test_single_cdr_prepare_does_not_lookup_raw_rows(
    monkeypatch,
):
    def forbidden_lookup(
        *args,
        **kwargs,
    ):
        raise AssertionError(
            "Raw-row master lookup was called."
        )

    monkeypatch.setattr(
        single_cdr_excel,
        "enrich_dataframe_with_sdr",
        forbidden_lookup,
    )

    monkeypatch.setattr(
        single_cdr_excel,
        "enrich_dataframe_with_cgi_address",
        forbidden_lookup,
    )

    dataframe = pd.DataFrame(
        [
            {
                "a_party": "9000000000",
                "b_party": "9000000001",
                "call_type": "Outgoing",
                "call_date": "2026-01-01",
                "call_time": "10:00:00",
                "call_duration": 10,
                "first_cell_id": (
                    "405-52-100-200"
                ),
                "last_cell_id": (
                    "405-52-100-201"
                ),
                "imei": "123456789012345",
            }
        ]
    )

    prepared = (
        single_cdr_excel
        ._prepare_dataframe(
            dataframe,
            "9000000000",
        )
    )

    assert len(
        prepared
    ) == 1

    assert prepared.loc[
        0,
        "b_party",
    ] == "9000000001"


def test_gprs_common_enrichment_excludes_nonstandard_ids(
    monkeypatch,
):
    calls = []

    def fake_sdr_lookup(
        values,
    ):
        calls.append(
            list(
                values
            )
        )

        return pd.DataFrame(
            [
                {
                    "lookup_mobile": "9000000001",
                    "subscriber_name": "Person One",
                    "sdr_found": "Yes",
                }
            ]
        )

    monkeypatch.setattr(
        telecom_master_enrichment,
        "lookup_sdr_subscribers",
        fake_sdr_lookup,
    )

    monkeypatch.setattr(
        telecom_master_enrichment,
        "lookup_cgi_addresses",
        lambda values: pd.DataFrame(),
    )

    bundle = {
        "gprs_priority_leads": pd.DataFrame(
            [
                {
                    "subscriber_number": "9000000001",
                    "priority": "HIGH",
                },
                {
                    "subscriber_number": (
                        "405123456789012"
                    ),
                    "priority": "MEDIUM",
                },
            ]
        )
    }

    result = enrich_analysis_bundle(
        bundle,
        table_specs=TOWER_GPRS_TABLE_SPECS,
    )

    assert calls == [
        [
            "9000000001",
        ]
    ]

    frame = result[
        "bundle"
    ][
        "gprs_priority_leads"
    ]

    assert frame.loc[
        0,
        "sdr_lookup_status",
    ] == "FOUND"

    assert frame.loc[
        1,
        "sdr_lookup_status",
    ] == "NOT_ELIGIBLE"
