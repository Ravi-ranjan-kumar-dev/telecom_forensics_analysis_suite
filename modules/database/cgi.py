"""DuckDB-backed CGI lookup & compatibility module."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional
import pandas as pd

from modules.database.cgi_repository import (
    lookup_cgi_dataframe_cached,
    lookup_cgi_once,
    normalize_cgi,
)
from modules.database.duckdb_core import query_dataframe


def get_tower_details(cell_id: str) -> Optional[Dict[str, Any]]:
    """Lookup CGI tower details from DuckDB."""
    norm = normalize_cgi(cell_id)
    if not norm:
        return None
    record = lookup_cgi_once(norm)
    if not record:
        return None
    return {
        "cell_id": record.get("cgi", norm),
        "cgi": record.get("cgi", norm),
        "address": record.get("address", ""),
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "azimuth": None,
        "operator": record.get("operator", ""),
        "circle": record.get("circle", ""),
        "state": record.get("state", ""),
        "district": record.get("district", ""),
        "police_station": record.get("police_station", ""),
        "town": record.get("town", ""),
        "site_name": record.get("site_name", ""),
        "source_file": record.get("source_file", ""),
    }


def lookup_cgi(cell_id: str) -> Optional[Dict[str, Any]]:
    return get_tower_details(cell_id)


def lookup_cgi_batch(cell_ids: Iterable[str]) -> pd.DataFrame:
    cleaned = tuple(sorted({normalize_cgi(c) for c in cell_ids if normalize_cgi(c)}))
    if not cleaned:
        return pd.DataFrame()
    return lookup_cgi_dataframe_cached(cleaned)


def count_cgi_records() -> int:
    try:
        df = query_dataframe("SELECT COUNT(*) AS cnt FROM cgi_addresses")
        if df is not None and not df.empty:
            return int(df.iloc[0]["cnt"])
    except Exception:
        pass
    return 0


def backup_database(*args: Any, **kwargs: Any) -> Any:
    from modules.database import cgi_repository as _repo
    fn = getattr(_repo, "backup_database", None)
    if callable(fn):
        return fn(*args, **kwargs)
    return None


def bulk_lookup_cgi(*args: Any, **kwargs: Any) -> Any:
    from modules.database import cgi_repository as _repo
    fn = getattr(_repo, "bulk_lookup_cgi", None)
    if callable(fn):
        return fn(*args, **kwargs)
    return None


def database_status(*args: Any, **kwargs: Any) -> Any:
    from modules.database import cgi_repository as _repo
    fn = getattr(_repo, "database_status", None)
    if callable(fn):
        return fn(*args, **kwargs)
    return None


def enrich_cdr_dataframe(*args: Any, **kwargs: Any) -> Any:
    from modules.database import cgi_repository as _repo
    fn = getattr(_repo, "enrich_cdr_dataframe", None)
    if callable(fn):
        return fn(*args, **kwargs)
    return None


def find_tower_by_cgi(*args: Any, **kwargs: Any) -> Any:
    from modules.database import cgi_repository as _repo
    fn = getattr(_repo, "find_tower_by_cgi", None)
    if callable(fn):
        return fn(*args, **kwargs)
    return None


def get_cgi_details(*args: Any, **kwargs: Any) -> Any:
    from modules.database import cgi_repository as _repo
    fn = getattr(_repo, "get_cgi_details", None)
    if callable(fn):
        return fn(*args, **kwargs)
    return None


def get_location(*args: Any, **kwargs: Any) -> Any:
    from modules.database import cgi_repository as _repo
    fn = getattr(_repo, "get_location", None)
    if callable(fn):
        return fn(*args, **kwargs)
    return None


def get_tower_candidates(*args: Any, **kwargs: Any) -> Any:
    from modules.database import cgi_repository as _repo
    fn = getattr(_repo, "get_tower_candidates", None)
    if callable(fn):
        return fn(*args, **kwargs)
    return None


def import_cgi_data(*args: Any, **kwargs: Any) -> Any:
    from modules.database import cgi_repository as _repo
    fn = getattr(_repo, "import_cgi_data", None)
    if callable(fn):
        return fn(*args, **kwargs)
    return None


def initialize_database(*args: Any, **kwargs: Any) -> Any:
    from modules.database import cgi_repository as _repo
    fn = getattr(_repo, "initialize_database", None)
    if callable(fn):
        return fn(*args, **kwargs)
    return None


def quick_integrity_check(*args: Any, **kwargs: Any) -> Any:
    from modules.database import cgi_repository as _repo
    fn = getattr(_repo, "quick_integrity_check", None)
    if callable(fn):
        return fn(*args, **kwargs)
    return None


def safe_enrich_cdr(*args: Any, **kwargs: Any) -> Any:
    from modules.database import cgi_repository as _repo
    fn = getattr(_repo, "safe_enrich_cdr", None)
    if callable(fn):
        return fn(*args, **kwargs)
    return None
