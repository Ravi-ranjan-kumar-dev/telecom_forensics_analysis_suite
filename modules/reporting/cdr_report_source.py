"""Immutable source-data links for CDR investigator reports."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from modules.core.paths import PROJECT_ROOT


LINK_SCHEMA_VERSION = 1
MAX_RELATED_RECORDS = 1000
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_-]+")
_PHONE_COLUMN = re.compile(
    r"(?:^|_)(?:a_party|b_party|target|contact|calling|called|source|"
    r"destination|msisdn|subscriber|mobile|phone)(?:_|$)",
    re.IGNORECASE,
)
_CELL_COLUMN = re.compile(r"(?:^|_)(?:cell(?:_?id)?|cgi|tower)(?:_|$)", re.IGNORECASE)
_IMEI_COLUMN = re.compile(r"(?:^|_)(?:imei|device_?id)(?:_|$)", re.IGNORECASE)
_IMSI_COLUMN = re.compile(r"(?:^|_)(?:imsi|sim_?id)(?:_|$)", re.IGNORECASE)
_IDENTIFIER_COLUMNS = {
    "phone": _PHONE_COLUMN,
    "cell_id": _CELL_COLUMN,
    "imei": _IMEI_COLUMN,
    "imsi": _IMSI_COLUMN,
}


class SourceLinkError(RuntimeError):
    """Raised when a report source link cannot be trusted."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_component(value: object, fallback: str) -> str:
    text = _SAFE_NAME.sub("_", str(value or "").strip()).strip("_")
    return text or fallback


def _portable_path(path: Path) -> str:
    """Return a project-relative path and reject paths outside the project."""

    resolved = path.expanduser().resolve(strict=False)
    try:
        return str(resolved.relative_to(PROJECT_ROOT.resolve(strict=False)))
    except ValueError as error:
        raise SourceLinkError(f"CDR source path is outside the project: {resolved}") from error


def _resolve_portable_path(value: object) -> Path:
    """Resolve one project-relative link without allowing path traversal."""

    text = str(value or "").strip()
    if not text or Path(text).is_absolute():
        raise SourceLinkError("The CDR source link contains an unsafe path.")
    path = (PROJECT_ROOT / text).resolve(strict=False)
    _portable_path(path)
    return path


def report_source_link_path(report_path: str | Path) -> Path:
    """Return the deterministic source-link sidecar for one report."""

    report = Path(report_path).expanduser().resolve(strict=False)
    return report.with_name(f"{report.stem}_source_link.json")


def create_cdr_source_run(
    *,
    case_id: str,
    analysis_run_id: str,
    target_frames: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    """Save one immutable Parquet dataset per target for an analysis run."""

    import duckdb

    run_id = _safe_component(analysis_run_id, "analysis")
    run_root = (
        PROJECT_ROOT
        / "cases"
        / "active"
        / str(case_id)
        / "staging"
        / "cdr_report_runs"
        / run_id
    ).resolve(strict=False)
    dataset_root = run_root / "parquet"
    dataset_root.mkdir(parents=True, exist_ok=True)

    datasets: list[dict[str, Any]] = []
    for index, (target, frame) in enumerate(target_frames.items(), start=1):
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        target_text = str(target).strip()
        filename = f"{index:03d}_{_safe_component(target_text, 'target')}.parquet"
        path = dataset_root / filename
        if path.exists():
            raise SourceLinkError(f"Immutable CDR dataset already exists: {path}")

        connection = duckdb.connect(database=":memory:")
        try:
            connection.register("source_frame", frame)
            path_literal = str(path).replace("'", "''")
            connection.execute(
                f"COPY source_frame TO '{path_literal}' "
                "(FORMAT PARQUET, COMPRESSION SNAPPY)",
            )
        finally:
            connection.close()

        datasets.append(
            {
                "target": target_text,
                "path": _portable_path(path),
                "sha256": _sha256(path),
                "record_count": int(len(frame)),
                "columns": list(map(str, frame.columns)),
            }
        )

    if not datasets:
        raise SourceLinkError("No valid CDR records were available for source linking.")

    manifest = {
        "schema_version": LINK_SCHEMA_VERSION,
        "case_id": str(case_id),
        "analysis_run_id": str(analysis_run_id),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "datasets": datasets,
    }
    manifest_path = run_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    manifest["manifest_path"] = _portable_path(manifest_path)
    manifest["manifest_sha256"] = _sha256(manifest_path)
    return manifest


def link_report_to_source(
    report_path: str | Path,
    source_run: dict[str, Any],
    *,
    targets: Iterable[str] | None = None,
) -> Path:
    """Write a verified report-to-dataset link without changing the workbook."""

    report = Path(report_path).expanduser().resolve(strict=True)
    selected_targets = {str(value).strip() for value in (targets or [])}
    datasets = [
        dict(item)
        for item in source_run.get("datasets", [])
        if isinstance(item, dict)
        and (not selected_targets or str(item.get("target", "")) in selected_targets)
    ]
    if not datasets:
        raise SourceLinkError("No matching CDR dataset was found for this report.")

    payload = {
        "schema_version": LINK_SCHEMA_VERSION,
        "case_id": str(source_run.get("case_id", "")),
        "analysis_run_id": str(source_run.get("analysis_run_id", "")),
        "report_path": _portable_path(report),
        "report_sha256": _sha256(report),
        "manifest_path": str(source_run.get("manifest_path", "")),
        "manifest_sha256": str(source_run.get("manifest_sha256", "")),
        "targets": sorted(selected_targets),
        "datasets": datasets,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
    }
    link_path = report_source_link_path(report)
    temporary = link_path.with_suffix(f"{link_path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(link_path)
    return link_path


def load_verified_source_link(report_path: str | Path) -> dict[str, Any] | None:
    """Load a source link and verify the report, manifest and dataset hashes."""

    report = Path(report_path).expanduser().resolve(strict=False)
    link_path = report_source_link_path(report)
    if not link_path.is_file():
        return None
    if not report.is_file():
        raise SourceLinkError("The linked report file is missing.")

    try:
        payload = json.loads(link_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SourceLinkError(f"The report source link is unreadable: {error}") from error

    if int(payload.get("schema_version", 0)) != LINK_SCHEMA_VERSION:
        raise SourceLinkError("The report source link version is not supported.")
    if str(payload.get("report_path", "")) != _portable_path(report):
        raise SourceLinkError("The source link belongs to a different report.")
    if _sha256(report) != str(payload.get("report_sha256", "")):
        raise SourceLinkError("The report changed after its source link was created.")

    manifest_path = _resolve_portable_path(payload.get("manifest_path"))
    if not manifest_path.is_file():
        raise SourceLinkError("The immutable CDR source manifest is missing.")
    if _sha256(manifest_path) != str(payload.get("manifest_sha256", "")):
        raise SourceLinkError("The immutable CDR source manifest failed verification.")

    datasets = payload.get("datasets", [])
    if not isinstance(datasets, list) or not datasets:
        raise SourceLinkError("The report has no linked CDR dataset.")
    for item in datasets:
        path = _resolve_portable_path(item.get("path"))
        if not path.is_file():
            raise SourceLinkError(f"A linked CDR dataset is missing: {path.name}")
        if _sha256(path) != str(item.get("sha256", "")):
            raise SourceLinkError(f"A linked CDR dataset failed verification: {path.name}")
    return payload


def query_related_records(
    source_link: dict[str, Any],
    identifier: str,
    *,
    identifier_type: str = "phone",
    limit: int = MAX_RELATED_RECORDS,
    ) -> pd.DataFrame:
    """Query linked Parquet files for one typed telecom identifier."""

    import duckdb

    column_pattern = _IDENTIFIER_COLUMNS.get(identifier_type)
    if column_pattern is None:
        raise ValueError(f"Unsupported identifier type: {identifier_type}")

    raw_value = str(identifier or "").strip()
    if identifier_type == "phone":
        digits = re.sub(r"\D", "", raw_value)
        canonical = digits[-10:] if len(digits) >= 10 else digits
    elif identifier_type == "cell_id":
        canonical = re.sub(r"[^0-9]", "", raw_value)
    else:
        canonical = re.sub(r"\D", "", raw_value)
    if not canonical:
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    remaining = max(1, min(int(limit), MAX_RELATED_RECORDS))
    for dataset in source_link.get("datasets", []):
        if remaining <= 0:
            break
        path = _resolve_portable_path(dataset.get("path"))
        columns = [str(value) for value in dataset.get("columns", [])]
        identifier_columns = [
            column for column in columns if column_pattern.search(column)
        ]
        if not identifier_columns:
            continue

        predicates: list[str] = []
        parameters: list[Any] = [str(path)]

        for column in identifier_columns:
            quoted = '"' + column.replace('"', '""') + '"'

            text_value = f"trim(CAST({quoted} AS VARCHAR))"
            without_float_suffix = (
                f"regexp_replace({text_value}, '\\.0+$', '', 'g')"
            )
            normalized = (
                f"regexp_replace("
                f"{without_float_suffix}, "
                f"'[^0-9]', '', 'g'"
                f")"
            )

            if identifier_type == "phone":
                normalized = f"right({normalized}, 10)"

            predicates.append(f"{normalized} = ?")
            parameters.append(canonical)

        if not predicates:
            continue

        parameters.append(remaining)
        sql = (
            "SELECT * FROM read_parquet(?) WHERE "
            + " OR ".join(predicates)
            + " LIMIT ?"
        )
        connection = duckdb.connect(database=":memory:", read_only=False)
        try:
            frame = connection.execute(sql, parameters).fetchdf()
        finally:
            connection.close()
        if not frame.empty:
            target_column = (
                "Linked Target"
                if "Source Target" in frame.columns
                else "Source Target"
            )
            frame.insert(0, target_column, str(dataset.get("target", "")))
            frames.append(frame)
            remaining -= len(frame)

    return (
        pd.concat(frames, ignore_index=True, sort=False)
        if frames
        else pd.DataFrame()
    )
