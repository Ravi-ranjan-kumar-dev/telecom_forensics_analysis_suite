"""Canonical persistence helpers shared by all case analysis run stores."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from modules.core.hashing import file_fingerprint, sha256_file
from modules.core.time_utils import new_run_id, utc_now_iso
from modules.reporting.excel_security import excel_safe_value

from .repository import (
    InvalidCaseError,
    case_relative_path,
    portable_path_reference,
    read_json,
    resolve_case_path,
    safe_descendant,
    update_json,
    write_json,
)
from .service import (
    capture_configuration_snapshot,
    case_directory,
    ensure_case_writable,
    open_case,
    source_provenance_snapshot,
)

RUN_MANIFEST_SCHEMA_VERSION = 2


def create_run_directory(
    case_id: str,
    *,
    root_parts: Iterable[str],
    prefix: str,
) -> tuple[str, Path, Path]:
    ensure_case_writable(case_id)
    root = case_directory(case_id).joinpath(*root_parts)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    run_id = new_run_id(prefix)
    run_dir = safe_descendant(root, run_id)
    run_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    return run_id, root, run_dir


def _safe_csv_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    output = dataframe.copy()
    for column in output.columns:
        if pd.api.types.is_object_dtype(output[column]) or pd.api.types.is_string_dtype(output[column]):
            output[column] = output[column].map(excel_safe_value)
    return output


def save_table(
    case_id: str,
    run_dir: Path,
    name: str,
    dataframe: pd.DataFrame,
) -> tuple[str, dict[str, Any]]:
    path = safe_descendant(run_dir, f"{name}.csv")
    _safe_csv_dataframe(dataframe).to_csv(path, index=False)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    reference = case_relative_path(case_id, path)
    fingerprint = {"path": reference, **file_fingerprint(path), "formula_escaped": True}
    return reference, fingerprint


def save_tables(
    case_id: str,
    run_dir: Path,
    source: dict[str, Any],
    names: Iterable[str],
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    files: dict[str, str] = {}
    fingerprints: dict[str, dict[str, Any]] = {}
    for name in names:
        value = source.get(name)
        if not isinstance(value, pd.DataFrame):
            continue
        reference, fingerprint = save_table(case_id, run_dir, str(name), value)
        files[str(name)] = reference
        fingerprints[str(name)] = fingerprint
    return files, fingerprints


def build_manifest_base(
    case_id: str,
    *,
    run_id: str,
    input_folder: str | Path = "",
    source_files: list[str | Path] | None = None,
) -> dict[str, Any]:
    metadata = open_case(case_id, include_archived=True)
    sources = list(source_files or [])
    provenance = source_provenance_snapshot(case_id, sources)
    return {
        "manifest_schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at_utc": utc_now_iso(timespec="microseconds"),
        "source_timezone": metadata.get("source_timezone", "Asia/Kolkata"),
        "input_folder": portable_path_reference(case_id, input_folder),
        "source_files": [portable_path_reference(case_id, path) for path in sources],
        "source_provenance": provenance,
        "evidence_ids": [
            item.get("evidence_id", "")
            for item in provenance
            if item.get("evidence_id")
        ],
        "configuration_snapshot": capture_configuration_snapshot(case_id),
        "user_facing_report": "",
        "report_status": "BACKEND_SAVED",
    }


def write_run_manifest(
    case_id: str,
    *,
    root: Path,
    run_dir: Path,
    manifest: dict[str, Any],
    latest_extra: dict[str, Any] | None = None,
) -> Path:
    manifest_path = run_dir / "manifest.json"
    write_json(manifest_path, manifest)
    manifest_sha256 = sha256_file(manifest_path)
    latest_record = {
        "run_id": str(manifest.get("run_id", "")),
        "run_directory": case_relative_path(case_id, run_dir),
        "manifest": case_relative_path(case_id, manifest_path),
        "manifest_sha256": manifest_sha256,
        "updated_at_utc": utc_now_iso(timespec="microseconds"),
        **(latest_extra or {}),
    }
    update_json(root / "latest.json", default={}, updater=lambda _: latest_record)
    return manifest_path


def load_latest_manifest(case_id: str, root_parts: Iterable[str]) -> dict[str, Any] | None:
    root = case_directory(case_id).joinpath(*root_parts)
    latest_path = root / "latest.json"
    if not latest_path.is_file():
        return None
    latest = read_json(latest_path, default={})
    if not isinstance(latest, dict):
        return None
    value = str(latest.get("manifest", "")).strip()
    if not value:
        return None
    manifest_path = resolve_case_path(case_id, value)
    if not manifest_path.is_file():
        return None
    expected_hash = str(latest.get("manifest_sha256", ""))
    if expected_hash and sha256_file(manifest_path) != expected_hash:
        raise InvalidCaseError(f"Run manifest hash mismatch: {manifest_path}")
    manifest = read_json(manifest_path, default=None)
    return manifest if isinstance(manifest, dict) else None


def attach_report(
    case_id: str,
    *,
    root_parts: Iterable[str],
    run_id: str,
    report_path: str | Path,
    report_field: str = "user_facing_report",
) -> dict[str, Any]:
    ensure_case_writable(case_id)
    root = case_directory(case_id).joinpath(*root_parts)
    run_directory = safe_descendant(root, str(run_id))
    manifest_path = run_directory / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Run manifest not found: {manifest_path}")

    report = Path(report_path).expanduser().resolve(strict=False)
    if not report.is_file():
        raise FileNotFoundError(f"Report file not found: {report}")
    report_reference = case_relative_path(case_id, report)
    if not report_reference.startswith("reports/"):
        raise InvalidCaseError("Report case reports directory ke andar hona chahiye.")
    report_metadata = {"path": report_reference, **file_fingerprint(report)}

    def update_manifest(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise InvalidCaseError(f"Invalid run manifest: {manifest_path}")
        value[report_field] = report_reference
        value["user_facing_report"] = report_reference
        value["report_status"] = "COMPLETED"
        value["report_fingerprint"] = report_metadata
        value["report_attached_at_utc"] = utc_now_iso(timespec="microseconds")
        return value

    manifest = update_json(manifest_path, default={}, updater=update_manifest)
    manifest_sha256 = sha256_file(manifest_path)

    def update_latest(value: Any) -> dict[str, Any]:
        latest = value if isinstance(value, dict) else {}
        latest.update(
            {
                "run_id": str(run_id),
                "run_directory": case_relative_path(case_id, run_directory),
                "manifest": case_relative_path(case_id, manifest_path),
                "manifest_sha256": manifest_sha256,
                report_field: report_reference,
                "user_facing_report": report_reference,
                "report_fingerprint": report_metadata,
                "updated_at_utc": utc_now_iso(timespec="microseconds"),
            }
        )
        return latest

    update_json(root / "latest.json", default={}, updater=update_latest)
    return manifest
