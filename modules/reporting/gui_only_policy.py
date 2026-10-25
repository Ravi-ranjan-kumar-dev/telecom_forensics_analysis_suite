"""Per-analysis execution policy. No process-wide environment mutation."""
from contextlib import contextmanager
from contextvars import ContextVar

_GUI_ONLY = ContextVar("ethicalarmor_gui_only_report", default=False)


def gui_only_report_mode() -> bool:
    return bool(_GUI_ONLY.get())


@contextmanager
def gui_only_reports():
    token = _GUI_ONLY.set(True)
    try:
        yield
    finally:
        _GUI_ONLY.reset(token)
