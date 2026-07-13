"""Filesystem repository for active and archived investigation cases."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, TypeVar
from uuid import uuid4

from modules.core.paths import ACTIVE_CASES_DIR, ARCHIVED_CASES_DIR, PROJECT_ROOT
from modules.core.time_utils import DEFAULT_SOURCE_TIMEZONE, utc_now_iso

from .locking import file_lock
from .models import CASE_SCHEMA_VERSION, CaseMetadata


CASE_ID_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,49}$")
SAFE_PATH_PART_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
T = TypeVar("T")


class CaseError(RuntimeError):
    """Base case-management exception."""


class CaseNotFoundError(CaseError):
    """Raised when a requested case does not exist."""


class CaseAlreadyExistsError(CaseError):
    """Raised when a case ID is already in use."""


class InvalidCaseError(CaseError):
    """Raised when case metadata or a case-local path is invalid."""


class ArchivedCaseReadOnlyError(CaseError):
    """Raised when a write is attempted against an archived case."""


def normalize_case_id(value: str) -> str:
    case_id = re.sub(r"\s+", "-", str(value).strip().upper())
    case_id = re.sub(r"[^A-Z0-9_-]", "", case_id)
    if not CASE_ID_PATTERN.fullmatch(case_id):
        raise InvalidCaseError(
            "Case ID 3-50 characters ka hona chahiye aur sirf "
            "A-Z, 0-9, hyphen aur underscore use kar sakta hai."
        )
    return case_id


def _secure_directory(path: Path) -> None:
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _secure_file(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _fsync_directory(directory: Path) -> None:
    flags = getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY
    try:
        descriptor = os.open(str(directory), flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _secure_directory(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        try:
            os.fchmod(descriptor, 0o600)
        except OSError:
            pass
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        _secure_file(path)
        _fsync_directory(path.parent)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def _read_json_unlocked(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, UnicodeError, OSError) as error:
        raise InvalidCaseError(f"Invalid JSON file: {path}: {error}") from error


def read_json(path: Path, default: Any = None) -> Any:
    return _read_json_unlocked(Path(path), default)


def write_json(path: Path, value: Any) -> None:
    """Atomically persist JSON under an advisory sidecar lock."""

    path = Path(path)
    with file_lock(path):
        _atomic_write_json(path, value)


def update_json(
    path: Path,
    *,
    default: T,
    updater: Callable[[T], T | None],
) -> T:
    """Perform one locked read-modify-write transaction."""

    path = Path(path)
    with file_lock(path):
        current = _read_json_unlocked(path, default)
        result = updater(current)
        final = current if result is None else result
        _atomic_write_json(path, final)
        return final


def active_case_dir(case_id: str) -> Path:
    return ACTIVE_CASES_DIR / normalize_case_id(case_id)


def archived_case_dir(case_id: str) -> Path:
    return ARCHIVED_CASES_DIR / normalize_case_id(case_id)


def locate_case_dir(case_id: str, *, include_archived: bool = True) -> Path:
    active = active_case_dir(case_id)
    if active.is_dir():
        return active
    if include_archived:
        archived = archived_case_dir(case_id)
        if archived.is_dir():
            return archived
    raise CaseNotFoundError(f"Case not found: {normalize_case_id(case_id)}")


def is_archived_case(case_id: str) -> bool:
    case_id = normalize_case_id(case_id)
    return archived_case_dir(case_id).is_dir() and not active_case_dir(case_id).is_dir()


def _validate_path_part(value: str) -> str:
    part = str(value).strip()
    if (
        not part
        or part in {".", ".."}
        or "/" in part
        or "\\" in part
        or "\x00" in part
        or not SAFE_PATH_PART_PATTERN.fullmatch(part)
    ):
        raise InvalidCaseError(f"Unsafe case path component: {value!r}")
    return part


def safe_descendant(base: Path, *parts: str) -> Path:
    root = Path(base).expanduser().resolve()
    candidate = root
    for value in parts:
        candidate = candidate / _validate_path_part(value)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise InvalidCaseError(
            f"Path case directory ke bahar resolve ho raha hai: {resolved}"
        ) from error
    return resolved


def case_relative_path(case_id: str, path: str | Path) -> str:
    root = locate_case_dir(case_id, include_archived=True).resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise InvalidCaseError(
            f"Path current case ke andar hona chahiye: {resolved}"
        ) from error
    return relative.as_posix() if relative.parts else "."


def portable_path_reference(case_id: str, path: str | Path) -> str:
    raw_text = str(path).strip()
    if not raw_text:
        return ""
    candidate = Path(raw_text).expanduser().resolve(strict=False)
    try:
        return case_relative_path(case_id, candidate)
    except InvalidCaseError:
        pass
    project_root = PROJECT_ROOT.resolve()
    try:
        project_relative = candidate.relative_to(project_root)
        return f"project://{project_relative.as_posix()}"
    except ValueError:
        return f"external://{candidate.name}"


def resolve_case_path(case_id: str, stored_path: str | Path) -> Path:
    case_id = normalize_case_id(case_id)
    root = locate_case_dir(case_id, include_archived=True).resolve()
    raw_text = str(stored_path).strip()
    if not raw_text:
        raise InvalidCaseError("Stored case path empty hai.")
    if raw_text.startswith(("project://", "external://")):
        raise InvalidCaseError(f"Path case-local nahi hai: {raw_text}")
    raw = Path(raw_text).expanduser()
    if not raw.is_absolute():
        candidate = (root / raw).resolve(strict=False)
    else:
        resolved_raw = raw.resolve(strict=False)
        try:
            resolved_raw.relative_to(root)
            candidate = resolved_raw
        except ValueError:
            parts = list(resolved_raw.parts)
            indexes = [i for i, value in enumerate(parts) if str(value).upper() == case_id]
            if not indexes:
                raise InvalidCaseError(
                    f"Legacy absolute path current case se related nahi hai: {raw}"
                )
            candidate = root.joinpath(*parts[indexes[-1] + 1 :]).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise InvalidCaseError(
            f"Stored path case directory ke bahar resolve ho raha hai: {candidate}"
        ) from error
    return candidate


def _workspace_document(metadata: CaseMetadata) -> dict[str, Any]:
    return {
        "schema_version": CASE_SCHEMA_VERSION,
        "created_at": metadata.created_at,
        "source_timezone": metadata.source_timezone or DEFAULT_SOURCE_TIMEZONE,
        "system_timestamp_timezone": "UTC",
    }


def create_case_directory(metadata: CaseMetadata) -> Path:
    case_id = normalize_case_id(metadata.case_id)
    metadata.case_id = case_id
    metadata.schema_version = CASE_SCHEMA_VERSION
    active = active_case_dir(case_id)
    archived = archived_case_dir(case_id)
    if active.exists() or archived.exists():
        raise CaseAlreadyExistsError(f"Case already exists: {case_id}")

    directories = [
        active / "evidence" / "cdr" / "single",
        active / "evidence" / "cdr" / "multiple",
        active / "evidence" / "tower_dump" / "normal",
        active / "evidence" / "tower_dump" / "gprs",
        active / "evidence" / "tower_dump" / "ipdr",
        active / "evidence" / "ipdr",
        active / "evidence" / "gprs_dump",
        active / "evidence" / "cctv",
        active / "configuration",
        active / "results" / "filtered_windows",
        active / "results" / "candidate_sets",
        active / "results" / "ranked_candidates",
        active / "results" / "gprs_dump",
        active / "results" / "ipdr" / "single",
        active / "results" / "ipdr" / "multiple",
        active / "results" / "tower_ipdr_dump",
        active / "reports" / "cdr" / "single",
        active / "reports" / "cdr" / "multiple" / "individual_targets",
        active / "reports" / "cdr" / "multiple" / "common_analysis",
        active / "reports" / "tower_dump" / "cdr",
        active / "reports" / "tower_dump" / "gprs",
        active / "reports" / "tower_dump" / "ipdr",
        active / "reports" / "ipdr" / "single",
        active / "reports" / "ipdr" / "multiple",
        active / "logs",
    ]

    active.mkdir(parents=True, exist_ok=False, mode=0o700)
    _secure_directory(active)
    try:
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            _secure_directory(directory)
        write_json(active / "case.json", metadata.to_dict())
        write_json(active / "workspace.json", _workspace_document(metadata))
        for name in (
            "targets.json",
            "evidence.json",
            "sightings.json",
            "cgi_groups.json",
            "reports.json",
            "analysis_runs.json",
        ):
            write_json(active / "configuration" / name, [])
    except Exception:
        shutil.rmtree(active, ignore_errors=True)
        raise
    return active


def load_case(case_id: str, *, include_archived: bool = True) -> CaseMetadata:
    requested = normalize_case_id(case_id)
    directory = locate_case_dir(requested, include_archived=include_archived)
    value = read_json(directory / "case.json")
    if not isinstance(value, dict):
        raise InvalidCaseError(f"Missing or invalid case.json: {directory}")
    try:
        metadata = CaseMetadata.from_dict(value)
    except (TypeError, ValueError) as error:
        raise InvalidCaseError(f"Invalid case metadata in {directory}: {error}") from error
    actual = normalize_case_id(metadata.case_id)
    if actual != requested or actual != normalize_case_id(directory.name):
        raise InvalidCaseError(
            f"Case identity mismatch: directory={directory.name}, case.json={metadata.case_id}"
        )
    metadata.case_id = actual
    return metadata


def save_case(metadata: CaseMetadata) -> None:
    metadata.case_id = normalize_case_id(metadata.case_id)
    directory = locate_case_dir(metadata.case_id, include_archived=True)
    write_json(directory / "case.json", metadata.to_dict())


def touch_case_metadata(case_id: str) -> CaseMetadata:
    case_id = normalize_case_id(case_id)
    directory = locate_case_dir(case_id, include_archived=True)
    path = directory / "case.json"
    captured: dict[str, CaseMetadata] = {}

    def updater(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise InvalidCaseError(f"Invalid case.json: {path}")
        try:
            metadata = CaseMetadata.from_dict(value)
        except (TypeError, ValueError) as error:
            raise InvalidCaseError(f"Invalid case metadata: {error}") from error
        if normalize_case_id(metadata.case_id) != case_id:
            raise InvalidCaseError("Case identity mismatch during metadata update.")
        metadata.updated_at = utc_now_iso()
        metadata.schema_version = CASE_SCHEMA_VERSION
        captured["value"] = metadata
        return metadata.to_dict()

    update_json(path, default={}, updater=updater)
    return captured["value"]


def list_case_metadata(*, archived: bool = False) -> list[CaseMetadata]:
    root = ARCHIVED_CASES_DIR if archived else ACTIVE_CASES_DIR
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    _secure_directory(root)
    output: list[CaseMetadata] = []
    for directory in sorted(root.iterdir()):
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        try:
            output.append(load_case(directory.name, include_archived=True))
        except CaseError:
            continue
    output.sort(key=lambda item: (item.updated_at or "", item.case_id), reverse=True)
    return output


def scan_case_health(*, archived: bool | None = None) -> list[dict[str, Any]]:
    """Surface valid and corrupt case folders instead of silently hiding them."""

    roots: list[tuple[str, Path]] = []
    if archived is not True:
        roots.append(("active", ACTIVE_CASES_DIR))
    if archived is not False:
        roots.append(("archived", ARCHIVED_CASES_DIR))
    results: list[dict[str, Any]] = []
    for storage, root in roots:
        if not root.is_dir():
            continue
        for directory in sorted(root.iterdir()):
            if not directory.is_dir() or directory.name.startswith("."):
                continue
            try:
                metadata = load_case(directory.name, include_archived=True)
                results.append(
                    {
                        "case_id": metadata.case_id,
                        "storage": storage,
                        "status": "OK",
                        "error": "",
                    }
                )
            except Exception as error:
                results.append(
                    {
                        "case_id": directory.name,
                        "storage": storage,
                        "status": "CORRUPT",
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
    return results


def archive_case_directory(
    case_id: str,
    *,
    metadata: CaseMetadata | None = None,
) -> Path:
    """Move an active case through a hidden staging directory with rollback."""

    case_id = normalize_case_id(case_id)
    source = active_case_dir(case_id)
    destination = archived_case_dir(case_id)
    if not source.is_dir():
        raise CaseNotFoundError(f"Active case not found: {case_id}")
    if destination.exists():
        raise CaseAlreadyExistsError(f"Archived case directory already exists: {case_id}")

    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = destination.parent / f".{case_id}.archive-{uuid4().hex}"
    try:
        os.replace(source, staging)
        if metadata is not None:
            metadata.case_id = case_id
            metadata.status = "archived"
            metadata.updated_at = utc_now_iso()
            _atomic_write_json(staging / "case.json", metadata.to_dict())
        os.replace(staging, destination)
        _secure_directory(destination)
        _fsync_directory(destination.parent)
        return destination
    except Exception:
        if staging.exists() and not source.exists():
            try:
                os.replace(staging, source)
            except OSError:
                pass
        raise


def reopen_case_directory(
    case_id: str,
    *,
    metadata: CaseMetadata,
) -> Path:
    """Move an archived case back to active storage through staging."""

    case_id = normalize_case_id(case_id)
    source = archived_case_dir(case_id)
    destination = active_case_dir(case_id)
    if not source.is_dir():
        raise CaseNotFoundError(f"Archived case not found: {case_id}")
    if destination.exists():
        raise CaseAlreadyExistsError(f"Active case directory already exists: {case_id}")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = destination.parent / f".{case_id}.reopen-{uuid4().hex}"
    try:
        os.replace(source, staging)
        metadata.case_id = case_id
        metadata.status = "active"
        metadata.updated_at = utc_now_iso()
        _atomic_write_json(staging / "case.json", metadata.to_dict())
        os.replace(staging, destination)
        _secure_directory(destination)
        _fsync_directory(destination.parent)
        return destination
    except Exception:
        if staging.exists() and not source.exists():
            try:
                os.replace(staging, source)
            except OSError:
                pass
        raise
