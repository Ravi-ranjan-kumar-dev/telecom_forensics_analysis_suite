"""Timezone-aware timestamps and collision-resistant identifiers."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

UTC = timezone.utc
DEFAULT_SOURCE_TIMEZONE = "Asia/Kolkata"


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso(*, timespec: str = "seconds") -> str:
    return utc_now().isoformat(timespec=timespec)


def utc_date_compact() -> str:
    return utc_now().strftime("%Y%m%d")


def new_run_id(prefix: str) -> str:
    """Return a UTC, microsecond and random-suffix based run identifier."""

    safe_prefix = "".join(
        char.lower() if char.isalnum() else "_" for char in str(prefix).strip()
    ).strip("_") or "run"
    stamp = utc_now().strftime("%Y%m%dT%H%M%S_%fZ")
    return f"{safe_prefix}_{stamp}_{uuid4().hex[:8]}"


def display_in_timezone(
    value: datetime | str,
    timezone_name: str = DEFAULT_SOURCE_TIMEZONE,
) -> str:
    """Format an aware UTC timestamp in a declared display timezone."""

    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
    else:
        parsed = value

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed.astimezone(ZoneInfo(timezone_name)).isoformat(timespec="seconds")
