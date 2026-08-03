"""Unified Tower Dump Analysis workspace.

The workspace groups all location/tower-originated source types:
- Tower CDR Dump
- Tower GPRS Dump
- Tower IPDR Dump
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any


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


def run_complete_tower_dump_analysis(
    case: dict[str, Any],
    *,
    source_type: str,
    input_folder: str | Path,
) -> dict[str, Any] | None:
    """Run one complete Tower Dump workflow without CLI prompts."""

    normalized_source = str(
        source_type
    ).strip().casefold()

    if normalized_source not in TOWER_DUMP_SOURCE_TYPES:
        raise ValueError(
            f"Unsupported Tower Dump source type: {source_type}"
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

    if normalized_source == "cdr":
        from modules.controllers.tower_cdr_controller import (
            _run_complete_analysis,
        )

        return _run_complete_analysis(
            case,
            input_folder=folder,
        )

    if normalized_source == "gprs":
        from modules.controllers.tower_gprs_controller import (
            _execute,
        )

        return _execute(
            case,
            use_partitions=False,
            input_folder=folder,
        )

    from modules.controllers.tower_ipdr_controller import (
        _run_complete_tower_ipdr_analysis,
    )

    return _run_complete_tower_ipdr_analysis(
        case,
        input_folder=folder,
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
