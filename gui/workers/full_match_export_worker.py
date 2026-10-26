"""Background exporter for all SQL-matched rows (CSV/XLSX)."""
from __future__ import annotations
from PySide6.QtCore import QObject, Signal, Slot


class FullMatchExportWorker(QObject):
    progress = Signal(int)
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, request: dict, destination: str):
        super().__init__()
        self.request = dict(request)
        self.destination = str(destination)

    @Slot()
    def run(self):
        try:
            from modules.analysis.towerdump.full_match_export import export_all_matches
            result = export_all_matches(
                self.request, self.destination, progress=self.progress.emit,
            )
            self.completed.emit(result)
        except Exception as exc:
            # EA_HANDLED_DIAGNOSTICS_V1
            try:
                from modules.core.diagnostic_events import record_handled_exception as _ea_record_handled_exception
                _ea_record_handled_exception()
            except Exception:
                pass
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.finished.emit()
