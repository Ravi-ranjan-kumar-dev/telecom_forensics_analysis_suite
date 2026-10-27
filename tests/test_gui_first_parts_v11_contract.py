"""GUI-first v1.1 part-wise source contract checks; synthetic / no case IO."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def _source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def _function(path, name):
    tree = ast.parse(_source(path))
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    assert matches
    return next((n for n in matches if any(arg.arg == "gui_only" for arg in n.args.kwonlyargs)), matches[0])


def test_cdr_partition_gui_only_preserves_default_and_saved_backend():
    fn = _function("modules/controllers/tower_cdr_controller.py", "_run_partition_analysis")
    assert fn.args.kwonlyargs[-1].arg == "gui_only"
    assert isinstance(fn.args.kw_defaults[-1], ast.Constant) and fn.args.kw_defaults[-1].value is False
    src = ast.get_source_segment(_source("modules/controllers/tower_cdr_controller.py"), fn)
    assert src.index('saved = save_partition_run(') < src.index('if gui_only:') < src.index('generate_tower_partition_excel_report(')


def test_ipdr_parts_gui_only_skips_export_and_contains_part_tables():
    fn = _function("modules/controllers/tower_ipdr_controller.py", "run_tower_ipdr_saved_parts")
    assert fn.args.kwonlyargs[-1].arg == "gui_only"
    assert isinstance(fn.args.kw_defaults[-1], ast.Constant) and fn.args.kw_defaults[-1].value is False
    src = ast.get_source_segment(_source("modules/controllers/tower_ipdr_controller.py"), fn)
    assert src.index('if gui_only:') < src.index('export_tower_ipdr_partwise_range_report(')
    assert '"gui_sheets": sheets' in src and '"gui_export_only": True' in src


def test_front_controller_does_not_change_cli_default():
    fn = _function("modules/controllers/tower_dump_controller.py", "run_tower_dump_partition_analysis")
    assert fn.args.kwonlyargs[-1].arg == "gui_only"
    assert isinstance(fn.args.kw_defaults[-1], ast.Constant) and fn.args.kw_defaults[-1].value is False
    src = ast.get_source_segment(_source("modules/controllers/tower_dump_controller.py"), fn)
    assert src.count('**({"gui_only": True} if gui_only else {})') == 2


def test_worker_requests_partition_gui_only():
    src = _source("gui/workers/tower_dump_worker.py")
    assert 'self.analysis_mode in {"complete", "partition"}' in src


def test_export_worker_handles_both_partwise_kinds():
    src = _source("gui/workers/lazy_excel_export_worker.py")
    assert 'kind == "tower_cdr_partition"' in src
    assert 'kind == "tower_ipdr_partition"' in src
    assert 'copy2(output, target)' in src
    ast.parse(src)
