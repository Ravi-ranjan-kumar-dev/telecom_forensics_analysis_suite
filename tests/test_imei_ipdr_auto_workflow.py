
from pathlib import Path

import pandas as pd

from modules.controllers import (
    imei_device_controller,
)


FIRST_IMEI = "862261072892730"
SECOND_IMEI = "862286069717070"


def _manifest(
    identifier: str,
    status: str,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Query Identifier": identifier,
                "Inspection Status": status,
                "Source Type": "IPDR",
                "SHA-256": "a" * 64,
            }
        ]
    )


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
        "supported_ipdr_content_groups": len(
            identifiers
        ),
        "non_ipdr_acquisitions": 0,
        "duplicate_ipdr_acquisitions": 0,
        "analytical_records": int(
            sum(
                len(frame)
                for frame in frames.values()
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
                "Evidence Source": "IPDR",
                "Evidence Type": "IPDR Record",
            }
        ]
    )

    return {
        "requested_imei": identifier,
        "overall_status": "FOUND",
        "message": "Requested IPDR evidence found.",
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
                    "Status": "FOUND",
                    "Evidence Unit": "IPDR records",
                    "Matched Count": 1,
                    "Message": "One IPDR record found.",
                },
                {
                    "Evidence Source": "GPRS",
                    "Status": "NO_INPUT",
                    "Evidence Unit": "GPRS sessions",
                    "Matched Count": 0,
                    "Message": "No GPRS evidence selected.",
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
            "status": "FOUND",
            "timeline": pd.DataFrame(
                [
                    {
                        "Event Time": "2025-10-05 08:14:24",
                    }
                ]
            ),
            "cells": pd.DataFrame(),
        },
        "gprs": {
            "status": "NO_INPUT",
            "timeline": pd.DataFrame(),
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

    return calls


def test_one_ipdr_identifier_runs_without_manual_prompt(
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
                "imei": "8622610728927300",
            }
        ]
    )

    inventory = _inventory(
        [
            FIRST_IMEI,
        ],
        {
            FIRST_IMEI: dataframe,
        },
        _manifest(
            FIRST_IMEI,
            "HAS_DATA",
        ),
        tmp_path,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_dedicated_imei_ipdr_inventory",
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

    report = tmp_path / "single-ipdr.xlsx"

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
                "Manual workflow must not run."
            )
        ),
    )

    result = (
        imei_device_controller
        ._execute_auto_detected_imei_ipdr(
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
        "ipdr_dataframe"
    ] is dataframe

    assert captured[
        "loaded_cdrs"
    ] is None

    assert captured[
        "gprs_dataframe"
    ] is None

    assert calls[
        "reports"
    ][
        0
    ][
        1
    ][
        "report_type"
    ] == "IMEI_IPDR_ANALYSIS"


def test_valid_empty_ipdr_report_creates_empty_workbook(
    monkeypatch,
    tmp_path: Path,
):
    calls = _patch_services(
        monkeypatch,
        tmp_path,
    )

    captured = []

    monkeypatch.setattr(
        imei_device_controller,
        "build_unified_imei_investigation",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "Event analysis must not run for a valid empty report."
            )
        ),
    )

    report = tmp_path / "empty-ipdr.xlsx"

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
        ._run_auto_single_imei_ipdr(
            case={
                "case_id": "CASE-001",
            },
            identifier=SECOND_IMEI,
            dataframe=pd.DataFrame(),
            acquisition_manifest=_manifest(
                SECOND_IMEI,
                "EMPTY_NO_DATA",
            ),
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
        "IPDR",
        "Status",
    ] == "EMPTY_NO_DATA"

    assert summary.loc[
        "CDR",
        "Status",
    ] == "NO_INPUT"

    assert summary.loc[
        "GPRS",
        "Status",
    ] == "NO_INPUT"

    assert captured[
        0
    ][
        "requested_imei"
    ] == SECOND_IMEI

    assert calls[
        "reports"
    ][
        0
    ][
        1
    ][
        "report_type"
    ] == "IMEI_IPDR_ANALYSIS"


def test_multiple_ipdr_identifiers_run_single_and_common_analysis(
    monkeypatch,
    tmp_path: Path,
):
    service_calls = _patch_services(
        monkeypatch,
        tmp_path,
    )

    manifest = pd.concat(
        [
            _manifest(
                FIRST_IMEI,
                "HAS_DATA",
            ),
            _manifest(
                SECOND_IMEI,
                "EMPTY_NO_DATA",
            ),
        ],
        ignore_index=True,
    )

    inventory = _inventory(
        [
            FIRST_IMEI,
            SECOND_IMEI,
        ],
        {
            FIRST_IMEI: pd.DataFrame(
                [
                    {
                        "imei": "8622610728927300",
                    }
                ]
            ),
            SECOND_IMEI: pd.DataFrame(),
        },
        manifest,
        tmp_path,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_dedicated_imei_ipdr_inventory",
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
        "_run_auto_single_imei_ipdr",
        fake_single,
    )

    common_analysis = {
        "status": "FOUND",
        "device_count": 2,
        "query_identifier_count": 2,
        "device_family_count": 2,
        "data_bearing_device_count": 1,
        "empty_report_count": 1,
        "message": "Common IMEI IPDR analysis.",
        "cross_device_timeline": pd.DataFrame(
            [
                {
                    "Query Identifier": FIRST_IMEI,
                }
            ]
        ),
    }

    common_calls = {}

    def fake_common_builder(
        frames,
        acquisition_manifest,
    ):
        common_calls[
            "frames"
        ] = frames

        common_calls[
            "manifest"
        ] = acquisition_manifest

        return common_analysis

    monkeypatch.setattr(
        imei_device_controller,
        "build_common_imei_ipdr_analysis",
        fake_common_builder,
    )

    common_report = (
        tmp_path
        / "common-ipdr.xlsx"
    )

    def fake_common_report(
        **kwargs,
    ):
        common_calls[
            "report_kwargs"
        ] = kwargs

        return common_report

    monkeypatch.setattr(
        imei_device_controller,
        "generate_imei_ipdr_common_report",
        fake_common_report,
    )

    result = (
        imei_device_controller
        ._execute_auto_detected_imei_ipdr(
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
    ] is not None

    assert result[
        "common_result"
    ][
        "analysis"
    ] is common_analysis

    assert result[
        "common_result"
    ][
        "report"
    ] == common_report

    assert result[
        "common_result"
    ][
        "output_records"
    ] == 1

    assert common_calls[
        "frames"
    ] is inventory[
        "device_frames"
    ]

    assert common_calls[
        "manifest"
    ] is inventory[
        "acquisition_manifest"
    ]

    assert common_calls[
        "report_kwargs"
    ][
        "analysis"
    ] is common_analysis

    assert any(
        kwargs.get(
            "report_type"
        )
        == "IMEI_IPDR_COMMON_ANALYSIS"
        for _, kwargs in service_calls[
            "reports"
        ]
    )

    assert any(
        kwargs.get(
            "analysis_type"
        )
        == "IMEI_IPDR_COMMON_ANALYSIS"
        and kwargs.get(
            "status"
        )
        == "COMPLETED"
        for _, kwargs in service_calls[
            "runs"
        ]
    )

    assert any(
        kwargs.get(
            "action"
        )
        == "IMEI_IPDR_COMMON_ANALYSIS_COMPLETED"
        for _, kwargs in service_calls[
            "events"
        ]
    )
def test_missing_ipdr_identifier_uses_manual_fallback(
    monkeypatch,
    tmp_path: Path,
):
    inventory = _inventory(
        [],
        {},
        pd.DataFrame(),
        tmp_path,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_dedicated_imei_ipdr_inventory",
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
        ._execute_auto_detected_imei_ipdr(
            {
                "case_id": "CASE-001",
            }
        )
    )

    assert captured[
        "mode"
    ] == "ipdr"

    assert result[
        "manual"
    ] is True


def test_menu_option_two_routes_to_automatic_ipdr(
    monkeypatch,
):
    choices = iter(
        [
            "2",
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
        "_execute_auto_detected_imei_ipdr",
        lambda case: calls.append(
            case
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_execute",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "Manual IPDR workflow must not be selected."
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
