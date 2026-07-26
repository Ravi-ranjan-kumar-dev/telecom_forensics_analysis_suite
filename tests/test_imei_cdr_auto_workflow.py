from pathlib import Path

import pandas as pd

from modules.analysis.cdr.imei_investigation import (
    build_imei_investigation,
)
from modules.analysis.device.imei_unified import (
    build_unified_imei_investigation,
)
from modules.controllers import imei_device_controller


def _canonical_frame(
    query_identifier: str,
    observed_identifier: str,
    target: str = "9000000001",
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "target": target,
                "call_date": "01/07/2026",
                "call_time": "10:00:00",
                "call_type": "outgoing",
                "b_party": "9111111111",
                "call_duration": 30,
                "imei": observed_identifier,
                "imsi": "405520123456789",
                "first_cell_id": "404-10-100-200",
                "last_cell_id": "",
                "query_identifier_raw": query_identifier,
                "query_identifier_normalized": query_identifier,
                "query_identifier_type": (
                    "BASE14"
                    if len(
                        query_identifier
                    )
                    == 14
                    else "IMEI15"
                ),
                "observed_imei_raw": observed_identifier,
                "observed_imei_normalized": observed_identifier,
                "match_relation": "BASE14_MATCH",
                "source_file": "sample.csv",
                "source_path": "/evidence/sample.csv",
                "source_row_number": 8,
            }
        ]
    )


def _analysis_bundle(
    identifier: str,
) -> dict:
    timeline = pd.DataFrame(
        [
            {
                "Evidence Source": "CDR",
                "Event Time": pd.Timestamp(
                    "2026-07-01 10:00:00"
                ),
            }
        ]
    )

    return {
        "requested_imei": identifier,
        "overall_status": "FOUND",
        "message": "Found.",
        "source_summary": pd.DataFrame(
            [
                {
                    "Evidence Source": "CDR",
                    "Status": "FOUND",
                    "Evidence Unit": "CDR records",
                    "Matched Count": 1,
                    "Message": "Found.",
                }
            ]
        ),
        "associated_identities": pd.DataFrame(),
        "cross_source_timeline": timeline,
        "cdr": {
            "status": "FOUND",
            "timeline": timeline,
            "towers": pd.DataFrame(),
        },
        "ipdr": {
            "status": "NO_INPUT",
            "timeline": pd.DataFrame(),
        },
        "gprs": {
            "status": "NO_INPUT",
            "timeline": pd.DataFrame(),
        },
        "review_indicators": pd.DataFrame(),
        "data_quality": pd.DataFrame(),
    }


def _patch_services(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        imei_device_controller,
        "case_report_dir",
        lambda case_id, report_type: tmp_path,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "register_target",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "register_report",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "register_analysis_run",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "log_case_event",
        lambda *args, **kwargs: None,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_print_source_summary",
        lambda analysis: None,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_prompt_imei",
        lambda: (_ for _ in ()).throw(
            AssertionError(
                "Manual IMEI prompt must not run."
            )
        ),
    )


def test_base14_report_query_matches_observed_imei():
    query = "35309885264836"
    observed = "353098852648360"

    payload = {
        "9000000001": {
            "df": _canonical_frame(
                query,
                observed,
            )
        }
    }

    cdr_result = build_imei_investigation(
        payload,
        query,
    )

    assert cdr_result[
        "status"
    ] == "FOUND"

    assert len(
        cdr_result[
            "timeline"
        ]
    ) == 1

    unified = build_unified_imei_investigation(
        query,
        loaded_cdrs=payload,
        ipdr_dataframe=None,
        gprs_dataframe=None,
    )

    assert unified[
        "overall_status"
    ] in {
        "FOUND",
        "PARTIAL",
    }


def test_one_detected_identifier_runs_one_single_analysis(
    monkeypatch,
    tmp_path: Path,
):
    _patch_services(
        monkeypatch,
        tmp_path,
    )

    identifier = "862261072892730"

    inventory = {
        "folder": tmp_path,
        "files_found": 1,
        "identifiers": [
            identifier,
        ],
        "device_frames": {
            identifier: _canonical_frame(
                identifier,
                "8622610728927300",
            ),
        },
        "acquisition_manifest": pd.DataFrame(
            [
                {
                    "Query Identifier": identifier,
                    "SHA-256": "a" * 64,
                }
            ]
        ),
        "unique_content_groups": 1,
        "analytical_records": 1,
        "warnings": [],
        "errors": [],
    }

    monkeypatch.setattr(
        imei_device_controller,
        "_load_dedicated_imei_cdr_inventory",
        lambda case_id: inventory,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "build_unified_imei_investigation",
        lambda requested_imei, **kwargs: (
            _analysis_bundle(
                requested_imei
            )
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "generate_imei_device_report",
        lambda **kwargs: (
            tmp_path
            / f"{kwargs['analysis']['requested_imei']}.xlsx"
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "generate_imei_common_report",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "Common report must not run for one identifier."
            )
        ),
    )

    result = (
        imei_device_controller
        ._execute_auto_detected_imei_cdr(
            {
                "case_id": "CASE-001",
            }
        )
    )

    assert result[
        "identifiers"
    ] == [
        identifier
    ]

    assert len(
        result[
            "single_results"
        ]
    ) == 1

    assert result[
        "common_result"
    ] is None


def test_multiple_identifiers_run_single_and_common_analysis(
    monkeypatch,
    tmp_path: Path,
):
    _patch_services(
        monkeypatch,
        tmp_path,
    )

    first = "862261072892730"
    second = "866284043482077"

    inventory = {
        "folder": tmp_path,
        "files_found": 2,
        "identifiers": [
            first,
            second,
        ],
        "device_frames": {
            first: _canonical_frame(
                first,
                "8622610728927300",
            ),
            second: _canonical_frame(
                second,
                second,
                target="9000000002",
            ),
        },
        "acquisition_manifest": pd.DataFrame(
            [
                {
                    "Query Identifier": first,
                    "SHA-256": "a" * 64,
                },
                {
                    "Query Identifier": second,
                    "SHA-256": "b" * 64,
                },
            ]
        ),
        "unique_content_groups": 2,
        "analytical_records": 2,
        "warnings": [],
        "errors": [],
    }

    monkeypatch.setattr(
        imei_device_controller,
        "_load_dedicated_imei_cdr_inventory",
        lambda case_id: inventory,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "build_unified_imei_investigation",
        lambda requested_imei, **kwargs: (
            _analysis_bundle(
                requested_imei
            )
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "generate_imei_device_report",
        lambda **kwargs: (
            tmp_path
            / f"{kwargs['analysis']['requested_imei']}.xlsx"
        ),
    )

    common_called = []

    monkeypatch.setattr(
        imei_device_controller,
        "build_common_imei_cdr_analysis",
        lambda frames, manifest: {
            "status": "FOUND",
            "device_count": 2,
            "message": "Common analysis.",
            "cross_device_timeline": pd.DataFrame(
                [
                    {
                        "Query Identifier": first,
                    },
                    {
                        "Query Identifier": second,
                    },
                ]
            ),
        },
    )

    monkeypatch.setattr(
        imei_device_controller,
        "generate_imei_common_report",
        lambda **kwargs: (
            common_called.append(
                kwargs
            )
            or (
                tmp_path
                / "common.xlsx"
            )
        ),
    )

    result = (
        imei_device_controller
        ._execute_auto_detected_imei_cdr(
            {
                "case_id": "CASE-001",
            }
        )
    )

    assert len(
        result[
            "single_results"
        ]
    ) == 2

    assert result[
        "common_result"
    ] is not None

    assert common_called
