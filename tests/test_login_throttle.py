"""Brute-force protection on the login endpoint."""

from __future__ import annotations

import pytest

from backend.app import login_throttle


@pytest.fixture(autouse=True)
def clean_state():
    login_throttle.reset()
    yield
    login_throttle.reset()


def test_locks_after_max_failures_and_unlocks_after_timeout():
    for i in range(login_throttle.MAX_FAILURES):
        assert login_throttle.seconds_locked("Officer1", now=100.0 + i) == 0
        login_throttle.record_failure("Officer1", now=100.0 + i)

    assert login_throttle.seconds_locked("officer1", now=110.0) > 0  # case-insensitive
    assert login_throttle.seconds_locked("other", now=110.0) == 0
    assert (
        login_throttle.seconds_locked(
            "officer1", now=110.0 + login_throttle.LOCKOUT_SECONDS + 1
        )
        == 0
    )


def test_success_clears_failures():
    for i in range(login_throttle.MAX_FAILURES - 1):
        login_throttle.record_failure("a", now=float(i))
    login_throttle.record_success("a")
    login_throttle.record_failure("a", now=50.0)
    assert login_throttle.seconds_locked("a", now=51.0) == 0


def test_old_failures_expire_from_window():
    for i in range(login_throttle.MAX_FAILURES - 1):
        login_throttle.record_failure("b", now=float(i))
    late = login_throttle.WINDOW_SECONDS + 100.0
    login_throttle.record_failure("b", now=late)
    assert login_throttle.seconds_locked("b", now=late + 1) == 0
