"""Generate a full Tower CDR investigator workbook only on user request."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot


class TowerExcelExportWorker(QObject):
    completed = Signal(str)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, analysis_result: dict, destination: str, *, case_id: str = "") -> None:
        super().__init__()
        self._result = analysis_result
        self._destination = Path(destination).expanduser().resolve()
        self._case_id = case_id

    @Slot()
    def run(self) -> None:
        try:
            from modules.reporting.tower_dump_excel import generate_tower_dump_excel_report
            target = self._destination
            if target.suffix.lower() != ".xlsx":
                raise ValueError("Choose an .xlsx destination")
            if not target.parent.is_dir():
                raise FileNotFoundError(f"Export directory not found: {target.parent}")
            # Generator writes its own filename into the user-selected directory.
            output = Path(generate_tower_dump_excel_report(
                self._result, output_dir=target.parent,
                case_name=self._case_id or "Tower_CDR",
            )).resolve()
            if output != target:
                os.replace(output, target)
            self.completed.emit(str(target))
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
