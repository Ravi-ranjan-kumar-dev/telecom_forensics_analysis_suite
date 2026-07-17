import pandas as pd

from .contact_classifier import classify_contact
from .datetime_utils import canonical_datetime
from .tower_utils import filter_valid_first_cell_rows


def _prepare_tower_data(df):
    if df is None or df.empty or "first_cell_id" not in df.columns:
        return pd.DataFrame()

    data = filter_valid_first_cell_rows(df)
    if data.empty:
        return pd.DataFrame()

    data = data.copy()
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

    if "imei" not in data.columns:
        data["imei"] = ""

    return data


def _top_value_by_group(data, category, output_column):
    subset = data[
        data["_contact_category"].eq(category)
        & data["b_party"].astype(str).str.strip().ne("")
    ].copy()

    if subset.empty:
        return pd.DataFrame(columns=["Cell ID", output_column])

    counts = (
        subset.groupby(["first_cell_id", "b_party"], dropna=False)
        .size()
        .reset_index(name="cnt")
        .sort_values(["first_cell_id", "cnt"], ascending=[True, False])
        .drop_duplicates("first_cell_id")
        .rename(columns={"first_cell_id": "Cell ID", "b_party": output_column})
    )

    return counts[["Cell ID", output_column]]


def _count_events_by_group(data, category, output_column):
    subset = data[data["_contact_category"].eq(category)].copy()

    if subset.empty:
        return pd.DataFrame(columns=["Cell ID", output_column])

    counts = (
        subset.groupby("first_cell_id")
        .size()
        .reset_index(name=output_column)
        .rename(columns={"first_cell_id": "Cell ID"})
    )

    return counts[["Cell ID", output_column]]


def tower_intelligence(df):
    data = _prepare_tower_data(df)

    if data.empty:
        return pd.DataFrame(
            columns=[
                "Cell ID",
                "First Seen",
                "Last Seen",
                "Total Events",
                "Unique Human Contacts",
                "Service Sender Events",
                "Short Code Events",
                "Unique IMEIs",
                "Total Duration (Sec)",
                "Most Used IMEI",
                "Most Human Contacted",
                "Top Service Sender ID",
            ]
        )

    summary = (
        data.groupby("first_cell_id", dropna=False)
        .agg(
            **{
                "First Seen": ("_event_datetime", "min"),
                "Last Seen": ("_event_datetime", "max"),
                "Total Events": ("first_cell_id", "count"),
                "Unique IMEIs": ("imei", lambda x: x.replace("", pd.NA).dropna().nunique()),
                "Total Duration (Sec)": ("_duration", "sum"),
            }
        )
        .reset_index()
        .rename(columns={"first_cell_id": "Cell ID"})
    )

    human_counts = (
        data[data["_contact_category"].eq("human_mobile")]
        .groupby("first_cell_id")["b_party"]
        .nunique()
        .reset_index(name="Unique Human Contacts")
        .rename(columns={"first_cell_id": "Cell ID"})
    )

    imei_counts = (
        data[data["imei"].astype(str).str.strip().ne("")]
        .groupby(["first_cell_id", "imei"], dropna=False)
        .size()
        .reset_index(name="cnt")
        .sort_values(["first_cell_id", "cnt"], ascending=[True, False])
        .drop_duplicates("first_cell_id")
        .rename(columns={"first_cell_id": "Cell ID", "imei": "Most Used IMEI"})
    )

    most_human = _top_value_by_group(data, "human_mobile", "Most Human Contacted")
    top_service = _top_value_by_group(data, "service_sender_id", "Top Service Sender ID")
    service_events = _count_events_by_group(data, "service_sender_id", "Service Sender Events")
    short_code_events = _count_events_by_group(data, "short_code", "Short Code Events")

    for extra in [human_counts, imei_counts[["Cell ID", "Most Used IMEI"]], most_human, top_service, service_events, short_code_events]:
        summary = summary.merge(extra, on="Cell ID", how="left")

    summary["Unique Human Contacts"] = summary["Unique Human Contacts"].fillna(0).astype(int)
    summary["Service Sender Events"] = summary["Service Sender Events"].fillna(0).astype(int)
    summary["Short Code Events"] = summary["Short Code Events"].fillna(0).astype(int)
    summary["Most Used IMEI"] = summary["Most Used IMEI"].fillna("N/A")
    summary["Most Human Contacted"] = summary["Most Human Contacted"].fillna("N/A")
    summary["Top Service Sender ID"] = summary["Top Service Sender ID"].fillna("N/A")

    return summary.sort_values("Total Events", ascending=False)


def home_tower(df):
    data = _prepare_tower_data(df)
    if data.empty:
        return pd.DataFrame(
            columns=[
                "Cell ID",
                "Night Events",
                "Unique Days",
                "Unique Human Contacts",
                "Window",
                "Ruleset",
            ]
        )

    data = data.dropna(subset=["_event_datetime"]).copy()
    if data.empty:
        return pd.DataFrame()

    data["_hour"] = data["_event_datetime"].dt.hour
    data["_date"] = data["_event_datetime"].dt.normalize()

    night = data[(data["_hour"] >= 22) | (data["_hour"] < 6)].copy()
    if night.empty:
        return pd.DataFrame(
            columns=[
                "Cell ID",
                "Night Events",
                "Unique Days",
                "Unique Human Contacts",
                "Window",
                "Ruleset",
            ]
        )

    human = night[night["_contact_category"].eq("human_mobile")].copy()

    result = (
        night.groupby("first_cell_id")
        .agg(
            **{
                "Night Events": ("first_cell_id", "count"),
                "Unique Days": ("_date", "nunique"),
            }
        )
        .reset_index()
        .rename(columns={"first_cell_id": "Cell ID"})
    )

    human_counts = (
        human.groupby("first_cell_id")["b_party"]
        .nunique()
        .reset_index(name="Unique Human Contacts")
        .rename(columns={"first_cell_id": "Cell ID"})
    )

    result = result.merge(human_counts, on="Cell ID", how="left")
    result["Unique Human Contacts"] = result["Unique Human Contacts"].fillna(0).astype(int)
    result["Window"] = "22:00-06:00"
    result["Ruleset"] = "CDR-RULES-1.0"

    return result.sort_values(["Night Events", "Unique Days"], ascending=False)


def work_tower(df):
    data = _prepare_tower_data(df)
    if data.empty:
        return pd.DataFrame(
            columns=[
                "Cell ID",
                "Office Events",
                "Working Days",
                "Unique Human Contacts",
            ]
        )

    data = data.dropna(subset=["_event_datetime"]).copy()
    if data.empty:
        return pd.DataFrame()

    data["_hour"] = data["_event_datetime"].dt.hour
    data["_date"] = data["_event_datetime"].dt.normalize()

    office = data[(data["_hour"] >= 9) & (data["_hour"] <= 18)].copy()
    if office.empty:
        return pd.DataFrame(
            columns=[
                "Cell ID",
                "Office Events",
                "Working Days",
                "Unique Human Contacts",
            ]
        )

    human = office[office["_contact_category"].eq("human_mobile")].copy()

    result = (
        office.groupby("first_cell_id")
        .agg(
            **{
                "Office Events": ("first_cell_id", "count"),
                "Working Days": ("_date", "nunique"),
            }
        )
        .reset_index()
        .rename(columns={"first_cell_id": "Cell ID"})
    )

    human_counts = (
        human.groupby("first_cell_id")["b_party"]
        .nunique()
        .reset_index(name="Unique Human Contacts")
        .rename(columns={"first_cell_id": "Cell ID"})
    )

    result = result.merge(human_counts, on="Cell ID", how="left")
    result["Unique Human Contacts"] = result["Unique Human Contacts"].fillna(0).astype(int)

    return result.sort_values(["Office Events", "Working Days"], ascending=False)
