#!/usr/bin/env python3
"""Safely install/upgrade source while preserving runtime workspaces."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from datetime import datetime, timezone

ALWAYS_EXCLUDE_NAMES = {
    ".git", ".pytest_cache", "__pycache__", ".venv", "venv",
}
ROOT_RUNTIME_NAMES = {"data", "cases", "output"}
_SOURCE_ROOT: Path | None = None
RUNTIME_DIRS = ("data", "cases", "output")
DATABASE_RUNTIME_PATTERNS = ("*.db", "*.db-wal", "*.db-shm", "*.sqlite", "*.sqlite3")
DATABASE_RUNTIME_DIRS = ("backups", "import_logs")


def ignore_source(directory: str, names: list[str]) -> set[str]:
    current = Path(directory).resolve()
    ignored = {name for name in names if name in ALWAYS_EXCLUDE_NAMES}
    if _SOURCE_ROOT is not None and current == _SOURCE_ROOT:
        ignored.update(name for name in names if name in ROOT_RUNTIME_NAMES)
    ignored.update(name for name in names if name.endswith((".pyc", ".pyo")))
    return ignored


def copy_runtime(backup: Path, staging: Path) -> None:
    for name in RUNTIME_DIRS:
        source = backup / name
        destination = staging / name
        if source.exists():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination, symlinks=False)

    old_database = backup / "database"
    new_database = staging / "database"
    new_database.mkdir(parents=True, exist_ok=True)
    if old_database.is_dir():
        for pattern in DATABASE_RUNTIME_PATTERNS:
            for source in old_database.glob(pattern):
                if source.is_file():
                    shutil.copy2(source, new_database / source.name)
        for name in DATABASE_RUNTIME_DIRS:
            source = old_database / name
            destination = new_database / name
            if source.is_dir():
                if destination.exists():
                    shutil.rmtree(destination)
                shutil.copytree(source, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install or upgrade Telecom Forensics Suite")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Extracted release source (default: current project)",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path.home() / "Desktop" / "telecom_forensics_analysis_suite",
    )
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    destination = args.destination.expanduser().resolve()
    global _SOURCE_ROOT
    _SOURCE_ROOT = source
    if not (source / "main.py").is_file() or not (source / "modules").is_dir():
        print(f"Invalid release source: {source}")
        return 2
    if source == destination:
        print("Source and destination are the same; no files replaced.")
        print("Run: python tools/release_check.py")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = destination.with_name(f"{destination.name}_backup_{stamp}")
    staging = destination.with_name(f".{destination.name}_staging_{stamp}")
    if backup.exists() or staging.exists():
        print("Backup/staging path already exists; run again after checking directories.")
        return 2

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(source, staging, ignore=ignore_source, symlinks=False)
        if destination.exists():
            os.replace(destination, backup)
            copy_runtime(backup, staging)
        os.replace(staging, destination)
    except Exception as error:
        print(f"Upgrade failed: {type(error).__name__}: {error}")
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if backup.exists() and not destination.exists():
            os.replace(backup, destination)
            print("Previous installation restored.")
        return 1

    print(f"Installed: {destination}")
    if backup.exists():
        print(f"Backup:    {backup}")
    print("Next: create/activate .venv, install requirements-dev.txt, then run release_check.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
