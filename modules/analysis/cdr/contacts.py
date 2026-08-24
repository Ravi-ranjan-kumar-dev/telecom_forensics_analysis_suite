import pandas as pd

from modules.loader.identity import normalize_msisdn

from .call_type_classifier import unknown_call_type_summary
from .contact_classifier import (
    add_contact_category,
    only_human_contacts,
    only_service_sender_ids,
    only_short_codes,
)
from .rules import (
    CONTACT_DURATION_MINUTE_WEIGHT,
    CONTACT_EVENT_WEIGHT,
    CONTACT_SCORE_FORMULA,
    CONTACT_UNIQUE_TOWER_WEIGHT,
    RULESET_VERSION,
)


def _safe_call_type_series(dataframe: pd.DataFrame) -> pd.Series:
    if dataframe is None or dataframe.empty or "call_type" not in dataframe.columns:
        return pd.Series(dtype="string")

    return dataframe["call_type"].astype("string").fillna("").str.lower().str.strip()


def _valid_mobile_counts(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Return normalized Indian mobile counts without changing source rows."""

    if (
        dataframe is None
        or dataframe.empty
        or "b_party" not in dataframe.columns
    ):
        return pd.DataFrame(columns=["Contact", "Total Calls"])

    normalized = dataframe["b_party"].map(normalize_msisdn).dropna()

    if normalized.empty:
        return pd.DataFrame(columns=["Contact", "Total Calls"])

    return (
        normalized.value_counts()
        .rename_axis("Contact")
        .reset_index(name="Total Calls")
    )


def top_contacts(df, limit=20):
    """Return the most frequent normalized Indian mobile contacts."""

    counts = _valid_mobile_counts(df)

    return (
        counts.sort_values(
            ["Total Calls", "Contact"],
            ascending=[False, True],
            kind="stable",
        )
        .head(max(1, int(limit)))
        .reset_index(drop=True)
    )


def bottom_contacts(df, limit=10):
    """Return the least frequent normalized Indian mobile contacts."""

    return (
        _valid_mobile_counts(df)
        .sort_values(
            ["Total Calls", "Contact"],
            ascending=[True, True],
            kind="stable",
        )
        .head(max(1, int(limit)))
        .reset_index(drop=True)
    )


def top_service_sender_ids(df, limit=20):
    """Top service/SMS sender IDs such as bank, operator, app and alert sender IDs."""
    if df is None or df.empty or "b_party" not in df.columns:
        return pd.DataFrame(columns=["Service Sender ID", "Total Events", "Why It Matters"])

    service_rows = only_service_sender_ids(df)
    if service_rows.empty:
        return pd.DataFrame(columns=["Service Sender ID", "Total Events", "Why It Matters"])

    result = service_rows["b_party"].value_counts().head(limit).reset_index()
    result.columns = ["Service Sender ID", "Total Events"]
    result["Why It Matters"] = (
        "Automated SMS/service sender. Review for banking, wallet, OTP, operator or app activity."
    )
    return result


def top_short_codes(df, limit=20):
    """Top short service numbers such as 50000, 52263 or 56321."""
    if df is None or df.empty or "b_party" not in df.columns:
        return pd.DataFrame(columns=["Short Code", "Total Events", "Why It Matters"])

    short_code_rows = only_short_codes(df)
    if short_code_rows.empty:
        return pd.DataFrame(columns=["Short Code", "Total Events", "Why It Matters"])

    result = short_code_rows["b_party"].value_counts().head(limit).reset_index()
    result.columns = ["Short Code", "Total Events"]
    result["Why It Matters"] = (
        "Short service number. Usually not a normal person-to-person contact."
    )
    return result


def contact_category_summary(df):
    """Simple count of human contacts, service sender IDs, short codes and unknown contacts."""
    if df is None or df.empty or "b_party" not in df.columns:
        return pd.DataFrame(columns=["Contact Category", "Total Records", "Meaning"])

    data = add_contact_category(df)
    if data.empty:
        return pd.DataFrame(columns=["Contact Category", "Total Records", "Meaning"])

    result = (
        data.groupby("contact_category", dropna=False)
        .size()
        .reset_index(name="Total Records")
        .rename(columns={"contact_category": "Contact Category"})
    )

    meanings = {
        "human_mobile": "Normal phone/mobile number; used for human contact analysis.",
        "service_sender_id": "SMS header/service sender such as bank, wallet, operator or app.",
        "short_code": "Short service number; usually automated or operator/service related.",
        "unknown_contact": "Blank or unsupported counterparty value; verify source data if important.",
    }

    result["Meaning"] = result["Contact Category"].map(meanings).fillna("Unclassified contact category.")
    return result[["Contact Category", "Total Records", "Meaning"]]


def contact_summary(df, target_number):
    """Returns a dictionary summary for a specific contact."""
    if df is None or df.empty or "b_party" not in df.columns:
        return {}

    target_key = normalize_msisdn(target_number)
    target_df = (
        df.loc[df["b_party"].map(normalize_msisdn).eq(target_key)]
        if target_key
        else df.loc[df["b_party"].astype(str).eq(str(target_number))]
    )
    if target_df.empty:
        return {"Status": "No interactions recorded"}

    call_type = _safe_call_type_series(target_df)

    summary = {
        "Total Interactions": len(target_df),
        "Incoming Events": int(call_type.isin(["incoming", "mtc", "a_in"]).sum()),
        "Outgoing Events": int(call_type.isin(["outgoing", "moc", "a_out"]).sum()),
        "Total Duration (Sec)": int(pd.to_numeric(target_df.get("call_duration", 0), errors="coerce").fillna(0).sum())
        if "call_duration" in target_df.columns
        else 0,
        "Unique IMEIs Used": target_df["imei"].nunique() if "imei" in target_df.columns else 0,
        "Unique Co-located Towers": target_df["first_cell_id"].nunique()
        if "first_cell_id" in target_df.columns
        else 0,
    }
    return summary


def incoming_outgoing(df):
    """Call type summary with simple explanation for unknown/operator-specific types."""
    if df is None or df.empty or "call_type" not in df.columns:
        return pd.DataFrame(columns=["Call Type", "Total Records", "Meaning"])

    result = (
        df.groupby("call_type", dropna=False)
        .size()
        .reset_index(name="Total Records")
        .rename(columns={"call_type": "Call Type"})
    )

    known_meanings = {
        "incoming": "Incoming Voice Call",
        "outgoing": "Outgoing Voice Call",
        "smsin": "Incoming SMS",
        "smsout": "Outgoing SMS",
        "sms": "SMS Event",
    }

    result["Meaning"] = (
        result["Call Type"]
        .astype("string")
        .fillna("")
        .str.lower()
        .str.strip()
        .map(known_meanings)
        .fillna("Other / Unclassified Operator Event")
    )

    return result[["Call Type", "Total Records", "Meaning"]]


def other_call_type_summary(df):
    """Separate explanation for non-standard call types such as dsm."""
    return unknown_call_type_summary(df)


def contact_ranking(df):
    """Human/mobile contact ranking only. Service sender IDs and short codes are excluded."""
    if df is None or df.empty or "b_party" not in df.columns:
        return pd.DataFrame()

    contacts = only_human_contacts(df)
    if contacts.empty:
        return pd.DataFrame()

    call_type = _safe_call_type_series(contacts)
    contacts = contacts.copy()
    contacts["_call_type_clean"] = call_type

    summary = contacts.groupby("b_party").agg(
        Total_Events=("b_party", "count"),
        Incoming=("_call_type_clean", lambda x: x.isin(["incoming", "mtc", "a_in"]).sum()),
        Outgoing=("_call_type_clean", lambda x: x.isin(["outgoing", "moc", "a_out"]).sum()),
        SMS=("_call_type_clean", lambda x: x.str.contains("sms", case=False, na=False).sum()),
        Total_Duration=("call_duration", "sum"),
        Unique_Towers=("first_cell_id", "nunique"),
    ).reset_index()

    summary["Score"] = (
        summary["Total_Events"] * CONTACT_EVENT_WEIGHT
        + (summary["Total_Duration"] / 60) * CONTACT_DURATION_MINUTE_WEIGHT
        + summary["Unique_Towers"] * CONTACT_UNIQUE_TOWER_WEIGHT
    )
    summary["Score_Ruleset"] = RULESET_VERSION
    summary["Score_Formula"] = CONTACT_SCORE_FORMULA

    return summary.sort_values("Score", ascending=False).rename(columns={"b_party": "Contact"})
