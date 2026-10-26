"""In-memory brute-force protection for the login endpoint.

After ``MAX_FAILURES`` failed attempts for one username inside ``WINDOW_SECONDS``
the account is locked for ``LOCKOUT_SECONDS``. State is per-process, which fits
the single-host deployment described in docs/PRODUCTION_RUNBOOK.md. Run a shared
store (e.g. the database or Redis) instead if the backend is ever scaled out.
"""

from __future__ import annotations

import os
import threading
import time

MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", "5"))
WINDOW_SECONDS = int(os.getenv("LOGIN_WINDOW_SECONDS", "900"))
LOCKOUT_SECONDS = int(os.getenv("LOGIN_LOCKOUT_SECONDS", "900"))

_lock = threading.Lock()
_failures: dict[str, list[float]] = {}
_locked_until: dict[str, float] = {}


def _key(username: str) -> str:
    return username.strip().casefold()


def seconds_locked(username: str, *, now: float | None = None) -> int:
    """Return remaining lockout seconds for ``username`` (0 when not locked)."""
    current = time.monotonic() if now is None else now
    key = _key(username)
    with _lock:
        until = _locked_until.get(key, 0.0)
        if until <= current:
            _locked_until.pop(key, None)
            return 0
        return int(until - current) + 1


def record_failure(username: str, *, now: float | None = None) -> None:
    current = time.monotonic() if now is None else now
    key = _key(username)
    with _lock:
        recent = [t for t in _failures.get(key, []) if current - t < WINDOW_SECONDS]
        recent.append(current)
        if len(recent) >= MAX_FAILURES:
            _locked_until[key] = current + LOCKOUT_SECONDS
            recent = []
        _failures[key] = recent


def record_success(username: str) -> None:
    key = _key(username)
    with _lock:
        _failures.pop(key, None)
        _locked_until.pop(key, None)


def reset() -> None:
    """Clear all state (used by tests)."""
    with _lock:
        _failures.clear()
        _locked_until.clear()
