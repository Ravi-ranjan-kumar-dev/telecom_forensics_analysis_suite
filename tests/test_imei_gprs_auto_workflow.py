
from __future__ import annotations

from pathlib import Path

import pandas as pd

from modules.controllers import (
    imei_device_controller,
)


FIRST_IMEI = "862261072892730"
SECOND_IMEI = "862286069717074"


def _manifest_row(
    identifier: str,
    status: str,
    *,
    source_type: str = "GPRS",
    digest: str = "a",
) -> dict:
    return {
        "Query Identifier": identifier,
        "Inspection Status": status,
        "Source Type": source_type,
        "SHA-256": digest * 64,
    }


def _inventory(
    identifiers,
    frames,
    manifest,
    tmp_path: Path,
):
    return {
        "folder": tmp_path,
        "files_found": len(
            manifest
        ),
        "identifiers": list(
            identifiers
        ),
        "device_frames": frames,
        "acquisition_manifest": manifest,
        "all_content_groups": len(
            manifest
        ),
        "supported_gprs_content_groups": len(
            identifiers
        ),
        "non_gprs_acquisitions": int(
            (
                manifest[
                    "Source Type"
                ]
                .astype(
                    str
                )
                .str.upper()
                .ne(
                    "GPRS"
                )
            ).sum()
        )
        if not manifest.empty
        else 0,
        "duplicate_gprs_acquisitions": 0,
        "analytical_records": int(
            sum(
                len(
                    dataframe
                )
                for dataframe in frames.values()
            )
        ),
        "warnings": [],
        "errors": [],
    }


def _found_analysis(
    identifier: str,
) -> dict:
    timeline = pd.DataFrame(
        [
            {
                "Evidence Source": "GPRS",
                "Evidence Type": "GPRS Session",
            }
        ]
    )

    return {
        "requested_imei": identifier,
        "overall_status": "FOUND",
        "message": "Requested GPRS evidence found.",
        "source_summary": pd.DataFrame(
            [
                {
                    "Evidence Source": "CDR",
                    "Status": "NO_INPUT",
                    "Evidence Unit": "CDR records",
                    "Matched Count": 0,
                    "Message": "No CDR evidence selected.",
                },
                {
                    "Evidence Source": "IPDR",
                    "Status": "NO_INPUT",
                    "Evidence Unit": "IPDR records",
                    "Matched Count": 0,
                    "Message": "No IPDR evidence selected.",
                },
                {
                    "Evidence Source": "GPRS",
                    "Status": "FOUND",
                    "Evidence Unit": "GPRS sessions",
                    "Matched Count": 1,
                    "Message": "One GPRS session found.",
                },
            ]
        ),
        "associated_identities": pd.DataFrame(),
        "cross_source_timeline": timeline,
        "cdr": {
            "status": "NO_INPUT",
            "timeline": pd.DataFrame(),
            "towers": pd.DataFrame(),
        },
        "ipdr": {
            "status": "NO_INPUT",
            "timeline": pd.DataFrame(),
            "cells": pd.DataFrame(),
        },
        "gprs": {
            "status": "FOUND",
            "timeline": timeline,
            "cells": pd.DataFrame(),
        },
        "review_indicators": pd.DataFrame(),
        "data_quality": pd.DataFrame(),
    }


def _patch_services(
    monkeypatch,
    tmp_path: Path,
):
    calls = {
        "targets": [],
        "reports": [],
        "runs": [],
        "events": [],
    }

    monkeypatch.setattr(
        imei_device_controller,
        "case_report_dir",
        lambda case_id, report_type: tmp_path,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "register_target",
        lambda *args, **kwargs: calls[
            "targets"
        ].append(
            (
                args,
                kwargs,
            )
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "register_report",
        lambda *args, **kwargs: calls[
            "reports"
        ].append(
            (
                args,
                kwargs,
            )
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "register_analysis_run",
        lambda *args, **kwargs: calls[
            "runs"
        ].append(
            (
                args,
                kwargs,
            )
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "log_case_event",
        lambda *args, **kwargs: calls[
            "events"
        ].append(
            (
                args,
                kwargs,
            )
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_print_source_summary",
        lambda analysis: None,
    )

    return calls


def test_one_gprs_identifier_runs_without_manual_prompt(
    monkeypatch,
    tmp_path: Path,
):
    calls = _patch_services(
        monkeypatch,
        tmp_path,
    )

    dataframe = pd.DataFrame(
        [
            {
                "query_identifier_normalized": FIRST_IMEI,
                "imei": FIRST_IMEI + "0",
            }
        ]
    )

    manifest = pd.DataFrame(
        [
            _manifest_row(
                FIRST_IMEI,
                "HAS_DATA",
            )
        ]
    )

    inventory = _inventory(
        [
            FIRST_IMEI,
        ],
        {
            FIRST_IMEI: dataframe,
        },
        manifest,
        tmp_path,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_dedicated_imei_gprs_inventory",
        lambda case_id: inventory,
    )

    captured = {}

    def fake_analysis(
        requested_imei,
        **kwargs,
    ):
        captured[
            "requested_imei"
        ] = requested_imei

        captured.update(
            kwargs
        )

        return _found_analysis(
            requested_imei
        )

    monkeypatch.setattr(
        imei_device_controller,
        "build_unified_imei_investigation",
        fake_analysis,
    )

    report = tmp_path / "single-gprs.xlsx"

    monkeypatch.setattr(
        imei_device_controller,
        "generate_imei_device_report",
        lambda **kwargs: report,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_execute",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "Manual GPRS workflow must not run."
            )
        ),
    )

    result = (
        imei_device_controller
        ._execute_auto_detected_imei_gprs(
            {
                "case_id": "CASE-001",
            }
        )
    )

    assert result[
        "identifiers"
    ] == [
        FIRST_IMEI,
    ]

    assert len(
        result[
            "single_results"
        ]
    ) == 1

    assert result[
        "common_result"
    ] is None

    assert captured[
        "requested_imei"
    ] == FIRST_IMEI

    assert captured[
        "gprs_dataframe"
    ] is dataframe

    assert captured[
        "loaded_cdrs"
    ] is None

    assert captured[
        "ipdr_dataframe"
    ] is None

    assert calls[
        "reports"
    ][
        0
    ][
        1
    ][
        "report_type"
    ] == "IMEI_GPRS_ANALYSIS"


def test_valid_empty_gprs_ignores_same_query_ipdr_acquisition(
    monkeypatch,
    tmp_path: Path,
):
    calls = _patch_services(
        monkeypatch,
        tmp_path,
    )

    manifest = pd.DataFrame(
        [
            _manifest_row(
                FIRST_IMEI,
                "EMPTY_NO_DATA",
                source_type="GPRS",
                digest="a",
            ),
            _manifest_row(
                FIRST_IMEI,
                "HAS_DATA",
                source_type="IPDR",
                digest="b",
            ),
        ]
    )

    monkeypatch.setattr(
        imei_device_controller,
        "build_unified_imei_investigation",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "Event analysis must not run for a valid "
                "empty GPRS report."
            )
        ),
    )

    captured = []

    report = tmp_path / "empty-gprs.xlsx"

    def fake_report(
        **kwargs,
    ):
        captured.append(
            kwargs[
                "analysis"
            ]
        )

        return report

    monkeypatch.setattr(
        imei_device_controller,
        "generate_imei_device_report",
        fake_report,
    )

    result = (
        imei_device_controller
        ._run_auto_single_imei_gprs(
            case={
                "case_id": "CASE-001",
            },
            identifier=FIRST_IMEI,
            dataframe=pd.DataFrame(),
            acquisition_manifest=manifest,
        )
    )

    analysis = result[
        "analysis"
    ]

    assert analysis[
        "overall_status"
    ] == "EMPTY_NO_DATA"

    summary = analysis[
        "source_summary"
    ].set_index(
        "Evidence Source"
    )

    assert summary.loc[
        "GPRS",
        "Status",
    ] == "EMPTY_NO_DATA"

    assert summary.loc[
        "CDR",
        "Status",
    ] == "NO_INPUT"

    assert summary.loc[
        "IPDR",
        "Status",
    ] == "NO_INPUT"

    report_manifest = captured[
        0
    ][
        "acquisition_manifest"
    ]

    assert len(
        report_manifest
    ) == 1

    assert report_manifest.iloc[
        0
    ][
        "Source Type"
    ] == "GPRS"

    assert calls[
        "reports"
    ][
        0
    ][
        1
    ][
        "report_type"
    ] == "IMEI_GPRS_ANALYSIS"


def test_multiple_gprs_identifiers_run_single_reports_only(
    monkeypatch,
    tmp_path: Path,
):
    manifest = pd.DataFrame(
        [
            _manifest_row(
                FIRST_IMEI,
                "EMPTY_NO_DATA",
                digest="a",
            ),
            _manifest_row(
                SECOND_IMEI,
                "EMPTY_NO_DATA",
                digest="b",
            ),
        ]
    )

    inventory = _inventory(
        [
            FIRST_IMEI,
            SECOND_IMEI,
        ],
        {
            FIRST_IMEI: pd.DataFrame(),
            SECOND_IMEI: pd.DataFrame(),
        },
        manifest,
        tmp_path,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_dedicated_imei_gprs_inventory",
        lambda case_id: inventory,
    )

    single_calls = []

    def fake_single(
        **kwargs,
    ):
        single_calls.append(
            kwargs[
                "identifier"
            ]
        )

        return {
            "identifier": kwargs[
                "identifier"
            ],
            "analysis": {},
            "report": None,
            "input_records": len(
                kwargs[
                    "dataframe"
                ]
            ),
            "output_records": 0,
        }

    monkeypatch.setattr(
        imei_device_controller,
        "_run_auto_single_imei_gprs",
        fake_single,
    )

    result = (
        imei_device_controller
        ._execute_auto_detected_imei_gprs(
            {
                "case_id": "CASE-001",
            }
        )
    )

    assert single_calls == [
        FIRST_IMEI,
        SECOND_IMEI,
    ]

    assert len(
        result[
            "single_results"
        ]
    ) == 2

    assert result[
        "common_result"
    ] is None

    assert result[
        "input_records"
    ] == 0


def test_missing_gprs_identifier_uses_manual_fallback(
    monkeypatch,
    tmp_path: Path,
):
    inventory = _inventory(
        [],
        {},
        pd.DataFrame(
            columns=[
                "Source Type",
            ]
        ),
        tmp_path,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_dedicated_imei_gprs_inventory",
        lambda case_id: inventory,
    )

    captured = {}

    def fake_execute(
        case,
        *,
        mode,
        requested_imei=None,
    ):
        captured[
            "mode"
        ] = mode

        return {
            "mode": mode,
            "manual": True,
        }

    monkeypatch.setattr(
        imei_device_controller,
        "_execute",
        fake_execute,
    )

    result = (
        imei_device_controller
        ._execute_auto_detected_imei_gprs(
            {
                "case_id": "CASE-001",
            }
        )
    )

    assert captured[
        "mode"
    ] == "gprs"

    assert result[
        "manual"
    ] is True


def test_menu_option_three_routes_to_automatic_gprs(
    monkeypatch,
):
    choices = iter(
        [
            "3",
            "0",
        ]
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_menu",
        lambda case: next(
            choices
        ),
    )

    calls = []

    monkeypatch.setattr(
        imei_device_controller,
        "_execute_auto_detected_imei_gprs",
        lambda case: calls.append(
            case
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_execute",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "Manual GPRS workflow must not be selected."
            )
        ),
    )

    case = {
        "case_id": "CASE-001",
    }

    imei_device_controller.handle_imei_device_workspace(
        case
    )

    assert calls == [
        case,
    ]
