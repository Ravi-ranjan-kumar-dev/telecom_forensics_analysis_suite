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
    'Return the canonical probable-device summary.'

    from modules.analysis.cdr.device_quality import (
        device_summary,
    )

    return device_summary(df)



def imei_intelligence(df):
    'Return the canonical probable-device intelligence table.'

    from modules.analysis.cdr.device_quality import (
        device_intelligence,
    )

    return device_intelligence(df)
