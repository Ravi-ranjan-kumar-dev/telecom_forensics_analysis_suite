"""CGI repository with caching and canonical normalization."""

from functools import lru_cache
from typing import Optional, Iterable

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
    """Add newer CGI master-data columns without rebuilding the database."""
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


@lru_cache(maxsize=4096)
def normalize_cgi_key(value: str) -> str:
    """Canonical CGI key: uppercase, remove spaces, normalize hyphens."""
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip().strip("'").strip('"').upper()
    import re
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"-+", "-", text)
    return text


def normalize_cgi(value) -> str:
    """Backward-compatible normalizer using canonical key."""
    return normalize_cgi_key(value)


def lookup_cgi(cgi_value: str) -> Optional[dict]:
    create_cgi_table()
    cgi = normalize_cgi_key(cgi_value)
    if not cgi:
        return None
    result = query_dataframe(
        f"SELECT * FROM {CGI_TABLE} WHERE cgi = ? LIMIT 1",
        [cgi],
    )
    if result.empty:
        return None
    return result.iloc[0].to_dict()


@lru_cache(maxsize=128)
def lookup_cgi_dataframe_cached(values: tuple[str, ...]) -> pd.DataFrame:
    create_cgi_table()
    cleaned = sorted({normalize_cgi_key(v) for v in values})
    if not cleaned:
        return pd.DataFrame()
    frames = []
    for i in range(0, len(cleaned), 5000):
        batch = cleaned[i:i+5000]
        placeholders = ",".join(["?"] * len(batch))
        result = query_dataframe(
            f"SELECT * FROM {CGI_TABLE} WHERE cgi IN ({placeholders})",
            batch,
        )
        if result is not None and not result.empty:
            frames.append(result)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def lookup_cgi_dataframe(values: Iterable) -> pd.DataFrame:
    """Public wrapper for cached lookup."""
    return lookup_cgi_dataframe_cached(tuple(values))


def clear_lookup_cache() -> None:
    """Clear all CGI lookup caches."""
    lookup_cgi_dataframe_cached.cache_clear()
    normalize_cgi_key.cache_clear()
    # Also clear SDR cache if imported
    try:
        from .sdr_repository import lookup_mobile_dataframe_cached
        lookup_mobile_dataframe_cached.cache_clear()
    except ImportError:
        pass


# ---------------------------------------------------------------------
# Backward-compatible CGI repository API
# ---------------------------------------------------------------------

def bulk_lookup_cgi(cgi_values):
    """Backward-compatible bulk CGI lookup."""
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
    create_cgi_table()
    return {
        "table": CGI_TABLE,
        "rows": cgi_count(),
        "status": "READY",
        "backend": "DuckDB",
    }


def get_cgi_repository_status():
    return get_cgi_database_status()


def initialize_cgi_repository():
    create_cgi_table()
    return get_cgi_database_status()


def search_cgi(cgi_value):
    return lookup_cgi(cgi_value)


def get_cgi_details(cgi_value):
    return lookup_cgi(cgi_value)


def database_status():
    create_cgi_table()
    return {
        "backend": "DuckDB",
        "table": CGI_TABLE,
        "rows": cgi_count(),
        "status": "READY",
    }


def get_tower_candidates(query_value=None, limit: int = 20):
    """Search possible tower/CGI address candidates."""
    create_cgi_table()
    if limit is None:
        limit = 20
    try:
        limit = int(limit)
    except Exception:
        limit = 20

    if query_value is None or str(query_value).strip() == "":
        return query_dataframe(
            f"SELECT * FROM {CGI_TABLE} ORDER BY imported_at DESC LIMIT {limit}"
        )

    query_text = f"%{str(query_value).strip()}%"
    return query_dataframe(
        f"""
        SELECT * FROM {CGI_TABLE}
        WHERE cgi ILIKE ?
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
    """Enrich CDR dataframe with CGI/tower address fields."""
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