from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import duckdb

from modules.database.db_paths import master_duckdb_path


def main() -> int:
    csv_path = Path("data/master/sdr/input/sdr_master_export.csv").resolve()

    if not csv_path.exists():
        print(f"[-] CSV file not found: {csv_path}")
        return 1

    db_path = master_duckdb_path()
    temp_dir = Path("database/tmp/duckdb_sdr_raw_import").resolve()
    temp_dir.mkdir(parents=True, exist_ok=True)

    print("[+] SDR raw large import starting")
    print("[+] CSV:", csv_path)
    print("[+] DB :", db_path)
    print("[+] Temp:", temp_dir)
    print("[+] CSV size GB:", round(csv_path.stat().st_size / (1024 ** 3), 2))

    with duckdb.connect(str(db_path), read_only=False) as connection:
        connection.execute(f"SET temp_directory='{str(temp_dir)}'")
        connection.execute("SET memory_limit='10GB'")
        connection.execute("SET threads=1")
        connection.execute("SET preserve_insertion_order=false")
        connection.execute("PRAGMA enable_progress_bar")

        print("[+] Dropping old raw table if exists...")
        connection.execute("DROP TABLE IF EXISTS sdr_subscribers_large")

        print("[+] Creating raw SDR table from CSV...")
        connection.execute(
            """
            CREATE TABLE sdr_subscribers_large AS
            WITH raw AS (
                SELECT
                    regexp_replace(CAST(mobile_number AS VARCHAR), '[^0-9]', '', 'g') AS raw_digits,
                    CAST(subscriber_name AS VARCHAR) AS subscriber_name,
                    CAST(father_name AS VARCHAR) AS father_name,
                    CAST(address AS VARCHAR) AS address,
                    CAST(id_type AS VARCHAR) AS id_type,
                    CAST(id_number AS VARCHAR) AS id_number,
                    CAST(operator AS VARCHAR) AS operator,
                    CAST(circle AS VARCHAR) AS circle,
                    CAST(activation_date AS VARCHAR) AS activation_date,
                    CAST(caf_number AS VARCHAR) AS caf_number
                FROM read_csv(
                    ?,
                    delim='|',
                    header=true,
                    all_varchar=true,
                    ignore_errors=true
                )
            )
            SELECT
                CASE
                    WHEN length(raw_digits) = 12 AND starts_with(raw_digits, '91') THEN right(raw_digits, 10)
                    WHEN length(raw_digits) = 11 AND starts_with(raw_digits, '0') THEN right(raw_digits, 10)
                    WHEN length(raw_digits) = 10 THEN raw_digits
                    ELSE NULL
                END AS mobile_number,
                nullif(trim(subscriber_name), '') AS subscriber_name,
                nullif(trim(father_name), '') AS father_name,
                nullif(trim(address), '') AS address,
                CASE
                    WHEN id_type IS NULL THEN NULL
                    WHEN trim(id_type) = '' THEN NULL
                    WHEN trim(id_type) = trim(coalesce(id_number, '')) THEN NULL
                    WHEN regexp_matches(trim(id_type), '^[0-9]+$') THEN NULL
                    ELSE trim(id_type)
                END AS id_type,
                nullif(trim(id_number), '') AS id_number,
                nullif(trim(operator), '') AS operator,
                nullif(trim(circle), '') AS circle,
                nullif(trim(activation_date), '') AS activation_date,
                nullif(trim(caf_number), '') AS caf_number,
                'sdr_master_export.csv' AS source_file,
                current_timestamp AS imported_at
            FROM raw
            WHERE
                CASE
                    WHEN length(raw_digits) = 12 AND starts_with(raw_digits, '91') THEN right(raw_digits, 10)
                    WHEN length(raw_digits) = 11 AND starts_with(raw_digits, '0') THEN right(raw_digits, 10)
                    WHEN length(raw_digits) = 10 THEN raw_digits
                    ELSE NULL
                END IS NOT NULL
            """,
            [str(csv_path)],
        )

        total = connection.execute("SELECT COUNT(*) FROM sdr_subscribers_large").fetchone()[0]
        unique_numbers = connection.execute(
            "SELECT COUNT(DISTINCT mobile_number) FROM sdr_subscribers_large"
        ).fetchone()[0]

        print("[+] Raw SDR rows:", total)
        print("[+] Unique mobile numbers:", unique_numbers)

        print("[+] SDR raw large import completed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
