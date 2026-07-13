"""Backend persistence for GPRS analysis runs."""

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

CORE_TABLES = (
    "summary", "file_summary", "technology_summary", "pre_post_summary",
    "roaming_summary", "subscriber_summary", "repeat_subscribers", "imei_summary",
    "shared_imei", "imsi_summary", "shared_imsi", "ip_summary",
    "duration_buckets", "hourly_activity", "long_sessions", "zero_volume_sessions",
    "non_standard_identifiers", "data_quality", "rejected_rows",
)
PARTITION_TABLES = (
    "partition_windows", "partition_summary", "partition_status",
    "time_only_excluded_by_location", "subscriber_presence", "n_of_m_candidates",
    "strict_common_candidates", "imei_presence", "imsi_presence", "ipv4_presence",
    "ipv6_presence",
)


def save_gprs_run(
    case_id: str,
    *,
    analysis: dict[str, Any],
    partition: dict[str, Any] | None = None,
    input_folder: str | Path = "",
    source_files: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    run_id, root, run_dir = create_run_directory(
        case_id, root_parts=("results", "gprs_dump"), prefix="gprs"
    )
    saved_files, fingerprints = save_tables(
        case_id, run_dir, analysis, CORE_TABLES
    )
    if isinstance(partition, dict):
        extra, extra_fp = save_tables(
            case_id, run_dir, partition, PARTITION_TABLES
        )
        saved_files.update(extra)
        fingerprints.update(extra_fp)
    manifest = {
        **build_manifest_base(
            case_id,
            run_id=run_id,
            input_folder=input_folder,
            source_files=list(source_files or []),
        ),
        "analysis_run_id": run_id,
        "analysis_type": "TOWER_GPRS_DUMP",
        "record_count": int(analysis.get("record_count", 0)),
        "partition_count": int(
            partition.get("total_partitions", 0)
            if isinstance(partition, dict) else 0
        ),
        "overlap_rule": (
            partition.get("overlap_rule", "")
            if isinstance(partition, dict) else ""
        ),
        "saved_files": saved_files,
        "saved_file_fingerprints": fingerprints,
        "warnings": list(warnings or []),
        "errors": list(errors or []),
    }
    manifest_path = write_run_manifest(
        case_id, root=root, run_dir=run_dir, manifest=manifest
    )
    log_case_event(
        case_id,
        action="GPRS_ANALYSIS_SAVED",
        details={
            "run_id": run_id,
            "record_count": manifest["record_count"],
            "partition_count": manifest["partition_count"],
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


def load_latest_gprs_manifest(case_id: str) -> dict[str, Any] | None:
    return load_latest_manifest(case_id, ("results", "gprs_dump"))


def attach_gprs_report(
    case_id: str,
    *,
    run_id: str,
    report_path: str | Path,
) -> dict[str, Any]:
    manifest = attach_report(
        case_id,
        root_parts=("results", "gprs_dump"),
        run_id=run_id,
        report_path=report_path,
    )
    log_case_event(
        case_id,
        action="TOWER_GPRS_REPORT_ATTACHED",
        details={
            "run_id": str(run_id),
            "report_fingerprint": manifest.get("report_fingerprint", {}),
        },
    )
    return manifest
