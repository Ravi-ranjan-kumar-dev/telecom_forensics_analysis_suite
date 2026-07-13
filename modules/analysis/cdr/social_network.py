import pandas as pd

from .rules import (
    NETWORK_DURATION_MINUTE_WEIGHT,
    NETWORK_EVENT_WEIGHT,
    NETWORK_STRENGTH_FORMULA,
    RULESET_VERSION,
)

def social_network(df):
    """Calculates network linkage communication strength matrix."""
    if df is None or df.empty or "b_party" not in df.columns:
        return pd.DataFrame()

    contacts = df[df["b_party"].astype(str).str.strip() != ""].copy()
    summary = contacts.groupby("b_party").agg(
        Total_Events=("b_party", "count"),
        Incoming=("call_type", lambda x: x.str.lower().isin(["incoming", "mtc", "a_in"]).sum()),
        Outgoing=("call_type", lambda x: x.str.lower().isin(["outgoing", "moc", "a_out"]).sum()),
        SMS=("call_type", lambda x: x.str.contains("sms", case=False, na=False).sum()),
        Total_Duration=("call_duration", "sum"),
        Unique_Towers=("first_cell_id", "nunique")
    ).reset_index()

    summary["Strength"] = (
        summary["Total_Events"] * NETWORK_EVENT_WEIGHT
        + (summary["Total_Duration"] / 60) * NETWORK_DURATION_MINUTE_WEIGHT
    )
    summary["Strength_Ruleset"] = RULESET_VERSION
    summary["Strength_Formula"] = NETWORK_STRENGTH_FORMULA
    return summary.sort_values(by="Strength", ascending=False).rename(columns={"b_party": "Contact"})
