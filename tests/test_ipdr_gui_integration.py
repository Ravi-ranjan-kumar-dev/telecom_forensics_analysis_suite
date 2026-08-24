from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault(
    "QT_QPA_PLATFORM",
    "offscreen",
)

from gui.app import build_application
from gui.main_window import MainWindow
from gui.pages.ipdr_page import IpdrPage
from gui.workers.ipdr_worker import (
    IpdrWorker,
    collect_ipdr_report_paths,
)
from modules.controllers import (
    app_controller,
    ipdr_case_controller,
)


def test_resolve_ipdr_input_folder_accepts_gui_selection(
    tmp_path,
):
    selected = tmp_path / "selected-ipdr"
    selected.mkdir()

    assert ipdr_case_controller.resolve_ipdr_input_folder(
        "DEV-WORKSPACE",
        "single",
        selected,
    ) == selected.resolve()

    with pytest.raises(
        FileNotFoundError,
    ):
        ipdr_case_controller.resolve_ipdr_input_folder(
            "DEV-WORKSPACE",
            "single",
            tmp_path / "missing",
        )


def test_public_ipdr_runner_forwards_selected_folder(
    tmp_path,
    monkeypatch,
):
    observed = {}

    def fake_execute(
        case,
        *,
        mode,
        input_folder,
    ):
        observed.update(
            {
                "case": case,
                "mode": mode,
                "input_folder": input_folder,
            }
        )
        return {
            "excel_report": "report.xlsx",
        }

    monkeypatch.setattr(
        ipdr_case_controller,
        "_execute",
        fake_execute,
    )

    case = {
        "case_id": "DEV-WORKSPACE",
    }
    result = ipdr_case_controller.run_ipdr_case_analysis(
        case,
        mode="single",
        input_folder=tmp_path,
    )

    assert result == {
        "excel_report": "report.xlsx",
    }
    assert observed == {
        "case": case,
        "mode": "single",
        "input_folder": tmp_path,
    }


def test_collect_ipdr_report_paths_returns_portable_path(
    tmp_path,
):
    report = tmp_path / "subscriber-ipdr.xlsx"

    assert collect_ipdr_report_paths(
        {
            "excel_report": report,
        }
    ) == [
        str(
            report.resolve()
        )
    ]

    assert collect_ipdr_report_paths(
        {}
    ) == []


def test_ipdr_worker_runs_selected_folder(
    tmp_path,
    monkeypatch,
):
    report = tmp_path / "ipdr-report.xlsx"
    report.touch()
    observed = {}

    monkeypatch.setattr(
        app_controller,
        "get_direct_analysis_workspace",
        lambda: {
            "case_id": "DEV-WORKSPACE",
        },
    )

    def fake_run(
        case,
        *,
        mode,
        input_folder,
    ):
        observed.update(
            {
                "case": case,
                "mode": mode,
                "input_folder": input_folder,
            }
        )
        print("IPDR worker test completed.")
        return {
            "excel_report": str(
                report
            ),
        }

    monkeypatch.setattr(
        ipdr_case_controller,
        "run_ipdr_case_analysis",
        fake_run,
    )

    worker = IpdrWorker(
        mode="single",
        input_folder=tmp_path,
    )
    completed = []
    failed = []
    finished = []
    logs = []

    worker.completed.connect(
        completed.append
    )
    worker.failed.connect(
        failed.append
    )
    worker.finished.connect(
        lambda: finished.append(
            True
        )
    )
    worker.log.connect(
        logs.append
    )

    worker.run()

    assert failed == []
    assert finished == [
        True
    ]
    assert len(
        completed
    ) == 1
    assert completed[
        0
    ][
        "report_paths"
    ] == [
        str(
            report.resolve()
        )
    ]
    assert observed[
        "case"
    ][
        "case_id"
    ] == "DEV-WORKSPACE"
    assert observed[
        "mode"
    ] == "single"
    assert Path(
        observed[
            "input_folder"
        ]
    ) == tmp_path.resolve()
    assert logs == [
        "IPDR worker test completed."
    ]


def test_ipdr_page_validates_supported_files(
    tmp_path,
):
    build_application(
        [
            "ipdr-gui-test",
        ]
    )

    page = IpdrPage()
    page.set_mode(
        "single"
    )
    page.set_selected_folder(
        tmp_path
    )

    assert "No supported" in page.validation_error()

    nested = tmp_path / "query"
    nested.mkdir()
    first = nested / "first.csv"
    first.write_text(
        "header\n",
        encoding="utf-8",
    )

    assert page.validation_error() == ""

    page.set_mode(
        "multiple"
    )
    page.set_selected_folder(
        tmp_path
    )

    assert "at least two" in page.validation_error()

    second = tmp_path / "second.xlsx"
    second.touch()

    assert page.validation_error() == ""

    page.close()


def test_main_window_uses_real_ipdr_page():
    build_application(
        [
            "ipdr-main-window-test",
        ]
    )

    window = MainWindow()
    window.select_page_by_key(
        "ipdr"
    )

    assert window.active_page_key == "ipdr"
    assert isinstance(
        window._page_stack.currentWidget(),
        IpdrPage,
    )

    window.close()
