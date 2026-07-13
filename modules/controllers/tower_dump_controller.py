"""Unified Tower Dump Analysis workspace.

The workspace groups all location/tower-originated source types:
- Tower CDR Dump
- Tower GPRS Dump
- Tower IPDR Dump
"""

from __future__ import annotations

import importlib
from typing import Any


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
