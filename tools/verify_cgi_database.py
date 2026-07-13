#!/usr/bin/env python3
"""Verify CGI database integrity or inspect one CGI record with provenance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.database.cgi_repository import lookup_cgi
from modules.database.connection import database_connection, get_db_path
from modules.database.normalization import digits_only
from modules.database.schema import initialize_database, quick_integrity_check


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify CGI SQLite database")
    parser.add_argument("cgi", nargs="?", help="Optional CGI/Cell ID to verify")
    args = parser.parse_args()

    initialize_database()
    ok, message = quick_integrity_check()
    output: dict[str, object] = {
        "database": str(get_db_path()),
        "integrity_ok": ok,
        "integrity_message": message,
    }
    if args.cgi:
        key = digits_only(args.cgi)
        tower = lookup_cgi(key)
        output["query"] = args.cgi
        output["normalized_key"] = key
        output["tower"] = tower
        if tower:
            with database_connection(read_only=True) as conn:
                rows = conn.execute(
                    "SELECT source_file, source_sheet, source_row, "
                    "source_record_sha256, imported_at, import_run_id "
                    "FROM cgi_source_records WHERE tower_id=("
                    "SELECT id FROM cgi_towers WHERE cgi_key=?"
                    ") ORDER BY id",
                    (tower["cgi_key"],),
                ).fetchall()
            output["source_provenance"] = [dict(row) for row in rows]
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
