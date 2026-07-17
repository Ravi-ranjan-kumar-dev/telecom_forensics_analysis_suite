import pandas as pd

from .contact_classifier import only_human_contacts
from .rules import (
    NETWORK_DURATION_MINUTE_WEIGHT,
    NETWORK_EVENT_WEIGHT,
    NETWORK_STRENGTH_FORMULA,
    RULESET_VERSION,
)


def social_network(df):
    """Human/mobile contact network only. Service sender IDs and short codes are excluded."""
    if df is None or df.empty or "b_party" not in df.columns:
        return pd.DataFrame()

    contacts = only_human_contacts(df)
    if contacts.empty:
        return pd.DataFrame()

    contacts = contacts.copy()
    contacts["_call_type_clean"] = (
        contacts["call_type"].astype("string").fillna("").str.lower().str.strip()
        if "call_type" in contacts.columns
        else ""
    )

    summary = contacts.groupby("b_party").agg(
        Total_Events=("b_party", "count"),
        Incoming=("_call_type_clean", lambda x: x.isin(["incoming", "mtc", "a_in"]).sum()),
        Outgoing=("_call_type_clean", lambda x: x.isin(["outgoing", "moc", "a_out"]).sum()),
        SMS=("_call_type_clean", lambda x: x.str.contains("sms", case=False, na=False).sum()),
        Total_Duration=("call_duration", "sum"),
        Unique_Towers=("first_cell_id", "nunique"),
    ).reset_index()

    summary["Strength"] = (
        summary["Total_Events"] * NETWORK_EVENT_WEIGHT
        + (summary["Total_Duration"] / 60) * NETWORK_DURATION_MINUTE_WEIGHT
    )
    summary["Strength_Ruleset"] = RULESET_VERSION
    summary["Strength_Formula"] = NETWORK_STRENGTH_FORMULA

    return summary.sort_values(by="Strength", ascending=False).rename(columns={"b_party": "Contact"})
