import pandas as pd


_CALL_TYPE_LABELS = {
    "incoming": "Incoming Voice Call",
    "outgoing": "Outgoing Voice Call",
    "smsin": "Incoming SMS",
    "smsout": "Outgoing SMS",
    "sms": "SMS Event",
}


def normalize_call_type(value) -> str:
    """Return normalized call type text."""
    if value is None or pd.isna(value):
        return ""

    return str(value).strip().lower()


def explain_call_type(value) -> str:
    """Return investigator-friendly meaning of a call type."""
    call_type = normalize_call_type(value)

    if call_type in _CALL_TYPE_LABELS:
        return _CALL_TYPE_LABELS[call_type]

    if not call_type:
        return "Missing / Blank Call Type"

    return "Other / Unclassified Operator Event"


def add_call_type_explanation(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Add call_type_explanation column to a CDR dataframe."""
    if dataframe is None or dataframe.empty or "call_type" not in dataframe.columns:
        return pd.DataFrame() if dataframe is None else dataframe.copy()

    result = dataframe.copy()
    result["call_type_explanation"] = result["call_type"].map(explain_call_type)
    return result


def unknown_call_type_summary(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Summarize non-standard call types such as dsm."""
    if dataframe is None or dataframe.empty or "call_type" not in dataframe.columns:
        return pd.DataFrame(columns=["Call Type", "Meaning", "Total Records", "Suggested Action"])

    data = add_call_type_explanation(dataframe)
    unknown = data[
        data["call_type_explanation"].eq("Other / Unclassified Operator Event")
    ].copy()

    if unknown.empty:
        return pd.DataFrame(columns=["Call Type", "Meaning", "Total Records", "Suggested Action"])

    summary = (
        unknown.groupby("call_type", dropna=False)
        .size()
        .reset_index(name="Total Records")
        .rename(columns={"call_type": "Call Type"})
    )

    summary["Meaning"] = "Other / Unclassified Operator Event"
    summary["Suggested Action"] = "Verify this event type with operator format notes if case-critical."

    return summary[["Call Type", "Meaning", "Total Records", "Suggested Action"]]
