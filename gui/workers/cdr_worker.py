"""Background CDR workflow worker for the desktop GUI."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, Slot


class _SignalTextStream(io.TextIOBase):
    """Send complete output lines through a Qt signal callback."""

    def __init__(
        self,
        emit_line: Callable[[str], None],
    ) -> None:
        super().__init__()
        self._emit_line = emit_line
        self._buffer = ""

    def writable(self) -> bool:
        return True

    def write(
        self,
        text: str,
    ) -> int:
        value = str(text)

        if not value:
            return 0

        self._buffer += value

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split(
                "\n",
                1,
            )

            if line.strip():
                self._emit_line(
                    line.rstrip()
                )

        return len(value)

    def flush(self) -> None:
        if self._buffer.strip():
            self._emit_line(
                self._buffer.rstrip()
            )

        self._buffer = ""


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

        self.mode = normalized_mode
        self.input_folder = Path(
            input_folder
        ).expanduser().resolve()

    @Slot()
    def run(
        self,
    ) -> None:
        """Execute the selected case-aware CDR workflow."""

        output_stream = _SignalTextStream(
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

            with contextlib.redirect_stdout(
                output_stream
            ), contextlib.redirect_stderr(
                output_stream
            ):
                case = get_direct_analysis_workspace()

                result = handler(
                    case,
                    input_folder=self.input_folder,
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
