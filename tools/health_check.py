from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


CASE_ID = "DEV-WORKSPACE"


def print_header(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def print_ok(message: str) -> None:
    print(f"[OK] {message}")


def print_fail(message: str) -> None:
    print(f"[FAIL] {message}")


def check_import(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        print_ok(f"Import OK: {module_name}")
        return True
    except Exception as exc:
        print_fail(f"Import failed: {module_name} | {exc}")
        return False


def check_file(path_value: str | None, label: str) -> bool:
    if not path_value:
        print_fail(f"{label}: path missing")
        return False

    path = Path(path_value)

    if path.exists():
        print_ok(f"{label}: {path}")
        return True

    print_fail(f"{label}: file not found -> {path}")
    return False


def check_git_clean() -> bool:
    result = subprocess.run(
        ["git", "status", "--short"],
        check=False,
        capture_output=True,
        text=True,
    )

    output = result.stdout.strip()

    if not output:
        print_ok("Git working tree clean")
        return True

    print_fail("Git working tree has changes")
    print(output)
    return False


def main() -> int:
    failures = 0

    print_header("TELECOM FORENSICS SUITE HEALTH CHECK")

    print_header("1. Dependency Check")
    for module_name in ["pandas", "duckdb", "openpyxl"]:
        if not check_import(module_name):
            failures += 1

    print_header("2. Project Import Check")
    for module_name in [
        "modules.controllers.app_controller",
        "modules.controllers.case_controller",
        "modules.controllers.tower_ipdr_controller",
        "modules.staging.tower_ipdr_staging",
        "modules.cases.date_time_partitions",
    ]:
        if not check_import(module_name):
            failures += 1

    print_header("3. Latest Tower IPDR Report Check")
    try:
        from modules.staging.tower_ipdr_staging import (
            load_tower_ipdr_partwise_latest_report,
        )

        latest = load_tower_ipdr_partwise_latest_report(CASE_ID)

        if not latest:
            print_fail("Latest Tower IPDR report pointer not found")
            failures += 1
        else:
            print_ok("Latest Tower IPDR report pointer found")
            check_file(latest.get("main_report"), "Main TXT Report") or (failures := failures + 1)
            check_file(latest.get("summary_csv"), "Summary CSV") or (failures := failures + 1)
            check_file(latest.get("excel_workbook"), "Excel Workbook") or (failures := failures + 1)
            check_file(latest.get("manifest"), "Manifest") or (failures := failures + 1)

    except Exception as exc:
        print_fail(f"Latest report check failed: {exc}")
        failures += 1

    print_header("4. User-Facing Wording Check")
    staging_file = Path("modules/staging/tower_ipdr_staging.py")

    if staging_file.exists():
        text = staging_file.read_text(encoding="utf-8")
        if "CCTV" in text:
            print_fail("CCTV wording still exists in tower_ipdr_staging.py")
            failures += 1
        else:
            print_ok("No CCTV-specific wording found in Tower IPDR staging output")
    else:
        print_fail("tower_ipdr_staging.py not found")
        failures += 1

    print_header("5. Git Cleanliness Check")
    if not check_git_clean():
        failures += 1

    print_header("HEALTH CHECK RESULT")

    if failures:
        print_fail(f"Health check completed with {failures} issue(s).")
        return 1

    print_ok("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
