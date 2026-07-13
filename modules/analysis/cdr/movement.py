import pandas as pd

from .datetime_utils import canonical_datetime


def tower_movement(df):
    """Chronological cell-site hops using the canonical event timestamp."""
    if df is None or df.empty or "first_cell_id" not in df.columns:
        return pd.DataFrame()

    cols = ["call_date", "call_time", "first_cell_id", "b_party", "call_type"]
    movement = df[[c for c in cols if c in df.columns]].copy()
    movement["_event_datetime"] = canonical_datetime(df)
    movement = movement.dropna(subset=["first_cell_id", "_event_datetime"])
    movement = movement.sort_values("_event_datetime")

    # Consecutive same-tower records are retained in source data; only this
    # derived route view suppresses repeated stationary points.
    movement = movement.loc[
        movement["first_cell_id"].astype(str).ne(
            movement["first_cell_id"].astype(str).shift()
        )
    ]
    return movement.drop(columns=["_event_datetime"], errors="ignore").reset_index(drop=True)


def tower_transition(df):
    """Step-by-step corridor analysis (From Tower -> To Tower)."""
    movement = tower_movement(df).copy()
    if movement.empty:
        return pd.DataFrame()

    movement["From Tower"] = movement["first_cell_id"].shift(1)
    movement["To Tower"] = movement["first_cell_id"]
    movement = movement.dropna(subset=["From Tower"])
    output = [
        column
        for column in [
            "call_date",
            "call_time",
            "From Tower",
            "To Tower",
            "b_party",
            "call_type",
        ]
        if column in movement.columns
    ]
    return movement[output].reset_index(drop=True)


def movement_pattern(df):
    """Identify repeated derived movement routes."""
    trans = tower_transition(df)
    if trans.empty:
        return pd.DataFrame(columns=["From Tower", "To Tower", "Occurrences"])

    return (
        trans.groupby(["From Tower", "To Tower"])
        .size()
        .reset_index(name="Occurrences")
        .sort_values(by="Occurrences", ascending=False, ignore_index=True)
    )
