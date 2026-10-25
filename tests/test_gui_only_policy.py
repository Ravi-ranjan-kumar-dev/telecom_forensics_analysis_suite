from modules.reporting.gui_only_policy import gui_only_report_mode, gui_only_reports


def test_scope_restored_after_gui_analysis():
    assert not gui_only_report_mode()
    with gui_only_reports():
        assert gui_only_report_mode()
    assert not gui_only_report_mode()


def test_scope_restored_after_exception():
    try:
        with gui_only_reports():
            assert gui_only_report_mode()
            raise RuntimeError("interrupted")
    except RuntimeError:
        pass
    assert not gui_only_report_mode()
