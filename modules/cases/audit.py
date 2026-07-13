"""Durable hash-chained JSONL audit logging for investigation cases."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from modules.core.time_utils import utc_now_iso

from .locking import file_lock

AUDIT_VERSION = 2
ZERO_HASH = "0" * 64


class AuditIntegrityError(RuntimeError):
    """Raised when an existing audit log fails verification."""


def _canonical_bytes(record: dict[str, Any]) -> bytes:
    value = {key: record[key] for key in sorted(record) if key != "record_hash"}
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _record_hash(record: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(record)).hexdigest()


def _parse_lines(raw_lines: list[bytes]) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, raw in enumerate(raw_lines, start=1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            errors.append(f"Line {index}: invalid JSON: {error}")
            continue
        if not isinstance(value, dict):
            errors.append(f"Line {index}: audit event must be an object")
            continue
        records.append(value)
    return records, errors


def _verify_raw_lines(raw_lines: list[bytes]) -> dict[str, Any]:
    records, errors = _parse_lines(raw_lines)
    legacy_raw: list[bytes] = []
    legacy_count = 0
    chained_count = 0
    chain_started = False
    expected_previous = ZERO_HASH
    last_hash = ZERO_HASH

    line_cursor = 0
    for line_number, raw in enumerate(raw_lines, start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            line_cursor += 1
            continue
        line_cursor += 1
        is_chained = (
            isinstance(record, dict)
            and "record_hash" in record
            and "previous_hash" in record
            and "sequence" in record
        )
        if not is_chained:
            if chain_started:
                errors.append(f"Line {line_number}: unchained event appears after chain start")
            else:
                legacy_raw.append(raw)
                legacy_count += 1
            continue

        if not chain_started:
            chain_started = True
            legacy_digest = hashlib.sha256(b"".join(legacy_raw)).hexdigest()
            expected_previous = legacy_digest if legacy_raw else ZERO_HASH
            declared_legacy = str(record.get("legacy_prefix_sha256", ""))
            if legacy_raw and declared_legacy != legacy_digest:
                errors.append(
                    f"Line {line_number}: legacy prefix hash mismatch"
                )
            if not legacy_raw and declared_legacy:
                errors.append(
                    f"Line {line_number}: unexpected legacy prefix hash"
                )

        chained_count += 1
        expected_sequence = legacy_count + chained_count
        try:
            sequence = int(record.get("sequence"))
        except (TypeError, ValueError):
            sequence = -1
        if sequence != expected_sequence:
            errors.append(
                f"Line {line_number}: sequence {sequence}, expected {expected_sequence}"
            )
        if str(record.get("previous_hash", "")) != expected_previous:
            errors.append(f"Line {line_number}: previous_hash mismatch")
        calculated = _record_hash(record)
        if str(record.get("record_hash", "")) != calculated:
            errors.append(f"Line {line_number}: record_hash mismatch")
        expected_previous = str(record.get("record_hash", ""))
        last_hash = expected_previous

    return {
        "valid": not errors,
        "event_count": len(records),
        "legacy_event_count": legacy_count,
        "chained_event_count": chained_count,
        "last_hash": last_hash,
        "errors": errors,
    }


def verify_audit_log(audit_file: str | Path) -> dict[str, Any]:
    path = Path(audit_file)
    if not path.exists():
        return {
            "valid": True,
            "event_count": 0,
            "legacy_event_count": 0,
            "chained_event_count": 0,
            "last_hash": ZERO_HASH,
            "errors": [],
        }
    with file_lock(path):
        return _verify_raw_lines(path.read_bytes().splitlines(keepends=True))


def append_audit_event(
    audit_file: Path,
    *,
    action: str,
    details: dict[str, Any] | None = None,
    actor: str = "",
) -> dict[str, Any]:
    """Append one verified event with sequence and SHA-256 hash chaining.

    Legacy unhashed events are preserved byte-for-byte. The first v2 event
    anchors their complete byte prefix using ``legacy_prefix_sha256``.
    """

    audit_file = Path(audit_file)
    audit_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(audit_file.parent, 0o700)
    except OSError:
        pass

    with file_lock(audit_file):
        raw_lines = (
            audit_file.read_bytes().splitlines(keepends=True)
            if audit_file.exists()
            else []
        )
        verification = _verify_raw_lines(raw_lines)
        if not verification["valid"]:
            raise AuditIntegrityError(
                "Audit log verification failed: " + "; ".join(verification["errors"])
            )

        legacy_raw: list[bytes] = []
        chained_records: list[dict[str, Any]] = []
        for raw in raw_lines:
            if not raw.strip():
                continue
            value = json.loads(raw.decode("utf-8"))
            if (
                isinstance(value, dict)
                and "record_hash" in value
                and "previous_hash" in value
                and "sequence" in value
            ):
                chained_records.append(value)
            elif not chained_records:
                legacy_raw.append(raw)

        previous_hash = (
            str(chained_records[-1]["record_hash"])
            if chained_records
            else hashlib.sha256(b"".join(legacy_raw)).hexdigest()
            if legacy_raw
            else ZERO_HASH
        )
        record: dict[str, Any] = {
            "audit_version": AUDIT_VERSION,
            "sequence": int(verification["event_count"]) + 1,
            "timestamp": utc_now_iso(timespec="microseconds"),
            "action": str(action).strip(),
            "actor": str(actor).strip(),
            "details": details or {},
            "previous_hash": previous_hash,
        }
        if legacy_raw and not chained_records:
            record["legacy_prefix_sha256"] = previous_hash
        record["record_hash"] = _record_hash(record)

        encoded = (
            json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
            + "\n"
        ).encode("utf-8")
        descriptor = os.open(
            audit_file,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        try:
            os.write(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.chmod(audit_file, 0o600)
        except OSError:
            pass
        return record
