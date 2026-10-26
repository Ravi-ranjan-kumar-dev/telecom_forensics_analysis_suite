"""Legacy entry point: import into the canonical SDR table, never recreate a base table."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description="Import SDR into sdr_subscribers using the validated master importer and its backup workflow.")
    parser.add_argument("file", type=Path, nargs="?", default=Path("data/master/sdr/input/sdr_master_export.csv"))
    args = parser.parse_args()
    if not args.file.is_file():
        parser.error(f"Input file not found: {args.file}")
    from modules.database.master_import_service import import_master_data_file, detect_master_data_type
    if detect_master_data_type(args.file).get("import_type") != "SDR":
        parser.error("Expected SDR data; refusing to import another master-data type.")
    result = import_master_data_file(args.file, create_backup=True)
    if result.get("status") != "FAILED":
        from modules.database.lookup_service import clear_all_lookup_caches
        clear_all_lookup_caches()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return int(result.get("status") == "FAILED")


if __name__ == "__main__":
    raise SystemExit(main())
