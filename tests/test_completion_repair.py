from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from modules.analysis.cdr.activity import analyze_activity
from modules.analysis.cdr.summary import cdr_summary
from modules.reporting import cdr_compact_excel as reports


def test_missing_duration_does_not_crash_summary_or_activity():
    data = pd.DataFrame({"b_party": ["9876543210"], "call_type": ["outgoing"]})
    original = data.copy(deep=True)
    assert cdr_summary(data)["Accumulated Airtime Duration (Sec)"] == 0
    activity = analyze_activity(data).set_index("Metric")["Value"]
    assert activity["Total Duration (Sec)"] == 0
    pd.testing.assert_frame_equal(data, original)


def test_health_distinguishes_missing_status_from_success_and_reports_failures():
    assert "Unverified" in reports._analysis_health({}).iloc[0]["Result"]
    bundle = {"status": pd.DataFrame([
        {"Status": "COMPLETED", "Result Key": "contacts"},
        {"Status": "FAILED", "Result Key": "movement", "Error": "Invalid timestamp"},
        {"Status": "SKIPPED", "Result Key": "location"},
    ])}
    health = reports._analysis_health(bundle).set_index("Check")["Result"]
    assert str(health["Analysis coverage"]).startswith("Partial")
    assert health["Failed functions"] == 1
    assert "Invalid timestamp" not in str(health.to_dict())


def test_generated_report_exposes_quality_and_incomplete_analysis(tmp_path: Path):
    source = pd.DataFrame({
        "a_party": ["9876543210"] * 3,
        "b_party": ["9876543211"] * 3,
        "call_type": ["outgoing"] * 3,
        "call_duration": [30, "broken", -5],
        "datetime": [pd.Timestamp("2026-07-01 12:00"), pd.NaT, pd.NaT],
        "first_cell_id": ["405-01-12345", "", ""],
    })
    bundle = {"results": {}, "status": pd.DataFrame([
        {"Status": "FAILED", "Result Key": "movement", "Error": "Synthetic test failure"},
    ]), "errors": {"movement": "Synthetic test failure"}}
    prepared = reports.detailed._prepare_dataframe(source, "9876543210")
    quality = reports._quality_summary(prepared, {}, original_data=source).set_index("Quality Check")["Value"]
    assert quality["Rows with missing or invalid timestamp"] == 2
    assert quality["Rows with missing or invalid duration"] == 2
    path = reports.generate_single_cdr_compact_report(source, "9876543210", analysis_bundle=bundle, output_dir=tmp_path)
    assert path
    workbook = load_workbook(path)
    text = "\n".join(str(c.value) for row in workbook.worksheets[0] for c in row if c.value is not None)
    assert "ANALYSIS COMPLETENESS" in text
    assert "Partial" in text
    assert "DATA QUALITY" in text
    assert "Synthetic test failure" not in text
    assert "Recorded analysis warnings" in text
    workbook.close()


def test_map_fallback_keeps_dialog_usable(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QLabel
    from gui.widgets import contact_map_dialog as maps
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(maps, "QWebEngineView", None)
    source = tmp_path / "map.html"
    source.write_text("<html><body>Test map</body></html>")
    dialog = maps.ContactMapDialog(source)
    assert isinstance(dialog._view, QLabel)
    assert "Open in Browser" in dialog._view.text()
    assert dialog.map_path == source
    dialog.close()


def test_map_only_completion_updates_paths_even_with_cached_tables(tmp_path):
    from gui.app import build_application
    from gui.pages.cdr_page import CdrPage
    from modules.reporting.gui_result_store import store_gui_sheets
    app = build_application(["repair-test"])
    store_gui_sheets({"Previous run": pd.DataFrame({"value": [1]})}, workflow="cdr")
    path = tmp_path / "current_map.html"
    path.write_text("<html></html>")
    page = CdrPage()
    page._analysis_completed({"report_paths": [], "map_paths": [str(path)]})
    assert page.map_paths == (str(path),)
    page.close()
