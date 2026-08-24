"""Background IMEI workflow worker for the desktop GUI."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from gui.workers.text_stream import SignalTextStream

IMEI_ANALYSIS_MODES = {
    "cdr",
    "ipdr",
    "gprs",
    "unified",
}


def _portable_report_path(value: object) -> str:
    text = str(value or "").strip()

    if not text:
        return ""

    return str(Path(text).expanduser().resolve(strict=False))


def collect_imei_report_paths(result: dict[str, Any]) -> list[str]:
    """Collect common and single-device reports in a useful order."""

    candidates: list[object] = []

    common_result = result.get("common_result")
    if isinstance(common_result, dict):
        candidates.append(common_result.get("report"))

    candidates.append(result.get("report"))

    for single_result in result.get("single_results", []) or []:
        if isinstance(single_result, dict):
            candidates.append(single_result.get("report"))

    paths: list[str] = []

    for candidate in candidates:
        path = _portable_report_path(candidate)

        if path and path not in paths:
            paths.append(path)

    return paths


class ImeiWorker(QObject):
    """Run one automatic IMEI workflow outside the GUI thread."""

    log = Signal(str)
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        *,
        mode: str,
        input_folder: str | Path,
    ) -> None:
        super().__init__()

        normalized_mode = str(mode).strip().casefold()

        if normalized_mode not in IMEI_ANALYSIS_MODES:
            raise ValueError(f"Unsupported IMEI mode: {mode}")

        self.mode = normalized_mode
        self.input_folder = Path(input_folder).expanduser().resolve(strict=False)

    @Slot()
    def run(self) -> None:
        """Execute the selected case-aware automatic IMEI workflow."""

        output_stream = SignalTextStream(self.log.emit)

        try:
            from modules.controllers.app_controller import (
                get_direct_analysis_workspace,
            )
            from modules.controllers.imei_device_controller import (
                run_imei_device_analysis,
            )

            with (
                contextlib.redirect_stdout(output_stream),
                contextlib.redirect_stderr(output_stream),
            ):
                case = get_direct_analysis_workspace()
                result = run_imei_device_analysis(
                    case,
                    mode=self.mode,
                    input_folder=self.input_folder,
                )

            output_stream.flush()

            if not isinstance(result, dict):
                raise TypeError("IMEI analysis did not return a valid result.")

            self.completed.emit(
                {
                    "mode": self.mode,
                    "input_folder": str(self.input_folder),
                    "identifiers": list(result.get("identifiers", []) or []),
                    "report_paths": collect_imei_report_paths(result),
                    "status": str(result.get("status", "COMPLETED")),
                    "message": str(result.get("message", "")),
                    "result": result,
                }
            )

        except Exception as error:  # noqa: BLE001 - worker failure boundary.
            output_stream.flush()
            self.failed.emit(f"{type(error).__name__}: {error}")

        finally:
            self.finished.emit()
