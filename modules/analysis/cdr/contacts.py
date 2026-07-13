import pandas as pd

from .rules import (
    CONTACT_DURATION_MINUTE_WEIGHT,
    CONTACT_EVENT_WEIGHT,
    CONTACT_SCORE_FORMULA,
    CONTACT_UNIQUE_TOWER_WEIGHT,
    RULESET_VERSION,
)

def top_contacts(df, limit=20):
    if df is None or df.empty or 'b_party' not in df.columns:
        return pd.DataFrame(columns=["Contact", "Total Calls"])
    
    contacts = df[df["b_party"].astype(str).str.strip() != ""]
    result = contacts["b_party"].value_counts().head(limit).reset_index()
    result.columns = ["Contact", "Total Calls"]
    return result

def contact_summary(df, target_number):
    """Returns a dictionary summary for a specific contact (fixes reports.py loop bug)."""
    if df is None or df.empty or 'b_party' not in df.columns:
        return {}
        
    target_df = df[df["b_party"] == target_number]
    if target_df.empty:
        return {"Status": "No interactions recorded"}
        
    summary = {
        "Total Interactions": len(target_df),
        "Incoming Events": len(target_df[target_df["call_type"].str.lower().isin(["incoming", "mtc", "a_in"])]) if "call_type" in target_df.columns else 0,
        "Outgoing Events": len(target_df[target_df["call_type"].str.lower().isin(["outgoing", "moc", "a_out"])]) if "call_type" in target_df.columns else 0,
        "Total Duration (Sec)": int(target_df["call_duration"].sum()) if "call_duration" in target_df.columns else 0,
        "Unique IMEIs Used": target_df["imei"].nunique() if "imei" in target_df.columns else 0,
        "Unique Co-located Towers": target_df["first_cell_id"].nunique() if "first_cell_id" in target_df.columns else 0
    }
    return summary

def incoming_outgoing(df):
    if df is None or df.empty or "call_type" not in df.columns:
        return pd.DataFrame()
    return df.groupby("call_type").size().reset_index(name="Total Records")

def contact_ranking(df):
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

    summary["Score"] = (
        summary["Total_Events"] * CONTACT_EVENT_WEIGHT
        + (summary["Total_Duration"] / 60) * CONTACT_DURATION_MINUTE_WEIGHT
        + summary["Unique_Towers"] * CONTACT_UNIQUE_TOWER_WEIGHT
    )
    summary["Score_Ruleset"] = RULESET_VERSION
    summary["Score_Formula"] = CONTACT_SCORE_FORMULA
    return summary.sort_values("Score", ascending=False).rename(columns={"b_party": "Contact"})
