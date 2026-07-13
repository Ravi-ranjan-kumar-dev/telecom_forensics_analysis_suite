"""Entry point for the Telecom Forensics Analysis Suite."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    try:
        from modules.core.paths import ensure_runtime_directories
        from modules.controllers.app_controller import run_application

        ensure_runtime_directories()
        run_application()
        return 0

    except Exception as error:
        print("\n[-] Fatal application error")
        print(f"    Error Type : {type(error).__name__}")
        print(f"    Message    : {error}")
        print("    Traceback:")
        print(traceback.format_exc(limit=10).rstrip())
        return 1


if __name__ == "__main__":
    sys.exit(main())
