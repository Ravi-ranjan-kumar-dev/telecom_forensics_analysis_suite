"""Background workers used by the desktop GUI."""

from gui.workers.cdr_worker import (
    CdrWorker,
    collect_cdr_report_paths,
)

__all__ = [
    "CdrWorker",
    "collect_cdr_report_paths",
]
