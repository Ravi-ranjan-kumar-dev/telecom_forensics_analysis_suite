"""Small dependency-free advisory file locking for case registries."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Iterator

try:  # Linux/Kali path.
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover - Windows fallback.
    fcntl = None

_LOCAL_LOCKS: dict[str, RLock] = {}


class FileLockTimeoutError(TimeoutError):
    """Raised when a case-local file lock cannot be acquired in time."""


def _local_lock(path: Path) -> RLock:
    key = str(path.resolve(strict=False))
    return _LOCAL_LOCKS.setdefault(key, RLock())


@contextmanager
def file_lock(
    target: str | Path,
    *,
    timeout: float = 30.0,
    poll_interval: float = 0.05,
) -> Iterator[None]:
    """Lock a sidecar file for the full read-modify-write transaction."""

    target_path = Path(target)
    lock_path = target_path.with_name(f".{target_path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    local = _local_lock(lock_path)

    with local:
        with lock_path.open("a+b") as handle:
            try:
                os.chmod(lock_path, 0o600)
            except OSError:
                pass

            if fcntl is None:  # The in-process lock still prevents thread races.
                yield
                return

            deadline = time.monotonic() + max(0.1, float(timeout))
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise FileLockTimeoutError(
                            f"Timed out waiting for lock: {lock_path}"
                        )
                    time.sleep(poll_interval)

            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
