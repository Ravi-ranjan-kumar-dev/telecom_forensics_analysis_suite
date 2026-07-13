from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ProgressEvent:
    stage: str
    message: str
    current: int | None = None
    total: int | None = None
    percent: float | None = None
    item: str | None = None
    level: str = "INFO"
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ProgressReporter(Protocol):
    def emit(
        self,
        stage: str,
        message: str,
        *,
        current: int | None = None,
        total: int | None = None,
        percent: float | None = None,
        item: str | None = None,
        level: str = "INFO",
    ) -> None:
        ...


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def calculate_percent(
    current: int | None,
    total: int | None,
) -> float | None:
    if current is None or total is None:
        return None

    if total <= 0:
        return None

    percent = (current / total) * 100
    return round(min(max(percent, 0.0), 100.0), 2)


class NullProgressReporter:
    """Progress reporter that does nothing.

    Use this in tests, background service calls, or when caller does not need
    progress output.
    """

    def emit(
        self,
        stage: str,
        message: str,
        *,
        current: int | None = None,
        total: int | None = None,
        percent: float | None = None,
        item: str | None = None,
        level: str = "INFO",
    ) -> None:
        return None


class CLIProgressReporter:
    """Terminal progress reporter.

    This keeps progress visible in CLI and uses flush=True so output appears
    immediately even during long processing.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        show_timestamp: bool = False,
    ) -> None:
        self.enabled = enabled
        self.show_timestamp = show_timestamp
        self.events: list[ProgressEvent] = []

    def emit(
        self,
        stage: str,
        message: str,
        *,
        current: int | None = None,
        total: int | None = None,
        percent: float | None = None,
        item: str | None = None,
        level: str = "INFO",
    ) -> None:
        if percent is None:
            percent = calculate_percent(current, total)

        event = ProgressEvent(
            stage=stage,
            message=message,
            current=current,
            total=total,
            percent=percent,
            item=item,
            level=level,
            timestamp=_now_iso(),
        )

        self.events.append(event)

        if not self.enabled:
            return

        parts: list[str] = []

        if self.show_timestamp:
            parts.append(event.timestamp)

        parts.append(f"[{level}]")
        parts.append(stage)

        if percent is not None:
            parts.append(f"{percent:>6.2f}%")

        if current is not None and total is not None:
            parts.append(f"({current}/{total})")

        if item:
            parts.append(f"{item}")

        parts.append(f"- {message}")

        print(" ".join(parts), flush=True)


def get_default_progress(
    *,
    enabled: bool = True,
) -> ProgressReporter:
    return CLIProgressReporter(enabled=enabled)


def emit_stage_start(
    progress: ProgressReporter | None,
    stage: str,
    message: str,
) -> None:
    reporter = progress or NullProgressReporter()
    reporter.emit(stage, message, level="INFO")


def emit_stage_done(
    progress: ProgressReporter | None,
    stage: str,
    message: str,
) -> None:
    reporter = progress or NullProgressReporter()
    reporter.emit(stage, message, percent=100.0, level="OK")


def emit_warning(
    progress: ProgressReporter | None,
    stage: str,
    message: str,
) -> None:
    reporter = progress or NullProgressReporter()
    reporter.emit(stage, message, level="WARNING")


def emit_error(
    progress: ProgressReporter | None,
    stage: str,
    message: str,
) -> None:
    reporter = progress or NullProgressReporter()
    reporter.emit(stage, message, level="ERROR")