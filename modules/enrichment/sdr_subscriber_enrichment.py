"""SDR subscriber enrichment with caching."""

from functools import lru_cache
from typing import Iterable, List

import pandas as pd
from modules.loader.identity import normalize_msisdn

from modules.database.duckdb_core import query_dataframe


@lru_cache(maxsize=1024)
def _normalize_mobile_cached(value: str) -> str:
    return normalize_msisdn(value) or ""


def normalize_mobile_number(value) -> str:
    return _normalize_mobile_cached(str(value))


def _chunks(values: List[str], size: int = 1000):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _empty_lookup_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "lookup_mobile",
            "subscriber_name",
            "father_name",
            "subscriber_address",
            "id_type",
            "id_number",
            "operator",
            "circle",
            "activation_date",
            "caf_number",
            "source_file",
            "sdr_found",
        ]
    )


def _table_exists(table_name: str) -> bool:
    try:
        result = query_dataframe(
            """
            SELECT COUNT(*) AS total
            FROM information_schema.tables
            WHERE table_name = ?
            """,
            [table_name],
        )
        return result is not None and not result.empty and int(result.iloc[0]["total"]) > 0
    except Exception:
        return False


def _lookup_from_large_table(numbers: List[str]) -> pd.DataFrame:
    if not numbers or not _table_exists("sdr_subscribers_large"):
        return _empty_lookup_frame()

    frames = []
    for batch in _chunks(numbers):
        candidates = list(dict.fromkeys(batch + ["91" + n for n in batch] + ["0" + n for n in batch]))
        placeholders = ",".join(["?"] * len(candidates))
        result = query_dataframe(
            f"""
            WITH ranked AS (
                SELECT
                    right(regexp_replace(CAST(mobile_number AS VARCHAR), '[^0-9]', '', 'g'), 10) AS lookup_mobile,
                    subscriber_name,
                    father_name,
                    address AS subscriber_address,
                    id_type,
                    id_number,
                    replace(operator, ' - Copy', '') AS operator,
                    CASE
                        WHEN circle IS NULL THEN NULL
                        WHEN circle = chr(0) THEN NULL
                        WHEN trim(circle) = '' THEN NULL
                        WHEN upper(trim(circle)) IN ('NONE', 'NULL') THEN NULL
                        ELSE circle
                    END AS circle,
                    activation_date,
                    caf_number,
                    source_file,
                    ROW_NUMBER() OVER (
                        PARTITION BY right(regexp_replace(CAST(mobile_number AS VARCHAR), '[^0-9]', '', 'g'), 10)
                        ORDER BY
                            TRY_CAST(activation_date AS DATE) DESC NULLS LAST,
                            TRY_CAST(caf_number AS BIGINT) DESC NULLS LAST
                    ) AS rn
                FROM sdr_subscribers_large
                WHERE mobile_number IN ({placeholders})
            )
            SELECT
                lookup_mobile,
                subscriber_name,
                father_name,
                subscriber_address,
                id_type,
                id_number,
                operator,
                circle,
                activation_date,
                caf_number,
                source_file,
                'Yes' AS sdr_found
            FROM ranked
            WHERE rn = 1
            """,
            candidates,
        )
        if result is not None and not result.empty:
            frames.append(result)
    if not frames:
        return _empty_lookup_frame()
    return pd.concat(frames, ignore_index=True)


def _lookup_from_primary_table(numbers: List[str]) -> pd.DataFrame:
    if not numbers:
        return _empty_lookup_frame()

    frames = []
    for batch in _chunks(numbers):
        placeholders = ",".join(["?"] * len(batch))
        result = query_dataframe(
            f"""
            SELECT
                mobile_number AS lookup_mobile,
                subscriber_name,
                father_name,
                address AS subscriber_address,
                id_type,
                id_number,
                operator,
                circle,
                activation_date,
                caf_number,
                source_file,
                'Yes' AS sdr_found
            FROM sdr_subscribers
            WHERE mobile_number IN ({placeholders})
            """,
            batch,
        )
        if result is not None and not result.empty:
            frames.append(result)
    if not frames:
        return _empty_lookup_frame()
    return pd.concat(frames, ignore_index=True)




# --- Fast Global Number Cache & Remote Circuit Breaker ---
_SDR_GLOBAL_ROW_CACHE: dict[str, dict] = {}
_SDR_NEGATIVE_CACHE: set[str] = set()
_REMOTE_API_DISABLED_FOR_SESSION: bool = False


def _lookup_from_remote_api(numbers: List[str]) -> pd.DataFrame:
    global _REMOTE_API_DISABLED_FOR_SESSION
    if not numbers or _REMOTE_API_DISABLED_FOR_SESSION:
        return _empty_lookup_frame()
    try:
        from gui.api_client import get_active_api_client
        client = get_active_api_client()
        if client is None or not client.token:
            return _empty_lookup_frame()
        # Skip remote call if pointing to localhost (already using local DuckDB on same machine)
        if "localhost" in client.base_url or "127.0.0.1" in client.base_url:
            return _empty_lookup_frame()
        records = client.lookup_sdr_batch(numbers)
        if not records:
            return _empty_lookup_frame()
        rows = []
        for rec in records:
            mob = normalize_mobile_number(rec.get("mobile_number", ""))
            if not mob:
                continue
            rows.append({
                "lookup_mobile": mob,
                "subscriber_name": rec.get("subscriber_name", "") or "",
                "father_name": rec.get("father_name", "") or "",
                "subscriber_address": rec.get("address", "") or "",
                "id_type": rec.get("id_type", "") or "",
                "id_number": rec.get("id_number", "") or "",
                "operator": rec.get("operator", "") or "",
                "circle": rec.get("circle", "") or "",
                "activation_date": rec.get("activation_date", "") or "",
                "caf_number": rec.get("caf_number", "") or "",
                "source_file": rec.get("source_file", "") or "",
                "sdr_found": "Yes",
            })
        return pd.DataFrame(rows) if rows else _empty_lookup_frame()
    except Exception:
        _REMOTE_API_DISABLED_FOR_SESSION = True
        return _empty_lookup_frame()


@lru_cache(maxsize=32)
def lookup_sdr_subscribers_cached(numbers: tuple[str, ...]) -> pd.DataFrame:
    """Cached lookup for repeated calls with same numbers."""
    normalized_numbers = sorted({normalize_mobile_number(n) for n in numbers})
    if not normalized_numbers:
        return _empty_lookup_frame()

    primary_result = _lookup_from_primary_table(normalized_numbers)
    primary_numbers = set(primary_result["lookup_mobile"]) if not primary_result.empty else set()
    missing_numbers = [n for n in normalized_numbers if n not in primary_numbers]
    large_result = _lookup_from_large_table(missing_numbers)
    large_numbers = set(large_result["lookup_mobile"]) if not large_result.empty else set()
    still_missing = [n for n in missing_numbers if n not in large_numbers]
    remote_result = _lookup_from_remote_api(still_missing)

    frames = []
    if not primary_result.empty:
        frames.append(primary_result)
    if not large_result.empty:
        frames.append(large_result)
    if not remote_result.empty:
        frames.append(remote_result)

    if not frames:
        output = pd.DataFrame({"lookup_mobile": normalized_numbers})
        output["sdr_found"] = "No"
        return output

    return pd.concat(frames, ignore_index=True)


def lookup_sdr_subscribers(numbers: Iterable) -> pd.DataFrame:
    """Public wrapper that converts iterable to tuple for caching."""
    return lookup_sdr_subscribers_cached(tuple(numbers))


def enrich_dataframe_with_sdr(
    dataframe: pd.DataFrame,
    number_column: str = "b_party",
    prefix: str = "other_party_",
) -> pd.DataFrame:
    """Enrich dataframe with SDR profile data."""
    if dataframe is None or not isinstance(dataframe, pd.DataFrame):
        return dataframe
    if dataframe.empty or number_column not in dataframe.columns:
        return dataframe

    output = dataframe.copy()
    output[f"{prefix}lookup_mobile"] = output[number_column].apply(normalize_mobile_number)

    lookup = lookup_sdr_subscribers(output[f"{prefix}lookup_mobile"].dropna().unique())

    if lookup.empty:
        output[f"{prefix}sdr_found"] = "No"
        return output

    renamed = lookup.rename(
        columns={
            "lookup_mobile": f"{prefix}lookup_mobile",
            "subscriber_name": f"{prefix}subscriber_name",
            "father_name": f"{prefix}father_name",
            "subscriber_address": f"{prefix}subscriber_address",
            "id_type": f"{prefix}id_type",
            "id_number": f"{prefix}id_number",
            "operator": f"{prefix}operator",
            "circle": f"{prefix}circle",
            "activation_date": f"{prefix}activation_date",
            "caf_number": f"{prefix}caf_number",
            "source_file": f"{prefix}source_file",
            "sdr_found": f"{prefix}sdr_found",
        }
    )
    output = output.merge(renamed, on=f"{prefix}lookup_mobile", how="left")
    output[f"{prefix}sdr_found"] = output[f"{prefix}sdr_found"].fillna("No")
    return output


# === CDR_FREEZE_FIX_SDR_V3 ===
import time as _sdr_time

_ORIG_LOOKUP_SDR_SUBSCRIBERS = lookup_sdr_subscribers
_ORIG_QUERY_DF_REF = query_dataframe
_SDR_MEM_POS: dict[str, dict] = {}
_SDR_MEM_NEG: set[str] = set()
_LARGE_TABLE_TIMED_OUT: bool = False

# Use the schema-correct, batched lookup above. A failed or slow query must not
# silently disable all remaining large-table lookups for the session.

_ORIG_PRIMARY_TABLE_FN = globals().get("_lookup_from_primary_table")
_ORIG_LARGE_TABLE_FN = globals().get("_lookup_from_large_table")


def lookup_sdr_subscribers(numbers: Iterable) -> pd.DataFrame:
    """O(1) per-number memory-cached SDR lookup preserving sdr_found='No' rows."""
    from modules.database.master_access import ensure_master_cache_current
    ensure_master_cache_current()
    if (
        query_dataframe is not _ORIG_QUERY_DF_REF
        or globals().get("_lookup_from_primary_table") is not _ORIG_PRIMARY_TABLE_FN
        or globals().get("_lookup_from_large_table") is not _ORIG_LARGE_TABLE_FN
    ):
        if "lookup_sdr_subscribers_cached" in globals() and hasattr(lookup_sdr_subscribers_cached, "cache_clear"):
            lookup_sdr_subscribers_cached.cache_clear()
        return _ORIG_LOOKUP_SDR_SUBSCRIBERS(numbers)

    normalized = sorted({normalize_mobile_number(n) for n in numbers if normalize_mobile_number(n)})
    if not normalized:
        return _ORIG_LOOKUP_SDR_SUBSCRIBERS(numbers)

    missing = [n for n in normalized if n not in _SDR_MEM_POS]

    if missing:
        if "lookup_sdr_subscribers_cached" in globals() and hasattr(lookup_sdr_subscribers_cached, "cache_clear"):
            lookup_sdr_subscribers_cached.cache_clear()
        new_df = _ORIG_LOOKUP_SDR_SUBSCRIBERS(missing)
        if isinstance(new_df, pd.DataFrame) and not new_df.empty:
            for rec in new_df.to_dict(orient="records"):
                k = str(rec.get("lookup_mobile", "")).strip()
                if k:
                    _SDR_MEM_POS[k] = rec
        for m in missing:
            if m not in _SDR_MEM_POS:
                _SDR_MEM_POS[m] = {"lookup_mobile": m, "sdr_found": "No"}

    hit_rows = [_SDR_MEM_POS[n] for n in normalized if n in _SDR_MEM_POS]
    if not hit_rows:
        return _empty_lookup_frame()
    return pd.DataFrame(hit_rows).drop_duplicates(subset=["lookup_mobile"], keep="first")




def clear_sdr_lookup_caches() -> None:
    """Invalidate all positive/negative caches after master-data imports."""
    lookup_sdr_subscribers_cached.cache_clear()
    _normalize_mobile_cached.cache_clear()
    for name in ("_SDR_MEM_POS", "_SDR_MEM_NEG", "_SDR_GLOBAL_ROW_CACHE", "_SDR_NEGATIVE_CACHE"):
        cache = globals().get(name)
        if hasattr(cache, "clear"):
            cache.clear()
