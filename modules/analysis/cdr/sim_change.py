import pandas as pd

from .datetime_utils import canonical_datetime


def sim_change(df):
    """Track chronological handset changes using canonical timestamps."""
    if df is None or df.empty or "imei" not in df.columns:
        return pd.DataFrame()

    data = df.copy()
    data["_event_datetime"] = canonical_datetime(data)
    imei_text = data["imei"].fillna("").astype(str).str.strip()
    data = data.loc[imei_text.ne("") & data["_event_datetime"].notna()].copy()
    data = data.sort_values("_event_datetime")
    data["prev_imei"] = data["imei"].shift(1)
    changes_df = data.loc[
        data["prev_imei"].notna() & data["imei"].ne(data["prev_imei"])
    ]

    rows = []
    for _, row in changes_df.iterrows():
        rows.append(
            {
                "Date": row["_event_datetime"].strftime("%d-%m-%Y"),
                "Time": row["_event_datetime"].strftime("%H:%M:%S"),
                "Old IMEI": row["prev_imei"],
                "New IMEI": row["imei"],
                "Tower": row.get("first_cell_id", "N/A"),
                "Contact": row.get("b_party", "N/A"),
                "Event": row.get("call_type", "N/A"),
            }
        )
    return pd.DataFrame(rows)
