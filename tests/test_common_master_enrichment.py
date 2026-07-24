
from __future__ import annotations

import pandas as pd

from modules.enrichment import (
    telecom_master_enrichment,
)
from modules.enrichment.telecom_master_enrichment import (
    IPDR_TABLE_SPECS,
    enrich_analysis_bundle,
)


def test_common_enrichment_batches_and_preserves_raw_tables(
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
                    "father_name": "Parent One",
                    "subscriber_address": "Address One",
                    "id_type": "ID",
                    "id_number": "ID-1",
                    "operator": "Operator One",
                    "circle": "Circle One",
                    "activation_date": "2024-01-01",
                    "caf_number": "CAF-1",
                    "source_file": "sdr_source.csv",
                    "sdr_found": "Yes",
                },
                {
                    "lookup_mobile": "9000000002",
                    "subscriber_name": "",
                    "father_name": "",
                    "subscriber_address": "",
                    "id_type": "",
                    "id_number": "",
                    "operator": "",
                    "circle": "",
                    "activation_date": "",
                    "caf_number": "",
                    "source_file": "",
                    "sdr_found": "No",
                },
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
                    "cgi": telecom_master_enrichment.normalize_cgi(
                        "405-52-100-200"
                    ),
                    "operator": "Operator One",
                    "circle": "Circle One",
                    "state": "State One",
                    "district": "District One",
                    "police_station": "Police Station One",
                    "town": "Town One",
                    "site_name": "Site One",
                    "address": "Tower Address One",
                    "latitude": 25.1,
                    "longitude": 85.1,
                    "source_file": "cgi_source.xlsx",
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

    original_subscribers = pd.DataFrame(
        [
            {
                "subscriber_number": "9000000001",
                "records": 10,
            },
            {
                "subscriber_number": "919000000002",
                "records": 8,
            },
            {
                "subscriber_number": "405123456789012",
                "records": 3,
            },
        ]
    )

    original_cells = pd.DataFrame(
        [
            {
                "cgi": "405-52-100-200",
                "records": 12,
            },
            {
                "cgi": "405-52-999-999",
                "records": 4,
            },
        ]
    )

    original_movements = pd.DataFrame(
        [
            {
                "subscriber_number": "9000000001",
                "first_cell_id": "405-52-100-200",
                "last_cell_id": "405-52-999-999",
            }
        ]
    )

    raw_events = pd.DataFrame(
        [
            {
                "subscriber_number": "9000000001",
                "cgi": "405-52-100-200",
            }
        ]
    )

    bundle = {
        "subscriber_summary": original_subscribers,
        "cgi_summary": original_cells,
        "cell_movement": original_movements,
        "normalized_events": raw_events,
    }

    result = enrich_analysis_bundle(
        bundle,
        table_specs=IPDR_TABLE_SPECS,
    )

    enriched = result[
        "bundle"
    ]

    assert len(
        sdr_calls
    ) == 1

    assert len(
        cgi_calls
    ) == 1

    assert sdr_calls[0] == [
        "9000000001",
        "9000000002",
    ]

    subscriber_table = enriched[
        "subscriber_summary"
    ]

    assert subscriber_table.loc[
        0,
        "sdr_lookup_status",
    ] == "FOUND"

    assert subscriber_table.loc[
        0,
        "sdr_subscriber_name",
    ] == "Person One"

    assert subscriber_table.loc[
        1,
        "sdr_lookup_status",
    ] == "NOT_FOUND"

    assert subscriber_table.loc[
        2,
        "sdr_lookup_status",
    ] == "NOT_ELIGIBLE"

    cgi_table = enriched[
        "cgi_summary"
    ]

    assert cgi_table.loc[
        0,
        "cgi_lookup_status",
    ] == "FOUND"

    assert cgi_table.loc[
        0,
        "cgi_address",
    ] == "Tower Address One"

    assert cgi_table.loc[
        1,
        "cgi_lookup_status",
    ] == "NOT_FOUND"

    assert (
        "sdr_lookup_status"
        not in original_subscribers.columns
    )

    assert (
        "cgi_lookup_status"
        not in original_cells.columns
    )

    pd.testing.assert_frame_equal(
        enriched[
            "normalized_events"
        ],
        raw_events,
    )

    assert (
        "sdr_lookup_status"
        not in enriched[
            "normalized_events"
        ].columns
    )

    summary = result[
        "summary"
    ]

    assert not summary.empty

    metrics = dict(
        zip(
            summary[
                "Metric"
            ],
            summary[
                "Value"
            ],
        )
    )

    assert metrics[
        "SDR Eligible Unique Mobiles"
    ] == 2

    assert metrics[
        "Non-standard SDR Identifiers"
    ] == 1

    assert metrics[
        "CGI Records Found"
    ] == 1


def test_common_enrichment_lookup_failure_is_non_fatal(
    monkeypatch,
):
    def fail_sdr(
        values,
    ):
        raise RuntimeError(
            "SDR database unavailable"
        )

    def fail_cgi(
        values,
    ):
        raise RuntimeError(
            "CGI database unavailable"
        )

    monkeypatch.setattr(
        telecom_master_enrichment,
        "lookup_sdr_subscribers",
        fail_sdr,
    )

    monkeypatch.setattr(
        telecom_master_enrichment,
        "lookup_cgi_addresses",
        fail_cgi,
    )

    bundle = {
        "subscriber_summary": pd.DataFrame(
            [
                {
                    "subscriber_number": "9000000001",
                }
            ]
        ),
        "cgi_summary": pd.DataFrame(
            [
                {
                    "cgi": "405-52-100-200",
                }
            ]
        ),
    }

    result = enrich_analysis_bundle(
        bundle,
        table_specs=IPDR_TABLE_SPECS,
    )

    assert len(
        result[
            "warnings"
        ]
    ) == 2

    assert result[
        "bundle"
    ][
        "subscriber_summary"
    ].loc[
        0,
        "sdr_lookup_status",
    ] == "LOOKUP_ERROR"

    assert result[
        "bundle"
    ][
        "cgi_summary"
    ].loc[
        0,
        "cgi_lookup_status",
    ] == "LOOKUP_ERROR"
