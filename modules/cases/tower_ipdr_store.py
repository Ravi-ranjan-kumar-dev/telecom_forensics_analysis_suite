"""Backend persistence for Tower IPDR analysis runs."""

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
    "summary", "file_summary", "cell_summary", "allocation_records",
    "subscriber_summary", "subscriber_cell_presence", "subscriber_multi_cell_candidates",
    "subscriber_all_cell_candidates", "imei_summary", "imei_cell_presence",
    "imsi_summary", "imsi_cell_presence", "source_ip_summary", "translated_ip_summary",
    "destination_ip_summary", "destination_port_summary", "destination_endpoint_summary",
    "apn_summary", "roaming_summary", "cell_movement_summary", "hourly_activity",
    "data_quality", "uncommon_priority_summary", "uncommon_numbers",
    "normalized_events", "rejected_rows",
)
PARTITION_TABLES = (
    "partition_windows", "partition_summary", "partition_status", "actual_event_hits",
    "actual_time_only_excluded_by_location", "allocation_time_only_excluded_by_location",
    "allocation_overlap_hits", "event_subscriber_presence", "event_n_of_m_candidates",
    "event_strict_common_candidates", "allocation_subscriber_presence",
    "allocation_n_of_m_candidates", "allocation_strict_common_candidates",
    "imei_event_presence", "imsi_event_presence",
)


def save_tower_ipdr_run(
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
        case_id, root_parts=("results", "tower_ipdr_dump"), prefix="tower_ipdr"
    )
    saved_files, fingerprints = save_tables(case_id, run_dir, analysis, CORE_TABLES)
    if isinstance(partition, dict):
        extra, extra_fp = save_tables(case_id, run_dir, partition, PARTITION_TABLES)
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
        "analysis_type": "TOWER_IPDR_DUMP",
        "record_count": int(analysis.get("record_count", 0)),
        "cell_count": int(analysis.get("total_cells", 0)),
        "partition_count": int(
            partition.get("total_partitions", 0)
            if isinstance(partition, dict) else 0
        ),
        "actual_event_rule": (
            partition.get("actual_event_rule", "")
            if isinstance(partition, dict) else ""
        ),
        "allocation_overlap_rule": (
            partition.get("allocation_overlap_rule", "")
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
        action="TOWER_IPDR_ANALYSIS_SAVED",
        details={
            "run_id": run_id,
            "record_count": manifest["record_count"],
            "cell_count": manifest["cell_count"],
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


def load_latest_tower_ipdr_manifest(case_id: str) -> dict[str, Any] | None:
    return load_latest_manifest(case_id, ("results", "tower_ipdr_dump"))


def attach_tower_ipdr_report(
    case_id: str,
    *,
    run_id: str,
    report_path: str | Path,
) -> dict[str, Any]:
    manifest = attach_report(
        case_id,
        root_parts=("results", "tower_ipdr_dump"),
        run_id=run_id,
        report_path=report_path,
    )
    log_case_event(
        case_id,
        action="TOWER_IPDR_REPORT_ATTACHED",
        details={
            "run_id": str(run_id),
            "report_fingerprint": manifest.get("report_fingerprint", {}),
        },
    )
    return manifest
