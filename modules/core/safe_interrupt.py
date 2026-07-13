#safe stop/checkpoint वाली common file
from __future__ import annotations

import json
import traceback
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

from modules.core.progress import (
    ProgressReporter,
    emit_error,
    emit_warning,
)


@dataclass(frozen=True)
class InterruptState:
    status: str
    stage: str
    message: str
    checkpoint_path: str
    timestamp: str
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


def write_json_atomic(
    path: str | Path,
    payload: dict,
) -> Path:
    """Write JSON safely using temporary file replacement.

    This reduces the chance of a half-written checkpoint file if the program
    is interrupted during write.
    """

    target = Path(path).expanduser().resolve()
    ensure_parent(target)

    temporary = target.with_suffix(
        target.suffix + ".tmp"
    )

    with temporary.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            payload,
            handle,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        handle.write("\n")

    temporary.replace(target)
    return target


def read_json_safe(
    path: str | Path,
) -> dict:
    target = Path(path).expanduser().resolve()

    if not target.exists():
        return {}

    try:
        with target.open(
            "r",
            encoding="utf-8",
        ) as handle:
            data = json.load(handle)

        if isinstance(data, dict):
            return data

        return {}
    except Exception:
        return {}


def save_interrupt_state(
    checkpoint_path: str | Path,
    *,
    stage: str,
    message: str,
    status: str = "INTERRUPTED",
    error: BaseException | None = None,
) -> InterruptState:
    error_type = type(error).__name__ if error else None
    error_message = str(error) if error else None

    state = InterruptState(
        status=status,
        stage=stage,
        message=message,
        checkpoint_path=str(
            Path(checkpoint_path).expanduser().resolve()
        ),
        timestamp=_now_iso(),
        error_type=error_type,
        error_message=error_message,
    )

    payload = state.to_dict()

    if error and not isinstance(error, KeyboardInterrupt):
        payload["traceback"] = traceback.format_exc()

    write_json_atomic(
        checkpoint_path,
        payload,
    )

    return state


@contextmanager
def safe_interrupt_context(
    checkpoint_path: str | Path,
    *,
    stage: str,
    progress: ProgressReporter | None = None,
) -> Iterator[None]:
    """Context manager for safe Ctrl+C handling.

    Usage:

        with safe_interrupt_context(
            checkpoint_path,
            stage="tower_ipdr_import",
            progress=progress,
        ):
            run_large_task()

    If Ctrl+C is pressed, checkpoint JSON is saved and KeyboardInterrupt is
    raised again so caller can stop cleanly.
    """

    try:
        yield

    except KeyboardInterrupt as error:
        state = save_interrupt_state(
            checkpoint_path,
            stage=stage,
            message=(
                "User interrupted the process using Ctrl+C. "
                "Checkpoint saved. You can resume or rerun safely."
            ),
            status="INTERRUPTED",
            error=error,
        )

        emit_warning(
            progress,
            stage,
            f"Interrupted safely. Checkpoint: {state.checkpoint_path}",
        )

        raise

    except Exception as error:
        state = save_interrupt_state(
            checkpoint_path,
            stage=stage,
            message=(
                "Process failed with an unexpected error. "
                "Checkpoint saved for diagnosis."
            ),
            status="FAILED",
            error=error,
        )

        emit_error(
            progress,
            stage,
            (
                f"Failed safely. Checkpoint: {state.checkpoint_path}. "
                f"Error: {type(error).__name__}: {error}"
            ),
        )

        raise


def mark_stage_status(
    checkpoint_path: str | Path,
    *,
    stage: str,
    status: str,
    message: str,
    extra: dict | None = None,
) -> Path:
    payload = {
        "status": status,
        "stage": stage,
        "message": message,
        "timestamp": _now_iso(),
    }

    if extra:
        payload.update(extra)

    return write_json_atomic(
        checkpoint_path,
        payload,
    )


def is_previous_run_interrupted(
    checkpoint_path: str | Path,
) -> bool:
    payload = read_json_safe(checkpoint_path)
    return payload.get("status") == "INTERRUPTED"


def print_checkpoint_summary(
    checkpoint_path: str | Path,
) -> None:
    payload = read_json_safe(checkpoint_path)

    if not payload:
        print("No checkpoint found.")
        return

    print("\nCHECKPOINT SUMMARY")
    print("-" * 70)
    print(f"Status    : {payload.get('status')}")
    print(f"Stage     : {payload.get('stage')}")
    print(f"Message   : {payload.get('message')}")
    print(f"Timestamp : {payload.get('timestamp')}")
    print(f"Path      : {Path(checkpoint_path).expanduser().resolve()}")

    if payload.get("error_type"):
        print(f"Error Type: {payload.get('error_type')}")
        print(f"Error     : {payload.get('error_message')}")