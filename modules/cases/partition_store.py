"""Persistence for Tower Dump partition runs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from .run_store import (
    attach_report,
    build_manifest_base,
    create_run_directory,
    load_latest_manifest,
    save_table,
    save_tables,
    write_run_manifest,
)
from .service import log_case_event

TABLES = (
    "partition_summary", "partition_status", "rejected_rows",
    "subscriber_presence", "n_of_m_candidates", "strict_common_candidates",
    "imei_presence", "imsi_presence",
)


def _serializable(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return "" if pd.isna(value) else value.isoformat(sep=" ")
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return value


def _safe_partition_name(value: Any, index: int) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]", "_", str(value).strip())
    return text[:100] or f"partition_{index:03d}"


def save_partition_run(
    case_id: str,
    result: dict[str, Any],
    *,
    export_full_partitions: bool = False,
    input_folder: str | Path = "",
    source_files: list[str] | None = None,
) -> dict[str, Any]:
    run_id, root, run_dir = create_run_directory(
        case_id,
        root_parts=("results", "filtered_windows"),
        prefix="partition",
    )
    saved_files, fingerprints = save_tables(case_id, run_dir, result, TABLES)
    partition_files: dict[str, str] = {}
    partition_fingerprints: dict[str, dict[str, Any]] = {}
    if export_full_partitions:
        partition_dir = run_dir / "partitions"
        partition_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        for index, (sighting_id, dataframe) in enumerate(
            result.get("partitions", {}).items(), start=1
        ):
            if not isinstance(dataframe, pd.DataFrame):
                continue
            safe_name = _safe_partition_name(sighting_id, index)
            reference, fingerprint = save_table(
                case_id, partition_dir, safe_name, dataframe
            )
            partition_files[str(sighting_id)] = reference
            partition_fingerprints[str(sighting_id)] = fingerprint

    summary = result.get("partition_summary")
    summary_records = (
        [
            {str(key): _serializable(value) for key, value in record.items()}
            for record in summary.to_dict(orient="records")
        ]
        if isinstance(summary, pd.DataFrame)
        else []
    )
    manifest = {
        **build_manifest_base(
            case_id,
            run_id=run_id,
            input_folder=input_folder,
            source_files=list(source_files or []),
        ),
        "analysis_run_id": run_id,
        "analysis_type": "TOWER_CDR_DUMP_PARTITION",
        "total_input_records": int(result.get("total_input_records", 0)),
        "total_sightings": int(result.get("total_sightings", 0)),
        "total_configured_sightings": int(
            result.get("total_configured_sightings", 0)
        ),
        "rejected_rows": int(len(result.get("rejected_rows", pd.DataFrame())))
        if isinstance(result.get("rejected_rows"), pd.DataFrame)
        else 0,
        "partition_summary": summary_records,
        "saved_files": saved_files,
        "saved_file_fingerprints": fingerprints,
        "full_partition_files": partition_files,
        "full_partition_fingerprints": partition_fingerprints,
        "full_partitions_exported": bool(export_full_partitions),
    }
    manifest_path = write_run_manifest(
        case_id, root=root, run_dir=run_dir, manifest=manifest
    )
    log_case_event(
        case_id,
        action="TOWER_DUMP_PARTITION_SAVED",
        details={
            "run_id": run_id,
            "sightings": manifest["total_sightings"],
            "full_partitions_exported": bool(export_full_partitions),
            "evidence_ids": manifest["evidence_ids"],
            "configuration_snapshot_sha256": manifest["configuration_snapshot"].get(
                "snapshot_sha256", ""
            ),
        },
    )
    return {
        "run_id": run_id,
        "analysis_run_id": run_id,
        "run_directory": str(run_dir),
        "manifest": str(manifest_path),
        "saved_files": saved_files,
        "full_partition_files": partition_files,
    }


def load_latest_partition_manifest(case_id: str) -> dict[str, Any] | None:
    return load_latest_manifest(case_id, ("results", "filtered_windows"))


def attach_partition_report(
    case_id: str,
    *,
    run_id: str,
    report_path: str | Path,
) -> dict[str, Any]:
    manifest = attach_report(
        case_id,
        root_parts=("results", "filtered_windows"),
        run_id=run_id,
        report_path=report_path,
        report_field="consolidated_excel_report",
    )
    log_case_event(
        case_id,
        action="TOWER_PARTITION_REPORT_ATTACHED",
        details={
            "run_id": str(run_id),
            "report_fingerprint": manifest.get("report_fingerprint", {}),
        },
    )
    return manifest
