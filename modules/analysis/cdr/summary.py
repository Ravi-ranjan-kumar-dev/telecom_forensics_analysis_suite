import pandas as pd

from .contact_classifier import add_contact_category
from .datetime_utils import canonical_datetime
from .tower_utils import filter_valid_first_cell_rows


def cdr_summary(df):
    """Master overview using chronological canonical timestamps."""
    if df is None or df.empty:
        return {}

    call_type = (
        df["call_type"].fillna("").astype(str).str.lower().str.strip()
        if "call_type" in df.columns
        else pd.Series("", index=df.index)
    )
    duration = pd.to_numeric(df.get("call_duration", 0), errors="coerce").fillna(0)

    known_mask = (
        call_type.isin(["incoming", "mtc", "a_in", "outgoing", "moc", "a_out"])
        | call_type.str.contains("smsin|sms_mt|a2p_smsin|smsout|sms_mo|p2p_smsout|sms", na=False)
    )
    unknown_call_type_count = int((~known_mask & call_type.ne("")).sum())

    contact_data = add_contact_category(df) if "b_party" in df.columns else pd.DataFrame()
    human_contacts = 0
    service_sender_records = 0
    short_code_records = 0

    if not contact_data.empty and "contact_category" in contact_data.columns:
        human_contacts = int(
            contact_data.loc[
                contact_data["contact_category"].eq("human_mobile"),
                "b_party",
            ].replace("", pd.NA).dropna().nunique()
        )
        service_sender_records = int(contact_data["contact_category"].eq("service_sender_id").sum())
        short_code_records = int(contact_data["contact_category"].eq("short_code").sum())

    valid_tower_rows = filter_valid_first_cell_rows(df) if "first_cell_id" in df.columns else pd.DataFrame()
    invalid_tower_rows = len(df) - len(valid_tower_rows) if "first_cell_id" in df.columns else 0

    summary = {
        "Total Records Logged": len(df),
        "Incoming Voice Calls": int(call_type.isin(["incoming", "mtc", "a_in"]).sum()),
        "Outgoing Voice Calls": int(call_type.isin(["outgoing", "moc", "a_out"]).sum()),
        "Incoming SMS Traffic": int(call_type.str.contains("smsin|sms_mt|a2p_smsin", na=False).sum()),
        "Outgoing SMS Traffic": int(call_type.str.contains("smsout|sms_mo|p2p_smsout", na=False).sum()),
        "Other / Unknown Call Type Records": unknown_call_type_count,
        "Accumulated Airtime Duration (Sec)": int(duration.sum()),
        "Unique Raw Counterparties": df["b_party"].replace("", pd.NA).dropna().nunique() if "b_party" in df.columns else 0,
        "Unique Human Mobile Counterparties": human_contacts,
        "Service Sender ID Records": service_sender_records,
        "Short Code Records": short_code_records,
        "Unique Physical Devices (IMEI)": df["imei"].replace("", pd.NA).dropna().nunique() if "imei" in df.columns else 0,
        "Unique SIM Identities (IMSI)": df["imsi"].replace("", pd.NA).dropna().nunique() if "imsi" in df.columns else 0,
        "Unique Valid Tower Footprints": valid_tower_rows["first_cell_id"].nunique() if not valid_tower_rows.empty else 0,
        "Invalid / Missing Tower Rows": invalid_tower_rows,
    }

    timestamps = canonical_datetime(df).dropna()
    if not timestamps.empty:
        summary["Observation Window Start"] = timestamps.min().strftime("%d-%m-%Y %H:%M:%S")
        summary["Observation Window Close"] = timestamps.max().strftime("%d-%m-%Y %H:%M:%S")
        summary["Total Net Active Days"] = int(timestamps.dt.normalize().nunique())

    return summary
