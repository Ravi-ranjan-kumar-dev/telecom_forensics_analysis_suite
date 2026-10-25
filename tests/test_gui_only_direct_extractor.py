"""Regression: GUI-only Tower CDR must not write a temporary Excel workbook."""
import sys
import types
import pandas as pd


def test_gui_only_result_uses_direct_tables(monkeypatch):
    from modules.reporting.gui_bundle_extractor import extract_gui_sheets_from_result
    poison = types.ModuleType("modules.reporting.tower_dump_excel")
    def fail(*args, **kwargs):
        raise AssertionError("Excel generator must not run before Export click")
    poison.generate_tower_dump_excel_report = fail
    monkeypatch.setitem(sys.modules, "modules.reporting.tower_dump_excel", poison)
    raw = pd.DataFrame({"subscriber_number": ["9000000001"] * 3000})
    result = {
        "gui_export_only": True,
        "analysis": {"results": {"tower_cdr_priority_leads": pd.DataFrame({"score": [15]})}},
        "df": raw,
    }
    sheets = extract_gui_sheets_from_result(result, workflow="tower cdr dump analysis")
    assert any("Priority Leads" in key for key in sheets)
    full = [v for k,v in sheets.items() if k.startswith("Preview Loaded Data")]
    assert full and len(full[0]) == 2000
