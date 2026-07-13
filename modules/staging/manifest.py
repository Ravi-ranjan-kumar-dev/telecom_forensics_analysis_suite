from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


STATUS_PENDING = "PENDING"
STATUS_LOADING = "LOADING"
STATUS_LOADED = "LOADED"
STATUS_FAILED = "FAILED"
STATUS_SKIPPED_DUPLICATE = "SKIPPED_DUPLICATE"
STATUS_SKIPPED_ALREADY_LOADED = "SKIPPED_ALREADY_LOADED"


@dataclass(frozen=True)
class ManifestRecord:
    file_name: str
    source_path: str
    sha256: str
    size_bytes: int
    status: str
    rows_loaded: int = 0
    started_at: str = ""
    completed_at: str = ""
    error_type: str = ""
    error_message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ManifestSummary:
    manifest_path: str
    total_records: int
    loaded: int
    failed: int
    pending: int
    skipped_duplicate: int
    skipped_already_loaded: int

    def to_dict(self) -> dict:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def calculate_sha256(
    path: str | Path,
    *,
    chunk_size: int = 1024 * 1024,
) -> str:
    """Calculate SHA-256 hash without loading full file into memory."""

    file_path = Path(path).expanduser().resolve()
    digest = hashlib.sha256()

    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def make_manifest_record(
    path: str | Path,
    *,
    status: str = STATUS_PENDING,
    rows_loaded: int = 0,
    calculate_hash: bool = True,
) -> ManifestRecord:
    file_path = Path(path).expanduser().resolve()

    sha256 = (
        calculate_sha256(file_path)
        if calculate_hash and file_path.exists()
        else ""
    )

    return ManifestRecord(
        file_name=file_path.name,
        source_path=str(file_path),
        sha256=sha256,
        size_bytes=_safe_size(file_path),
        status=status,
        rows_loaded=rows_loaded,
    )


def _record_key(record: ManifestRecord) -> str:
    if record.sha256:
        return record.sha256

    return f"{record.source_path}|{record.size_bytes}"


def read_manifest(
    manifest_path: str | Path,
) -> list[ManifestRecord]:
    path = Path(manifest_path).expanduser().resolve()

    if not path.exists():
        return []

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            raw = json.load(handle)
    except Exception:
        return []

    if not isinstance(raw, list):
        return []

    records: list[ManifestRecord] = []

    for item in raw:
        if not isinstance(item, dict):
            continue

        records.append(
            ManifestRecord(
                file_name=str(item.get("file_name", "")),
                source_path=str(item.get("source_path", "")),
                sha256=str(item.get("sha256", "")),
                size_bytes=int(item.get("size_bytes", 0) or 0),
                status=str(item.get("status", STATUS_PENDING)),
                rows_loaded=int(item.get("rows_loaded", 0) or 0),
                started_at=str(item.get("started_at", "")),
                completed_at=str(item.get("completed_at", "")),
                error_type=str(item.get("error_type", "")),
                error_message=str(item.get("error_message", "")),
            )
        )

    return records


def write_manifest(
    manifest_path: str | Path,
    records: Iterable[ManifestRecord],
) -> Path:
    path = Path(manifest_path).expanduser().resolve()
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = [
        record.to_dict()
        for record in records
    ]

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temporary.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            payload,
            handle,
            indent=2,
            ensure_ascii=False,
        )
        handle.write("\n")

    temporary.replace(path)
    return path


def upsert_manifest_record(
    manifest_path: str | Path,
    record: ManifestRecord,
) -> list[ManifestRecord]:
    records = read_manifest(manifest_path)

    incoming_key = _record_key(record)
    updated: list[ManifestRecord] = []
    replaced = False

    for old_record in records:
        if _record_key(old_record) == incoming_key:
            updated.append(record)
            replaced = True
        else:
            updated.append(old_record)

    if not replaced:
        updated.append(record)

    write_manifest(
        manifest_path,
        updated,
    )

    return updated


def mark_file_loading(
    manifest_path: str | Path,
    path: str | Path,
) -> ManifestRecord:
    record = make_manifest_record(
        path,
        status=STATUS_LOADING,
    )

    record = ManifestRecord(
        **{
            **record.to_dict(),
            "started_at": _now_iso(),
        }
    )

    upsert_manifest_record(
        manifest_path,
        record,
    )

    return record


def mark_file_loaded(
    manifest_path: str | Path,
    path: str | Path,
    *,
    rows_loaded: int,
) -> ManifestRecord:
    record = make_manifest_record(
        path,
        status=STATUS_LOADED,
        rows_loaded=rows_loaded,
    )

    record = ManifestRecord(
        **{
            **record.to_dict(),
            "completed_at": _now_iso(),
        }
    )

    upsert_manifest_record(
        manifest_path,
        record,
    )

    return record


def mark_file_failed(
    manifest_path: str | Path,
    path: str | Path,
    *,
    error: BaseException,
) -> ManifestRecord:
    record = make_manifest_record(
        path,
        status=STATUS_FAILED,
    )

    record = ManifestRecord(
        **{
            **record.to_dict(),
            "completed_at": _now_iso(),
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
    )

    upsert_manifest_record(
        manifest_path,
        record,
    )

    return record


def is_file_already_loaded(
    manifest_path: str | Path,
    path: str | Path,
) -> bool:
    candidate = make_manifest_record(path)
    candidate_key = _record_key(candidate)

    for record in read_manifest(manifest_path):
        if (
            _record_key(record) == candidate_key
            and record.status == STATUS_LOADED
        ):
            return True

    return False


def summarize_manifest(
    manifest_path: str | Path,
) -> ManifestSummary:
    records = read_manifest(manifest_path)

    def count(status: str) -> int:
        return sum(
            1
            for record in records
            if record.status == status
        )

    return ManifestSummary(
        manifest_path=str(
            Path(manifest_path).expanduser().resolve()
        ),
        total_records=len(records),
        loaded=count(STATUS_LOADED),
        failed=count(STATUS_FAILED),
        pending=count(STATUS_PENDING) + count(STATUS_LOADING),
        skipped_duplicate=count(STATUS_SKIPPED_DUPLICATE),
        skipped_already_loaded=count(STATUS_SKIPPED_ALREADY_LOADED),
    )


def write_manifest_csv(
    manifest_path: str | Path,
    csv_path: str | Path,
) -> Path:
    records = read_manifest(manifest_path)
    output = Path(csv_path).expanduser().resolve()
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = [
        "file_name",
        "source_path",
        "sha256",
        "size_bytes",
        "status",
        "rows_loaded",
        "started_at",
        "completed_at",
        "error_type",
        "error_message",
    ]

    with output.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()

        for record in records:
            writer.writerow(record.to_dict())

    return output


def print_manifest_summary(
    manifest_path: str | Path,
) -> None:
    summary = summarize_manifest(manifest_path)

    print("\nMANIFEST SUMMARY")
    print("-" * 70)
    print(f"Manifest path          : {summary.manifest_path}")
    print(f"Total records          : {summary.total_records}")
    print(f"Loaded                 : {summary.loaded}")
    print(f"Failed                 : {summary.failed}")
    print(f"Pending/loading        : {summary.pending}")
    print(f"Skipped duplicate      : {summary.skipped_duplicate}")
    print(f"Skipped already loaded : {summary.skipped_already_loaded}")