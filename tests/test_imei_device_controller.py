from __future__ import annotations

from pathlib import Path

import pandas as pd

from modules.cases.service import REPORT_PATHS
from modules.controllers import (
    imei_device_controller,
)
from modules.controllers.ipdr_case_controller import (
    resolve_ipdr_input_folder,
)
from modules.controllers.tower_gprs_controller import (
    resolve_gprs_input_folder,
)


IMEI = "862518054878650"


def _cdr_payload():
    return {
        "9000000001": {
            "df": pd.DataFrame(
                [
                    {
                        "imei": IMEI,
                    }
                ]
            )
        }
    }


def _ipdr_payload():
    return pd.DataFrame(
        [
            {
                "imei": IMEI,
            }
        ]
    )


def _gprs_payload():
    return pd.DataFrame(
        [
            {
                "imei": IMEI,
            }
        ]
    )


def _analysis_bundle(
    *,
    cdr=None,
    ipdr=None,
    gprs=None,
    found=True,
):
    rows = []

    source_values = {
        "CDR": cdr,
        "IPDR": ipdr,
        "GPRS": gprs,
    }

    source_units = {
        "CDR": "CDR records",
        "IPDR": "IPDR records",
        "GPRS": "GPRS sessions",
    }

    timeline_rows = []

    for source, payload in source_values.items():
        matched = (
            payload is not None
            and found
        )

        rows.append(
            {
                "Evidence Source": source,
                "Status": (
                    "FOUND"
                    if matched
                    else "NO_INPUT"
                ),
                "Evidence Unit": source_units[
                    source
                ],
                "Matched Count": (
                    1
                    if matched
                    else 0
                ),
                "Message": "",
            }
        )

        if matched:
            timeline_rows.append(
                {
                    "Evidence Source": source,
                    "Start Time": pd.Timestamp(
                        "2026-01-01 10:00:00"
                    ),
                }
            )

    return {
        "requested_imei": IMEI,
        "overall_status": (
            "FOUND"
            if timeline_rows
            else "NOT_FOUND"
        ),
        "message": "",
        "source_summary": pd.DataFrame(
            rows
        ),
        "cross_source_timeline": pd.DataFrame(
            timeline_rows
        ),
        "cdr": {
            "status": rows[0][
                "Status"
            ],
            "timeline": pd.DataFrame(),
        },
        "ipdr": {
            "status": rows[1][
                "Status"
            ],
            "timeline": pd.DataFrame(),
        },
        "gprs": {
            "status": rows[2][
                "Status"
            ],
            "timeline": pd.DataFrame(),
        },
    }


def _patch_case_services(
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
        lambda case_id, **kwargs: (
            calls[
                "targets"
            ].append(
                (
                    case_id,
                    kwargs,
                )
            )
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "register_report",
        lambda case_id, **kwargs: (
            calls[
                "reports"
            ].append(
                (
                    case_id,
                    kwargs,
                )
            )
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "register_analysis_run",
        lambda case_id, **kwargs: (
            calls[
                "runs"
            ].append(
                (
                    case_id,
                    kwargs,
                )
            )
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "log_case_event",
        lambda case_id, **kwargs: (
            calls[
                "events"
            ].append(
                (
                    case_id,
                    kwargs,
                )
            )
        ),
    )

    return calls


def test_cdr_mode_loads_only_cdr(
    monkeypatch,
    tmp_path: Path,
):
    calls = _patch_case_services(
        monkeypatch,
        tmp_path,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_cdr_evidence",
        lambda case_id: _cdr_payload(),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_ipdr_evidence",
        lambda case_id: (_ for _ in ()).throw(
            AssertionError(
                "IPDR loader should not run."
            )
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_gprs_evidence",
        lambda case_id: (_ for _ in ()).throw(
            AssertionError(
                "GPRS loader should not run."
            )
        ),
    )

    captured = {}

    def fake_builder(
        requested_imei,
        *,
        loaded_cdrs=None,
        ipdr_dataframe=None,
        gprs_dataframe=None,
    ):
        captured[
            "cdr"
        ] = loaded_cdrs

        captured[
            "ipdr"
        ] = ipdr_dataframe

        captured[
            "gprs"
        ] = gprs_dataframe

        return _analysis_bundle(
            cdr=loaded_cdrs,
        )

    monkeypatch.setattr(
        imei_device_controller,
        "build_unified_imei_investigation",
        fake_builder,
    )

    report_path = tmp_path / "cdr_imei.xlsx"

    monkeypatch.setattr(
        imei_device_controller,
        "generate_imei_device_report",
        lambda **kwargs: report_path,
    )

    result = imei_device_controller._execute(
        {
            "case_id": "CASE-001",
            "case_name": "Test",
        },
        mode="cdr",
        requested_imei=IMEI,
    )

    assert captured[
        "cdr"
    ] is not None

    assert captured[
        "ipdr"
    ] is None

    assert captured[
        "gprs"
    ] is None

    assert result[
        "report"
    ] == report_path

    assert calls[
        "reports"
    ]


def test_unified_mode_loads_all_sources(
    monkeypatch,
    tmp_path: Path,
):
    _patch_case_services(
        monkeypatch,
        tmp_path,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_cdr_evidence",
        lambda case_id: _cdr_payload(),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_ipdr_evidence",
        lambda case_id: _ipdr_payload(),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_gprs_evidence",
        lambda case_id: _gprs_payload(),
    )

    captured = {}

    def fake_builder(
        requested_imei,
        *,
        loaded_cdrs=None,
        ipdr_dataframe=None,
        gprs_dataframe=None,
    ):
        captured.update(
            {
                "cdr": loaded_cdrs,
                "ipdr": ipdr_dataframe,
                "gprs": gprs_dataframe,
            }
        )

        return _analysis_bundle(
            cdr=loaded_cdrs,
            ipdr=ipdr_dataframe,
            gprs=gprs_dataframe,
        )

    monkeypatch.setattr(
        imei_device_controller,
        "build_unified_imei_investigation",
        fake_builder,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "generate_imei_device_report",
        lambda **kwargs: (
            tmp_path / "unified.xlsx"
        ),
    )

    result = imei_device_controller._execute(
        {
            "case_id": "CASE-001",
        },
        mode="unified",
        requested_imei=IMEI,
    )

    assert captured[
        "cdr"
    ] is not None

    assert isinstance(
        captured[
            "ipdr"
        ],
        pd.DataFrame,
    )

    assert isinstance(
        captured[
            "gprs"
        ],
        pd.DataFrame,
    )

    assert result[
        "input_records"
    ] == 3


def test_one_loader_error_produces_partial_result(
    monkeypatch,
    tmp_path: Path,
):
    _patch_case_services(
        monkeypatch,
        tmp_path,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_cdr_evidence",
        lambda case_id: (_ for _ in ()).throw(
            ValueError(
                "CDR unavailable"
            )
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_ipdr_evidence",
        lambda case_id: _ipdr_payload(),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_gprs_evidence",
        lambda case_id: _gprs_payload(),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "build_unified_imei_investigation",
        lambda requested_imei, **kwargs: (
            _analysis_bundle(
                ipdr=kwargs[
                    "ipdr_dataframe"
                ],
                gprs=kwargs[
                    "gprs_dataframe"
                ],
            )
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "generate_imei_device_report",
        lambda **kwargs: (
            tmp_path / "partial.xlsx"
        ),
    )

    result = imei_device_controller._execute(
        {
            "case_id": "CASE-001",
        },
        mode="unified",
        requested_imei=IMEI,
    )

    assert result[
        "analysis"
    ][
        "overall_status"
    ] == "PARTIAL"

    summary = result[
        "analysis"
    ][
        "source_summary"
    ].set_index(
        "Evidence Source"
    )

    assert summary.loc[
        "CDR",
        "Status",
    ] == "ERROR"


def test_invalid_imei_does_not_load_sources(
    monkeypatch,
    tmp_path: Path,
):
    _patch_case_services(
        monkeypatch,
        tmp_path,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_selected_sources",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "Sources should not be loaded."
            )
        ),
    )

    result = imei_device_controller._execute(
        {
            "case_id": "CASE-001",
        },
        mode="unified",
        requested_imei="12345",
    )

    assert result[
        "analysis"
    ][
        "overall_status"
    ] == "INVALID_IMEI"

    assert result[
        "report"
    ] is None


def test_not_found_does_not_generate_report(
    monkeypatch,
    tmp_path: Path,
):
    calls = _patch_case_services(
        monkeypatch,
        tmp_path,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_cdr_evidence",
        lambda case_id: _cdr_payload(),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "build_unified_imei_investigation",
        lambda requested_imei, **kwargs: (
            _analysis_bundle(
                found=False
            )
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "generate_imei_device_report",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "Report generator should not run."
            )
        ),
    )

    result = imei_device_controller._execute(
        {
            "case_id": "CASE-001",
        },
        mode="cdr",
        requested_imei=IMEI,
    )

    assert result[
        "analysis"
    ][
        "overall_status"
    ] == "NOT_FOUND"

    assert result[
        "report"
    ] is None

    assert not calls[
        "reports"
    ]

    assert calls[
        "runs"
    ][
        -1
    ][
        1
    ][
        "status"
    ] == "COMPLETED"


def test_success_registers_imei_target_and_report(
    monkeypatch,
    tmp_path: Path,
):
    calls = _patch_case_services(
        monkeypatch,
        tmp_path,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_load_gprs_evidence",
        lambda case_id: _gprs_payload(),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "build_unified_imei_investigation",
        lambda requested_imei, **kwargs: (
            _analysis_bundle(
                gprs=kwargs[
                    "gprs_dataframe"
                ],
            )
        ),
    )

    report = tmp_path / "gprs.xlsx"

    monkeypatch.setattr(
        imei_device_controller,
        "generate_imei_device_report",
        lambda **kwargs: report,
    )

    imei_device_controller._execute(
        {
            "case_id": "CASE-001",
        },
        mode="gprs",
        requested_imei=IMEI,
    )

    assert calls[
        "targets"
    ][
        0
    ][
        1
    ][
        "target_type"
    ] == "IMEI"

    assert calls[
        "reports"
    ][
        0
    ][
        1
    ][
        "report_path"
    ] == report

    assert calls[
        "runs"
    ][
        -1
    ][
        1
    ][
        "status"
    ] == "COMPLETED"


def test_device_menu_contract(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": "0",
    )

    choice = imei_device_controller._menu(
        {
            "case_id": "CASE-001",
            "case_name": "Test",
        }
    )

    output = capsys.readouterr().out

    assert choice == "0"
    assert "1. IMEI CDR Analysis" in output
    assert "2. IMEI IPDR Analysis" in output
    assert "3. IMEI GPRS Analysis" in output
    assert "4. Unified IMEI Analysis" in output


def test_public_source_resolvers_and_report_mapping():
    assert callable(
        resolve_ipdr_input_folder
    )

    assert callable(
        resolve_gprs_input_folder
    )

    assert REPORT_PATHS[
        "imei_device"
    ] == (
        "reports",
        "device",
        "imei",
    )
