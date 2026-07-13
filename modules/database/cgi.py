"""Stable public CGI API. Other modules should import from this file."""

from __future__ import annotations

from typing import Any

from .cgi_importer import ImportStats, import_cgi_data
from .cgi_repository import (
    bulk_lookup_cgi,
    clear_lookup_cache,
    database_status,
    enrich_cdr_dataframe,
    get_tower_candidates,
    lookup_cgi,
)
from .schema import backup_database, initialize_database, quick_integrity_check


def safe_enrich_cdr(df: Any) -> Any:
    return enrich_cdr_dataframe(df, inplace=False)


def find_tower_by_cgi(cgi: Any):
    return lookup_cgi(cgi)


def get_cgi_details(cgi: Any):
    return lookup_cgi(cgi) or {}


def get_tower_details(cgi: Any):
    return lookup_cgi(cgi) or {}


def get_location(cgi: Any) -> str:
    result = lookup_cgi(cgi) or {}
    return result.get("address") or result.get("site_name") or ""


__all__ = [
    "ImportStats", "import_cgi_data", "initialize_database", "backup_database",
    "quick_integrity_check", "lookup_cgi", "find_tower_by_cgi", "get_cgi_details",
    "get_tower_details", "get_location", "get_tower_candidates", "bulk_lookup_cgi",
    "enrich_cdr_dataframe", "safe_enrich_cdr", "database_status", "clear_lookup_cache",
]
