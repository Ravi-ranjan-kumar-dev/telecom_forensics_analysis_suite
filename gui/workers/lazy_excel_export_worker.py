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
            # EA_GUI_FIRST_EXPORT_V1: choose the matching report generator.
            kind = str(self._result.get("_ea_gui_first_export_kind") or "")
            if kind == "tower_ipdr":
                from datetime import datetime
                from modules.reporting.tower_ipdr_excel import generate_tower_ipdr_complete_excel_report
                output = Path(generate_tower_ipdr_complete_excel_report(
                    case=self._result["_ea_gui_first_export_case"],
                    report_path=target,
                    tables=self._result["_ea_gui_first_export_tables"],
                    generated_at=datetime.now().isoformat(timespec="seconds"),
                )).resolve()
            elif kind == "tower_cdr_partition":
                from modules.reporting.tower_partition_excel import generate_tower_partition_excel_report
                output = Path(generate_tower_partition_excel_report(
                    self._result,
                    case=self._result["_ea_gui_first_export_case"],
                    sightings=self._result["_ea_gui_first_export_sightings"],
                    output_dir=target.parent,
                    input_folder=self._result["_ea_gui_first_export_input_folder"],
                    saved=self._result["_ea_gui_first_export_saved"],
                )).resolve()
            elif kind == "tower_ipdr_partition":
                from modules.staging.tower_ipdr_staging import export_tower_ipdr_partwise_range_report
                manifest = export_tower_ipdr_partwise_range_report(
                    self._result["_ea_gui_first_export_case_id"],
                    self._result["_ea_gui_first_export_selected_parts"],
                    comparison_parts=self._result["_ea_gui_first_export_comparison_parts"],
                    precomputed_results=self._result["_ea_gui_first_export_results_by_part"],
                    lead_limit=50,
                    max_leads_in_text=20,
                )
                saved_files = manifest.get("saved_files", {})
                output = Path(saved_files.get("excel_workbook") or "").expanduser().resolve()
                if not output.is_file() or output.suffix.lower() != ".xlsx":
                    raise RuntimeError("Part-wise Tower IPDR exporter produced no valid Excel workbook")
            elif kind == "tower_gprs":
                from modules.reporting.tower_gprs_excel import generate_tower_gprs_excel_report
                output = Path(generate_tower_gprs_excel_report(
                    case=self._result["_ea_gui_first_export_case"],
                    load_result=self._result["_ea_gui_first_export_load"],
                    analysis=self._result["_ea_gui_first_export_analysis"],
                    partition=self._result["_ea_gui_first_export_partition"],
                    output_dir=target.parent,
                    saved=self._result["_ea_gui_first_export_saved"],
                )).resolve()
            else:
                # Tower CDR: generator chooses its own filename.
                output = Path(generate_tower_dump_excel_report(
                self._result, output_dir=target.parent,
                case_name=self._case_id or "Tower_CDR",
                )).resolve()
            if output != target:
                if kind == "tower_ipdr_partition":
                    # The part-wise manifest points at its generated case workbook.
                    # Preserve that original so report history/provenance never breaks.
                    from shutil import copy2
                    copy2(output, target)
                else:
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
