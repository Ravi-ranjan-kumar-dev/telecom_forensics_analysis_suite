#!/usr/bin/env python3
"""Command-line CGI importer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.database.cgi import database_status, import_cgi_data, initialize_database


def main() -> int:
    parser = argparse.ArgumentParser(description="Import CGI Excel/CSV data into SQLite")
    parser.add_argument("source", nargs="?", default="data/cgi/raw", help="CGI file or folder")
    parser.add_argument("--include-deleted", action="store_true", help="Also import Deleted/Old sheets")
    parser.add_argument("--no-backup", action="store_true", help="Do not create pre-import backup")
    parser.add_argument("--dry-run", action="store_true", help="Validate files without changing tower table")
    parser.add_argument("--status", action="store_true", help="Show database status only")
    args = parser.parse_args()

    initialize_database()
    if args.status:
        print(json.dumps(database_status(), ensure_ascii=False, indent=2, default=str))
        return 0

    stats = import_cgi_data(
        args.source,
        include_deleted_sheets=args.include_deleted,
        create_backup=not args.no_backup,
        dry_run=args.dry_run,
    )

    print("\n" + "=" * 64)
    print("CGI DATABASE IMPORT SUMMARY")
    print("=" * 64)
    print(f"Status          : {stats.status}")
    print(f"Files Found     : {stats.files_found}")
    print(f"Files Completed : {stats.files_completed}")
    print(f"Sheets Completed: {stats.sheets_completed}")
    print(f"Rows Read       : {stats.rows_read}")
    print(f"New Inserted    : {stats.inserted}")
    print(f"Existing Updated: {stats.updated}")
    print(f"Rejected Rows   : {stats.rejected}")
    print(f"Skipped Sheets  : {stats.skipped}")
    print(f"Backup          : {stats.backup_path or 'Not created / new database'}")
    print(f"Log             : {stats.log_path}")
    if stats.message:
        print(f"Message         : {stats.message}")
    print("=" * 64)

    return 0 if stats.status in {"COMPLETED", "DRY_RUN_OK", "COMPLETED_WITH_WARNING"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
