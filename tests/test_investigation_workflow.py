from __future__ import annotations
import json
from pathlib import Path
import re
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pandas as pd
import pytest
from PySide6.QtCore import Qt


@pytest.fixture
def cases(tmp_path, monkeypatch):
    from modules.cases import repository, create_case
    from modules.reporting import cdr_report_source

    monkeypatch.setattr(repository, "ACTIVE_CASES_DIR", tmp_path / "cases/active")
    monkeypatch.setattr(repository, "ARCHIVED_CASES_DIR", tmp_path / "cases/archived")
    monkeypatch.setattr(repository, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cdr_report_source, "PROJECT_ROOT", tmp_path)
    one = create_case(case_name="SYNTHETIC ONE", case_id="TEST-ONE")
    two = create_case(case_name="SYNTHETIC TWO", case_id="TEST-TWO")
    return one["case_id"], two["case_id"]


@pytest.fixture
def app():
    from gui.app import build_application

    return build_application(["investigation-test"])


def events():
    return pd.DataFrame(
        {
            "a_party": ["9000000001"] * 3,
            "b_party": ["9000000002", "9000000003", "9000000002"],
            "first_cell_id": ["405-01-1", "405-01-2", "405-01-1"],
            "first_cell_latitude": [25.5, 25.6, 25.5],
            "first_cell_longitude": [85.1, 85.2, 85.1],
            "datetime": pd.to_datetime(
                ["2026-01-01 10:00", "2026-01-01 10:05", "2026-01-01 10:10"]
            ),
            "raw_call_type": ["MOC"] * 3,
        }
    )


def test_bookmark_transaction_deduplicates_and_is_case_scoped(cases):
    from modules.cases.investigation import (
        bookmark_id,
        add_bookmarks,
        list_bookmarks,
        remove_bookmarks,
    )

    one, two = cases
    entry = dict(
        source_id="run1",
        sheet="Full CDR",
        source_row="0",
        row_data={"number": "9000000001", "optional": pd.NA},
    )
    entry["bookmark_id"] = bookmark_id(
        entry["source_id"], entry["sheet"], entry["row_data"], entry["source_row"]
    )
    assert add_bookmarks(one, [entry, entry]) == (1, 1)
    assert list_bookmarks(one)[0]["row_data"]["optional"] == ""
    assert list_bookmarks(two) == []
    remove_bookmarks(one, [entry["bookmark_id"]])
    assert list_bookmarks(one) == []


def test_bookmarks_survive_viewer_reopen_and_sort_filter(app, cases):
    from gui.widgets.data_viewer import ForensicDataViewer
    from modules.cases.investigation import list_bookmarks

    case, _ = cases
    frame = pd.DataFrame({"Name": ["two", "one"], "Value": [2, 1]}, index=[40, 80])
    viewer = ForensicDataViewer(case_id=case, source_id="run1")
    viewer.load_dataframe({"Rows": frame})
    viewer.table_view.selectRow(1)
    viewer.bookmark_btn.click()
    assert len(list_bookmarks(case)) == 1
    viewer.bookmark_btn.click()
    assert "1 already bookmarked" in viewer.bookmark_status.text()
    assert viewer._is_row_bookmarked(1)
    assert (
        viewer._current_model.data(viewer._current_model.index(1, 0), Qt.ItemDataRole.ToolTipRole)
        == "Already bookmarked in this case"
    )
    viewer._current_model.sort(1, Qt.SortOrder.AscendingOrder)
    viewer._apply_filter("one")
    viewer.table_view.selectRow(0)
    viewer.bookmark_btn.click()
    assert len(list_bookmarks(case)) == 1
    other = ForensicDataViewer(case_id=case, source_id="run1")
    other.load_dataframe({"Rows": frame})
    assert other.view_bookmarks_btn.text() == "View Bookmarks (1)"
    assert other._is_row_bookmarked(1)
    viewer.close()
    other.close()


def test_global_search_keeps_bookmark_source_identity(app, cases):
    from gui.widgets.data_viewer import ForensicDataViewer
    from modules.cases.investigation import list_bookmarks

    case, _ = cases
    frame = pd.DataFrame({"Name": ["unmatched", "match-me"], "Value": [2, 1]}, index=[40, 80])
    viewer = ForensicDataViewer(case_id=case, source_id="run1")
    viewer.load_dataframe({"Rows": frame})
    viewer.table_view.selectRow(1)
    viewer.bookmark_btn.click()
    viewer.search_input.setText("match-me")
    viewer._search_all_sheets()
    viewer.table_view.selectRow(0)
    viewer.bookmark_btn.click()
    assert len(list_bookmarks(case)) == 1
    viewer.close()


def test_identical_rows_with_different_source_positions_are_distinct(app, cases):
    from gui.widgets.data_viewer import ForensicDataViewer
    from modules.cases.investigation import list_bookmarks

    viewer = ForensicDataViewer(case_id=cases[0], source_id="run1")
    viewer.load_dataframe({"Rows": pd.DataFrame({"Name": ["same", "same"]})})
    viewer.table_view.selectRow(0)
    viewer.bookmark_btn.click()
    viewer.table_view.selectRow(1)
    viewer.bookmark_btn.click()
    assert len(list_bookmarks(cases[0])) == 2
    viewer.close()


def test_case_number_index_replaces_same_run_and_combines_runs(cases):
    from modules.cases.investigation import index_case_numbers, numbers_frame
    from modules.cases import register_target

    one, two = cases
    register_target(one, target_type="MSISDN", target_value="9000000099")
    index_case_numbers(one, "run1", [("Full", events())])
    index_case_numbers(one, "run1", [("Full", events())])
    frame = numbers_frame(one).set_index("Number")
    assert set(frame.index) == {"9000000001", "9000000002", "9000000003", "9000000099"}
    assert frame.loc["9000000002", "Analyzed Appearances"] == 2
    assert numbers_frame(two).empty
    index_case_numbers(one, "run2", [("Full", events().iloc[:1])])
    frame = numbers_frame(one).set_index("Number")
    assert frame.loc["9000000002", "Analysis Runs"] == 2


def test_backfills_old_case_sources_without_cross_case_files(cases, tmp_path):
    from modules.reporting.cdr_report_source import create_cdr_source_run
    from modules.cases.investigation import backfill_saved_numbers, numbers_frame

    one, two = cases
    manifest = create_cdr_source_run(
        case_id=one, analysis_run_id="run-old", target_frames={"9000000001": events()}
    )
    assert backfill_saved_numbers(one) == []
    assert len(numbers_frame(one)) == 3
    assert backfill_saved_numbers(one) == []
    assert numbers_frame(two).empty
    # A forged reference into another case must be rejected, not read.
    source = tmp_path / manifest["manifest_path"]
    payload = json.loads(source.read_text())
    payload["analysis_run_id"] = "forged"
    payload["datasets"][0]["path"] = "cases/active/TEST-TWO/outside.parquet"
    (tmp_path / payload["datasets"][0]["path"]).write_bytes(b"not parquet")
    source.write_text(json.dumps(payload))
    assert "outside this case" in backfill_saved_numbers(one)[0]


def test_gui_maps_do_not_require_an_excel_report(tmp_path):
    from modules.reporting.cdr_gui_artifacts import generate_gui_maps

    maps, routes = generate_gui_maps({"Full CDR (9000000001)": events()}, tmp_path / "previews")
    assert len(maps) == len(routes) == 1
    assert Path(maps[0]).is_file() and Path(routes[0]).is_file()
    assert not list(tmp_path.rglob("*.xlsx"))
    route = Path(routes[0]).read_text()
    assert "9000000001" in route and "405-01-2" in route and '"route": true' in route


def test_gui_completion_sets_buttons_and_opens_the_current_maps(app, cases, tmp_path, monkeypatch):
    from gui.pages import cdr_page
    from gui.dialogs import fullscreen_results_window

    monkeypatch.setattr(
        fullscreen_results_window, "open_fullscreen_results_window", lambda *a, **kw: None
    )
    opened = []

    class Dialog:
        def __init__(self, path, *a, **kw):
            opened.append(Path(path))

        def exec(self):
            pass

    monkeypatch.setattr(cdr_page, "ContactMapDialog", Dialog)
    paths = []
    for name in ["contact.html", "route.html"]:
        p = tmp_path / name
        p.write_text("<html>current</html>")
        paths.append(str(p))
    page = cdr_page.CdrPage()
    page._analysis_completed(
        dict(
            case_id=cases[0],
            analysis_run_id="run1",
            gui_sheets={"Full CDR": events()},
            report_paths=[],
            map_paths=[paths[0]],
            route_paths=[paths[1]],
        )
    )
    assert page._open_map_button.isEnabled() and page._open_route_button.isEnabled()
    page._open_map_button.click()
    page._open_route_button.click()
    assert opened == list(map(Path, paths))
    page.set_case_id(cases[1])
    assert not page._open_map_button.isEnabled()
    page.close()


def test_worker_emits_current_sheets_maps_and_pinned_case(app, cases, tmp_path, monkeypatch):
    from gui.workers.cdr_worker import CdrWorker
    from modules.controllers import app_controller
    from modules.cases.investigation import numbers_frame

    monkeypatch.setattr(
        app_controller,
        "handle_single_cdr",
        lambda case, **kw: dict(gui_sheets={"Full CDR": events()}, analysis_run_id="run-worker"),
    )
    worker = CdrWorker(mode="single", input_folder=tmp_path, case_id=cases[0])
    outputs = []
    errors = []
    worker.completed.connect(outputs.append)
    worker.failed.connect(errors.append)
    worker.run()
    assert not errors
    result = outputs[0]
    assert result["case_id"] == cases[0] and result["report_paths"] == []
    assert result["gui_sheets"] and result["map_paths"] and result["route_paths"]
    assert len(numbers_frame(cases[0])) == 3
    assert numbers_frame(cases[1]).empty


def test_lists_search_sorted_remove_and_export_source(app, cases):
    from modules.cases.investigation import (
        add_bookmarks,
        bookmark_id,
        index_case_numbers,
        list_bookmarks,
    )
    from gui.widgets.investigation_dialog import InvestigationDialog

    case = cases[0]
    entry = dict(
        source_id="run", sheet="Full CDR", source_row="1", row_data={"Number": "9000000002"}
    )
    entry["bookmark_id"] = bookmark_id("run", "Full CDR", entry["row_data"], "1")
    add_bookmarks(case, [entry])
    index_case_numbers(case, "run", [("Full", events())])
    dialog = InvestigationDialog(case, initial="numbers")
    dialog.search.setText("9000000002")
    assert dialog.models["numbers"].rowCount() == 1
    dialog.tabs.setCurrentIndex(0)
    dialog.tables["bookmarks"].selectRow(0)
    dialog.remove_btn.click()
    assert list_bookmarks(case) == []
    dialog.close()


def test_no_stale_global_sheets_on_empty_completion(app, monkeypatch):
    from gui.pages.cdr_page import CdrPage
    from modules.reporting.gui_result_store import store_gui_sheets
    from gui.dialogs import fullscreen_results_window

    store_gui_sheets({"Old": events()}, workflow="cdr")
    opened = []
    monkeypatch.setattr(
        fullscreen_results_window,
        "open_fullscreen_results_window",
        lambda *a, **kw: opened.append(kw),
    )
    page = CdrPage()
    page._analysis_completed({})
    assert page._result_sheets == {} and opened == []
    page.close()


def _drain_jobs(app, viewer, seconds=12):
    import time

    deadline = time.monotonic() + seconds
    while (viewer._export_jobs or not viewer._dialogs) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert not viewer._export_jobs and viewer._dialogs


def test_case_number_button_opens_searchable_dialog(app, cases):
    from gui.widgets.data_viewer import ForensicDataViewer

    viewer = ForensicDataViewer(case_id=cases[0], source_id="run-button")
    viewer.load_dataframe({"Full CDR": events()})
    viewer.case_numbers_btn.click()
    _drain_jobs(app, viewer)
    dialog = viewer._dialogs[0]
    assert dialog.case_id == cases[0] and dialog.tabs.currentIndex() == 1
    assert dialog.models["numbers"].rowCount() == 3
    dialog.close()
    app.processEvents()
    viewer.close()


def test_bookmark_list_export_and_copy_use_filtered_rows(app, cases, tmp_path, monkeypatch):
    from gui.widgets.investigation_dialog import InvestigationDialog
    from gui.widgets import investigation_dialog
    from modules.cases.investigation import index_case_numbers

    index_case_numbers(cases[0], "run", [("Full", events())])
    dialog = InvestigationDialog(cases[0], initial="numbers")
    dialog.search.setText("9000000002")
    path = tmp_path / "selected.csv"
    monkeypatch.setattr(
        investigation_dialog.QFileDialog, "getSaveFileName", lambda *a, **kw: (str(path), "CSV")
    )
    dialog.export_btn.click()
    frame = pd.read_csv(path, dtype=str)
    assert frame["Number"].tolist() == ["9000000002"]
    dialog.tables["numbers"].selectRow(0)
    dialog.copy_btn.click()
    assert "9000000002" in app.clipboard().text() and "9000000003" not in app.clipboard().text()
    app.clipboard().clear()
    dialog.close()


def test_case_details_can_open_lists_without_analysis(app, cases):
    from gui.pages.case_details_page import CaseDetailsPage

    page = CaseDetailsPage(loader=lambda: {"case": {"case_id": cases[0]}, "audit": {"valid": True}})
    page._numbers_button.click()
    _drain_jobs(app, page._list_viewer)
    assert page._list_viewer._dialogs[0].case_id == cases[0]
    page._list_viewer._dialogs[0].close()
    app.processEvents()
    page.close()


def test_archived_case_bookmarks_are_readable_but_not_editable(cases):
    from modules.cases.investigation import (
        add_bookmarks,
        bookmark_id,
        list_bookmarks,
        remove_bookmarks,
    )
    from modules.cases import archive_case, ArchivedCaseReadOnlyError

    entry = dict(
        source_id="run", sheet="Full CDR", source_row="1", row_data={"Number": "9000000002"}
    )
    entry["bookmark_id"] = bookmark_id("run", "Full CDR", entry["row_data"], "1")
    add_bookmarks(cases[0], [entry])
    archive_case(cases[0])
    assert len(list_bookmarks(cases[0])) == 1
    with pytest.raises(ArchivedCaseReadOnlyError):
        remove_bookmarks(cases[0], [entry["bookmark_id"]])


def test_all_case_number_scope_preserves_case_identity(app, cases):
    from modules.cases.investigation import index_case_numbers, all_case_numbers_frame
    from gui.widgets.investigation_dialog import InvestigationDialog

    index_case_numbers(cases[0], "run", [("Full", events())])
    index_case_numbers(cases[1], "run", [("Full", events().iloc[:1])])
    frame, errors = all_case_numbers_frame()
    assert not errors and set(frame["Case ID"]) == set(cases)
    assert len(frame[frame["Number"] == "9000000002"]) == 2
    dialog = InvestigationDialog(cases[0], initial="numbers")
    dialog.scope.setCurrentIndex(1)
    import time

    deadline = time.monotonic() + 12
    while dialog._jobs and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert not dialog._jobs
    assert set(dialog.models["numbers"]._frame["Case ID"]) == set(cases)
    dialog.close()


def test_summary_copies_and_truncated_sources_are_not_number_events():
    from modules.reporting.cdr_gui_artifacts import event_frames

    full = events()
    truncated = events()
    truncated.attrs["source_truncated"] = True
    combined = events()
    combined.attrs["row_level_source"] = True
    sources = event_frames(
        {
            "Full CDR one": full,
            "Full Loaded Data": combined,
            "Full CDR preview": truncated,
            "Contact Summary": full,
        }
    )
    assert len(sources) == 1 and sources[0][0] == "Full Loaded Data"
