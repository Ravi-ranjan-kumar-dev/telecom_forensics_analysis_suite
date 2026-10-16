"""Flexible file and folder selection from anywhere on the computer."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Iterable

from modules.core.paths import PROJECT_ROOT


def resolve_user_path(path_value: str | Path) -> Path:
    """Resolve any file or folder path on the computer (supports ~, env vars, relative/absolute)."""
    expanded = os.path.expandvars(os.path.expanduser(str(path_value or "").strip()))
    return Path(expanded).resolve(strict=False)


def stage_selected_files_as_folder(
    files: Iterable[str | Path],
    *,
    workflow: str = "general",
    case_id: str = "DEV-WORKSPACE",
) -> Path:
    """Create a clean staging folder linking/copying arbitrary files selected from anywhere on the PC."""
    file_list = [resolve_user_path(f) for f in files if str(f or "").strip()]
    valid_files = [f for f in file_list if f.is_file()]
    if not valid_files:
        raise FileNotFoundError("None of the selected files exist.")

    digest = hashlib.sha256(
        "|".join(sorted(str(f) for f in valid_files)).encode("utf-8")
    ).hexdigest()[:12]

    safe_case = "".join(
        c if c.isalnum() or c in "-_" else "_"
        for c in str(case_id or "DEV-WORKSPACE")
    )
    stage_dir = (
        PROJECT_ROOT
        / "cases"
        / "active"
        / safe_case
        / "staging"
        / "selected_files"
        / f"{workflow}_{digest}"
    )
    if stage_dir.exists():
        shutil.rmtree(stage_dir, ignore_errors=True)
    stage_dir.mkdir(parents=True, exist_ok=True)

    used_names: set[str] = set()
    for src in valid_files:
        name = src.name
        if name.lower() in used_names:
            stem, suffix = src.stem, src.suffix
            counter = 2
            while f"{stem}_{counter}{suffix}".lower() in used_names:
                counter += 1
            name = f"{stem}_{counter}{suffix}"
        used_names.add(name.lower())
        dst = stage_dir / name
        shutil.copy2(src, dst)

    return stage_dir


def ensure_folder_input(
    path_or_files: str | Path | list[str | Path] | tuple[str | Path, ...],
    *,
    workflow: str = "general",
    case_id: str = "DEV-WORKSPACE",
) -> Path:
    """Accept a folder path, a single file path, or a list of file paths from anywhere on the PC."""
    if isinstance(path_or_files, (list, tuple, set)):
        items = [resolve_user_path(p) for p in path_or_files if str(p or "").strip()]
        if len(items) == 1 and items[0].is_dir():
            return items[0]
        return stage_selected_files_as_folder(items, workflow=workflow, case_id=case_id)

    raw_text = str(path_or_files or "").strip()
    if ";" in raw_text and not Path(raw_text).exists():
        parts = [p.strip() for p in raw_text.split(";") if p.strip()]
        return stage_selected_files_as_folder(parts, workflow=workflow, case_id=case_id)

    resolved = resolve_user_path(raw_text)
    if resolved.is_dir():
        return resolved
    if resolved.is_file():
        return stage_selected_files_as_folder([resolved], workflow=workflow, case_id=case_id)
    return resolved
