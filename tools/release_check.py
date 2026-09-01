#!/usr/bin/env python3
"""Local release gate: syntax, tests, source hygiene and optional DB integrity."""

from __future__ import annotations

import argparse
import compileall
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Directories and file suffixes that must never be committed
FORBIDDEN_DIRS = {".git", ".pytest_cache", "__pycache__", ".venv", "venv"}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pyc"}

# Sensitive or unwanted files that indicate a hygiene leak
SENSITIVE_FILES = [
    ".env",
    "backend/.env",
    "*.env",
    "changes.diff",
    "*.save",
    "*.bak",
    "*.tmp",
    "gprs_finalization_source_bundle.txt",
]

# Files that must exist for a release
REQUIRED_FILES = [
    "VERSION",
    "requirements.txt",
    "pyproject.toml",
    "README.md",
]

SOURCE_DIRECTORIES = (
    "modules",
    "gui",
    "tools",
    "tests",
)
ROOT_PYTHON_FILES = (
    "main.py",
    "manage.py",
    "run_gui.py",
)


def source_hygiene() -> list[str]:
    """Check for forbidden file types in the source tree."""
    errors: list[str] = []
    for path in PROJECT_ROOT.rglob("*"):
        relative = path.relative_to(PROJECT_ROOT)
        if any(part in FORBIDDEN_DIRS for part in relative.parts):
            continue
        if path.is_file() and path.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"Runtime/binary artifact in source tree: {relative}")
    return errors


def sensitive_files_check() -> list[str]:
    """Check for sensitive/unwanted files that should not be in the repo."""
    issues: list[str] = []
    for pattern in SENSITIVE_FILES:
        # Use glob to find matches (including recursive for backend/.env)
        for path in PROJECT_ROOT.rglob(pattern):
            # Exclude .git etc.
            if any(part in FORBIDDEN_DIRS for part in path.relative_to(PROJECT_ROOT).parts):
                continue
            issues.append(f"Found sensitive/unwanted file: {path.relative_to(PROJECT_ROOT)}")
    return issues


def required_files_check() -> list[str]:
    """Check that required release files exist."""
    issues: list[str] = []
    for file in REQUIRED_FILES:
        if not (PROJECT_ROOT / file).exists():
            issues.append(f"Missing required file: {file}")
    return issues


def version_consistency_check() -> list[str]:
    """Check VERSION and pyproject.toml match (and optionally backend main.py)."""
    issues: list[str] = []
    try:
        version_file = (PROJECT_ROOT / "VERSION").read_text().strip()
        pyproject_text = (PROJECT_ROOT / "pyproject.toml").read_text()
        match = re.search(r'version\s*=\s*"([^"]+)"', pyproject_text)
        pyproject_version = match.group(1) if match else ""
        if version_file != pyproject_version:
            issues.append(f"Version mismatch: VERSION={version_file}, pyproject={pyproject_version}")

        # Optional: check backend main.py __version__
        backend_main = PROJECT_ROOT / "backend" / "app" / "main.py"
        if backend_main.exists():
            main_text = backend_main.read_text()
            version_match = re.search(r'__version__\s*=\s*"([^"]+)"', main_text)
            backend_version = version_match.group(1) if version_match else ""
            if backend_version != version_file:
                issues.append(f"Backend version mismatch: main.py={backend_version}, VERSION={version_file}")
    except FileNotFoundError:
        issues.append("VERSION or pyproject.toml not found")
    return issues


def compile_source(project_root: Path = PROJECT_ROOT) -> bool:
    """Compile only application-owned Python source paths."""
    success = True
    for directory_name in SOURCE_DIRECTORIES:
        directory = project_root / directory_name
        if not directory.is_dir():
            continue
        success = compileall.compile_dir(directory, quiet=1) and success
    for file_name in ROOT_PYTHON_FILES:
        source_file = project_root / file_name
        if not source_file.is_file():
            continue
        success = compileall.compile_file(source_file, quiet=1) and success
    return success


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-db", action="store_true", help="Also run CGI SQLite quick_check")
    args = parser.parse_args()

    failures: list[str] = []

    # 1. Compile source
    if not compile_source():
        failures.append("Python compilation failed")

    # 2. Run tests
    test = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=PROJECT_ROOT)
    if test.returncode:
        failures.append("Automated tests failed")

    # 3. Source hygiene (forbidden file types)
    failures.extend(source_hygiene())

    # 4. Sensitive/unwanted files
    failures.extend(sensitive_files_check())

    # 5. Required files
    failures.extend(required_files_check())

    # 6. Version consistency
    failures.extend(version_consistency_check())

    # 7. Optional DB integrity
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