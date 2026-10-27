"""Dedicated background worker for explicit full IMEI report exports."""
from __future__ import annotations
from PySide6.QtCore import QObject, Signal, Slot

class ImeiFullExportWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, analysis_result: dict, destination: str):
        super().__init__()
        self._result = analysis_result
        self._destination = destination

    @Slot()
    def run(self) -> None:
        try:
            from modules.controllers.imei_gui_first_export import export_imei_full_reports
            paths = export_imei_full_reports(self._result, self._destination)
            self.completed.emit(paths)
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")
        finally:
            self.finished.emit()
