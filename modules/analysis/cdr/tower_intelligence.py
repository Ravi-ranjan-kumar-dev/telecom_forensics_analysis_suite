import pandas as pd

from .datetime_utils import canonical_datetime
from .rules import HOME_WINDOW, RULESET_VERSION, WORK_WINDOW

def tower_intelligence(df):
    """
    Generate a highly optimized forensic intelligence report for every Cell ID.
    Replaces slow python loops with blazing-fast vectorized operations.
    """
    if df is None or df.empty or "first_cell_id" not in df.columns:
        return pd.DataFrame(columns=[
            "Cell ID", "First Seen", "Last Seen", "Total Events", 
            "Unique Contacts", "Unique IMEIs", "Total Duration (Sec)", 
            "Most Used IMEI", "Most Contacted"
        ])

    # Clean and filter blank cell IDs
    data = df[df["first_cell_id"].astype(str).str.strip() != ""].copy()
    if data.empty:
        return pd.DataFrame(columns=["Cell ID", "First Seen", "Last Seen", "Total Events"])

    # Combine date and time safely into a single datetime index
    data["datetime"] = canonical_datetime(data)
    data = data.dropna(subset=["datetime"])
    if data.empty:
        return pd.DataFrame()

    # 1. Vectorized Core Metrics Aggregation (Super Fast)
    agg_dict = {
        "First Seen": ("datetime", "min"),
        "Last Seen": ("datetime", "max"),
        "Total Events": ("datetime", "size")
    }
    if "b_party" in data.columns:
        agg_dict["Unique Contacts"] = ("b_party", "nunique")
    if "imei" in data.columns:
        agg_dict["Unique IMEIs"] = ("imei", "nunique")
    if "call_duration" in data.columns:
        agg_dict["Total Duration (Sec)"] = ("call_duration", "sum")

    summary = data.groupby("first_cell_id").agg(**agg_dict).reset_index()
    summary.rename(columns={"first_cell_id": "Cell ID"}, inplace=True)

    # 2. Optimized Mode Calculation for IMEI (Vectorized Groupby Hack)
    if "imei" in data.columns and not data["imei"].dropna().empty:
        imei_counts = data[data["imei"].astype(str).str.strip() != ""].groupby(["first_cell_id", "imei"]).size().reset_index(name="cnt")
        top_imei = imei_counts.sort_values("cnt", ascending=False).drop_duplicates("first_cell_id").rename(columns={"first_cell_id": "Cell ID", "imei": "Most Used IMEI"})
        summary = pd.merge(summary, top_imei[["Cell ID", "Most Used IMEI"]], on="Cell ID", how="left")
    else:
        summary["Most Used IMEI"] = "N/A"

    # 3. Optimized Mode Calculation for B-Party (Vectorized Groupby Hack)
    if "b_party" in data.columns and not data["b_party"].dropna().empty:
        b_counts = data[data["b_party"].astype(str).str.strip() != ""].groupby(["first_cell_id", "b_party"]).size().reset_index(name="cnt")
        top_b = b_counts.sort_values("cnt", ascending=False).drop_duplicates("first_cell_id").rename(columns={"first_cell_id": "Cell ID", "b_party": "Most Contacted"})
        summary = pd.merge(summary, top_b[["Cell ID", "Most Contacted"]], on="Cell ID", how="left")
    else:
        summary["Most Contacted"] = "N/A"

    # Fill missing column defaults for safety assurance
    for col in ["Unique Contacts", "Unique IMEIs", "Total Duration (Sec)"]:
        if col not in summary.columns:
            summary[col] = 0
    summary["Most Used IMEI"] = summary["Most Used IMEI"].fillna("N/A")
    summary["Most Contacted"] = summary["Most Contacted"].fillna("N/A")
    summary["Total Duration (Sec)"] = summary["Total Duration (Sec)"].fillna(0).astype(int)
    
    return summary.sort_values(by="Total Events", ascending=False).reset_index(drop=True)


def home_tower(df):
    """
    Detect probable Home Tower based on night-time activity (22:00–06:00).
    Returns an empty DataFrame instead of None to prevent module crashes.
    """
    if df is None or df.empty or "first_cell_id" not in df.columns:
        return pd.DataFrame(columns=["Cell ID", "Night_Events", "Unique_Days", "Unique_Contacts"])

    data = df[df["first_cell_id"].astype(str).str.strip() != ""].copy()
    if "call_time" not in data.columns:
        return pd.DataFrame(columns=["Cell ID", "Night_Events", "Unique_Days", "Unique_Contacts"])

    data["datetime"] = canonical_datetime(data)
    data = data.dropna(subset=["datetime"])
    if data.empty:
        return pd.DataFrame(columns=["Cell ID", "Night_Events", "Unique_Days", "Unique_Contacts"])

    data["Hour"] = data["datetime"].dt.hour
    night = data[(data["Hour"] >= 22) | (data["Hour"] < 6)]

    if night.empty:
        return pd.DataFrame(columns=["Cell ID", "Night_Events", "Unique_Days", "Unique_Contacts"])

    agg_dict = {
        "Night_Events": ("first_cell_id", "count"),
        "Unique_Days": ("call_date", "nunique")
    }
    if "b_party" in night.columns:
        agg_dict["Unique_Contacts"] = ("b_party", "nunique")

    summary = night.groupby("first_cell_id").agg(**agg_dict).reset_index()
    summary.rename(columns={"first_cell_id": "Cell ID"}, inplace=True)
    
    if "Unique_Contacts" not in summary.columns:
        summary["Unique_Contacts"] = 0

    summary["Window"] = HOME_WINDOW
    summary["Ruleset"] = RULESET_VERSION
    return summary.sort_values(by="Night_Events", ascending=False).reset_index(drop=True)


def work_tower(df):
    """
    Detect probable Work Tower based on office-hour activity (09:00–18:00).
    """
    if df is None or df.empty or "first_cell_id" not in df.columns:
        return pd.DataFrame(columns=["Cell ID", "Office_Events", "Working_Days", "Unique_Contacts"])

    data = df[df["first_cell_id"].astype(str).str.strip() != ""].copy()
    if "call_time" not in data.columns:
        return pd.DataFrame(columns=["Cell ID", "Office_Events", "Working_Days", "Unique_Contacts"])

    data["datetime"] = canonical_datetime(data)
    data = data.dropna(subset=["datetime"])
    if data.empty:
        return pd.DataFrame(columns=["Cell ID", "Office_Events", "Working_Days", "Unique_Contacts"])

    data["Hour"] = data["datetime"].dt.hour
    office = data[(data["Hour"] >= 9) & (data["Hour"] < 18)]

    if office.empty:
        return pd.DataFrame(columns=["Cell ID", "Office_Events", "Working_Days", "Unique_Contacts"])

    agg_dict = {
        "Office_Events": ("first_cell_id", "count"),
        "Working_Days": ("call_date", "nunique")
    }
    if "b_party" in office.columns:
        agg_dict["Unique_Contacts"] = ("b_party", "nunique")

    summary = office.groupby("first_cell_id").agg(**agg_dict).reset_index()
    summary.rename(columns={"first_cell_id": "Cell ID"}, inplace=True)

    if "Unique_Contacts" not in summary.columns:
        summary["Unique_Contacts"] = 0

    return summary.sort_values(by="Office_Events", ascending=False).reset_index(drop=True)