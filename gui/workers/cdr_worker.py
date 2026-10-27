"""Background CDR workflow worker for the desktop GUI."""

from __future__ import annotations
import os

import contextlib
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from gui.workers.text_stream import SignalTextStream


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


def collect_cdr_report_paths(
    mode: str,
    result: dict[str, Any],
) -> list[str]:
    """Collect generated report paths from one CDR workflow result."""

    paths: list[str] = []

    if mode == "single":
        paths.append(
            _portable_report_path(
                result.get(
                    "excel"
                )
            )
        )

    elif mode == "multiple":
        paths.append(
            _portable_report_path(
                result.get(
                    "multiple_common_report"
                )
            )
        )

        individual = result.get(
            "individual_reports",
            {},
        )

        if isinstance(
            individual,
            dict,
        ):
            for item in individual.values():
                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                paths.append(
                    _portable_report_path(
                        item.get(
                            "excel"
                        )
                    )
                )

    else:
        raise ValueError(
            f"Unsupported CDR mode: {mode}"
        )

    return list(
        dict.fromkeys(
            path
            for path in paths
            if path
        )
    )


def collect_cdr_map_paths(
    report_paths: list[str] | tuple[str, ...],
) -> list[str]:
    """Collect existing contact map sidecars for generated reports."""

    from modules.reporting.cdr_contact_map import (
        contact_map_path,
    )

    paths = []

    for report_path in report_paths:
        text = str(
            report_path
            or ""
        ).strip()

        if not text:
            continue

        candidate = contact_map_path(
            text
        )

        if candidate.is_file():
            paths.append(
                str(
                    candidate
                )
            )

    return list(
        dict.fromkeys(
            paths
        )
    )


def collect_cdr_route_paths(
    report_paths: list[str] | tuple[str, ...],
) -> list[str]:
    """Collect existing movement-route sidecars for generated reports."""

    from modules.reporting.cdr_movement_route import (
        movement_route_path,
    )

    paths = []

    for report_path in report_paths:
        text = str(
            report_path
            or ""
        ).strip()

        if not text:
            continue

        candidate = movement_route_path(
            text
        )

        if candidate.is_file():
            paths.append(
                str(
                    candidate
                )
            )

    return list(
        dict.fromkeys(
            paths
        )
    )


class CdrWorker(QObject):
    """Run one CDR workflow outside the GUI thread."""

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
        mode: str,
        input_folder: str | Path,
        generate_individual_reports: bool = False,
        case_id: str | None = None,
    ) -> None:
        super().__init__()

        normalized_mode = str(
            mode
        ).strip().casefold()

        if normalized_mode not in {
            "single",
            "multiple",
        }:
            raise ValueError(
                f"Unsupported CDR mode: {mode}"
            )

        self.case_id = case_id
        self.mode = normalized_mode
        self.input_folder = Path(
            input_folder
        ).expanduser().resolve()
        self.generate_individual_reports = bool(
            generate_individual_reports
        )

    @Slot()
    def run(
        self,
    ) -> None:
        """Execute the selected case-aware CDR workflow."""

        output_stream = SignalTextStream(
            self.log.emit
        )

        try:
            from modules.controllers.app_controller import (
                get_direct_analysis_workspace,
                handle_multiple_cdr,
                handle_single_cdr,
            )

            handler = (
                handle_single_cdr
                if self.mode == "single"
                else handle_multiple_cdr
            )

            from gui.workers.gui_first_policy import supports_gui_only
            gui_kwargs = {"gui_only": True} if supports_gui_only(handler) else {}

            with contextlib.redirect_stdout(
                output_stream
            ), contextlib.redirect_stderr(
                output_stream
            ):
                if self.case_id:
                    from modules.cases import open_case
                    from modules.controllers.app_controller import DIRECT_ANALYSIS_CASE_ID, _direct_analysis_workspace
                    case = _direct_analysis_workspace() if self.case_id == DIRECT_ANALYSIS_CASE_ID else open_case(self.case_id)
                else:
                    case = get_direct_analysis_workspace()

                if self.mode == "multiple":
                    result = handler(
                        case,
                        input_folder=self.input_folder,
                        generate_individual_reports=(
                            self.generate_individual_reports
                        ),
                        **gui_kwargs,
                    )
                else:
                    result = handler(
                        case,
                        input_folder=self.input_folder,
                        **gui_kwargs,
                    )

            output_stream.flush()

            if not isinstance(
                result,
                dict,
            ):
                raise RuntimeError(
                    "CDR analysis did not complete successfully."
                )

            report_paths = collect_cdr_report_paths(
                self.mode,
                result,
            )
            map_paths = collect_cdr_map_paths(
                report_paths
            )
            route_paths = collect_cdr_route_paths(
                report_paths
            )

            from uuid import uuid4
            from modules.reporting.cdr_gui_artifacts import event_frames, generate_gui_maps
            from modules.cases import case_directory
            from modules.cases.investigation import index_case_numbers
            case_id = str(case["case_id"])
            run_id = str(result.get("analysis_run_id") or uuid4().hex)
            gui_sheets = result.get("gui_sheets") or {}
            warnings = []
            if gui_sheets:
                for frame in gui_sheets.values():
                    if hasattr(frame, "attrs"):
                        frame.attrs.update(case_id=case_id, analysis_run_id=run_id)
                try:
                    index_case_numbers(case_id, run_id, event_frames(gui_sheets))
                except Exception as error:
                    # EA_HANDLED_DIAGNOSTICS_V1
                    try:
                        from modules.core.diagnostic_events import record_handled_exception as _ea_record_handled_exception
                        _ea_record_handled_exception()
                    except Exception:
                        pass
                    warnings.append(f"Case number index: {type(error).__name__}: {error}")
                if not map_paths or not route_paths:
                    try:
                        maps, routes = generate_gui_maps(gui_sheets, case_directory(case_id)/"reports/interactive"/run_id)
                        map_paths = map_paths or maps
                        route_paths = route_paths or routes
                    except Exception as error:
                        # EA_HANDLED_DIAGNOSTICS_V1
                        try:
                            from modules.core.diagnostic_events import record_handled_exception as _ea_record_handled_exception
                            _ea_record_handled_exception()
                        except Exception:
                            pass
                        warnings.append(f"Map preview: {type(error).__name__}: {error}")
            for warning in warnings:
                self.log.emit("[!] " + warning)
            self.completed.emit(
                {
                    "case_id": case_id,
                    "analysis_run_id": run_id,
                    "gui_sheets": gui_sheets,
                    "warnings": warnings,
                    "mode": self.mode,
                    "input_folder": str(
                        self.input_folder
                    ),
                    "report_paths": report_paths,
                    "gui_sheets": {
                        (name if len(frame) <= 2000 else
                         f"{name} (preview 2,000/{len(frame):,})"):
                            frame.head(2000).copy()
                        for name, frame in result.get("gui_sheets", {}).items()
                        if hasattr(frame, "head") and not frame.empty
                    },
                    "map_paths": map_paths,
                    "route_paths": route_paths,
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


