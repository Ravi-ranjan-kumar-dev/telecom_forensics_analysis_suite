#imei.py

import pandas as pd

from .datetime_utils import canonical_datetime

def imei_summary(df):
    """
    Generate a summary report for IMEIs in the dataset using optimized groupby.
    """
    # 1. Prepare Data
    data = df[df["imei"].notnull() & (df["imei"] != "")].copy()
    
    # 2. Consume the loader-created canonical timestamp.
    data["datetime"] = canonical_datetime(data)
    data = data.dropna(subset=["datetime"])

    # 3. Optimized Aggregation (Groupby is much faster than loops)
    summary = data.groupby("imei").agg(
        First_Seen=("datetime", "min"),
        Last_Seen=("datetime", "max"),
        Total_Events=("imei", "size"),
        Unique_Contacts=("b_party", "nunique"),
        Unique_Towers=("first_cell_id", "nunique"),
        Total_Duration_Sec=("call_duration", "sum")
    ).reset_index()

    # Rename columns for cleaner output
    summary = summary.rename(columns={
        "First_Seen": "First Seen",
        "Last_Seen": "Last Seen",
        "Total_Events": "Total Events",
        "Unique_Contacts": "Unique Contacts",
        "Unique_Towers": "Unique Towers",
        "Total_Duration_Sec": "Total Duration (Sec)"
    })

    return summary




def imei_intelligence(df):
    """
    Generate intelligence report for every IMEI.

    Returns:
        DataFrame
    """

    # Remove blank IMEIs
    data = df[df["imei"] != ""].copy()

    # Consume the loader-created canonical timestamp.
    data["datetime"] = canonical_datetime(data)
    data = data.dropna(subset=["datetime"])

    intelligence = []

    for imei in data["imei"].unique():

        imei_df = data[data["imei"] == imei]

        report = {
            "IMEI": imei,
            "First Seen": imei_df["datetime"].min(),
            "Last Seen": imei_df["datetime"].max(),
            "Total Events": len(imei_df),
            "Unique Contacts": imei_df["b_party"].nunique(),
            "Unique Towers": imei_df["first_cell_id"].nunique(),
            "Total Duration (Sec)": int(imei_df["call_duration"].sum()),
            "Most Used Tower": imei_df["first_cell_id"].mode().iloc[0]
            if not imei_df["first_cell_id"].mode().empty else "",
            "Most Contacted": imei_df["b_party"].mode().iloc[0]
            if not imei_df["b_party"].mode().empty else ""
        }

        intelligence.append(report)

    return pd.DataFrame(intelligence)