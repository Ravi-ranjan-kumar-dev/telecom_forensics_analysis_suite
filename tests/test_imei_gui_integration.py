from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui.app import build_application
from gui.main_window import MainWindow
from gui.pages.imei_page import ImeiPage
from gui.workers.imei_worker import (
    ImeiWorker,
    collect_imei_report_paths,
)
from modules.controllers import app_controller, imei_device_controller


def test_public_imei_runner_is_noninteractive_and_forwards_folder(
    tmp_path,
    monkeypatch,
):
    observed = {}

    def fake_handler(
        case,
        *,
        input_folder,
        allow_manual_fallback,
    ):
        observed.update(
            {
                "case": case,
                "input_folder": input_folder,
                "allow_manual_fallback": allow_manual_fallback,
            }
        )
        return {"identifiers": ["354079831251890"]}

    monkeypatch.setattr(
        imei_device_controller,
        "_execute_auto_detected_imei_cdr",
        fake_handler,
    )

    case = {"case_id": "DEV-WORKSPACE"}
    result = imei_device_controller.run_imei_device_analysis(
        case,
        mode="cdr",
        input_folder=tmp_path,
    )

    assert result == {"identifiers": ["354079831251890"]}
    assert observed == {
        "case": case,
        "input_folder": tmp_path.resolve(),
        "allow_manual_fallback": False,
    }


def test_public_imei_runner_rejects_invalid_inputs(tmp_path):
    with pytest.raises(ValueError):
        imei_device_controller.run_imei_device_analysis(
            {"case_id": "DEV-WORKSPACE"},
            mode="unknown",
            input_folder=tmp_path,
        )

    with pytest.raises(FileNotFoundError):
        imei_device_controller.run_imei_device_analysis(
            {"case_id": "DEV-WORKSPACE"},
            mode="cdr",
            input_folder=tmp_path / "missing",
        )


def test_collect_imei_report_paths_prefers_common_report(tmp_path):
    common = tmp_path / "common.xlsx"
    first = tmp_path / "first.xlsx"
    second = tmp_path / "second.xlsx"

    assert collect_imei_report_paths(
        {
            "common_result": {"report": common},
            "single_results": [
                {"report": first},
                {"report": second},
                {"report": first},
            ],
        }
    ) == [
        str(common.resolve()),
        str(first.resolve()),
        str(second.resolve()),
    ]


def test_imei_worker_runs_selected_folder(tmp_path, monkeypatch):
    report = tmp_path / "imei-report.xlsx"
    report.touch()
    observed = {}

    monkeypatch.setattr(
        app_controller,
        "get_direct_analysis_workspace",
        lambda: {"case_id": "DEV-WORKSPACE"},
    )

    def fake_run(case, *, mode, input_folder):
        observed.update(
            {
                "case": case,
                "mode": mode,
                "input_folder": input_folder,
            }
        )
        print("IMEI worker test completed.")
        return {
            "identifiers": ["354079831251890"],
            "single_results": [{"report": report}],
        }

    monkeypatch.setattr(
        imei_device_controller,
        "run_imei_device_analysis",
        fake_run,
    )

    worker = ImeiWorker(mode="cdr", input_folder=tmp_path)
    completed = []
    failed = []
    finished = []
    logs = []
    worker.completed.connect(completed.append)
    worker.failed.connect(failed.append)
    worker.finished.connect(lambda: finished.append(True))
    worker.log.connect(logs.append)
    worker.run()

    assert failed == []
    assert finished == [True]
    assert completed[0]["identifiers"] == ["354079831251890"]
    assert completed[0]["report_paths"] == [str(report.resolve())]
    assert observed["case"]["case_id"] == "DEV-WORKSPACE"
    assert observed["mode"] == "cdr"
    assert Path(observed["input_folder"]) == tmp_path.resolve()
    assert logs == ["IMEI worker test completed."]


def test_imei_page_validates_supported_evidence(tmp_path):
    build_application(["imei-gui-test"])
    page = ImeiPage()
    page.set_mode("cdr")
    page.set_selected_folder(tmp_path)

    assert "No supported" in page.validation_error()

    evidence = tmp_path / "query.csv"
    evidence.write_text("header\n", encoding="utf-8")

    assert page.validation_error() == ""
    page.close()


def test_main_window_uses_real_imei_page():
    build_application(["imei-main-window-test"])
    window = MainWindow()
    window.select_page_by_key("imei")

    assert window.active_page_key == "imei"
    assert isinstance(window._page_stack.currentWidget(), ImeiPage)
    window.close()
