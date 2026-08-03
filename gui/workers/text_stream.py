"""Text stream helpers shared by GUI background workers."""

from __future__ import annotations

import io
from collections.abc import Callable


class SignalTextStream(io.TextIOBase):
    """Send complete output lines through a signal-compatible callback."""

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
        value = str(
            text
        )

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

        return len(
            value
        )

    def flush(
        self,
    ) -> None:
        if self._buffer.strip():
            self._emit_line(
                self._buffer.rstrip()
            )

        self._buffer = ""
