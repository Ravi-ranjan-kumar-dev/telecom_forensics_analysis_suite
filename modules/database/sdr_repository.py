"""SDR repository with caching and normalization."""

from functools import lru_cache
from typing import Optional, Iterable

import pandas as pd
from modules.loader.identity import normalize_msisdn

from .duckdb_core import execute_sql, query_dataframe, table_count


SDR_TABLE = "sdr_subscribers"


def create_sdr_table() -> None:
    execute_sql(
        f"""
        CREATE TABLE IF NOT EXISTS {SDR_TABLE} (
            mobile_number TEXT PRIMARY KEY,
            subscriber_name TEXT,
            father_name TEXT,
            address TEXT,
            id_type TEXT,
            id_number TEXT,
            operator TEXT,
            circle TEXT,
            activation_date TEXT,
            caf_number TEXT,
            source_file TEXT,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def sdr_count() -> int:
    create_sdr_table()
    return table_count(SDR_TABLE)


@lru_cache(maxsize=1024)
def _normalize_mobile_cached(value: str) -> str:
    """Cached normalization, avoiding repeated computation."""
    return normalize_msisdn(value) or ""


def normalize_mobile(value) -> str:
    """Backward-compatible strict Indian MSISDN normalizer using cache."""
    return _normalize_mobile_cached(str(value))


def lookup_mobile(number: str) -> Optional[dict]:
    create_sdr_table()
    mobile = normalize_mobile(number)
    if not mobile:
        return None
    result = query_dataframe(
        f"SELECT * FROM {SDR_TABLE} WHERE mobile_number = ? LIMIT 1",
        [mobile],
    )
    if result.empty:
        return None
    return result.iloc[0].to_dict()


@lru_cache(maxsize=128)
def lookup_mobile_dataframe_cached(values: tuple[str, ...]) -> pd.DataFrame:
    create_sdr_table()
    cleaned = sorted({normalize_mobile(value) for value in values})
    if not cleaned:
        return pd.DataFrame()
    placeholders = ",".join(["?"] * len(cleaned))
    return query_dataframe(
        f"SELECT * FROM {SDR_TABLE} WHERE mobile_number IN ({placeholders})",
        cleaned,
    )


def lookup_mobile_dataframe(values: Iterable) -> pd.DataFrame:
    """Public wrapper for cached lookup."""
    return lookup_mobile_dataframe_cached(tuple(values))