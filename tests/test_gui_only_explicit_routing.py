"""Fast regression tests for GUI-only report path: no large datasets required."""
import inspect


def test_controller_accepts_explicit_gui_only():
    from modules.controllers.tower_cdr_controller import _run_complete_analysis
    from modules.controllers.tower_dump_controller import _ORIG_RUN_COMPLETE_TOWER_DUMP_ANALYSIS
    assert 'gui_only' in inspect.signature(_run_complete_analysis).parameters
    assert 'gui_only' in inspect.signature(_ORIG_RUN_COMPLETE_TOWER_DUMP_ANALYSIS).parameters


def test_worker_explicit_flag_and_preview_limit():
    import inspect
    from gui.workers.tower_dump_worker import TowerDumpWorker
    from modules.reporting.gui_bundle_extractor import extract_gui_sheets_from_result
    worker = inspect.getsource(TowerDumpWorker.run)
    assert 'selection_kwargs["gui_only"] = True' in worker
    source = inspect.getsource(extract_gui_sheets_from_result)
    assert 'kwargs["max_rows"] = min(' in source
    assert 'not result.get("gui_export_only")' in source
