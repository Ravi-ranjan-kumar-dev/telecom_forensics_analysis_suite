"""Background worker for existing full dump loader/search (no GUI calls)."""
from PySide6.QtCore import QObject, Signal, Slot

class FullDumpSearchWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, *, case_id, source_type, input_folder, selected_spots, include_root_files, query):
        super().__init__()
        self.case_id = case_id
        self.source_type = source_type
        self.input_folder = input_folder
        self.selected_spots = selected_spots
        self.include_root_files = include_root_files
        self.query = query

    @Slot()
    def run(self):
        try:
            if str(self.source_type).casefold() == "cdr":
                from modules.analysis.towerdump.scalable_full_search import (
                    search_verified_tower_cdr_stage,
                )
                result = search_verified_tower_cdr_stage(
                    self.case_id,
                    input_folder=self.input_folder,
                    selected_spot_folders=self.selected_spots,
                    include_root_files=self.include_root_files,
                    query=self.query,
                )
                result["full_export_request"] = {
                    "case_id": str(self.case_id),
                    "source_type": str(self.source_type),
                    "input_folder": str(self.input_folder),
                    "selected_spot_folders": list(self.selected_spots) if self.selected_spots is not None else None,
                    "include_root_files": bool(self.include_root_files),
                    "query": str(self.query),
                }
                self.completed.emit({
                    "empty": result["total_dump_records"] == 0,
                    "total": result["total_dump_records"],
                    "result": result,
                })
            elif str(self.source_type).casefold() in {"gprs", "ipdr"}:
                from modules.analysis.towerdump.verified_session_search import (
                    search_verified_tower_sessions,
                )
                result = search_verified_tower_sessions(
                    self.case_id,
                    source_type=self.source_type,
                    input_folder=self.input_folder,
                    selected_spot_folders=self.selected_spots,
                    include_root_files=self.include_root_files,
                    query=self.query,
                )
                result["full_export_request"] = {
                    "case_id": str(self.case_id),
                    "source_type": str(self.source_type),
                    "input_folder": str(self.input_folder),
                    "selected_spot_folders": list(self.selected_spots) if self.selected_spots is not None else None,
                    "include_root_files": bool(self.include_root_files),
                    "query": str(self.query),
                }
                self.completed.emit({
                    "empty": result["total_dump_records"] == 0,
                    "total": result["total_dump_records"],
                    "result": result,
                })
            else:
                raise ValueError("Unsupported Tower Dump source type")
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
