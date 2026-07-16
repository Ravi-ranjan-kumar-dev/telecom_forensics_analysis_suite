"""CCTV sightings and CGI-group configuration for Tower Dump cases."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from modules.analysis.partition_scope import cell_key
from modules.core.time_utils import utc_now_iso

from .repository import CaseError, read_json, update_json
from .service import case_directory, ensure_case_writable, log_case_event, open_case

ID_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,39}$")
ALLOWED_SOURCE_TYPES = {"NORMAL_CDR", "GPRS", "IPDR"}
DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
)


def _normalize_id(value: str, label: str) -> str:
    normalized = re.sub(r"\s+", "-", str(value).strip().upper())
    normalized = re.sub(r"[^A-Z0-9_-]", "", normalized)
    if not ID_PATTERN.fullmatch(normalized):
        raise CaseError(
            f"{label} 1-40 characters ka hona chahiye aur sirf "
            "A-Z, 0-9, hyphen aur underscore use kar sakta hai."
        )
    return normalized


def _normalize_cgi(value: Any) -> str:
    raw = str(value or "").strip().upper()
    key = cell_key(raw)
    if not key or len(key) < 4:
        raise CaseError(f"Invalid CGI/Cell ID: {value!r}")
    return raw


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None, microsecond=0)
    text = str(value).strip()
    for format_string in DATETIME_FORMATS:
        try:
            return datetime.strptime(text, format_string)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None, microsecond=0)
    except ValueError as error:
        raise CaseError(
            "Date-time invalid hai. Example: 10-07-2026 13:00:00"
        ) from error


def _configuration_file(case_id: str, name: str):
    return case_directory(case_id) / "configuration" / name


def _read_records(case_id: str, name: str) -> list[dict[str, Any]]:
    value = read_json(_configuration_file(case_id, name), default=[])
    return value if isinstance(value, list) else []


def _source_timezone(case_id: str) -> str:
    return str(open_case(case_id, include_archived=True).get("source_timezone", "Asia/Kolkata"))


def save_cgi_group(
    case_id: str,
    *,
    group_id: str,
    group_name: str,
    cgi_values: list[str],
    location_name: str = "",
    notes: str = "",
) -> dict[str, Any]:
    ensure_case_writable(case_id)
    group_id = _normalize_id(group_id, "CGI Group ID")
    group_name = str(group_name).strip()
    if not group_name:
        raise CaseError("CGI group name required hai.")

    by_key: dict[str, str] = {}
    for value in cgi_values:
        normalized = _normalize_cgi(value)
        by_key.setdefault(cell_key(normalized), normalized)
    values = list(by_key.values())
    if not values:
        raise CaseError("Kam-se-kam ek CGI/Cell ID required hai.")

    path = _configuration_file(case_id, "cgi_groups.json")
    now = utc_now_iso()
    captured: dict[str, Any] = {"before": None, "action": "CGI_GROUP_CREATED"}

    def updater(value: Any) -> list[dict[str, Any]]:
        records = value if isinstance(value, list) else []
        record = {
            "group_id": group_id,
            "group_name": group_name,
            "location_name": str(location_name).strip(),
            "cgi_values": values,
            "cgi_keys": list(by_key),
            "notes": str(notes).strip(),
            "updated_at": now,
        }
        for index, existing in enumerate(records):
            if isinstance(existing, dict) and existing.get("group_id") == group_id:
                captured["before"] = dict(existing)
                record["created_at"] = existing.get("created_at", now)
                record["version"] = int(existing.get("version", 1)) + 1
                records[index] = record
                captured["action"] = "CGI_GROUP_UPDATED"
                captured["record"] = record
                break
        else:
            record["created_at"] = now
            record["version"] = 1
            records.append(record)
            captured["record"] = record
        records.sort(key=lambda item: str(item.get("group_id", "")))
        return records

    update_json(path, default=[], updater=updater)
    log_case_event(
        case_id,
        action=captured["action"],
        details={
            "group_id": group_id,
            "before": captured["before"],
            "after": captured["record"],
        },
    )
    return captured["record"]


def list_cgi_groups(case_id: str) -> list[dict[str, Any]]:
    return _read_records(case_id, "cgi_groups.json")


def get_cgi_group(case_id: str, group_id: str) -> dict[str, Any]:
    normalized = _normalize_id(group_id, "CGI Group ID")
    for record in list_cgi_groups(case_id):
        if record.get("group_id") == normalized:
            return record
    raise CaseError(f"CGI group not found: {normalized}")


def _normalize_sources(source_types: list[str] | None) -> list[str]:
    values = list(
        dict.fromkeys(
            str(value).strip().upper()
            for value in (source_types or ["NORMAL_CDR"])
            if str(value).strip()
        )
    )
    invalid = sorted(set(values) - ALLOWED_SOURCE_TYPES)
    if invalid:
        raise CaseError(f"Unsupported source_types: {', '.join(invalid)}")
    return values or ["NORMAL_CDR"]


def save_sighting(
    case_id: str,
    *,
    sighting_id: str,
    location_name: str,
    cctv_timestamp: str | datetime,
    minutes_before: int = 0,
    minutes_after: int = 0,
    cgi_group_id: str,
    source_types: list[str] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    ensure_case_writable(case_id)
    sighting_id = _normalize_id(sighting_id, "Sighting ID")
    location_name = str(location_name).strip()
    if not location_name:
        raise CaseError("Location name required hai.")
    group = get_cgi_group(case_id, cgi_group_id)
    timestamp = _parse_datetime(cctv_timestamp)
    before, after = int(minutes_before), int(minutes_after)
    if not 0 <= before <= 1440 or not 0 <= after <= 1440:
        raise CaseError("Before/After minutes 0 se 1440 ke beech hona chahiye.")
    sources = _normalize_sources(source_types)
    now = utc_now_iso()
    record = {
        "sighting_id": sighting_id,
        "location_name": location_name,
        "cctv_timestamp": timestamp.isoformat(sep=" "),
        "source_timezone": _source_timezone(case_id),
        "minutes_before": before,
        "minutes_after": after,
        "window_start": timestamp.isoformat(sep=" "),
        "window_end": timestamp.isoformat(sep=" "),
                "partition_type": "data_time_partition",
        "partition_type": "data_time_partition",
        "cgi_group_id": group["group_id"],
        "cgi_group_version": int(group.get("version", 1)),
        "source_types": sources,
        "scope_mode": "LOCATION_SCOPED",
        "notes": str(notes).strip(),
        "updated_at": now,
    }
    path = _configuration_file(case_id, "sightings.json")
    captured: dict[str, Any] = {"before": None, "action": "SIGHTING_CREATED"}

    def updater(value: Any) -> list[dict[str, Any]]:
        records = value if isinstance(value, list) else []
        for index, existing in enumerate(records):
            if isinstance(existing, dict) and existing.get("sighting_id") == sighting_id:
                captured["before"] = dict(existing)
                record["created_at"] = existing.get("created_at", now)
                record["version"] = int(existing.get("version", 1)) + 1
                records[index] = record
                captured["action"] = "SIGHTING_UPDATED"
                break
        else:
            record["created_at"] = now
            record["version"] = 1
            records.append(record)
        records.sort(key=lambda item: (str(item.get("cctv_timestamp", "")), str(item.get("sighting_id", ""))))
        captured["record"] = dict(record)
        return records

    update_json(path, default=[], updater=updater)
    log_case_event(
        case_id,
        action=captured["action"],
        details={
            "sighting_id": sighting_id,
            "before": captured["before"],
            "after": captured["record"],
        },
    )
    return captured["record"]


def list_sightings(case_id: str) -> list[dict[str, Any]]:
    return _read_records(case_id, "sightings.json")


def delete_sighting(case_id: str, sighting_id: str) -> bool:
    ensure_case_writable(case_id)
    normalized = _normalize_id(sighting_id, "Sighting ID")
    path = _configuration_file(case_id, "sightings.json")
    captured: dict[str, Any] = {"deleted": None}

    def updater(value: Any) -> list[dict[str, Any]]:
        records = value if isinstance(value, list) else []
        remaining = []
        for item in records:
            if isinstance(item, dict) and item.get("sighting_id") == normalized:
                captured["deleted"] = dict(item)
            else:
                remaining.append(item)
        return remaining

    update_json(path, default=[], updater=updater)
    if captured["deleted"] is None:
        return False
    log_case_event(
        case_id,
        action="SIGHTING_DELETED",
        details={"sighting_id": normalized, "deleted_record": captured["deleted"]},
    )
    return True


def replace_simple_sightings(
    case_id: str,
    date_time_pairs: list[tuple[str, str]],
    *,
    minutes_before: int = 0,
    minutes_after: int = 0,
) -> list[dict[str, Any]]:
    ensure_case_writable(case_id)
    before, after = int(minutes_before), int(minutes_after)
    if not 0 <= before <= 1440 or not 0 <= after <= 1440:
        raise CaseError("Default window invalid hai.")
    parsed = [
        _parse_datetime(f"{str(date).strip()} {str(time).strip()}")
        for date, time in date_time_pairs
        if str(date).strip() and str(time).strip()
    ]
    if not parsed:
        raise CaseError("Kam-se-kam ek valid CCTV date aur time required hai.")
    timestamps = sorted(set(item.replace(microsecond=0) for item in parsed))
    now = utc_now_iso()
    timezone_name = _source_timezone(case_id)
    records: list[dict[str, Any]] = []
    for index, timestamp in enumerate(timestamps, start=1):
        records.append(
            {
                "sighting_id": f"S{index}",
                "location_name": f"Auto Partition {index}",
                "cctv_timestamp": timestamp.isoformat(sep=" "),
                "source_timezone": timezone_name,
                "minutes_before": before,
                "minutes_after": after,
                "window_start": timestamp.isoformat(sep=" "),
                "window_end": timestamp.isoformat(sep=" "),
                "cgi_group_id": "AUTO_ALL",
                "cgi_group_version": 0,
                "source_types": ["NORMAL_CDR", "GPRS", "IPDR"],
                "scope_mode": "ALL_LOADED_CGI",
                "notes": (
                    "Simple mode: time window applies to every CGI already loaded in "
                    "the selected dump. This is not a location-confirmed sighting."
                ),
                "created_at": now,
                "updated_at": now,
                "version": 1,
            }
        )
    path = _configuration_file(case_id, "sightings.json")
    previous = _read_records(case_id, "sightings.json")
    update_json(path, default=[], updater=lambda _: records)
    log_case_event(
        case_id,
        action="SIMPLE_SIGHTINGS_REPLACED",
        details={
            "previous_records": previous,
            "new_records": records,
            "sighting_count": len(records),
            "mode": "DATE_TIME_ALL_LOADED_CGI",
        },
    )
    return records


def clear_sightings(case_id: str) -> None:
    ensure_case_writable(case_id)
    path = _configuration_file(case_id, "sightings.json")
    previous = _read_records(case_id, "sightings.json")
    update_json(path, default=[], updater=lambda _: [])
    log_case_event(
        case_id,
        action="SIGHTINGS_CLEARED",
        details={"cleared_records": previous},
    )
