import pandas as pd

from .datetime_utils import canonical_datetime


def cdr_summary(df):
    """Master overview using chronological canonical timestamps."""
    if df is None or df.empty:
        return {}

    call_type = (
        df["call_type"].fillna("").astype(str).str.lower()
        if "call_type" in df.columns
        else pd.Series("", index=df.index)
    )
    duration = pd.to_numeric(df.get("call_duration", 0), errors="coerce").fillna(0)

    summary = {
        "Total Records Logged": len(df),
        "Incoming Voice Calls": int(call_type.isin(["incoming", "mtc", "a_in"]).sum()),
        "Outgoing Voice Calls": int(call_type.isin(["outgoing", "moc", "a_out"]).sum()),
        "Incoming SMS Traffic": int(call_type.str.contains("smsin|sms_mt|a2p_smsin", na=False).sum()),
        "Outgoing SMS Traffic": int(call_type.str.contains("smsout|sms_mo|p2p_smsout", na=False).sum()),
        "Accumulated Airtime Duration (Sec)": int(duration.sum()),
        "Unique Counterparties": df["b_party"].replace("", pd.NA).dropna().nunique() if "b_party" in df.columns else 0,
        "Unique Physical Devices (IMEI)": df["imei"].replace("", pd.NA).dropna().nunique() if "imei" in df.columns else 0,
        "Unique SIM Identities (IMSI)": df["imsi"].replace("", pd.NA).dropna().nunique() if "imsi" in df.columns else 0,
        "Unique Tower Footprints": df["first_cell_id"].replace("", pd.NA).dropna().nunique() if "first_cell_id" in df.columns else 0,
    }

    timestamps = canonical_datetime(df).dropna()
    if not timestamps.empty:
        summary["Observation Window Start"] = timestamps.min().strftime("%d-%m-%Y %H:%M:%S")
        summary["Observation Window Close"] = timestamps.max().strftime("%d-%m-%Y %H:%M:%S")
        summary["Total Net Active Days"] = int(timestamps.dt.normalize().nunique())

    return summary
