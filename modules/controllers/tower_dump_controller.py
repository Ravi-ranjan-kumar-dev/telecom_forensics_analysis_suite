"""Unified Tower Dump Analysis workspace.

The workspace groups all location/tower-originated source types:
- Tower CDR Dump
- Tower GPRS Dump
- Tower IPDR Dump
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Iterable


TOWER_DUMP_SOURCE_TYPES = (
    "cdr",
    "gprs",
    "ipdr",
)

TOWER_DUMP_SOURCE_SUFFIXES = {
    "cdr": frozenset(
        {
            ".csv",
            ".txt",
            ".tsv",
            ".xlsx",
            ".xls",
        }
    ),
    "gprs": frozenset(
        {
            ".csv",
            ".txt",
        }
    ),
    "ipdr": frozenset(
        {
            ".csv",
            ".txt",
        }
    ),
}

TOWER_DUMP_PARTITION_WORKFLOWS = {
    "cdr": "tower_cdr",
    "gprs": "tower_gprs",
    "ipdr": "tower_ipdr",
}


def _normalize_source_type(
    source_type: str,
) -> str:
    """Return one validated Tower Dump source type."""

    normalized_source = str(
        source_type
    ).strip().casefold()

    if normalized_source not in TOWER_DUMP_SOURCE_TYPES:
        raise ValueError(
            f"Unsupported Tower Dump source type: {source_type}"
        )

    return normalized_source


def _normalize_analysis_request(
    *,
    source_type: str,
    input_folder: str | Path,
    selected_spot_folders: Iterable[str] | None,
    include_root_files: bool,
) -> tuple[str, Path, dict[str, Any]]:
    """Validate shared complete and Date-Time Part analysis inputs."""

    normalized_source = _normalize_source_type(
        source_type
    )
    folder_text = str(
        input_folder
    ).strip()

    if not folder_text:
        raise ValueError(
            "Tower Dump input folder is required."
        )

    folder = Path(
        folder_text
    ).expanduser().resolve()

    if not folder.is_dir():
        raise FileNotFoundError(
            f"Tower Dump input folder not found: {folder}"
        )

    normalized_selection = (
        None
        if selected_spot_folders is None
        else tuple(
            str(value)
            for value in selected_spot_folders
            if str(value).strip()
        )
    )

    if (
        selected_spot_folders is not None
        and not normalized_selection
    ):
        raise ValueError(
            "Select at least one Tower Dump Spot folder."
        )

    selection_kwargs: dict[str, Any] = {}

    if (
        normalized_selection is not None
        or not include_root_files
    ):
        selection_kwargs = {
            "selected_spot_folders": normalized_selection,
            "include_root_files": bool(
                include_root_files
            ),
        }

    return (
        normalized_source,
        folder,
        selection_kwargs,
    )


def run_complete_tower_dump_analysis(
    case: dict[str, Any],
    *,
    source_type: str,
    input_folder: str | Path,
    selected_spot_folders: Iterable[str] | None = None,
    include_root_files: bool = True,
) -> dict[str, Any] | None:
    """Run one complete Tower Dump workflow without CLI prompts."""

    (
        normalized_source,
        folder,
        selection_kwargs,
    ) = _normalize_analysis_request(
        source_type=source_type,
        input_folder=input_folder,
        selected_spot_folders=selected_spot_folders,
        include_root_files=include_root_files,
    )

    if normalized_source == "cdr":
        from modules.controllers.tower_cdr_controller import (
            _run_complete_analysis,
        )

        return _run_complete_analysis(
            case,
            input_folder=folder,
            **selection_kwargs,
        )

    if normalized_source == "gprs":
        from modules.controllers.tower_gprs_controller import (
            _execute,
        )

        return _execute(
            case,
            use_partitions=False,
            input_folder=folder,
            **selection_kwargs,
        )

    from modules.controllers.tower_ipdr_controller import (
        _run_complete_tower_ipdr_analysis,
    )

    return _run_complete_tower_ipdr_analysis(
        case,
        input_folder=folder,
        **selection_kwargs,
    )


def list_tower_dump_date_time_parts(
    case: dict[str, Any],
    *,
    source_type: str,
) -> list[dict[str, Any]]:
    """Return saved Date-Time Parts for one Tower Dump source type."""

    from modules.cases.date_time_partitions import (
        list_date_time_parts,
    )

    normalized_source = _normalize_source_type(
        source_type
    )
    case_id = str(
        case.get(
            "case_id",
            "",
        )
    ).strip()

    if not case_id:
        raise ValueError(
            "Active case ID is required."
        )

    return list_date_time_parts(
        case_id,
        TOWER_DUMP_PARTITION_WORKFLOWS[
            normalized_source
        ],
    )


def save_tower_dump_date_time_parts(
    case: dict[str, Any],
    *,
    source_type: str,
    part_specs: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Validate and save GUI Date-Time Parts using the canonical store."""

    from modules.cases.date_time_partitions import (
        find_overlapping_date_time_parts,
        save_spot_date_time_parts,
    )

    normalized_source = _normalize_source_type(
        source_type
    )
    case_id = str(
        case.get(
            "case_id",
            "",
        )
    ).strip()

    if not case_id:
        raise ValueError(
            "Active case ID is required."
        )

    specifications = [
        dict(item)
        for item in part_specs
        if isinstance(
            item,
            dict,
        )
    ]

    if not specifications:
        raise ValueError(
            "Add at least one Date-Time Part before saving."
        )

    payload = save_spot_date_time_parts(
        case_id,
        TOWER_DUMP_PARTITION_WORKFLOWS[
            normalized_source
        ],
        specifications,
    )
    saved_parts = list(
        payload.get(
            "parts",
            [],
        )
    )
    overlap_warnings: list[dict[str, Any]] = []

    for index, left in enumerate(
        saved_parts
    ):
        left_scope = str(
            left.get(
                "spot_scope_mode",
                "",
            )
            or ""
        ).strip().upper()
        left_spot = str(
            left.get(
                "spot_id",
                "",
            )
            or ""
        ).strip()

        for right in saved_parts[
            index + 1:
        ]:
            right_scope = str(
                right.get(
                    "spot_scope_mode",
                    "",
                )
                or ""
            ).strip().upper()
            right_spot = str(
                right.get(
                    "spot_id",
                    "",
                )
                or ""
            ).strip()
            all_scope_modes = {
                "ALL_SPOTS",
                "LEGACY_ALL_SPOTS",
            }

            if (
                left_scope not in all_scope_modes
                and right_scope not in all_scope_modes
                and left_spot
                and right_spot
                and left_spot != right_spot
            ):
                continue

            overlap_warnings.extend(
                find_overlapping_date_time_parts(
                    [
                        left,
                        right,
                    ]
                )
            )

    payload["overlap_warnings"] = overlap_warnings
    return payload


def _validate_saved_part_spots(
    *,
    source_type: str,
    input_folder: Path,
    parts: list[dict[str, Any]],
    selected_spot_folders: Iterable[str] | None,
    include_root_files: bool,
) -> None:
    """Prevent saved Parts from silently targeting a different Spot."""

    from modules.loader.tower_spot_layout import (
        build_tower_spot_layout,
        select_tower_evidence_files,
    )

    candidate_files = sorted(
        path
        for path in input_folder.rglob(
            "*"
        )
        if (
            path.is_file()
            and path.suffix.casefold()
            in TOWER_DUMP_SOURCE_SUFFIXES[
                source_type
            ]
        )
    )

    if not candidate_files:
        return

    selected_files = select_tower_evidence_files(
        input_folder,
        candidate_files,
        selected_spot_folders=selected_spot_folders,
        include_root_files=include_root_files,
    )
    layout = build_tower_spot_layout(
        input_folder,
        selected_files,
        identity_files=candidate_files,
    )
    available = {
        str(
            item.get(
                "spot_id",
                "",
            )
        ).strip(): str(
            item.get(
                "spot_name",
                "",
            )
        ).strip()
        for item in layout.get(
            "spot_summary",
            [],
        )
        if isinstance(
            item,
            dict,
        )
    }

    for part in parts:
        scope_mode = str(
            part.get(
                "spot_scope_mode",
                "",
            )
            or ""
        ).strip().upper()
        spot_id = str(
            part.get(
                "spot_id",
                "",
            )
            or ""
        ).strip()
        spot_name = str(
            part.get(
                "spot_name",
                "",
            )
            or ""
        ).strip()

        if (
            not spot_id
            or scope_mode
            in {
                "ALL_SPOTS",
                "LEGACY_ALL_SPOTS",
            }
        ):
            continue

        current_name = available.get(
            spot_id
        )

        if (
            current_name is None
            or (
                spot_name
                and current_name != spot_name
            )
        ):
            part_name = str(
                part.get(
                    "part_name",
                    "Date-Time Part",
                )
            )
            raise ValueError(
                f"{part_name}: the saved Spot mapping does not match "
                "the currently selected evidence. Open Create / Manage "
                "Date-Time Parts and save the Part again."
            )


def run_tower_dump_partition_analysis(
    case: dict[str, Any],
    *,
    source_type: str,
    input_folder: str | Path,
    selected_spot_folders: Iterable[str] | None = None,
    include_root_files: bool = True,
) -> dict[str, Any] | None:
    """Run saved pair-based Date-Time Parts without CLI prompts."""

    (
        normalized_source,
        folder,
        selection_kwargs,
    ) = _normalize_analysis_request(
        source_type=source_type,
        input_folder=input_folder,
        selected_spot_folders=selected_spot_folders,
        include_root_files=include_root_files,
    )

    parts = list_tower_dump_date_time_parts(
        case,
        source_type=normalized_source,
    )

    if not parts:
        raise ValueError(
            "No Date-Time Parts are saved for the selected Tower Dump type."
        )

    _validate_saved_part_spots(
        source_type=normalized_source,
        input_folder=folder,
        parts=parts,
        selected_spot_folders=selection_kwargs.get(
            "selected_spot_folders"
        ),
        include_root_files=bool(
            selection_kwargs.get(
                "include_root_files",
                include_root_files,
            )
        ),
    )

    if normalized_source == "cdr":
        from modules.controllers.tower_cdr_controller import (
            _run_partition_analysis,
        )

        return _run_partition_analysis(
            case,
            input_folder=folder,
            **selection_kwargs,
        )

    if normalized_source == "gprs":
        from modules.controllers.tower_gprs_controller import (
            _execute,
        )

        return _execute(
            case,
            use_partitions=True,
            input_folder=folder,
            **selection_kwargs,
        )

    from modules.controllers.tower_ipdr_controller import (
        run_tower_ipdr_saved_parts,
    )

    return run_tower_ipdr_saved_parts(
        case,
        input_folder=folder,
        **selection_kwargs,
    )


def _menu(case: dict[str, Any]) -> str:
    print("\n" + "=" * 78)
    print(
        f"TOWER DUMP ANALYSIS | "
        f"{case.get('case_id', '')} | "
        f"{case.get('case_name', '')}"
    )
    print("=" * 78)
    print("1. Tower CDR Dump Analysis")
    print("2. Tower GPRS Dump Analysis")
    print("3. Tower IPDR Dump Analysis")
    print("0. Back to Case Workspace")
    return input("\nChoose Source Section: ").strip()


def _load_handler(
    module_path: str,
    function_name: str,
):
    try:
        module = importlib.import_module(module_path)
        handler = getattr(module, function_name, None)

        if not callable(handler):
            raise AttributeError(
                f"{function_name} not found in {module_path}"
            )

        return handler

    except Exception as error:
        print(
            f"[-] Section load failed: "
            f"{type(error).__name__}: {error}"
        )
        return None


def handle_tower_dump_analysis(
    case: dict[str, Any],
) -> None:
    while True:
        try:
            choice = _menu(case)

            if choice == "1":
                handler = _load_handler(
                    "modules.controllers.tower_cdr_controller",
                    "handle_tower_cdr_workspace",
                )

                if callable(handler):
                    handler(case)

            elif choice == "2":
                handler = _load_handler(
                    "modules.controllers.tower_gprs_controller",
                    "handle_tower_gprs_workspace",
                )

                if callable(handler):
                    handler(case)

            elif choice == "3":
                handler = _load_handler(
                    "modules.controllers.tower_ipdr_controller",
                    "handle_tower_ipdr_workspace",
                )

                if callable(handler):
                    handler(case)

            elif choice == "0":
                return

            else:
                print("[-] Invalid choice. Select 0, 1, 2 or 3.")

        except KeyboardInterrupt:
            print("\n[-] Returning to Tower Dump Analysis menu.")

        except EOFError:
            return

        except Exception as error:
            print(
                f"[-] Tower Dump Analysis error: "
                f"{type(error).__name__}: {error}"
            )
