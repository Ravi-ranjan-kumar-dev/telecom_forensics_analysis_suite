"""Background subscriber IPDR workflow worker for the desktop GUI."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from gui.workers.text_stream import SignalTextStream


IPDR_ANALYSIS_MODES = {
    "single",
    "multiple",
}


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


def collect_ipdr_report_paths(
    result: dict[str, Any],
) -> list[str]:
    """Collect investigator-facing reports from one IPDR result."""

    report_path = _portable_report_path(
        result.get(
            "excel_report"
        )
    )

    return [
        report_path
    ] if report_path else []


class IpdrWorker(QObject):
    """Run one subscriber IPDR workflow outside the GUI thread."""

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
    ) -> None:
        super().__init__()

        normalized_mode = str(
            mode
        ).strip().casefold()

        if normalized_mode not in IPDR_ANALYSIS_MODES:
            raise ValueError(
                f"Unsupported IPDR mode: {mode}"
            )

        self.mode = normalized_mode
        self.input_folder = Path(
            input_folder
        ).expanduser().resolve(
            strict=False
        )

    @Slot()
    def run(
        self,
    ) -> None:
        """Execute the selected case-aware subscriber IPDR workflow."""

        output_stream = SignalTextStream(
            self.log.emit
        )

        try:
            from modules.controllers.app_controller import (
                get_direct_analysis_workspace,
            )
            from modules.controllers.ipdr_case_controller import (
                run_ipdr_case_analysis,
            )

            with contextlib.redirect_stdout(
                output_stream
            ), contextlib.redirect_stderr(
                output_stream
            ):
                case = get_direct_analysis_workspace()
                result = run_ipdr_case_analysis(
                    case,
                    mode=self.mode,
                    input_folder=self.input_folder,
                )

            output_stream.flush()

            if not isinstance(
                result,
                dict,
            ):
                raise RuntimeError(
                    "IPDR analysis did not complete successfully."
                )

            report_paths = collect_ipdr_report_paths(
                result
            )

            self.completed.emit(
                {
                    "mode": self.mode,
                    "input_folder": str(
                        self.input_folder
                    ),
                    "report_paths": report_paths,
                    "result": result,
                }
            )

        except Exception as error:
            output_stream.flush()
            self.failed.emit(
                f"{type(error).__name__}: {error}"
            )

        finally:
            self.finished.emit()
