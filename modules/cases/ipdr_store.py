"""Case-local backend persistence for top-level IPDR analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .run_store import (
    attach_report,
    build_manifest_base,
    create_run_directory,
    load_latest_manifest,
    save_tables,
    write_run_manifest,
)
from .service import log_case_event

TABLES = (
    "summary", "file_summary", "query_summary", "subscriber_summary",
    "multi_file_subscribers", "subscriber_file_presence", "imei_summary",
    "shared_imei", "imei_file_presence", "imsi_summary", "shared_imsi",
    "imsi_file_presence", "source_ip_summary", "translated_ip_summary",
    "destination_ip_summary", "destination_port_summary",
    "destination_endpoint_summary", "allocation_records", "apn_summary",
    "technology_summary", "cgi_summary", "cell_movement", "hourly_activity",
    "reverse_query_validation", "search_requests", "data_quality",
    "normalized_events", "rejected_rows",
)


def save_ipdr_run(
    case_id: str,
    *,
    mode: str,
    analysis: dict[str, Any],
    input_folder: str | Path,
    source_files: list[str],
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    mode = str(mode).strip().lower()
    if mode not in {"single", "multiple"}:
        raise ValueError("IPDR mode must be single or multiple.")
    root_parts = ("results", "ipdr", mode)
    run_id, root, run_dir = create_run_directory(
        case_id, root_parts=root_parts, prefix=f"ipdr_{mode}"
    )
    saved_files, fingerprints = save_tables(case_id, run_dir, analysis, TABLES)
    manifest = {
        **build_manifest_base(
            case_id,
            run_id=run_id,
            input_folder=input_folder,
            source_files=source_files,
        ),
        "analysis_run_id": run_id,
        "analysis_type": f"IPDR_{mode.upper()}",
        "mode": mode,
        "record_count": int(analysis.get("record_count", 0)),
        "saved_files": saved_files,
        "saved_file_fingerprints": fingerprints,
        "warnings": list(warnings or []),
        "errors": list(errors or []),
    }
    manifest_path = write_run_manifest(
        case_id,
        root=root,
        run_dir=run_dir,
        manifest=manifest,
        latest_extra={"mode": mode},
    )
    log_case_event(
        case_id,
        action="IPDR_ANALYSIS_SAVED",
        details={
            "run_id": run_id,
            "mode": mode,
            "record_count": manifest["record_count"],
            "evidence_ids": manifest["evidence_ids"],
        },
    )
    return {
        "run_id": run_id,
        "analysis_run_id": run_id,
        "run_directory": str(run_dir),
        "manifest": str(manifest_path),
        "saved_files": saved_files,
    }


def load_latest_ipdr_manifest(case_id: str, mode: str) -> dict[str, Any] | None:
    return load_latest_manifest(
        case_id, ("results", "ipdr", str(mode).strip().lower())
    )


def attach_ipdr_report(
    case_id: str,
    *,
    mode: str,
    run_id: str,
    report_path: str | Path,
) -> dict[str, Any]:
    manifest = attach_report(
        case_id,
        root_parts=("results", "ipdr", str(mode).strip().lower()),
        run_id=run_id,
        report_path=report_path,
    )
    log_case_event(
        case_id,
        action="IPDR_REPORT_ATTACHED",
        details={
            "run_id": str(run_id),
            "mode": str(mode),
            "report_fingerprint": manifest.get("report_fingerprint", {}),
        },
    )
    return manifest
