"""Deterministic Spot-folder discovery for Tower Dump inputs.

Folder contract:
    input/
        Spot A/
            operator/cell files...
        Spot B/
            operator/cell files...

Each immediate child directory of the supplied input folder represents
one investigation Spot. Deeper folders remain part of that same Spot.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT_SPOT_ID = "UNASSIGNED-ROOT"
ROOT_SPOT_NAME = "ROOT_LEVEL_FILES"


def normalize_selected_spot_folders(
    root_folder: str | Path,
    selected_spot_folders: Iterable[str],
) -> tuple[str, ...]:
    """Return validated immediate Spot folder names."""

    root = Path(
        root_folder
    ).expanduser().resolve()

    if not root.is_dir():
        raise FileNotFoundError(
            f"Tower Dump parent folder not found: {root}"
        )

    selected: dict[str, str] = {}

    for value in selected_spot_folders:
        name = str(
            value
        ).strip()

        if (
            not name
            or name in {
                ".",
                "..",
            }
            or "/" in name
            or "\\" in name
            or "\x00" in name
            or Path(name).is_absolute()
        ):
            raise ValueError(
                f"Unsafe Spot folder name: {value!r}"
            )

        candidate = (
            root
            / name
        ).resolve(
            strict=False
        )

        try:
            relative = candidate.relative_to(
                root
            )
        except ValueError as error:
            raise ValueError(
                f"Spot folder is outside the parent folder: {name}"
            ) from error

        if (
            len(relative.parts) != 1
            or not candidate.is_dir()
        ):
            raise ValueError(
                f"Spot folder was not found under the parent folder: {name}"
            )

        selected.setdefault(
            name,
            name,
        )

    return tuple(
        sorted(
            selected.values(),
            key=lambda item: (
                item.casefold(),
                item,
            ),
        )
    )


def select_tower_evidence_files(
    root_folder: str | Path,
    candidate_files: Iterable[str | Path],
    *,
    selected_spot_folders: Iterable[str] | None = None,
    include_root_files: bool = True,
) -> list[Path]:
    """Filter evidence files using validated immediate Spot folders."""

    root = Path(
        root_folder
    ).expanduser().resolve()

    selected = (
        None
        if selected_spot_folders is None
        else set(
            normalize_selected_spot_folders(
                root,
                selected_spot_folders,
            )
        )
    )

    output: set[Path] = set()

    for value in candidate_files:
        path = Path(
            value
        ).expanduser().resolve(
            strict=False
        )

        if not path.is_file():
            continue

        try:
            relative = path.relative_to(
                root
            )
        except ValueError:
            continue

        is_root_file = len(
            relative.parts
        ) == 1

        if is_root_file:
            if include_root_files:
                output.add(
                    path
                )
            continue

        if (
            selected is None
            or relative.parts[0] in selected
        ):
            output.add(
                path
            )

    return sorted(
        output,
        key=lambda path: str(
            path.relative_to(
                root
            )
        ).casefold(),
    )


def build_tower_spot_layout(
    root_folder: str | Path,
    files: Iterable[str | Path],
) -> dict[str, Any]:
    """Resolve every input file to one deterministic Spot."""

    root = Path(root_folder).expanduser().resolve()
    resolved_files = sorted(
        {
            Path(file_path).expanduser().resolve()
            for file_path in files
        },
        key=lambda path: str(path).casefold(),
    )

    relative_paths: dict[Path, Path] = {}
    folder_names: set[str] = set()
    root_level_files: list[Path] = []

    for path in resolved_files:
        try:
            relative = path.relative_to(root)
        except ValueError:
            relative = Path(path.name)

        relative_paths[path] = relative

        if len(relative.parts) >= 2:
            folder_names.add(relative.parts[0])
        else:
            root_level_files.append(path)

    ordered_folders = sorted(
        folder_names,
        key=lambda value: (value.casefold(), value),
    )

    spot_id_by_folder = {
        folder_name: f"SPOT-{index:02d}"
        for index, folder_name in enumerate(
            ordered_folders,
            start=1,
        )
    }

    assignments: dict[str, dict[str, Any]] = {}
    summary_counter: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "spot_id": "",
            "spot_name": "",
            "spot_folder": "",
            "files_found": 0,
        }
    )

    for path in resolved_files:
        relative = relative_paths[path]

        if len(relative.parts) >= 2:
            spot_folder = relative.parts[0]
            spot_id = spot_id_by_folder[spot_folder]
            spot_name = spot_folder
            is_root_file = False
        else:
            spot_folder = "."
            spot_id = ROOT_SPOT_ID
            spot_name = ROOT_SPOT_NAME
            is_root_file = True

        assignment = {
            "spot_id": spot_id,
            "spot_name": spot_name,
            "spot_folder": spot_folder,
            "source_relative_path": str(relative),
            "is_root_file": is_root_file,
        }

        assignments[str(path)] = assignment

        counter = summary_counter[spot_id]
        counter["spot_id"] = spot_id
        counter["spot_name"] = spot_name
        counter["spot_folder"] = spot_folder
        counter["files_found"] += 1

    spot_summary = sorted(
        summary_counter.values(),
        key=lambda item: (
            item["spot_id"] == ROOT_SPOT_ID,
            item["spot_id"],
        ),
    )

    folder_spot_count = len(ordered_folders)

    if folder_spot_count >= 2:
        input_mode = "MULTI_SPOT"
    elif folder_spot_count == 1:
        input_mode = "SINGLE_SPOT_FOLDER"
    else:
        input_mode = "LEGACY_ROOT_FILES"

    warnings: list[str] = []

    if folder_spot_count and root_level_files:
        warnings.append(
            f"{len(root_level_files)} root-level Tower Dump file(s) kisi "
            "Spot folder ke andar nahi hain. Inhe UNASSIGNED-ROOT mark kiya gaya."
        )

    if folder_spot_count == 1:
        warnings.append(
            "Sirf ek Spot folder mila. Cross-Spot comparison ke liye "
            "kam se kam do Spot folders required hain."
        )

    return {
        "input_mode": input_mode,
        "spot_count": folder_spot_count,
        "spot_names": ordered_folders,
        "root_level_file_count": len(root_level_files),
        "assignments": assignments,
        "spot_summary": spot_summary,
        "warnings": warnings,
    }
