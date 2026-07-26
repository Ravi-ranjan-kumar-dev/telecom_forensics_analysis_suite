"""Public service layer for common investigation case management."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from modules.core.hashing import file_fingerprint, sha256_file
from modules.core.time_utils import new_run_id, utc_date_compact, utc_now_iso

from .audit import append_audit_event, verify_audit_log
from .models import CASE_SCHEMA_VERSION, CaseMetadata
from .repository import (
    ArchivedCaseReadOnlyError,
    CaseError,
    InvalidCaseError,
    archive_case_directory,
    case_relative_path,
    create_case_directory,
    is_archived_case,
    list_case_metadata,
    load_case,
    locate_case_dir,
    normalize_case_id,
    portable_path_reference,
    read_json,
    reopen_case_directory,
    safe_descendant,
    scan_case_health,
    touch_case_metadata,
    update_json,
)

REPORT_PATHS = {
    "cdr_single": ("reports", "cdr", "single"),
    "cdr_multiple_individual": ("reports", "cdr", "multiple", "individual_targets"),
    "cdr_multiple_common": ("reports", "cdr", "multiple", "common_analysis"),
    "tower_cdr_dump": ("reports", "tower_dump", "cdr"),
    "tower_gprs_dump": ("reports", "tower_dump", "gprs"),
    "tower_ipdr_dump": ("reports", "tower_dump", "ipdr"),
    "ipdr_single": ("reports", "ipdr", "single"),
    "ipdr_multiple": ("reports", "ipdr", "multiple"),
    "ipdr": ("reports", "ipdr"),
    "imei_device": ("reports", "device", "imei"),
    "tower_dump": ("reports", "tower_dump", "cdr"),
    "gprs_dump": ("reports", "tower_dump", "gprs"),
}
ALLOWED_REPORT_SUFFIXES = {".xlsx", ".xlsm", ".pdf", ".csv", ".html"}


def generate_case_id() -> str:
    prefix = f"CASE-{utc_date_compact()}-"
    existing_ids = {
        metadata.case_id
        for metadata in (list_case_metadata(archived=False) + list_case_metadata(archived=True))
    }
    for sequence in range(1, 10000):
        candidate = f"{prefix}{sequence:03d}"
        if candidate not in existing_ids:
            return candidate
    raise CaseError("Automatic Case ID generate nahi ho saka.")


def create_case(
    *,
    case_name: str,
    case_id: str | None = None,
    fir_number: str = "",
    incident_date: str = "",
    investigator: str = "",
    unit_name: str = "",
    incident_location: str = "",
    description: str = "",
    source_timezone: str = "Asia/Kolkata",
) -> dict[str, Any]:
    case_name = str(case_name).strip()
    if not case_name:
        raise CaseError("Case name required hai.")
    resolved_case_id = (
        normalize_case_id(case_id)
        if case_id is not None and str(case_id).strip()
        else generate_case_id()
    )
    metadata = CaseMetadata(
        case_id=resolved_case_id,
        case_name=case_name,
        fir_number=str(fir_number).strip(),
        incident_date=str(incident_date).strip(),
        investigator=str(investigator).strip(),
        unit_name=str(unit_name).strip(),
        incident_location=str(incident_location).strip(),
        description=str(description).strip(),
        status="active",
        schema_version=CASE_SCHEMA_VERSION,
        source_timezone=source_timezone,
    )
    directory = create_case_directory(metadata)
    append_audit_event(
        directory / "logs" / "audit.jsonl",
        action="CASE_CREATED",
        actor=metadata.investigator,
        details={
            "case_id": metadata.case_id,
            "case_name": metadata.case_name,
            "creation_mode": "SIMPLE",
            "schema_version": CASE_SCHEMA_VERSION,
            "source_timezone": metadata.source_timezone,
        },
    )
    return metadata.to_dict()


def open_case(case_id: str, *, include_archived: bool = False) -> dict[str, Any]:
    return load_case(case_id, include_archived=include_archived).to_dict()


def list_cases(*, archived: bool = False) -> list[dict[str, Any]]:
    return [metadata.to_dict() for metadata in list_case_metadata(archived=archived)]


def case_health() -> list[dict[str, Any]]:
    """Return metadata and audit-chain health without modifying case storage."""

    results = scan_case_health()
    for item in results:
        if item.get("status") != "OK":
            item["audit_valid"] = False
            item["healthy"] = False
            continue
        try:
            verification = verify_case_audit(str(item.get("case_id", "")))
            item["audit_valid"] = bool(verification.get("valid"))
            item["audit_events"] = int(verification.get("event_count", 0))
            item["audit_errors"] = verification.get("errors", [])
        except Exception as error:
            item["audit_valid"] = False
            item["audit_errors"] = [f"{type(error).__name__}: {error}"]
        item["healthy"] = item.get("status") == "OK" and item["audit_valid"]
    return results


def case_directory(case_id: str) -> Path:
    return locate_case_dir(case_id, include_archived=True)


def ensure_case_writable(case_id: str) -> CaseMetadata:
    metadata = load_case(case_id, include_archived=True)
    if is_archived_case(case_id) or metadata.status != "active":
        raise ArchivedCaseReadOnlyError(
            f"Archived case read-only hai: {metadata.case_id}. "
            "Changes ke liye controlled reopen workflow use karein."
        )
    return metadata


def case_report_dir(case_id: str, report_type: str) -> Path:
    ensure_case_writable(case_id)
    if report_type not in REPORT_PATHS:
        raise CaseError(f"Unknown report type: {report_type}")
    directory = safe_descendant(case_directory(case_id), *REPORT_PATHS[report_type])
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def case_evidence_dir(case_id: str, *parts: str) -> Path:
    ensure_case_writable(case_id)
    directory = safe_descendant(case_directory(case_id), "evidence", *parts)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def _config_file(case_id: str, name: str) -> Path:
    return safe_descendant(case_directory(case_id), "configuration", name)


def _append_unique_record(
    path: Path,
    record: dict[str, Any],
    *,
    unique_keys: tuple[str, ...],
) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def updater(value: Any) -> list[dict[str, Any]]:
        records = value if isinstance(value, list) else []
        for existing in records:
            if not isinstance(existing, dict):
                continue
            if all(existing.get(key) == record.get(key) for key in unique_keys):
                created = existing.get("created_at") or existing.get("registered_at")
                existing.update(record)
                if created:
                    existing["created_at"] = created
                existing["updated_at"] = utc_now_iso()
                captured["record"] = dict(existing)
                return records
        fresh = dict(record)
        fresh.setdefault("created_at", fresh.pop("registered_at", utc_now_iso()))
        fresh.setdefault("updated_at", fresh["created_at"])
        records.append(fresh)
        captured["record"] = dict(fresh)
        return records

    update_json(path, default=[], updater=updater)
    return captured["record"]


def register_target(
    case_id: str,
    *,
    target_type: str,
    target_value: str,
    description: str = "",
) -> dict[str, Any] | None:
    ensure_case_writable(case_id)
    value = str(target_value).strip()
    if not value:
        return None
    record = _append_unique_record(
        _config_file(case_id, "targets.json"),
        {
            "target_type": str(target_type).strip().upper(),
            "target_value": value,
            "description": str(description).strip(),
            "updated_at": utc_now_iso(),
        },
        unique_keys=("target_type", "target_value"),
    )
    log_case_event(case_id, action="TARGET_REGISTERED", details=record)
    return record


def _source_identity(case_id: str, path: Path) -> tuple[str, str, str]:
    resolved = path.expanduser().resolve(strict=False)
    reference = portable_path_reference(case_id, resolved)
    identity_basis = reference if not reference.startswith("external://") else str(resolved)
    source_path_id = hashlib.sha256(
        identity_basis.encode("utf-8", errors="surrogatepass")
    ).hexdigest()
    return str(resolved), reference, source_path_id


def _stable_file_fingerprint(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "file_name": path.name,
            "file_exists": False,
            "file_size_bytes": 0,
            "sha256": "",
        }
    before = path.stat()
    digest = sha256_file(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise CaseError(f"Evidence file hashing ke dauran change hui: {path}")
    return {
        "file_name": path.name,
        "file_exists": True,
        "file_size_bytes": int(after.st_size),
        "sha256": digest,
    }


def _next_numeric_id(records: list[Any], prefix: str, width: int = 6) -> str:
    highest = 0
    marker = f"{prefix}-"
    for record in records:
        if not isinstance(record, dict):
            continue
        value = str(record.get(f"{prefix.lower()}_id", record.get("evidence_id", "")))
        if value.startswith(marker) and value[len(marker) :].isdigit():
            highest = max(highest, int(value[len(marker) :]))
    return f"{marker}{highest + 1:0{width}d}"


def register_evidence(
    case_id: str,
    *,
    evidence_type: str,
    source_file: str | Path,
    operator: str = "",
    source_category: str = "",
) -> dict[str, Any]:
    ensure_case_writable(case_id)
    path = Path(source_file).expanduser().resolve(strict=False)
    source_identity, source_reference, source_path_id = _source_identity(case_id, path)
    fingerprint = _stable_file_fingerprint(path)
    evidence_file = _config_file(case_id, "evidence.json")
    captured: dict[str, Any] = {}

    def updater(value: Any) -> list[dict[str, Any]]:
        records = value if isinstance(value, list) else []
        previous: dict[str, Any] | None = None
        previous_index = -1
        for index in range(len(records) - 1, -1, -1):
            candidate = records[index]
            if not isinstance(candidate, dict):
                continue
            if str(candidate.get("source_path_id", "")) == source_path_id:
                previous, previous_index = candidate, index
                break
        if previous is None:
            change_status = "NEW" if fingerprint["file_exists"] else "MISSING"
            previous_evidence_id = ""
        else:
            previous_hash = str(previous.get("sha256", ""))
            if not fingerprint["file_exists"]:
                change_status = "MISSING"
            elif previous_hash == fingerprint["sha256"]:
                change_status = "UNCHANGED"
            else:
                change_status = "MODIFIED"
            previous_evidence_id = str(
                previous.get("evidence_id") or f"LEGACY-EVD-{previous_index + 1:06d}"
            )
        evidence_id = _next_numeric_id(records, "EVD")
        record = {
            "evidence_id": evidence_id,
            "previous_evidence_id": previous_evidence_id,
            "change_status": change_status,
            "evidence_type": str(evidence_type).strip().upper(),
            "source_file": source_reference,
            "source_path_id": source_path_id,
            "source_identity_sha256": hashlib.sha256(source_identity.encode()).hexdigest(),
            **fingerprint,
            "operator": str(operator).strip(),
            "source_category": str(source_category).strip().upper(),
            "registered_at": utc_now_iso(timespec="microseconds"),
        }
        records.append(record)
        captured["record"] = record
        return records

    update_json(evidence_file, default=[], updater=updater)
    record = captured["record"]
    log_case_event(
        case_id,
        action="EVIDENCE_REGISTERED",
        details={key: record[key] for key in (
            "evidence_id",
            "previous_evidence_id",
            "file_name",
            "evidence_type",
            "change_status",
            "sha256",
            "file_size_bytes",
        )},
    )
    return record


def source_provenance_snapshot(
    case_id: str,
    source_files: list[str | Path] | None,
) -> list[dict[str, Any]]:
    """Resolve exact bytes and latest immutable evidence IDs for a run."""

    ledger = read_json(_config_file(case_id, "evidence.json"), default=[])
    records = ledger if isinstance(ledger, list) else []
    output: list[dict[str, Any]] = []
    for source in source_files or []:
        path = Path(source).expanduser().resolve(strict=False)
        _, reference, source_path_id = _source_identity(case_id, path)
        latest = next(
            (
                item
                for item in reversed(records)
                if isinstance(item, dict)
                and str(item.get("source_path_id", "")) == source_path_id
            ),
            None,
        )
        current = _stable_file_fingerprint(path)
        output.append(
            {
                "source_file": reference,
                "source_path_id": source_path_id,
                "evidence_id": str((latest or {}).get("evidence_id", "")),
                "registered_sha256": str((latest or {}).get("sha256", "")),
                "current_sha256": current["sha256"],
                "sha256": current["sha256"],
                "file_size_bytes": current["file_size_bytes"],
                "provenance_status": (
                    "VERIFIED"
                    if latest and current["sha256"] and current["sha256"] == latest.get("sha256")
                    else "CHANGED_SINCE_REGISTRATION"
                    if latest and current["sha256"]
                    else "UNREGISTERED"
                    if current["file_exists"]
                    else "MISSING"
                ),
            }
        )
    return output


def capture_configuration_snapshot(case_id: str) -> dict[str, Any]:
    """Capture the exact analysis configuration without mutable file paths."""

    metadata = open_case(case_id, include_archived=True)
    targets = read_json(_config_file(case_id, "targets.json"), default=[])
    sightings = read_json(_config_file(case_id, "sightings.json"), default=[])
    groups = read_json(_config_file(case_id, "cgi_groups.json"), default=[])
    value = {
        "schema_version": CASE_SCHEMA_VERSION,
        "captured_at_utc": utc_now_iso(timespec="microseconds"),
        "source_timezone": metadata.get("source_timezone", "Asia/Kolkata"),
        "targets": targets if isinstance(targets, list) else [],
        "sightings": sightings if isinstance(sightings, list) else [],
        "cgi_groups": groups if isinstance(groups, list) else [],
    }
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    value["snapshot_sha256"] = digest
    value["sha256"] = digest
    return value


def _validate_report_path(case_id: str, report_path: str | Path) -> tuple[Path, str]:
    path = Path(report_path).expanduser().resolve(strict=False)
    if not path.is_file():
        raise FileNotFoundError(f"Report file not found: {path}")
    if path.suffix.lower() not in ALLOWED_REPORT_SUFFIXES:
        raise CaseError(f"Unsupported report extension: {path.suffix}")
    relative = case_relative_path(case_id, path)
    if not relative.startswith("reports/"):
        raise InvalidCaseError("Report case ke reports directory ke andar hona chahiye.")
    return path, relative


def register_report(
    case_id: str,
    *,
    report_type: str,
    report_path: str | Path,
    status: str = "COMPLETED",
    analysis_run_id: str = "",
    exporter_version: str = "1",
) -> dict[str, Any]:
    ensure_case_writable(case_id)
    path, reference = _validate_report_path(case_id, report_path)
    fingerprint = file_fingerprint(path)
    registry = _config_file(case_id, "reports.json")
    captured: dict[str, Any] = {}

    def updater(value: Any) -> list[dict[str, Any]]:
        records = value if isinstance(value, list) else []
        previous = next(
            (
                item for item in reversed(records)
                if isinstance(item, dict) and item.get("report_path") == reference
            ),
            None,
        )
        record = {
            "report_id": new_run_id("report"),
            "previous_report_id": str((previous or {}).get("report_id", "")),
            "report_type": str(report_type).strip().upper(),
            "report_path": reference,
            **fingerprint,
            "status": str(status).strip().upper(),
            "analysis_run_id": str(analysis_run_id).strip(),
            "exporter_version": str(exporter_version).strip(),
            "created_at": utc_now_iso(timespec="microseconds"),
        }
        records.append(record)
        captured["record"] = record
        return records

    update_json(registry, default=[], updater=updater)
    record = captured["record"]
    log_case_event(case_id, action="REPORT_REGISTERED", details=record)
    return record


def register_analysis_run(
    case_id: str,
    *,
    analysis_type: str,
    status: str,
    input_records: int = 0,
    output_records: int = 0,
    report_path: str = "",
    error_message: str = "",
    analysis_run_id: str = "",
    source_files: list[str | Path] | None = None,
    evidence_snapshot: list[dict[str, Any]] | None = None,
    configuration_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_case_writable(case_id)
    portable_report = case_relative_path(case_id, report_path) if str(report_path).strip() else ""
    record = {
        "analysis_run_id": str(analysis_run_id).strip() or new_run_id("analysis"),
        "analysis_type": str(analysis_type).strip().upper(),
        "status": str(status).strip().upper(),
        "input_records": int(input_records or 0),
        "output_records": int(output_records or 0),
        "report_path": portable_report,
        "error_message": str(error_message),
        "evidence_snapshot": evidence_snapshot
        if evidence_snapshot is not None
        else source_provenance_snapshot(case_id, source_files),
        "configuration_snapshot": configuration_snapshot
        if configuration_snapshot is not None
        else capture_configuration_snapshot(case_id),
        "recorded_at": utc_now_iso(timespec="microseconds"),
    }

    def updater(value: Any) -> list[dict[str, Any]]:
        records = value if isinstance(value, list) else []
        records.append(record)
        return records

    update_json(_config_file(case_id, "analysis_runs.json"), default=[], updater=updater)
    log_case_event(case_id, action="ANALYSIS_RUN_RECORDED", details={
        "analysis_run_id": record["analysis_run_id"],
        "analysis_type": record["analysis_type"],
        "status": record["status"],
        "input_records": record["input_records"],
        "output_records": record["output_records"],
        "evidence_ids": [
            item.get("evidence_id", "") for item in record["evidence_snapshot"]
            if isinstance(item, dict) and item.get("evidence_id")
        ],
    })
    return record


def list_case_reports(case_id: str) -> list[dict[str, Any]]:
    value = read_json(_config_file(case_id, "reports.json"), default=[])
    return value if isinstance(value, list) else []


def verify_case_audit(case_id: str) -> dict[str, Any]:
    return verify_audit_log(case_directory(case_id) / "logs" / "audit.jsonl")


def log_case_event(
    case_id: str,
    *,
    action: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = ensure_case_writable(case_id)
    record = append_audit_event(
        case_directory(case_id) / "logs" / "audit.jsonl",
        action=action,
        actor=metadata.investigator,
        details=details,
    )
    touch_case_metadata(case_id)
    return record


def archive_case(case_id: str) -> dict[str, Any]:
    metadata = ensure_case_writable(case_id)
    log_case_event(
        metadata.case_id,
        action="CASE_ARCHIVE_REQUESTED",
        details={"case_id": metadata.case_id},
    )
    metadata.status = "archived"
    metadata.updated_at = utc_now_iso()
    destination = archive_case_directory(metadata.case_id, metadata=metadata)
    append_audit_event(
        destination / "logs" / "audit.jsonl",
        action="CASE_ARCHIVED",
        actor=metadata.investigator,
        details={"case_id": metadata.case_id},
    )
    return metadata.to_dict()


def reopen_case(case_id: str, *, reason: str, actor: str = "") -> dict[str, Any]:
    metadata = load_case(case_id, include_archived=True)
    if not is_archived_case(case_id) or metadata.status != "archived":
        raise CaseError(f"Case archived state mein nahi hai: {metadata.case_id}")
    reason = str(reason).strip()
    if not reason:
        raise CaseError("Case reopen reason required hai.")
    audit_path = case_directory(case_id) / "logs" / "audit.jsonl"
    append_audit_event(
        audit_path,
        action="CASE_REOPEN_REQUESTED",
        actor=str(actor).strip() or metadata.investigator,
        details={"case_id": metadata.case_id, "reason": reason},
    )
    metadata.status = "active"
    metadata.updated_at = utc_now_iso()
    destination = reopen_case_directory(metadata.case_id, metadata=metadata)
    append_audit_event(
        destination / "logs" / "audit.jsonl",
        action="CASE_REOPENED",
        actor=str(actor).strip() or metadata.investigator,
        details={"case_id": metadata.case_id, "reason": reason},
    )
    return metadata.to_dict()
