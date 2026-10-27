"""Source-contract regressions for GUI-first mode; never loads case evidence."""
from __future__ import annotations
import ast
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(path):
    return (ROOT / path).read_text(encoding='utf-8')


def _function(path, name):
    tree = ast.parse(_source(path))
    functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    assert functions, f'Missing {name} in {path}'
    # Prefer actual signature with gui_only, not a compatibility wrapper.
    return next((n for n in functions if any(a.arg == 'gui_only' for a in n.args.args + n.args.kwonlyargs)), functions[0])


def test_gui_first_supported_keyword_detection():
    from gui.workers.gui_first_policy import supports_gui_only
    def explicit(*, gui_only=False):
        return gui_only
    def flexible(**kwargs):
        return kwargs
    def strict(case, *, mode):
        return case, mode
    assert supports_gui_only(explicit)
    assert supports_gui_only(flexible)
    assert not supports_gui_only(strict)


def test_tower_ipdr_gui_only_branch_precedes_excel_writer():
    p = 'modules/controllers/tower_ipdr_controller.py'
    fn = _function(p, '_run_complete_tower_ipdr_analysis')
    assert any(a.arg == 'gui_only' for a in fn.args.kwonlyargs)
    src = _source(p)
    assert src.index('if gui_only:\n            # Curated GUI summary') < src.index('        generate_tower_ipdr_complete_excel_report(\n            case=case')
    assert '"_ea_gui_first_export_tables": complete_tables' in src


def test_tower_gprs_and_subscriber_ipdr_have_deferred_export():
    gprs = _function('modules/controllers/tower_gprs_controller.py', '_execute')
    ipdr = _function('modules/controllers/ipdr_case_controller.py', '_execute')
    assert any(a.arg == 'gui_only' for a in gprs.args.kwonlyargs)
    assert any(a.arg == 'gui_only' for a in ipdr.args.kwonlyargs)
    for filename in ('modules/controllers/tower_gprs_controller.py', 'modules/controllers/ipdr_case_controller.py'):
        src = _source(filename)
        assert 'if gui_only:\n            from modules.reporting.gui_bundle_extractor' in src
        assert '"excel_report": ""' in src


def test_gui_workers_and_exporter_use_on_demand_mode():
    for filename in ('gui/workers/cdr_worker.py', 'gui/workers/tower_dump_worker.py', 'gui/workers/ipdr_worker.py'):
        assert 'supports_gui_only' in _source(filename)
    exporter = _source('gui/workers/lazy_excel_export_worker.py')
    assert 'kind == "tower_ipdr"' in exporter
    assert 'kind == "tower_gprs"' in exporter
    assert 'self._result["_ea_gui_first_export_tables"]' in exporter


def test_legacy_gui_only_default_false():
    for filename, names in (
        ('modules/controllers/app_controller.py', ('handle_single_cdr', 'handle_multiple_cdr')),
        ('modules/controllers/tower_ipdr_controller.py', ('_run_complete_tower_ipdr_analysis',)),
        ('modules/controllers/tower_gprs_controller.py', ('_execute',)),
        ('modules/controllers/ipdr_case_controller.py', ('_execute', 'run_ipdr_case_analysis')),
    ):
        for name in names:
            node = _function(filename, name)
            args = node.args.kwonlyargs
            defaults = node.args.kw_defaults
            idx = next(i for i, x in enumerate(args) if x.arg == 'gui_only')
            assert isinstance(defaults[idx], ast.Constant) and defaults[idx].value is False
