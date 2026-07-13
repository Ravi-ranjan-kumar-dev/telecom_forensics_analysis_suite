#!/usr/bin/env python3
"""Local release gate: syntax, tests, source hygiene and optional DB integrity."""
from __future__ import annotations

import argparse
import compileall
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_DIRS = {".git", ".pytest_cache", "__pycache__", ".venv", "venv"}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pyc"}


def source_hygiene() -> list[str]:
    errors: list[str] = []
    for path in PROJECT_ROOT.rglob("*"):
        relative = path.relative_to(PROJECT_ROOT)
        if any(part in FORBIDDEN_DIRS for part in relative.parts):
            continue
        if path.is_file() and path.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"Runtime/binary artifact in source tree: {relative}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-db", action="store_true", help="Also run CGI SQLite quick_check")
    args = parser.parse_args()
    failures: list[str] = []
    if not compileall.compile_dir(PROJECT_ROOT, quiet=1):
        failures.append("Python compilation failed")
    test = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=PROJECT_ROOT)
    if test.returncode:
        failures.append("Automated tests failed")
    failures.extend(source_hygiene())
    if args.with_db:
        try:
            from modules.database.schema import quick_integrity_check
            valid, message = quick_integrity_check()
            print(f"CGI database quick_check: {message}")
            if not valid:
                failures.append("CGI database integrity check failed")
        except Exception as exc:
            failures.append(f"CGI database check error: {type(exc).__name__}: {exc}")
    if failures:
        print("\nRELEASE CHECK: FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("\nRELEASE CHECK: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
