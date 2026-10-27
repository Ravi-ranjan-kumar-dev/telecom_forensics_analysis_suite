"""Background Tower Dump workflow worker for the desktop GUI."""

from __future__ import annotations
import os

import contextlib
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from gui.workers.text_stream import SignalTextStream
from modules.controllers.tower_dump_controller import (
    TOWER_DUMP_SOURCE_TYPES,
)


TOWER_DUMP_ANALYSIS_MODES = (
    "complete",
    "partition",
)


def _portable_report_path(
    value: object,
) -> str:
    """Return one normalized report path."""

    text = str(
        value or ""
    ).strip()

    if not text:
        return ""

    return str(
        Path(
            text
        ).expanduser().resolve(
            strict=False
        )
    )


def collect_tower_report_paths(
    result: dict[str, Any],
) -> list[str]:
    """Collect user-facing report paths from one Tower workflow result."""

    saved_files = result.get(
        "saved_files",
        {},
    )

    if not isinstance(
        saved_files,
        dict,
    ):
        saved_files = {}

    paths = [
        _portable_report_path(
            result.get(
                "excel_report"
            )
        ),
        _portable_report_path(
            result.get(
                "summary_report"
            )
        ),
        _portable_report_path(
            saved_files.get(
                "excel_workbook"
            )
        ),
        _portable_report_path(
            saved_files.get(
                "investigation_summary_all_parts"
            )
        ),
        _portable_report_path(
            saved_files.get(
                "latest_report"
            )
        ),
    ]

    return list(
        dict.fromkeys(
            path
            for path in paths
            if path
        )
    )


class TowerDumpWorker(QObject):
    """Run one complete Tower Dump workflow outside the GUI thread."""

    log = Signal(
        str
    )
    completed = Signal(
        object
    )
    failed = Signal(
        str
    )
    finished = Signal()

    def __init__(
        self,
        *,
        source_type: str,
        input_folder: str | Path,
        analysis_mode: str = "complete",
        selected_spot_folders: tuple[str, ...] | None = None,
        include_root_files: bool = True,
    ) -> None:
        super().__init__()

        normalized_source = str(
            source_type
        ).strip().casefold()

        if normalized_source not in TOWER_DUMP_SOURCE_TYPES:
            raise ValueError(
                f"Unsupported Tower Dump source type: {source_type}"
            )

        normalized_mode = str(
            analysis_mode
        ).strip().casefold()

        if normalized_mode not in TOWER_DUMP_ANALYSIS_MODES:
            raise ValueError(
                f"Unsupported Tower Dump analysis mode: {analysis_mode}"
            )

        self.source_type = normalized_source
        self.analysis_mode = normalized_mode
        self.input_folder = Path(
            input_folder
        ).expanduser().resolve()
        self.selected_spot_folders = (
            None
            if selected_spot_folders is None
            else tuple(
                str(value)
                for value in selected_spot_folders
                if str(value).strip()
            )
        )
        self.include_root_files = bool(
            include_root_files
        )

    @Slot()
    def run(
        self,
    ) -> None:
        """Execute the selected case-aware Tower Dump workflow."""

        output_stream = SignalTextStream(
            self.log.emit
        )

        try:
            from modules.controllers.app_controller import (
                get_direct_analysis_workspace,
            )
            from modules.controllers.tower_dump_controller import (
                run_complete_tower_dump_analysis,
                run_tower_dump_partition_analysis,
            )

            with contextlib.redirect_stdout(
                output_stream
            ), contextlib.redirect_stderr(
                output_stream
            ):
                case = get_direct_analysis_workspace()
                selection_kwargs = {}

                if (
                    self.selected_spot_folders is not None
                    or not self.include_root_files
                ):
                    selection_kwargs = {
                        "selected_spot_folders": (
                            self.selected_spot_folders
                        ),
                        "include_root_files": (
                            self.include_root_files
                        ),
                    }

                # Explicit request: do not export Excel during GUI Tower CDR analysis.
                if self.source_type == "cdr" and self.analysis_mode == "complete":
                    selection_kwargs["gui_only"] = True

                analysis_function = (
                    run_tower_dump_partition_analysis
                    if self.analysis_mode == "partition"
                    else run_complete_tower_dump_analysis
                )
                # Only Tower CDR complete-analysis gets deferred Excel in this patch.
                from modules.reporting.gui_only_policy import gui_only_reports
                policy = (
                    gui_only_reports()
                    if self.source_type == "cdr" and self.analysis_mode == "complete"
                    else contextlib.nullcontext()
                )
                from gui.workers.gui_first_policy import supports_gui_only
                if supports_gui_only(analysis_function) and (
                    self.analysis_mode in {"complete", "partition"}
                ):
                    selection_kwargs["gui_only"] = True
                with policy:
                    result = analysis_function(
                        case,
                        source_type=self.source_type,
                        input_folder=self.input_folder,
                        **selection_kwargs,
                    )

            output_stream.flush()

            if not isinstance(
                result,
                dict,
            ):
                raise RuntimeError(
                    "Tower Dump analysis did not complete successfully."
                )

            report_paths = collect_tower_report_paths(
                result
            )
            if not isinstance(result.get("gui_sheets"), dict) or not result.get("gui_sheets"):
                try:
                    from modules.reporting.gui_bundle_extractor import extract_gui_sheets_from_result
                    candidate_sheets = extract_gui_sheets_from_result(
                        result, workflow=f"tower {self.source_type} {self.analysis_mode}"
                    )
                    result["gui_sheets"] = {
                        k: v.head(600).copy() for k, v in candidate_sheets.items()
                        if hasattr(v, "head") and not v.empty
                    }
                except Exception:
                    result["gui_sheets"] = {}

            self.completed.emit(
                {
                    "source_type": self.source_type,
                    "analysis_mode": self.analysis_mode,
                    "input_folder": str(
                        self.input_folder
                    ),
                    "report_paths": report_paths,
                    "gui_sheets": (
                        result.get("gui_sheets", {})
                        if isinstance(result.get("gui_sheets"), dict)
                        else {}
                    ),
                    "selected_spot_folders": (
                        self.selected_spot_folders
                    ),
                    "include_root_files": (
                        self.include_root_files
                    ),
                    "result": result,
                }
            )

        except Exception as error:
            # EA_HANDLED_DIAGNOSTICS_V1
            try:
                from modules.core.diagnostic_events import record_handled_exception as _ea_record_handled_exception
                _ea_record_handled_exception()
            except Exception:
                pass
            output_stream.flush()

            self.failed.emit(
                f"{type(error).__name__}: {error}"
            )

        finally:
            self.finished.emit()
