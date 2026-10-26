"""Run: python tools/database_diagnostics.py [--output diagnostic.json]."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modules.database.diagnostics import database_diagnostics


def main():
    parser = argparse.ArgumentParser(description="Read-only database status; does not create, migrate or repair stores.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = database_diagnostics()
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    return int(any(item["status"] in {"UNAVAILABLE", "CHECK FAILED"} for item in result["stores"]))


if __name__ == "__main__":
    raise SystemExit(main())
