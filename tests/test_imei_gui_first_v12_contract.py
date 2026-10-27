"""IMEI GUI-first, synthetic no-evidence regression contracts."""
from __future__ import annotations
import ast
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def source(rel):
    return (ROOT / rel).read_text(encoding='utf-8')

def test_imei_gui_only_thread_local_and_legacy_default():
    s = source('modules/controllers/imei_device_controller.py')
    assert '_EA_IMEI_GUI_ONLY.set(gui_only)' in s
    assert '_EA_IMEI_GUI_ONLY.reset(token)' in s
    assert 'kwargs.pop("gui_only", False)' in s
    for f in ('_run_auto_single_imei_source', '_run_auto_single_imei_unified'):
        body = next(n for n in ast.parse(s).body if isinstance(n, ast.FunctionDef) and n.name == f)
        assert '_EA_IMEI_GUI_ONLY.get()' in ast.get_source_segment(s, body)

def test_common_reports_deferred():
    s = source('modules/controllers/imei_device_controller.py')
    assert 'common_report = generate_imei_common_report(' in s
    assert 'common_report = generate_imei_ipdr_common_report(' in s
    assert s.count('if not _EA_IMEI_GUI_ONLY.get() else None') == 2

def test_viewer_preview_is_not_full_export():
    from modules.controllers.imei_gui_first_export import build_imei_viewer_sheets
    original = pd.DataFrame({'x': range(801)})
    sheets = build_imei_viewer_sheets({'single_results': [{'identifier':'123456789012345','analysis':{'overall_status':'FOUND','cross_source_timeline':original}, 'input_records':801,'output_records':801}]})
    assert len(sheets['IMEI Analysis Summary']) == 1
    assert len(next(v for k,v in sheets.items() if 'Timeline' in k)) == 600
    assert len(original) == 801

def test_worker_opt_in_and_export_action_present():
    assert 'gui_only=True' in source('gui/workers/imei_worker.py')
    assert 'Export Full IMEI Reports' in source('gui/pages/imei_page.py')
    assert '_latest_imei_payload' in source('gui/pages/imei_page.py')
    assert 'export_imei_full_reports(' in source('gui/workers/imei_full_export_worker.py')

def test_no_report_generated_without_explicit_export(tmp_path):
    from modules.controllers.imei_gui_first_export import build_imei_viewer_sheets
    value = {'mode':'cdr','single_results':[{'identifier':'123456789012345','analysis':{'overall_status':'FOUND','cross_source_timeline':pd.DataFrame({'x':[1]})}}]}
    assert build_imei_viewer_sheets(value)
    assert list(tmp_path.iterdir()) == []


def test_on_demand_report_export_does_not_overwrite(tmp_path, monkeypatch):
    import sys, types
    from modules.controllers.imei_gui_first_export import export_imei_full_reports
    reports = []
    def fake_report(*, case, analysis, output_dir):
        p = Path(output_dir) / f"IMEI_{analysis['requested_imei']}.xlsx"
        p.write_bytes(b"synthetic-report")
        return p
    reporting = types.ModuleType('modules.reporting')
    reporting.generate_imei_device_report = fake_report
    reporting.generate_imei_common_report = lambda **kw: None
    reporting.generate_imei_ipdr_common_report = lambda **kw: None
    cases = types.ModuleType('modules.cases')
    cases.register_report = lambda *a, **kw: reports.append((a, kw))
    monkeypatch.setitem(sys.modules, 'modules.reporting', reporting)
    monkeypatch.setitem(sys.modules, 'modules.cases', cases)
    value = {'mode':'gprs','_ea_imei_export_mode':'gprs', '_ea_imei_export_case':{'case_id':'SYNTHETIC'},
             'single_results':[{'identifier':'123456789012345','analysis':{'overall_status':'FOUND','requested_imei':'123456789012345'}}]}
    assert list(tmp_path.iterdir()) == []
    result = export_imei_full_reports(value, tmp_path)
    assert len(result) == 1
    assert Path(result[0]).read_bytes() == b'synthetic-report'
    assert len(reports) == 1
    import pytest
    with pytest.raises(FileExistsError):
        export_imei_full_reports(value, tmp_path)
    assert Path(result[0]).read_bytes() == b'synthetic-report'
    assert len(reports) == 1
