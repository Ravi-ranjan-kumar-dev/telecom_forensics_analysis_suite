from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _case_config_dir(case_id: str) -> Path:
    return Path("cases") / "active" / str(case_id) / "configuration"


def date_time_partition_path(case_id: str, workflow: str) -> Path:
    safe_workflow = str(workflow).strip().lower().replace(" ", "_")
    return _case_config_dir(case_id) / f"{safe_workflow}_date_time_parts.json"


def parse_user_datetime(value: Any) -> str:
    """Parse user date-time and return canonical YYYY-MM-DD HH:MM:SS string."""

    text = str(value or "").strip()

    if not text:
        raise ValueError("Date-time blank hai.")

    normalized = text.replace("T", " ")

    for fmt in DATETIME_FORMATS:
        try:
            parsed = datetime.strptime(normalized, fmt)
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ValueError(
            "Date-time format samajh nahi aaya. "
            "Example use karein: 2026-06-11 20:00:00"
        ) from exc


def build_date_time_parts(
    ranges: Iterable[tuple[Any, Any]],
) -> list[dict[str, Any]]:
    """Build pair-based date-time parts.

    Pair rule:
    - start/end pair 1 = Part 1
    - start/end pair 2 = Part 2

    Range rule:
    - start_time <= event_time < end_time
    """

    parts: list[dict[str, Any]] = []

    for index, pair in enumerate(ranges, start=1):
        if len(pair) != 2:
            raise ValueError(f"Part {index}: start aur end dono date-time required hain.")

        start_raw, end_raw = pair
        start_time = parse_user_datetime(start_raw)
        end_time = parse_user_datetime(end_raw)

        start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")

        if end_dt <= start_dt:
            raise ValueError(
                f"Part {index}: End date-time start date-time ke baad hona chahiye."
            )

        parts.append(
            {
                "part_no": index,
                "part_name": f"Part {index}",
                "start_time": start_time,
                "end_time": end_time,
                "range_rule": "start_time <= event_time < end_time",
                "display_rule": "Start aur End Date-Time ke beech ka data",
                "simple_meaning": (
                    f"{start_time} se {end_time} ke beech ka data"
                ),
            }
        )

    return parts


def save_date_time_parts(
    case_id: str,
    workflow: str,
    ranges: Iterable[tuple[Any, Any]],
) -> dict[str, Any]:
    """Save pair-based date-time parts for a case workflow."""

    parts = build_date_time_parts(ranges)

    payload = {
        "schema_version": 1,
        "case_id": str(case_id),
        "workflow": str(workflow),
        "updated_at": _now_iso(),
        "partition_method": "start_end_pair",
        "range_rule": "start_time <= event_time < end_time",
        "display_rule": "Start aur End Date-Time ke beech ka data",
        "parts_count": len(parts),
        "parts": parts,
        "note": (
            "Date-time parts are created in start/end pairs. "
            "Two date-times create one part; four date-times create two parts."
        ),
    }

    path = date_time_partition_path(case_id, workflow)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return payload


def load_date_time_parts(case_id: str, workflow: str) -> dict[str, Any]:
    path = date_time_partition_path(case_id, workflow)

    if not path.exists():
        return {
            "schema_version": 1,
            "case_id": str(case_id),
            "workflow": str(workflow),
            "partition_method": "start_end_pair",
            "range_rule": "start_time <= event_time < end_time",
            "display_rule": "Start aur End Date-Time ke beech ka data",
            "parts_count": 0,
            "parts": [],
        }

    return json.loads(path.read_text(encoding="utf-8"))


def list_date_time_parts(case_id: str, workflow: str) -> list[dict[str, Any]]:
    payload = load_date_time_parts(case_id, workflow)
    return list(payload.get("parts", []))


def clear_date_time_parts(case_id: str, workflow: str) -> bool:
    path = date_time_partition_path(case_id, workflow)

    if path.exists():
        path.unlink()
        return True

    return False


def print_date_time_parts(case_id: str, workflow: str) -> None:
    payload = load_date_time_parts(case_id, workflow)
    parts = list(payload.get("parts", []))

    print("\n" + "=" * 78)
    print("SAVED DATE-TIME PARTS")
    print("=" * 78)

    if not parts:
        print("No date-time parts saved.")
        print("Create parts first by entering start and end date-time pairs.")
        return

    print(f"Method    : Start/End Pair")
    print(f"Rule      : {payload.get('range_rule', 'start_time <= event_time < end_time')}")
    print(f"Total Part: {len(parts)}")

    for part in parts:
        print()
        print(f"{part.get('part_name', 'Part')}")
        print(f"  Start : {part.get('start_time')}")
        print(f"  End   : {part.get('end_time')}")
        print(f"  Meaning: {part.get('simple_meaning')}")
