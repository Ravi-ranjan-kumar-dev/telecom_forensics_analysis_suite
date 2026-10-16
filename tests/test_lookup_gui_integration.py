from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui.app import build_application
from gui.main_window import MainWindow
from gui.pages.lookup_page import LookupPage
from gui.workers.lookup_worker import LookupWorker
from modules.controllers import app_controller, lookup_controller


def test_programmatic_lookup_logs_minimal_status(monkeypatch):
    logged = []
    expected = {"status": "MATCHED", "record": {"cgi": "405-52-1-2"}}

    monkeypatch.setattr(
        lookup_controller,
        "lookup_cgi_profile",
        lambda value: expected,
    )
    monkeypatch.setattr(
        lookup_controller,
        "_log_lookup_event",
        lambda case, **details: logged.append((case, details)),
    )

    case = {"case_id": "DEV-WORKSPACE"}
    assert lookup_controller.run_cgi_lookup(case, "405-52-1-2") is expected
    assert logged == [
        (
            case,
            {
                "lookup_type": "CGI",
                "query": "405-52-1-2",
                "status": "MATCHED",
            },
        )
    ]


def test_lookup_worker_runs_sdr_operation(monkeypatch):
    monkeypatch.setattr(
        app_controller,
        "get_direct_analysis_workspace",
        lambda: {"case_id": "DEV-WORKSPACE"},
    )
    monkeypatch.setattr(
        lookup_controller,
        "run_sdr_lookup",
        lambda case, value: {
            "status": "MATCHED",
            "record": {"mobile_number": value},
            "records": [{"mobile_number": value}],
        },
    )

    worker = LookupWorker(operation="sdr", value="9876543210")
    completed = []
    failed = []
    finished = []
    worker.completed.connect(completed.append)
    worker.failed.connect(failed.append)
    worker.finished.connect(lambda: finished.append(True))
    worker.run()

    assert failed == []
    assert finished == [True]
    assert completed[0]["operation"] == "sdr"
    assert completed[0]["result"]["status"] == "MATCHED"


def test_lookup_page_displays_sdr_and_cgi_results():
    build_application(["lookup-gui-test"])
    page = LookupPage()

    page._operation_completed(
        {
            "operation": "sdr",
            "result": {
                "status": "MATCHED",
                "records": [
                    {
                        "mobile_number": "9876543210",
                        "subscriber_name": "Test Person",
                    }
                ],
            },
        }
    )
    assert page._sdr_table.rowCount() == 1
    assert page._sdr_table.item(0, 0).text() == "9876543210"
    assert page._sdr_table.item(0, 1).text() == "Test Person"

    page._operation_completed(
        {
            "operation": "cgi",
            "result": {
                "status": "MATCHED",
                "record": {
                    "cgi": "405-52-1-2",
                    "district": "Jamui",
                },
            },
        }
    )
    assert page._cgi_table.rowCount() == 1
    assert page._cgi_table.item(0, 0).text() == "405-52-1-2"
    assert page._cgi_table.item(0, 5).text() == "Jamui"
    page.close()


def test_lookup_page_validates_master_import_file(tmp_path):
    build_application(["lookup-import-test"])
    page = LookupPage()
    page.set_import_file(tmp_path / "missing.csv")
    assert "does not exist" in page.import_validation_error()

    unsupported = tmp_path / "master.json"
    unsupported.write_text("{}", encoding="utf-8")
    page.set_import_file(unsupported)
    assert "not supported" in page.import_validation_error()

    supported = tmp_path / "master.csv"
    supported.write_text("mobile_number\n9876543210\n", encoding="utf-8")
    page.set_import_file(supported)
    assert page.import_validation_error() == ""
    page.close()


def test_main_window_uses_real_lookup_page():
    build_application(["lookup-main-window-test"])
    window = MainWindow()
    window.select_page_by_key("lookup")

    assert window.active_page_key == "lookup"
    assert isinstance(window._page_stack.currentWidget(), LookupPage)
    window.close()
