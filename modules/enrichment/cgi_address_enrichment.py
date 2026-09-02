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
    if found is not None and not found.empty:
        return found.drop_duplicates(
            subset=["cgi"],
            keep="last",
        )
    return pd.DataFrame(columns=CGI_LOOKUP_COLUMNS)


def lookup_cgi_addresses(cgi_values: Iterable) -> pd.DataFrame:
    normalized = sorted({normalize_cgi(v) for v in cgi_values if normalize_cgi(v)})
    if not normalized:
        return pd.DataFrame(columns=CGI_LOOKUP_COLUMNS)
    try:
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