from __future__ import annotations

import os
import threading
import time
from pathlib import Path

os.environ.setdefault(
    "QT_QPA_PLATFORM",
    "offscreen",
)

from gui.app import build_application
from gui import main_window as main_window_module
from gui.main_window import MainWindow
from gui.pages.tower_dump_page import TowerDumpPage
from gui.workers.tower_dump_worker import (
    TowerDumpWorker,
    collect_tower_report_paths,
)
from modules.controllers import (
    app_controller,
    tower_dump_controller,
)


def test_collect_tower_report_paths_preserves_user_facing_order(
    tmp_path: Path,
):
    excel = tmp_path / "tower.xlsx"
    summary = tmp_path / "summary.txt"

    paths = collect_tower_report_paths(
        {
            "summary_report": summary,
            "excel_report": excel,
        }
    )

    assert paths == [
        str(
            excel.resolve()
        ),
        str(
            summary.resolve()
        ),
    ]


def test_tower_page_validates_each_mode_and_remembers_folders(
    tmp_path: Path,
):
    build_application(
        [
            "tower-gui-test",
        ]
    )
    page = TowerDumpPage()

    cdr_folder = tmp_path / "cdr"
    cdr_spot = cdr_folder / "spot_1"
    cdr_spot.mkdir(
        parents=True
    )
    (
        cdr_spot
        / "tower.xlsx"
    ).write_bytes(
        b"placeholder"
    )

    gprs_folder = tmp_path / "gprs"
    gprs_folder.mkdir()
    (
        gprs_folder
        / "tower.csv"
    ).write_text(
        "header\n",
        encoding="utf-8",
    )

    ipdr_folder = tmp_path / "ipdr"
    ipdr_folder.mkdir()
    (
        ipdr_folder
        / "tower.txt"
    ).write_text(
        "header\n",
        encoding="utf-8",
    )

    page.set_mode(
        "cdr"
    )
    page.set_selected_folder(
        cdr_folder
    )
    assert page.validation_error() == ""

    page.set_mode(
        "gprs"
    )
    page.set_selected_folder(
        gprs_folder
    )
    assert page.validation_error() == ""

    page.set_mode(
        "ipdr"
    )
    page.set_selected_folder(
        ipdr_folder
    )
    assert page.validation_error() == ""

    page.set_mode(
        "cdr"
    )
    assert page.selected_folder == str(
        cdr_folder.resolve()
    )

    page.set_mode(
        "gprs"
    )
    assert page.selected_folder == str(
        gprs_folder.resolve()
    )

    page.close()


def test_tower_page_rejects_wrong_file_type_for_gprs(
    tmp_path: Path,
):
    build_application(
        [
            "tower-gui-test",
        ]
    )
    page = TowerDumpPage()
    folder = tmp_path / "gprs"
    folder.mkdir()
    (
        folder
        / "unsupported.xlsx"
    ).write_bytes(
        b"placeholder"
    )

    page.set_mode(
        "gprs"
    )
    page.set_selected_folder(
        folder
    )

    assert "No supported evidence files" in (
        page.validation_error()
    )

    page.close()


def test_tower_worker_uses_direct_case_and_selected_folder(
    tmp_path: Path,
    monkeypatch,
):
    build_application(
        [
            "tower-worker-test",
        ]
    )
    case = {
        "case_id": "DEV-WORKSPACE",
    }
    report = tmp_path / "tower.xlsx"
    observed = {}

    monkeypatch.setattr(
        app_controller,
        "get_direct_analysis_workspace",
        lambda: case,
    )

    def fake_run(
        selected_case,
        *,
        source_type,
        input_folder,
    ):
        observed["case"] = selected_case
        observed["source_type"] = source_type
        observed["input_folder"] = input_folder
        print("backend progress")
        return {
            "excel_report": report,
        }

    monkeypatch.setattr(
        tower_dump_controller,
        "run_complete_tower_dump_analysis",
        fake_run,
    )

    worker = TowerDumpWorker(
        source_type="cdr",
        input_folder=tmp_path,
    )
    logs = []
    completed = []
    failures = []
    finished = []
    worker.log.connect(
        logs.append
    )
    worker.completed.connect(
        completed.append
    )
    worker.failed.connect(
        failures.append
    )
    worker.finished.connect(
        lambda: finished.append(
            True
        )
    )

    worker.run()

    assert observed["case"] is case
    assert observed["source_type"] == "cdr"
    assert observed["input_folder"] == tmp_path.resolve()
    assert logs == [
        "backend progress",
    ]
    assert failures == []
    assert finished == [
        True,
    ]
    assert completed[0]["report_paths"] == [
        str(
            report.resolve()
        )
    ]


def test_main_window_uses_real_tower_dump_page():
    build_application(
        [
            "tower-main-window-test",
        ]
    )
    window = MainWindow()
    tower_index = window.navigation_keys.index(
        "tower_dump"
    )

    assert isinstance(
        window._page_stack.widget(
            tower_index
        ),
        TowerDumpPage,
    )

    window.close()


def test_main_window_blocks_close_until_tower_analysis_finishes(
    tmp_path: Path,
    monkeypatch,
):
    application = build_application(
        [
            "tower-thread-lifecycle-test",
        ]
    )
    case = {
        "case_id": "DEV-WORKSPACE",
    }
    started = threading.Event()
    release = threading.Event()
    warnings: list[tuple[str, str]] = []
    report = tmp_path / "tower.xlsx"
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (
        evidence
        / "tower.csv"
    ).write_text(
        "header\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        app_controller,
        "get_direct_analysis_workspace",
        lambda: case,
    )

    def controlled_run(
        selected_case,
        *,
        source_type,
        input_folder,
    ):
        assert selected_case is case
        assert source_type == "cdr"
        assert input_folder == evidence.resolve()
        started.set()

        if not release.wait(
            timeout=3.0
        ):
            raise TimeoutError(
                "Test worker was not released."
            )

        report.write_bytes(
            b"report"
        )
        return {
            "excel_report": report,
        }

    monkeypatch.setattr(
        tower_dump_controller,
        "run_complete_tower_dump_analysis",
        controlled_run,
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append(
            (
                title,
                message,
            )
        ),
    )

    window = MainWindow()
    tower_index = window.navigation_keys.index(
        "tower_dump"
    )
    page = window._page_stack.widget(
        tower_index
    )
    assert isinstance(
        page,
        TowerDumpPage,
    )
    page.set_mode(
        "cdr"
    )
    page.set_selected_folder(
        evidence
    )
    window.show()

    try:
        page._start_analysis()
        deadline = time.monotonic() + 3.0

        while (
            not started.is_set()
            and time.monotonic() < deadline
        ):
            application.processEvents()

        assert started.is_set()
        assert page.is_running
        assert window.close() is False
        assert window.isVisible()
        assert warnings
        assert warnings[0][0] == "Analysis in Progress"
        assert "Tower Dump Analysis is still running" in (
            warnings[0][1]
        )

        release.set()
        deadline = time.monotonic() + 3.0

        while (
            page.is_running
            and time.monotonic() < deadline
        ):
            application.processEvents()

        assert not page.is_running
        assert window.close() is True

    finally:
        release.set()

        if page.is_running:
            page._thread.quit()
            page._thread.wait(
                3000
            )

        window.close()
