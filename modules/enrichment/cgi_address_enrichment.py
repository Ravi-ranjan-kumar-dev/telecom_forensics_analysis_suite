"""CGI address enrichment with caching and dynamic prefixes."""

from functools import lru_cache
from typing import Iterable, Optional

import pandas as pd
import duckdb

from modules.database.cgi_repository import normalize_cgi, lookup_cgi_dataframe_cached
from modules.database.duckdb_core import query_dataframe as _original_query_dataframe

# Module-level reference for monkeypatching in tests
query_dataframe = _original_query_dataframe

CELL_ID_CANDIDATES = [
    "tower", "Tower", "Tower ID", "Cell Tower", "Cell ID / CGI",
    "First Cell ID", "Last Cell ID", "From Tower", "To Tower",
    "Primary Tower", "first_cell_id", "last_cell_id", "cell_id",
    "cgi", "cgi_id", "first_cell_global_id", "last_cell_global_id",
    "first_cell_global_identity", "last_cell_global_identity",
    "Cell ID", "CGI", "First Cell Global Id", "Last Cell Global Id",
]

CGI_LOOKUP_COLUMNS = [
    "cgi", "operator", "circle", "state", "district", "police_station",
    "town", "site_name", "address", "latitude", "longitude", "source_file",
]


def detect_cell_id_column(dataframe: pd.DataFrame) -> Optional[str]:
    if dataframe is None or dataframe.empty:
        return None
    existing_columns = {str(column).strip(): column for column in dataframe.columns}
    for candidate in CELL_ID_CANDIDATES:
        if candidate in existing_columns:
            return existing_columns[candidate]
    normalized_map = {
        str(column).strip().lower().replace(" ", "_"): column
        for column in dataframe.columns
    }
    for candidate in CELL_ID_CANDIDATES:
        normalized_candidate = candidate.strip().lower().replace(" ", "_")
        if normalized_candidate in normalized_map:
            return normalized_map[normalized_candidate]
    return None




def _lookup_cgi_from_remote_api(cgis: list[str]) -> pd.DataFrame:
    if not cgis:
        return pd.DataFrame(columns=CGI_LOOKUP_COLUMNS)
    try:
        from gui.api_client import get_active_api_client
        client = get_active_api_client()
        if client is None or not client.token:
            return pd.DataFrame(columns=CGI_LOOKUP_COLUMNS)
        if 'localhost' in client.base_url or '127.0.0.1' in client.base_url:
            return pd.DataFrame(columns=CGI_LOOKUP_COLUMNS)
        records = client.lookup_cgi_batch(cgis)
        if not records:
            return pd.DataFrame(columns=CGI_LOOKUP_COLUMNS)
        rows = []
        for rec in records:
            key = normalize_cgi(rec.get("cgi", ""))
            if not key:
                continue
            rows.append({
                "cgi": key,
                "operator": rec.get("operator", "") or "",
                "circle": rec.get("circle", "") or "",
                "state": rec.get("state", "") or "",
                "district": rec.get("district", "") or "",
                "police_station": rec.get("police_station", "") or "",
                "town": rec.get("town", "") or "",
                "site_name": rec.get("site_name", "") or "",
                "address": rec.get("address", "") or "",
                "latitude": rec.get("latitude"),
                "longitude": rec.get("longitude"),
                "source_file": rec.get("source_file", "") or "",
            })
        return pd.DataFrame(rows, columns=CGI_LOOKUP_COLUMNS) if rows else pd.DataFrame(columns=CGI_LOOKUP_COLUMNS)
    except Exception:
        return pd.DataFrame(columns=CGI_LOOKUP_COLUMNS)


@lru_cache(maxsize=32)
def _lookup_cgi_addresses_cached(cgi_tuple: tuple[str, ...]) -> pd.DataFrame:
    if not cgi_tuple:
        return pd.DataFrame(columns=CGI_LOOKUP_COLUMNS)
    unique = list(cgi_tuple)
    placeholders = ",".join(["?"] * len(unique))
    sql = f"""
        SELECT cgi, operator, circle, state, district, police_station,
               town, site_name, address, latitude, longitude, source_file
        FROM cgi_addresses
        WHERE cgi IN ({placeholders})
    """
    found = query_dataframe(sql, unique)

    frames = []
    found_keys: set[str] = set()
    if found is not None and not found.empty:
        deduped = found.drop_duplicates(subset=["cgi"], keep="last")
        frames.append(deduped)
        found_keys = set(deduped["cgi"].astype(str).tolist())

    missing = [c for c in unique if c not in found_keys]
    if missing:
        remote_df = _lookup_cgi_from_remote_api(missing)
        if not remote_df.empty:
            frames.append(remote_df)

    if frames:
        return pd.concat(frames, ignore_index=True).drop_duplicates(subset=["cgi"], keep="last")
    return pd.DataFrame(columns=CGI_LOOKUP_COLUMNS)


def lookup_cgi_addresses(cgi_values: Iterable) -> pd.DataFrame:
    normalized = sorted({normalize_cgi(v) for v in cgi_values if normalize_cgi(v)})
    if not normalized:
        return pd.DataFrame(columns=CGI_LOOKUP_COLUMNS)
    try:
        if query_dataframe is not _original_query_dataframe:
            _lookup_cgi_addresses_cached.cache_clear()
        return _lookup_cgi_addresses_cached(
            tuple(normalized)
        )
    except duckdb.CatalogException as error:
        message = str(error).casefold()
        missing_table = (
            "cgi_addresses" in message
            and "does not exist" in message
        )
        if missing_table:
            remote_df = _lookup_cgi_from_remote_api(normalized)
            if not remote_df.empty:
                return remote_df
            return pd.DataFrame(
                columns=CGI_LOOKUP_COLUMNS
            )
        raise


def enrich_dataframe_with_cgi_address(
    dataframe: pd.DataFrame,
    cell_id_column: Optional[str] = None,
    prefix: Optional[str] = None,
) -> pd.DataFrame:
    if dataframe is None or dataframe.empty:
        return dataframe

    output = dataframe.copy()
    selected_column = cell_id_column or detect_cell_id_column(output)

    if selected_column is None:
        prefix = prefix or "tower_"
        output[f"{prefix}address_found"] = "No"
        output[f"{prefix}lookup_key"] = ""
        output[f"{prefix}operator"] = ""
        output[f"{prefix}circle"] = ""
        output[f"{prefix}town"] = ""
        output[f"{prefix}site_name"] = ""
        output[f"{prefix}address"] = ""
        output[f"{prefix}latitude"] = pd.NA
        output[f"{prefix}longitude"] = pd.NA
        output[f"{prefix}source_file"] = ""
        return output

    if prefix is None:
        prefix = _cgi_prefix_from_column(selected_column)

    output[f"{prefix}lookup_key"] = output[selected_column].map(normalize_cgi)
    lookup = lookup_cgi_addresses(output[f"{prefix}lookup_key"].dropna().unique())

    if lookup.empty:
        output[f"{prefix}address_found"] = "No"
        for col in [f"{prefix}operator", f"{prefix}circle", f"{prefix}town", f"{prefix}site_name", f"{prefix}address", f"{prefix}source_file"]:
            output[col] = ""
        output[f"{prefix}latitude"] = pd.NA
        output[f"{prefix}longitude"] = pd.NA
        return output

    lookup = lookup.rename(
        columns={
            "cgi": f"{prefix}lookup_key",
            "operator": f"{prefix}operator",
            "circle": f"{prefix}circle",
            "town": f"{prefix}town",
            "site_name": f"{prefix}site_name",
            "address": f"{prefix}address",
            "latitude": f"{prefix}latitude",
            "longitude": f"{prefix}longitude",
            "source_file": f"{prefix}source_file",
        }
    )

    keep_columns = [
        f"{prefix}lookup_key", f"{prefix}operator", f"{prefix}circle",
        f"{prefix}town", f"{prefix}site_name", f"{prefix}address",
        f"{prefix}latitude", f"{prefix}longitude", f"{prefix}source_file",
    ]

    output = output.merge(lookup[keep_columns], on=f"{prefix}lookup_key", how="left")
    output[f"{prefix}address_found"] = output[f"{prefix}address"].fillna("").astype(str).str.strip()
    output[f"{prefix}address_found"] = output[f"{prefix}address_found"].map(lambda v: "Yes" if v else "No")

    for col in [f"{prefix}operator", f"{prefix}circle", f"{prefix}town", f"{prefix}site_name", f"{prefix}address", f"{prefix}source_file"]:
        output[col] = output[col].fillna("")

    return output


def _cgi_prefix_from_column(column: str) -> str:
    col_lower = str(column).lower()
    mapping = {
        "cgi": "cgi_",
        "cell_id": "cell_",
        "searched_cell_id": "searched_cell_",
        "first_cell_id": "first_cell_",
        "last_cell_id": "last_cell_",
        "primary_cell_id": "primary_cell_",
    }
    if col_lower in mapping:
        return mapping[col_lower]
    return col_lower.replace(" ", "_").replace("-", "_") + "_"


def build_missing_cgi_lookup_summary(
    dataframe: pd.DataFrame,
    cell_id_column: Optional[str] = None,
    source_table: str = "",
) -> pd.DataFrame:
    if dataframe is None or dataframe.empty:
        return pd.DataFrame(columns=["cell_id", "records", "source_table"])

    enriched = enrich_dataframe_with_cgi_address(dataframe, cell_id_column)

    if "tower_address_found" not in enriched.columns:
        return pd.DataFrame(columns=["cell_id", "records", "source_table"])

    missing = enriched[enriched["tower_address_found"].eq("No")].copy()
    if missing.empty:
        return pd.DataFrame(columns=["cell_id", "records", "source_table"])

    cell_column = cell_id_column or detect_cell_id_column(missing)
    if cell_column is None:
        return pd.DataFrame(columns=["cell_id", "records", "source_table"])

    summary = (
        missing.groupby(cell_column, dropna=False)
        .size()
        .reset_index(name="records")
        .rename(columns={cell_column: "cell_id"})
    )
    summary["source_table"] = source_table
    return summary.sort_values("records", ascending=False)


# === CDR_FREEZE_FIX_CGI_V3 ===
_ORIG_LOOKUP_CGI_ADDRESSES = lookup_cgi_addresses
_CGI_MEM_POS: dict[str, dict] = {}
_CGI_MEM_NEG: set[str] = set()


def clear_cgi_lookup_caches():
    _lookup_cgi_addresses_cached.cache_clear()
    _CGI_MEM_POS.clear()
    _CGI_MEM_NEG.clear()


def lookup_cgi_addresses(cgi_values: Iterable) -> pd.DataFrame:
    """O(1) per-CGI memory-cached lookup across CDR/IPDR/Tower tables (monkeypatch-safe)."""
    from modules.database.master_access import ensure_master_cache_current
    ensure_master_cache_current()
    if query_dataframe is not _original_query_dataframe:
        _lookup_cgi_addresses_cached.cache_clear()
        return _ORIG_LOOKUP_CGI_ADDRESSES(cgi_values)

    normalized = sorted({normalize_cgi(v) for v in cgi_values if normalize_cgi(v)})
    if not normalized:
        return pd.DataFrame(columns=CGI_LOOKUP_COLUMNS)

    hit_rows = [_CGI_MEM_POS[c] for c in normalized if c in _CGI_MEM_POS]
    missing = [c for c in normalized if c not in _CGI_MEM_POS and c not in _CGI_MEM_NEG]

    if missing:
        _lookup_cgi_addresses_cached.cache_clear()
        new_df = _ORIG_LOOKUP_CGI_ADDRESSES(missing)
        found_keys = set()
        if isinstance(new_df, pd.DataFrame) and not new_df.empty:
            for rec in new_df.to_dict(orient="records"):
                k = str(rec.get("cgi", "")).strip()
                if k:
                    _CGI_MEM_POS[k] = rec
                    found_keys.add(k)
                    hit_rows.append(rec)
        for c in missing:
            if c not in found_keys:
                _CGI_MEM_NEG.add(c)

    if not hit_rows:
        return pd.DataFrame(columns=CGI_LOOKUP_COLUMNS)
    return pd.DataFrame(hit_rows, columns=CGI_LOOKUP_COLUMNS).drop_duplicates(subset=["cgi"], keep="last")


