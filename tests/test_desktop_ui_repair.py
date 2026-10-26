from __future__ import annotations

import hashlib
import json
from pathlib import Path
import urllib.request
import urllib.error

import pandas as pd
from PySide6.QtCore import Qt

from modules.reporting import forensic_intelligence_suite as suite


def _rows(count=4):
    return pd.DataFrame({
        "a_party": ["9000000001"] * count,
        "b_party": ["9000000002"] * count,
        "raw_call_type": ["MOC"] * count,
        "call_type": ["outgoing"] * count,
        "call_duration": [10] * count,
        "datetime": pd.date_range("2026-01-01", periods=count, freq="min"),
        "tower_address": ["405-01-12345"] * count,
        "first_cell_id": ["405-01-12345"] * count,
    })


def test_hash_covers_rows_after_old_500_row_limit_and_sections():
    df = _rows(520)
    first = suite.compute_sheets_sha256({"Full CDR Data": df})
    df.loc[519, "call_duration"] = 999
    assert first != suite.compute_sheets_sha256({"Full CDR Data": df})
    parent = pd.DataFrame({"summary": [1]})
    parent.attrs["sections"] = {"Detail": df}
    first = suite.compute_sheets_sha256({"Report": parent})
    df.loc[518, "call_duration"] = 333
    assert first != suite.compute_sheets_sha256({"Report": parent})


def test_graph_counts_all_rows_and_never_uses_arbitrary_columns():
    full = _rows(3500)
    full.loc[3499, "b_party"] = "9000000003"
    data = suite.build_call_links({"Executive summary": pd.DataFrame({"Metric": ["Records"], "Value": [3500]}), "Full CDR Data": full})
    assert sum(e["events"] for e in data["edges"]) == 3500
    assert len(data["edges"]) == 2
    assert suite.build_call_links({"Summary": pd.DataFrame({"Metric": ["Records"], "Value": [2]})})["edges"] == []


def test_contact_summary_uses_event_weights_without_counting_other_sheets():
    frame = pd.DataFrame({"Target": ["A", "A"], "Other Party": ["B", "C"], "Total Calls": [20, 30]})
    data = suite.build_call_links({"Full Contact Summary": frame, "Copy": frame})
    assert sum(e["events"] for e in data["edges"]) == 50


def test_brief_handles_nullable_columns_and_verifies_exact_artifact(tmp_path):
    frame = pd.DataFrame({"Duration": pd.Series([1, pd.NA], dtype="Int64"), "Text": ["</script><img src=x onerror=alert(1)>", None]})
    path, digest = suite.export_court_forensic_brief_html({"Test": frame}, tmp_path / "new" / "brief.html")
    assert digest == suite.compute_sheets_sha256({"Test": frame})
    manifest = json.loads(path.with_suffix(".html.manifest.json").read_text())
    assert manifest["html_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert manifest["html_sha256"] in path.with_suffix(".html.sha256").read_text()
    assert "<img src=x" not in path.read_text()
    assert "chain-of-custody or legal admissibility certificate" in path.read_text()


def test_map_includes_both_coordinate_pairs_and_bundles_leaflet(tmp_path):
    df = pd.DataFrame({"Most Used Latitude": [25.5], "Most Used Longitude": [85.1], "Most Used Target CGI": ["405-01-1"], "Last Interaction Latitude": [25.6], "Last Interaction Longitude": [85.2], "Last Interaction CGI": ["405-01-2"]})
    path, count = suite.export_interactive_map_html({"Contact summary": df}, tmp_path / "map.html")
    text = path.read_text()
    assert count == 2
    assert 'src="https://unpkg.com' not in text
    assert "Leaflet 1.9.4" in text
    assert "Load street basemap (internet)" in text
    assert 'href="leaflet.css"' not in text  # CSS is embedded, not a file request.


def test_full_cdr_view_uses_raw_type_and_omits_redundant_address():
    from modules.utils.cdr_column_sanitizer import sanitize_cdr_sheet_columns
    original = _rows()
    original.loc[0, "raw_call_type"] = "MiXeD-Operator-Type"
    original.loc[1, "raw_call_type"] = ""
    original.attrs["preserve_excel_columns"] = True
    result = sanitize_cdr_sheet_columns(original, "Full CDR Data")
    assert "tower_address" not in result
    assert result.loc[0, "call_type"] == "MiXeD-Operator-Type"
    assert result.loc[1, "call_type"] == ""
    assert original.loc[0, "call_type"] == "outgoing"


def test_report_call_type_uses_raw_value():
    from modules.reporting import single_cdr_excel
    frame = single_cdr_excel._prepare_dataframe(_rows(), "9000000001")
    assert single_cdr_excel._call_type_display(frame).tolist() == ["MOC"] * 4


def test_sort_filter_and_bookmark_match_visible_rows():
    from gui.app import build_application
    from gui.widgets.data_viewer import ForensicDataViewer
    app = build_application(["desktop-test"])
    widget = ForensicDataViewer()
    widget.load_dataframe({"Results": pd.DataFrame({"Name": ["two", "ten", "one"], "Count": [2, 10, 1]})})
    widget._current_model.sort(1, Qt.SortOrder.AscendingOrder)
    assert widget._current_df["Count"].tolist() == [1, 2, 10]
    widget.table_view.selectRow(0)
    widget._bookmark_selected_rows()
    assert widget._bookmarked_rows[-1]["Name"] == "one"
    widget.filter_column.setCurrentText("Name")
    widget._apply_filter("ten")
    assert widget._current_df["Name"].tolist() == ["ten"]
    widget.close()


def test_preview_serves_only_registered_html(tmp_path):
    from gui.utils.local_preview import preview_url
    file = tmp_path / "map.html"
    file.write_text("<html>verified</html>")
    url = preview_url(file)
    with urllib.request.urlopen(url, timeout=5) as response:
        assert response.read() == b"<html>verified</html>"
        assert response.headers["Cache-Control"] == "no-store"
    import pytest
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(url + "/../private.txt", timeout=5)


def test_diagnostics_does_not_create_missing_stores(tmp_path, monkeypatch):
    from modules.database import diagnostics as diag
    monkeypatch.setattr(diag, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(diag, "master_duckdb_path", lambda: tmp_path / "master.duckdb")
    monkeypatch.setattr(diag, "get_db_path", lambda: tmp_path / "lookup.db")
    result = diag.database_diagnostics()
    assert all(r["status"] == "NOT INITIALIZED" for r in result["stores"])
    assert list(tmp_path.iterdir()) == []


def test_portable_data_root_and_master_override(tmp_path, monkeypatch):
    from modules.core import paths
    from modules.database.db_paths import master_duckdb_path
    monkeypatch.setenv("ETHICALARMOR_DATA_DIR", str(tmp_path / "data"))
    assert paths.application_data_root() == tmp_path / "data"
    monkeypatch.setenv("ETHICALARMOR_MASTER_DB", str(tmp_path / "existing.duckdb"))
    assert master_duckdb_path() == tmp_path / "existing.duckdb"


def _drain_exports(app, widget):
    import time
    from PySide6.QtTest import QTest
    deadline = time.monotonic() + 5
    while widget._export_jobs and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(10)
    assert not widget._export_jobs


def test_court_brief_button_runs_export_and_completes_on_gui_thread(tmp_path, monkeypatch):
    from gui.app import build_application
    from gui.widgets.data_viewer import ForensicDataViewer, QFileDialog
    from gui.utils import local_preview
    from PySide6.QtCore import QThread
    app = build_application(["desktop-export-test"])
    widget = ForensicDataViewer()
    widget.load_dataframe({"Full CDR Data": _rows()})
    path = tmp_path / "court.html"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(path), "HTML"))
    calls = []
    monkeypatch.setattr(local_preview, "open_preview", lambda file: calls.append((file, QThread.currentThread() == app.thread())))
    widget._open_court_forensic_brief()
    _drain_exports(app, widget)
    assert calls == [(path, True)]
    assert path.is_file()
    assert path.with_suffix(".html.sha256").is_file()
    assert widget.court_brief_btn.isEnabled()
    widget.close()


def test_frozen_platforms_choose_writable_user_data(monkeypatch):
    import sys
    from modules.core.paths import application_data_root
    monkeypatch.delenv("ETHICALARMOR_DATA_DIR", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", "/tmp/ea-windows-user")
    monkeypatch.setattr(sys, "platform", "win32")
    assert application_data_root() == Path("/tmp/ea-windows-user/EthicalArmor")
    monkeypatch.setattr(sys, "platform", "darwin")
    assert application_data_root() == Path.home() / "Library/Application Support/EthicalArmor"
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/ea-linux-user")
    monkeypatch.setattr(sys, "platform", "linux")
    assert application_data_root() == Path("/tmp/ea-linux-user/EthicalArmor")
