import pandas as pd

from .contact_classifier import classify_contact
from .datetime_utils import canonical_datetime
from .tower_utils import valid_cell_mask


def _prepare_imei_data(df):
    if df is None or df.empty or "imei" not in df.columns:
        return pd.DataFrame()

    data = df.copy()
    data["imei"] = data["imei"].astype("string").fillna("").str.strip()
    data = data[data["imei"].ne("")].copy()

    if data.empty:
        return pd.DataFrame()

    data["_event_datetime"] = canonical_datetime(data)
    data["_duration"] = (
        pd.to_numeric(data["call_duration"], errors="coerce").fillna(0)
        if "call_duration" in data.columns
        else 0
    )

    if "b_party" in data.columns:
        data["_contact_category"] = data["b_party"].map(classify_contact)
    else:
        data["_contact_category"] = "unknown_contact"
        data["b_party"] = ""

    if "first_cell_id" in data.columns:
        data["_valid_cell_id"] = data["first_cell_id"].where(valid_cell_mask(data["first_cell_id"]), "")
    else:
        data["_valid_cell_id"] = ""

    return data


def _top_value_by_imei(data, category, output_column):
    subset = data[
        data["_contact_category"].eq(category)
        & data["b_party"].astype(str).str.strip().ne("")
    ].copy()

    if subset.empty:
        return pd.DataFrame(columns=["IMEI", output_column])

    counts = (
        subset.groupby(["imei", "b_party"], dropna=False)
        .size()
        .reset_index(name="cnt")
        .sort_values(["imei", "cnt"], ascending=[True, False])
        .drop_duplicates("imei")
        .rename(columns={"imei": "IMEI", "b_party": output_column})
    )

    return counts[["IMEI", output_column]]


def _count_events_by_imei(data, category, output_column):
    subset = data[data["_contact_category"].eq(category)].copy()

    if subset.empty:
        return pd.DataFrame(columns=["IMEI", output_column])

    counts = (
        subset.groupby("imei")
        .size()
        .reset_index(name=output_column)
        .rename(columns={"imei": "IMEI"})
    )

    return counts[["IMEI", output_column]]


def _most_used_valid_tower(data):
    subset = data[data["_valid_cell_id"].astype(str).str.strip().ne("")].copy()

    if subset.empty:
        return pd.DataFrame(columns=["IMEI", "Most Used Valid Tower"])

    counts = (
        subset.groupby(["imei", "_valid_cell_id"], dropna=False)
        .size()
        .reset_index(name="cnt")
        .sort_values(["imei", "cnt"], ascending=[True, False])
        .drop_duplicates("imei")
        .rename(columns={"imei": "IMEI", "_valid_cell_id": "Most Used Valid Tower"})
    )

    return counts[["IMEI", "Most Used Valid Tower"]]


def imei_summary(df):
    data = _prepare_imei_data(df)

    if data.empty:
        return pd.DataFrame(
            columns=[
                "imei",
                "First Seen",
                "Last Seen",
                "Total Events",
                "Unique Human Contacts",
                "Unique Valid Towers",
                "Total Duration (Sec)",
            ]
        )

    human = data[data["_contact_category"].eq("human_mobile")].copy()

    result = (
        data.groupby("imei")
        .agg(
            **{
                "First Seen": ("_event_datetime", "min"),
                "Last Seen": ("_event_datetime", "max"),
                "Total Events": ("imei", "count"),
                "Unique Valid Towers": ("_valid_cell_id", lambda x: x.replace("", pd.NA).dropna().nunique()),
                "Total Duration (Sec)": ("_duration", "sum"),
            }
        )
        .reset_index()
    )

    human_counts = (
        human.groupby("imei")["b_party"]
        .nunique()
        .reset_index(name="Unique Human Contacts")
    )

    result = result.merge(human_counts, on="imei", how="left")
    result["Unique Human Contacts"] = result["Unique Human Contacts"].fillna(0).astype(int)

    return result[
        [
            "imei",
            "First Seen",
            "Last Seen",
            "Total Events",
            "Unique Human Contacts",
            "Unique Valid Towers",
            "Total Duration (Sec)",
        ]
    ].sort_values("Total Events", ascending=False)


def imei_intelligence(df):
    data = _prepare_imei_data(df)

    if data.empty:
        return pd.DataFrame(
            columns=[
                "IMEI",
                "First Seen",
                "Last Seen",
                "Total Events",
                "Unique Human Contacts",
                "Unique Valid Towers",
                "Total Duration (Sec)",
                "Most Used Valid Tower",
                "Most Human Contacted",
                "Top Service Sender ID",
                "Service Sender Events",
                "Short Code Events",
            ]
        )

    summary = (
        data.groupby("imei")
        .agg(
            **{
                "First Seen": ("_event_datetime", "min"),
                "Last Seen": ("_event_datetime", "max"),
                "Total Events": ("imei", "count"),
                "Unique Valid Towers": ("_valid_cell_id", lambda x: x.replace("", pd.NA).dropna().nunique()),
                "Total Duration (Sec)": ("_duration", "sum"),
            }
        )
        .reset_index()
        .rename(columns={"imei": "IMEI"})
    )

    human = data[data["_contact_category"].eq("human_mobile")].copy()
    human_counts = (
        human.groupby("imei")["b_party"]
        .nunique()
        .reset_index(name="Unique Human Contacts")
        .rename(columns={"imei": "IMEI"})
    )

    most_tower = _most_used_valid_tower(data)
    most_human = _top_value_by_imei(data, "human_mobile", "Most Human Contacted")
    top_service = _top_value_by_imei(data, "service_sender_id", "Top Service Sender ID")
    service_events = _count_events_by_imei(data, "service_sender_id", "Service Sender Events")
    short_code_events = _count_events_by_imei(data, "short_code", "Short Code Events")

    for extra in [human_counts, most_tower, most_human, top_service, service_events, short_code_events]:
        summary = summary.merge(extra, on="IMEI", how="left")

    summary["Unique Human Contacts"] = summary["Unique Human Contacts"].fillna(0).astype(int)
    summary["Service Sender Events"] = summary["Service Sender Events"].fillna(0).astype(int)
    summary["Short Code Events"] = summary["Short Code Events"].fillna(0).astype(int)
    summary["Most Used Valid Tower"] = summary["Most Used Valid Tower"].fillna("N/A")
    summary["Most Human Contacted"] = summary["Most Human Contacted"].fillna("N/A")
    summary["Top Service Sender ID"] = summary["Top Service Sender ID"].fillna("N/A")

    return summary[
        [
            "IMEI",
            "First Seen",
            "Last Seen",
            "Total Events",
            "Unique Human Contacts",
            "Unique Valid Towers",
            "Total Duration (Sec)",
            "Most Used Valid Tower",
            "Most Human Contacted",
            "Top Service Sender ID",
            "Service Sender Events",
            "Short Code Events",
        ]
    ].sort_values("Total Events", ascending=False)
