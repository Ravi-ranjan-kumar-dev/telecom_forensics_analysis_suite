from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from modules.controllers import (
    tower_cdr_controller,
    tower_dump_controller,
    tower_gprs_controller,
    tower_ipdr_controller,
)


def test_complete_tower_backends_accept_optional_input_folder():
    functions = (
        tower_cdr_controller._run_complete_analysis,
        tower_gprs_controller._execute,
        tower_ipdr_controller._run_complete_tower_ipdr_analysis,
    )

    for function in functions:
        parameter = inspect.signature(
            function
        ).parameters[
            "input_folder"
        ]

        assert parameter.default is None


def test_unified_tower_dispatch_uses_selected_cdr_folder(
    tmp_path: Path,
    monkeypatch,
):
    observed = {}

    def fake_run(
        case,
        *,
        input_folder=None,
    ):
        observed["case"] = case
        observed["input_folder"] = input_folder
        return {
            "excel_report": "cdr.xlsx",
        }

    monkeypatch.setattr(
        tower_cdr_controller,
        "_run_complete_analysis",
        fake_run,
    )

    case = {
        "case_id": "DEV-WORKSPACE",
    }
    result = tower_dump_controller.run_complete_tower_dump_analysis(
        case,
        source_type="cdr",
        input_folder=tmp_path,
    )

    assert observed["case"] is case
    assert observed["input_folder"] == tmp_path.resolve()
    assert result == {
        "excel_report": "cdr.xlsx",
    }


def test_unified_tower_dispatch_uses_complete_gprs_workflow(
    tmp_path: Path,
    monkeypatch,
):
    observed = {}

    def fake_run(
        case,
        *,
        use_partitions,
        input_folder=None,
    ):
        observed["case"] = case
        observed["use_partitions"] = use_partitions
        observed["input_folder"] = input_folder
        return {
            "excel_report": "gprs.xlsx",
        }

    monkeypatch.setattr(
        tower_gprs_controller,
        "_execute",
        fake_run,
    )

    case = {
        "case_id": "DEV-WORKSPACE",
    }
    result = tower_dump_controller.run_complete_tower_dump_analysis(
        case,
        source_type="gprs",
        input_folder=tmp_path,
    )

    assert observed["case"] is case
    assert observed["use_partitions"] is False
    assert observed["input_folder"] == tmp_path.resolve()
    assert result == {
        "excel_report": "gprs.xlsx",
    }


def test_unified_tower_dispatch_uses_scalable_ipdr_workflow(
    tmp_path: Path,
    monkeypatch,
):
    observed = {}

    def fake_run(
        case,
        *,
        input_folder=None,
    ):
        observed["case"] = case
        observed["input_folder"] = input_folder
        return {
            "excel_report": "ipdr.xlsx",
        }

    monkeypatch.setattr(
        tower_ipdr_controller,
        "_run_complete_tower_ipdr_analysis",
        fake_run,
    )

    case = {
        "case_id": "DEV-WORKSPACE",
    }
    result = tower_dump_controller.run_complete_tower_dump_analysis(
        case,
        source_type="ipdr",
        input_folder=tmp_path,
    )

    assert observed["case"] is case
    assert observed["input_folder"] == tmp_path.resolve()
    assert result == {
        "excel_report": "ipdr.xlsx",
    }


def test_unified_tower_dispatch_rejects_unknown_source(
    tmp_path: Path,
):
    with pytest.raises(
        ValueError,
        match="Unsupported Tower Dump source type",
    ):
        tower_dump_controller.run_complete_tower_dump_analysis(
            {
                "case_id": "DEV-WORKSPACE",
            },
            source_type="unknown",
            input_folder=tmp_path,
        )


def test_unified_tower_dispatch_rejects_missing_folder(
    tmp_path: Path,
):
    missing_folder = tmp_path / "missing"

    with pytest.raises(
        FileNotFoundError,
        match="Tower Dump input folder not found",
    ):
        tower_dump_controller.run_complete_tower_dump_analysis(
            {
                "case_id": "DEV-WORKSPACE",
            },
            source_type="cdr",
            input_folder=missing_folder,
        )


def test_ipdr_fingerprint_uses_selected_gui_folder(
    tmp_path: Path,
):
    spot_folder = tmp_path / "spot_1"
    spot_folder.mkdir()
    source = spot_folder / "cell_ipdr.csv"
    source.write_text(
        "header\n",
        encoding="utf-8",
    )

    fingerprint = tower_ipdr_controller._tower_ipdr_input_fingerprint(
        tmp_path
    )

    assert fingerprint["input_dir"] == str(
        tmp_path.resolve()
    )
    assert fingerprint["file_count"] == 1
    assert fingerprint["files"][0]["path"] == (
        "spot_1/cell_ipdr.csv"
    )

@pytest.mark.parametrize(
    ("source_type", "attribute_name"),
    [
        (
            "cdr",
            "_run_complete_analysis",
        ),
        (
            "gprs",
            "_execute",
        ),
        (
            "ipdr",
            "_run_complete_tower_ipdr_analysis",
        ),
    ],
)
def test_unified_tower_dispatch_forwards_selected_spots(
    tmp_path: Path,
    monkeypatch,
    source_type,
    attribute_name,
):
    observed = {}

    def fake_run(
        case,
        **kwargs,
    ):
        observed.update(
            kwargs
        )
        return {
            "excel_report": "report.xlsx",
        }

    module = {
        "cdr": tower_cdr_controller,
        "gprs": tower_gprs_controller,
        "ipdr": tower_ipdr_controller,
    }[
        source_type
    ]

    monkeypatch.setattr(
        module,
        attribute_name,
        fake_run,
    )

    result = (
        tower_dump_controller
        .run_complete_tower_dump_analysis(
            {
                "case_id": "DEV-WORKSPACE",
            },
            source_type=source_type,
            input_folder=tmp_path,
            selected_spot_folders=[
                "Second Spot",
                "First Spot",
            ],
            include_root_files=False,
        )
    )

    assert result == {
        "excel_report": "report.xlsx",
    }
    assert observed["input_folder"] == (
        tmp_path.resolve()
    )
    assert observed[
        "selected_spot_folders"
    ] == (
        "Second Spot",
        "First Spot",
    )
    assert observed[
        "include_root_files"
    ] is False

    if source_type == "gprs":
        assert observed[
            "use_partitions"
        ] is False
