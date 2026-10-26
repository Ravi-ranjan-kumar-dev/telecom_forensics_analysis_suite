"""Selection-aware Tower IPDR evidence input fingerprint.

Read-only: inspects supported input filenames and file metadata only.
The implementation was moved verbatim from tower_ipdr_controller.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


def _tower_ipdr_input_fingerprint(
    input_folder: str | Path | None = None,
    *,
    selected_spot_folders: Iterable[str] | None = None,
    include_root_files: bool = True,
) -> dict:
    """Return a selection-aware Tower IPDR input fingerprint."""

    from modules.loader.tower_spot_layout import (
        normalize_selected_spot_folders,
        select_tower_evidence_files,
    )

    input_dir = (
        Path(
            input_folder
        ).expanduser().resolve()
        if input_folder is not None
        else Path(
            "data/tower_dump/ipdr/input"
        ).resolve(
            strict=False
        )
    )
    allowed_suffixes = {
        ".csv",
        ".txt",
        ".xlsx",
        ".xls",
    }
    normalized_selection: tuple[str, ...] | None = None
    files = []
    total_size = 0

    if input_dir.is_dir():
        if selected_spot_folders is not None:
            normalized_selection = normalize_selected_spot_folders(
                input_dir,
                selected_spot_folders,
            )

        candidates = [
            file_path
            for file_path in input_dir.rglob("*")
            if (
                file_path.is_file()
                and file_path.suffix.lower()
                in allowed_suffixes
            )
        ]
        selected_files = select_tower_evidence_files(
            input_dir,
            candidates,
            selected_spot_folders=normalized_selection,
            include_root_files=include_root_files,
        )

        for file_path in selected_files:
            stat = file_path.stat()
            files.append(
                {
                    "path": file_path.relative_to(
                        input_dir
                    ).as_posix(),
                    "size": int(
                        stat.st_size
                    ),
                    "mtime_ns": int(
                        stat.st_mtime_ns
                    ),
                }
            )
            total_size += int(
                stat.st_size
            )

    return {
        "input_dir": str(
            input_dir
        ),
        "selected_spot_folders": (
            list(
                normalized_selection
            )
            if normalized_selection is not None
            else None
        ),
        "include_root_files": bool(
            include_root_files
        ),
        "file_count": len(
            files
        ),
        "total_size": total_size,
        "files": files,
    }
