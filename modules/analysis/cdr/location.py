import pandas as pd

from .tower_utils import (
    filter_valid_first_cell_rows,
    normalize_cell_id,
)


def analyze_location(df):
    """Analyze valid first cell ID tower profile."""
    if df is None or df.empty or "first_cell_id" not in df.columns:
        return pd.DataFrame()

    valid_tower_rows = filter_valid_first_cell_rows(df)

    location_summary = {
        "Metric": [
            "Total Logged Cell-Site Rows",
            "Rows With Valid Cell ID",
            "Rows With Invalid/Missing Cell ID",
            "Unique Valid Cell Towers Discovered",
            "Primary/Most Frequent Valid Cell Site",
        ],
        "Value": [
            len(df),
            len(valid_tower_rows),
            len(df) - len(valid_tower_rows),
            valid_tower_rows["first_cell_id"].nunique()
            if not valid_tower_rows.empty
            else 0,
            valid_tower_rows["first_cell_id"].mode().iloc[0]
            if not valid_tower_rows.empty
            and not valid_tower_rows["first_cell_id"].mode().empty
            else "N/A",
        ],
    }

    return pd.DataFrame(location_summary)


def frequent_locations(df, top_n=5):
    """Return top valid cell towers only."""
    if df is None or df.empty or "first_cell_id" not in df.columns:
        return pd.DataFrame(columns=["Cell ID", "Total Events"])

    valid_tower_rows = filter_valid_first_cell_rows(df)
    if valid_tower_rows.empty:
        return pd.DataFrame(columns=["Cell ID", "Total Events"])

    counts = valid_tower_rows["first_cell_id"].value_counts().head(top_n).reset_index()
    counts.columns = ["Cell ID", "Total Events"]
    return counts


def bottom_cgi(df, limit=10):
    """Return the least-frequent valid serving CGI/tower identifiers."""

    if df is None or df.empty or "first_cell_id" not in df.columns:
        return pd.DataFrame(
            columns=[
                "Cell ID",
                "Total Events",
            ]
        )

    valid_tower_rows = filter_valid_first_cell_rows(
        df
    )

    if valid_tower_rows.empty:
        return pd.DataFrame(
            columns=[
                "Cell ID",
                "Total Events",
            ]
        )

    normalized = valid_tower_rows[
        "first_cell_id"
    ].map(
        normalize_cell_id
    )

    return (
        normalized.value_counts()
        .rename_axis(
            "Cell ID"
        )
        .reset_index(
            name="Total Events"
        )
        .sort_values(
            [
                "Total Events",
                "Cell ID",
            ],
            ascending=[
                True,
                True,
            ],
            kind="stable",
        )
        .head(
            max(
                1,
                int(
                    limit
                ),
            )
        )
        .reset_index(
            drop=True
        )
    )
