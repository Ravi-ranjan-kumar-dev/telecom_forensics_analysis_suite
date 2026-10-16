"""
DuckDB -> PostgreSQL Migration (Batch, Memory-Optimized)
- Reads SDR and CGI data from DuckDB in chunks
- Inserts into PostgreSQL using batch executemany
"""

import sys
import os
import duckdb
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# PostgreSQL connection from .env
DATABASE_URL = os.getenv("DATABASE_URL")

# DuckDB path (adjust if your DuckDB file is elsewhere)
DUCKDB_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'database', 'telecom_forensics.duckdb'
)

# Batch size for reading and inserting
BATCH_SIZE = 1000


def migrate_table(engine, duck_table, pg_table, columns, conflict_key):
    """
    Migrate one table from DuckDB to PostgreSQL in batches.
    columns: list of column names (string) to select and insert.
    conflict_key: column name to use for ON CONFLICT (e.g., 'mobile_number' or 'cgi')
    """
    print(f"\n[+] Migrating {duck_table} to {pg_table}...")

    # Connect to DuckDB (read-only)
    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    try:
        # Check if table exists in DuckDB
        try:
            con.execute(f"SELECT 1 FROM {duck_table} LIMIT 1")
        except Exception:
            print(f"[-] Table {duck_table} not found in DuckDB. Skipping.")
            return 0

        # Build SELECT query (only needed columns to reduce memory)
        select_sql = f"SELECT {', '.join(columns)} FROM {duck_table}"

        # PostgreSQL INSERT statement (without ON CONFLICT for now; we'll use DO NOTHING)
        # We'll use parameterized insertion with named placeholders
        placeholders = ', '.join([f":{col}" for col in columns])
        insert_sql = text(
            f"INSERT INTO {pg_table} ({', '.join(columns)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_key}) DO NOTHING"
        )

        total = 0
        # Read in chunks using fetchmany
        cursor = con.execute(select_sql)
        while True:
            rows = cursor.fetchmany(BATCH_SIZE)
            if not rows:
                break

            # Convert rows to list of dicts for executemany
            dict_rows = []
            for row in rows:
                row_dict = {}
                for idx, col in enumerate(columns):
                    row_dict[col] = row[idx]
                dict_rows.append(row_dict)

            # Insert batch using SQLAlchemy
            with engine.begin() as conn:
                conn.execute(insert_sql, dict_rows)
            total += len(dict_rows)
            print(f"    Inserted {total} rows so far...")

        con.close()
        print(f"[+] Inserted {total} rows in {pg_table}.")
        return total
    except Exception as e:
        con.close()
        print(f"[-] Migration failed for {duck_table}: {e}")
        return 0


if __name__ == "__main__":
    if not os.path.exists(DUCKDB_PATH):
        print(f"[-] DuckDB file not found at {DUCKDB_PATH}")
        sys.exit(1)

    print("=" * 60)
    print("DUCKDB TO POSTGRESQL MIGRATION (Batch Mode)")
    print("=" * 60)

    engine = create_engine(DATABASE_URL)

    # SDR columns (must match your PostgreSQL schema exactly)
    sdr_columns = [
        "mobile_number", "subscriber_name", "father_name", "address",
        "id_type", "id_number", "operator", "circle", "activation_date",
        "caf_number", "source_file"
    ]

    # CGI columns
    cgi_columns = [
        "cgi", "operator", "circle", "state", "district", "police_station",
        "address", "latitude", "longitude", "source_file", "site_name",
        "town", "landmark", "azimuth", "technology", "status",
        "status_change_date", "mcc_mnc", "lac", "cid", "tac_id",
        "site_id", "gnb_id", "cell_id"
    ]

    # Migrate SDR
    migrate_table(engine, "sdr_subscribers", "sdr_subscribers", sdr_columns, "mobile_number")

    # Migrate CGI
    migrate_table(engine, "cgi_addresses", "cgi_addresses", cgi_columns, "cgi")

    print("\n[+] Migration completed successfully!")