from __future__ import annotations

from typing import Iterable, Optional
import pandas as pd

from modules.database.cgi_repository import normalize_cgi
from modules.database.duckdb_core import query_dataframe


CELL_ID_CANDIDATES = [
    "tower",
    "Tower",
    "Tower ID",
    "Cell Tower",
    "Cell ID / CGI",
    "First Cell ID",
    "Last Cell ID",
    "From Tower",
    "To Tower",
    "Primary Tower",
    "first_cell_id",
    "last_cell_id",
    "cell_id",
    "cgi",
    "cgi_id",
    "first_cell_global_id",
    "last_cell_global_id",
    "first_cell_global_identity",
    "last_cell_global_identity",
    "Cell ID",
    "CGI",
    "First Cell Global Id",
    "Last Cell Global Id",
]


CGI_LOOKUP_COLUMNS = [
    "cgi",
    "operator",
    "circle",
    "state",
    "district",
    "police_station",
    "town",
    "site_name",
    "address",
    "latitude",
    "longitude",
    "source_file",
]


def detect_cell_id_column(dataframe: pd.DataFrame) -> Optional[str]:
    """
    Detect the most likely Cell ID / CGI column in a dataframe.
    """
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


def _chunks(values: list[str], size: int = 5000):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def lookup_cgi_addresses(cgi_values: Iterable) -> pd.DataFrame:
    """
    Bulk lookup CGI values from DuckDB cgi_addresses table.

    Returns one row per found CGI key.
    """
    normalized_values = []

    for value in cgi_values:
        normalized = normalize_cgi(value)
        if normalized:
            normalized_values.append(str(normalized).strip())

    unique_values = sorted(set(normalized_values))

    if not unique_values:
        return pd.DataFrame(columns=CGI_LOOKUP_COLUMNS)

    frames = []

    for batch in _chunks(unique_values):
        placeholders = ", ".join(["?"] * len(batch))

        sql = f"""
            SELECT
                cgi,
                operator,
                circle,
                state,
                district,
                police_station,
                town,
                site_name,
                address,
                latitude,
                longitude,
                source_file
            FROM cgi_addresses
            WHERE cgi IN ({placeholders})
        """

        found = query_dataframe(sql, batch)

        if found is not None and not found.empty:
            frames.append(found)

    if not frames:
        return pd.DataFrame(columns=CGI_LOOKUP_COLUMNS)

    result = pd.concat(frames, ignore_index=True)
    result = result.drop_duplicates(subset=["cgi"], keep="last")

    return result


def enrich_dataframe_with_cgi_address(
    dataframe: pd.DataFrame,
    cell_id_column: Optional[str] = None,
    prefix: str = "tower_",
) -> pd.DataFrame:
    """
    Add CGI tower address columns to any dataframe.

    This is intentionally simple:
    - Found address = Yes
    - Not found = No
    - No confidence system added
    """
    if dataframe is None or dataframe.empty:
        return dataframe

    output = dataframe.copy()

    selected_column = cell_id_column or detect_cell_id_column(output)

    if selected_column is None:
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

    output[f"{prefix}lookup_key"] = output[selected_column].map(normalize_cgi)

    lookup = lookup_cgi_addresses(output[f"{prefix}lookup_key"].dropna().unique())

    if lookup.empty:
        output[f"{prefix}address_found"] = "No"
        output[f"{prefix}operator"] = ""
        output[f"{prefix}circle"] = ""
        output[f"{prefix}town"] = ""
        output[f"{prefix}site_name"] = ""
        output[f"{prefix}address"] = ""
        output[f"{prefix}latitude"] = pd.NA
        output[f"{prefix}longitude"] = pd.NA
        output[f"{prefix}source_file"] = ""
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
        f"{prefix}lookup_key",
        f"{prefix}operator",
        f"{prefix}circle",
        f"{prefix}town",
        f"{prefix}site_name",
        f"{prefix}address",
        f"{prefix}latitude",
        f"{prefix}longitude",
        f"{prefix}source_file",
    ]

    output = output.merge(
        lookup[keep_columns],
        on=f"{prefix}lookup_key",
        how="left",
    )

    output[f"{prefix}address_found"] = output[f"{prefix}address"].fillna("").astype(str).str.strip()
    output[f"{prefix}address_found"] = output[f"{prefix}address_found"].map(
        lambda value: "Yes" if value else "No"
    )

    for column in [
        f"{prefix}operator",
        f"{prefix}circle",
        f"{prefix}town",
        f"{prefix}site_name",
        f"{prefix}address",
        f"{prefix}source_file",
    ]:
        output[column] = output[column].fillna("")

    return output


def build_missing_cgi_lookup_summary(
    dataframe: pd.DataFrame,
    cell_id_column: Optional[str] = None,
) -> pd.DataFrame:
    """
    Build simple missing CGI lookup summary.
    """
    if dataframe is None or dataframe.empty:
        return pd.DataFrame(columns=["cell_id", "records"])

    enriched = enrich_dataframe_with_cgi_address(dataframe, cell_id_column)

    if "tower_address_found" not in enriched.columns:
        return pd.DataFrame(columns=["cell_id", "records"])

    missing = enriched[enriched["tower_address_found"].eq("No")].copy()

    if missing.empty:
        return pd.DataFrame(columns=["cell_id", "records"])

    cell_column = cell_id_column or detect_cell_id_column(missing)

    if cell_column is None:
        return pd.DataFrame(columns=["cell_id", "records"])

    summary = (
        missing.groupby(cell_column, dropna=False)
        .size()
        .reset_index(name="records")
        .rename(columns={cell_column: "cell_id"})
        .sort_values("records", ascending=False)
    )

    return summary
