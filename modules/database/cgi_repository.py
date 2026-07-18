from typing import Optional

import pandas as pd

from .duckdb_core import execute_sql, query_dataframe, table_count


CGI_TABLE = "cgi_addresses"


CGI_OPTIONAL_COLUMNS = {
    "site_name": "TEXT",
    "town": "TEXT",
    "landmark": "TEXT",
    "azimuth": "TEXT",
    "technology": "TEXT",
    "status": "TEXT",
    "status_change_date": "TEXT",
    "mcc_mnc": "TEXT",
    "lac": "TEXT",
    "cid": "TEXT",
    "tac_id": "TEXT",
    "site_id": "TEXT",
    "gnb_id": "TEXT",
    "cell_id": "TEXT",
}


def _ensure_optional_cgi_columns() -> None:
    """
    Add newer CGI master-data columns without rebuilding the database.

    This keeps old DuckDB data safe and only adds missing columns.
    """
    try:
        info = query_dataframe(f"PRAGMA table_info('{CGI_TABLE}')")
        existing = set(info["name"].astype(str).tolist()) if not info.empty else set()

        for column_name, column_type in CGI_OPTIONAL_COLUMNS.items():
            if column_name not in existing:
                execute_sql(
                    f"ALTER TABLE {CGI_TABLE} ADD COLUMN {column_name} {column_type}"
                )
    except Exception:
        # Table may not exist yet during first initialization.
        # create_cgi_table() will be called again after CREATE TABLE.
        return


def create_cgi_table() -> None:
    execute_sql(
        f"""
        CREATE TABLE IF NOT EXISTS {CGI_TABLE} (
            cgi TEXT PRIMARY KEY,
            operator TEXT,
            circle TEXT,
            state TEXT,
            district TEXT,
            police_station TEXT,
            address TEXT,
            latitude DOUBLE,
            longitude DOUBLE,
            source_file TEXT,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _ensure_optional_cgi_columns()


def cgi_count() -> int:
    create_cgi_table()
    return table_count(CGI_TABLE)


def normalize_cgi(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().strip("'").strip('"')


def lookup_cgi(cgi_value: str) -> Optional[dict]:
    create_cgi_table()
    cgi = normalize_cgi(cgi_value)

    if not cgi:
        return None

    result = query_dataframe(
        f"""
        SELECT *
        FROM {CGI_TABLE}
        WHERE cgi = ?
        LIMIT 1
        """,
        [cgi],
    )

    if result.empty:
        return None

    return result.iloc[0].to_dict()


def lookup_cgi_dataframe(values) -> pd.DataFrame:
    create_cgi_table()
    cleaned = sorted({normalize_cgi(value) for value in values if normalize_cgi(value)})

    if not cleaned:
        return pd.DataFrame()

    placeholders = ", ".join(["?"] * len(cleaned))
    return query_dataframe(
        f"""
        SELECT *
        FROM {CGI_TABLE}
        WHERE cgi IN ({placeholders})
        """,
        cleaned,
    )

def clear_lookup_cache() -> None:
    """
    Compatibility hook for older CGI importer code.

    Earlier CGI code calls this after import so cached lookup results
    do not stay stale. Current DuckDB lookup functions do not keep an
    in-memory cache yet, so this is intentionally a safe no-op.
    """
    return None

# ---------------------------------------------------------------------
# Backward-compatible CGI repository API
# ---------------------------------------------------------------------
# Older modules/database/cgi.py and cgi_importer.py expect these names.
# These wrappers keep the old project API working while the backend uses
# the new DuckDB master lookup database.

def bulk_lookup_cgi(cgi_values):
    """
    Backward-compatible bulk CGI lookup.

    Returns a dictionary:
        {
            "cgi_value": {row-data},
            ...
        }
    """
    create_cgi_table()

    if not cgi_values:
        return {}

    result = lookup_cgi_dataframe(cgi_values)
    if result is None or result.empty:
        return {}

    output = {}
    for _, row in result.iterrows():
        row_dict = row.to_dict()
        cgi_key = normalize_cgi(row_dict.get("cgi", ""))
        if cgi_key:
            output[cgi_key] = row_dict

    return output


def get_cgi_database_status():
    """
    Backward-compatible CGI database status helper.
    """
    create_cgi_table()
    return {
        "table": CGI_TABLE,
        "rows": cgi_count(),
        "status": "READY",
        "backend": "DuckDB",
    }


def get_cgi_repository_status():
    """
    Alias used by older code.
    """
    return get_cgi_database_status()


def initialize_cgi_repository():
    """
    Backward-compatible initializer.
    """
    create_cgi_table()
    return get_cgi_database_status()


def search_cgi(cgi_value):
    """
    Backward-compatible single CGI search.
    """
    return lookup_cgi(cgi_value)


def get_cgi_details(cgi_value):
    """
    Backward-compatible CGI detail lookup.
    """
    return lookup_cgi(cgi_value)


def clear_lookup_cache() -> None:
    """
    Compatibility hook for older CGI importer code.

    Current DuckDB lookup functions do not keep an in-memory cache yet,
    so this is intentionally a safe no-op.
    """
    return None

def database_status():
    """
    Public CGI database status expected by modules/database/cgi.py.
    """
    create_cgi_table()
    return {
        "backend": "DuckDB",
        "table": CGI_TABLE,
        "rows": cgi_count(),
        "status": "READY",
    }


def get_tower_candidates(query_value=None, limit: int = 20):
    """
    Search possible tower/CGI address candidates.

    This keeps the old public CGI API working while using the DuckDB
    master database table.
    """
    create_cgi_table()

    if limit is None:
        limit = 20

    try:
        limit = int(limit)
    except Exception:
        limit = 20

    if query_value is None or str(query_value).strip() == "":
        return query_dataframe(
            f"""
            SELECT *
            FROM {CGI_TABLE}
            ORDER BY imported_at DESC
            LIMIT {limit}
            """
        )

    query_text = f"%{str(query_value).strip()}%"

    return query_dataframe(
        f"""
        SELECT *
        FROM {CGI_TABLE}
        WHERE
            cgi ILIKE ?
            OR operator ILIKE ?
            OR circle ILIKE ?
            OR state ILIKE ?
            OR district ILIKE ?
            OR police_station ILIKE ?
            OR address ILIKE ?
        LIMIT {limit}
        """,
        [query_text, query_text, query_text, query_text, query_text, query_text, query_text],
    )


def enrich_cdr_dataframe(dataframe, inplace: bool = False):
    """
    Enrich CDR dataframe with CGI/tower address fields.

    It checks common CDR tower columns:
    - first_cell_id
    - last_cell_id
    - searched_cell_id

    Raw evidence columns are not changed. New lookup columns are added.
    """
    create_cgi_table()

    if dataframe is None:
        return dataframe

    data = dataframe if inplace else dataframe.copy()

    lookup_columns = [
        column
        for column in ["first_cell_id", "last_cell_id", "searched_cell_id"]
        if column in data.columns
    ]

    if not lookup_columns:
        return data

    all_values = []
    for column in lookup_columns:
        all_values.extend(data[column].dropna().astype(str).tolist())

    lookup_rows = bulk_lookup_cgi(all_values)

    for column in lookup_columns:
        prefix = column.replace("_cell_id", "")
        data[f"{prefix}_tower_address"] = data[column].map(
            lambda value: (lookup_rows.get(normalize_cgi(value)) or {}).get("address", "")
        )
        data[f"{prefix}_tower_district"] = data[column].map(
            lambda value: (lookup_rows.get(normalize_cgi(value)) or {}).get("district", "")
        )
        data[f"{prefix}_tower_state"] = data[column].map(
            lambda value: (lookup_rows.get(normalize_cgi(value)) or {}).get("state", "")
        )
        data[f"{prefix}_tower_latitude"] = data[column].map(
            lambda value: (lookup_rows.get(normalize_cgi(value)) or {}).get("latitude", None)
        )
        data[f"{prefix}_tower_longitude"] = data[column].map(
            lambda value: (lookup_rows.get(normalize_cgi(value)) or {}).get("longitude", None)
        )

    return data

