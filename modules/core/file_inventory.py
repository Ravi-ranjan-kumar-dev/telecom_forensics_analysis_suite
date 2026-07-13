#common inventory utility file
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_SUPPORTED_SUFFIXES = {
    ".csv",
    ".txt",
    ".xlsx",
    ".xls",
}


@dataclass(frozen=True)
class FileInventoryItem:
    path: str
    name: str
    suffix: str
    size_bytes: int
    size_mb: float
    is_supported: bool
    estimated_rows: int | None


@dataclass(frozen=True)
class FileInventory:
    folder: str
    recursive: bool
    file_count: int
    supported_file_count: int
    unsupported_file_count: int
    total_size_bytes: int
    total_size_mb: float
    estimated_rows: int | None
    largest_file: str | None
    largest_file_size_mb: float
    files: list[FileInventoryItem]

    def to_dict(self) -> dict:
        return asdict(self)


def _normalise_suffixes(
    suffixes: Iterable[str] | None,
) -> set[str]:
    if suffixes is None:
        suffixes = DEFAULT_SUPPORTED_SUFFIXES

    result: set[str] = set()

    for suffix in suffixes:
        value = str(suffix).strip().lower()

        if not value:
            continue

        if not value.startswith("."):
            value = f".{value}"

        result.add(value)

    return result


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _estimate_text_rows(
    path: Path,
    *,
    max_sample_bytes: int = 1024 * 1024,
) -> int | None:
    """Estimate CSV/TXT rows without loading the full file."""

    suffix = path.suffix.lower()

    if suffix not in {".csv", ".txt"}:
        return None

    size = _safe_size(path)

    if size == 0:
        return 0

    sample_size = min(size, max_sample_bytes)

    try:
        with path.open("rb") as handle:
            sample = handle.read(sample_size)
    except OSError:
        return None

    if not sample:
        return 0

    line_count = sample.count(b"\n")

    if line_count <= 0:
        return 1

    if sample_size >= size:
        return line_count

    estimated = int((line_count / sample_size) * size)
    return max(estimated, line_count)


def _iter_files(
    folder: Path,
    *,
    recursive: bool,
) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        return []

    pattern = "**/*" if recursive else "*"

    return sorted(
        path
        for path in folder.glob(pattern)
        if path.is_file()
    )


def scan_input_folder(
    folder: str | Path,
    *,
    supported_suffixes: Iterable[str] | None = None,
    recursive: bool = True,
    estimate_rows: bool = True,
) -> FileInventory:
    """Scan an analysis input folder.

    This function does not modify any evidence file.
    It only reads metadata and a small sample from CSV/TXT files.
    """

    input_folder = Path(folder).expanduser().resolve()
    supported = _normalise_suffixes(supported_suffixes)

    items: list[FileInventoryItem] = []

    for path in _iter_files(input_folder, recursive=recursive):
        size_bytes = _safe_size(path)
        suffix = path.suffix.lower()
        is_supported = suffix in supported

        row_estimate = (
            _estimate_text_rows(path)
            if estimate_rows and is_supported
            else None
        )

        items.append(
            FileInventoryItem(
                path=str(path),
                name=path.name,
                suffix=suffix,
                size_bytes=size_bytes,
                size_mb=round(size_bytes / (1024 * 1024), 3),
                is_supported=is_supported,
                estimated_rows=row_estimate,
            )
        )

    total_size = sum(item.size_bytes for item in items)

    supported_items = [
        item
        for item in items
        if item.is_supported
    ]

    unsupported_items = [
        item
        for item in items
        if not item.is_supported
    ]

    row_values = [
        item.estimated_rows
        for item in supported_items
        if item.estimated_rows is not None
    ]

    largest = max(
        items,
        key=lambda item: item.size_bytes,
        default=None,
    )

    return FileInventory(
        folder=str(input_folder),
        recursive=recursive,
        file_count=len(items),
        supported_file_count=len(supported_items),
        unsupported_file_count=len(unsupported_items),
        total_size_bytes=total_size,
        total_size_mb=round(total_size / (1024 * 1024), 3),
        estimated_rows=sum(row_values) if row_values else None,
        largest_file=largest.name if largest else None,
        largest_file_size_mb=largest.size_mb if largest else 0.0,
        files=items,
    )


def print_inventory_summary(
    inventory: FileInventory,
    *,
    max_files: int = 20,
) -> None:
    """Print a small CLI-friendly inventory summary."""

    print("\nINPUT INVENTORY")
    print("-" * 70)
    print(f"Folder              : {inventory.folder}")
    print(f"Recursive           : {inventory.recursive}")
    print(f"Total files         : {inventory.file_count}")
    print(f"Supported files     : {inventory.supported_file_count}")
    print(f"Unsupported files   : {inventory.unsupported_file_count}")
    print(f"Total size          : {inventory.total_size_mb:,.3f} MB")
    print(f"Estimated rows      : {inventory.estimated_rows}")
    print(f"Largest file        : {inventory.largest_file}")
    print(f"Largest file size   : {inventory.largest_file_size_mb:,.3f} MB")

    if not inventory.files:
        print("\nNo files found.")
        return

    print("\nFiles:")
    print("-" * 70)

    for number, item in enumerate(inventory.files[:max_files], start=1):
        status = "SUPPORTED" if item.is_supported else "UNSUPPORTED"

        print(
            f"{number:>3}. {status:<11} "
            f"{item.size_mb:>10,.3f} MB  "
            f"rows≈{str(item.estimated_rows):<10} "
            f"{item.name}"
        )

    remaining = len(inventory.files) - max_files

    if remaining > 0:
        print(f"... {remaining} more file(s)")