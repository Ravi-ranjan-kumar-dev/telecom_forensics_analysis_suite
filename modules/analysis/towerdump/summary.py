from __future__ import annotations

import pandas as pd

from .utils import datetime_series, numeric_series, safe_nunique, text_series


def tower_dump_summary(df: pd.DataFrame) -> dict:
    dt = datetime_series(df)
    return {
        "total_records": int(len(df)),
        "unique_subscribers": safe_nunique(df, "subscriber_number"),
        "unique_other_parties": safe_nunique(df, "other_party"),
        "unique_imei": safe_nunique(df, "imei"),
        "unique_imsi": safe_nunique(df, "imsi"),
        "unique_operators": safe_nunique(df, "operator"),
        "unique_searched_cells": safe_nunique(df, "searched_cell_id"),
        "total_duration_seconds": int(numeric_series(df, "call_duration").sum()),
        "date_from": dt.min() if dt.notna().any() else pd.NaT,
        "date_to": dt.max() if dt.notna().any() else pd.NaT,
    }


def operator_summary(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["operator"] = text_series(work, "operator").replace("", "unknown")
    work["_dt"] = datetime_series(work)

    rows = []
    for operator, group in work.groupby("operator", dropna=False):
        rows.append(
            {
                "operator": operator,
                "records": len(group),
                "unique_subscribers": safe_nunique(group, "subscriber_number"),
                "unique_other_parties": safe_nunique(group, "other_party"),
                "unique_imei": safe_nunique(group, "imei"),
                "unique_imsi": safe_nunique(group, "imsi"),
                "unique_cells": safe_nunique(group, "searched_cell_id"),
                "first_seen": group["_dt"].min(),
                "last_seen": group["_dt"].max(),
            }
        )
    return pd.DataFrame(rows).sort_values("records", ascending=False, ignore_index=True)


def cell_summary(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["searched_cell_id"] = text_series(work, "searched_cell_id")
    work = work.loc[work["searched_cell_id"].ne("")].copy()
    work["_dt"] = datetime_series(work)

    rows = []
    for cell_id, group in work.groupby("searched_cell_id"):
        rows.append(
            {
                "searched_cell_id": cell_id,
                "records": len(group),
                "operators": ", ".join(sorted(set(text_series(group, "operator")) - {""})),
                "unique_subscribers": safe_nunique(group, "subscriber_number"),
                "unique_imei": safe_nunique(group, "imei"),
                "unique_imsi": safe_nunique(group, "imsi"),
                "first_seen": group["_dt"].min(),
                "last_seen": group["_dt"].max(),
                "source_files": safe_nunique(group, "source_file"),
            }
        )
    return pd.DataFrame(rows).sort_values("records", ascending=False, ignore_index=True)


def call_type_summary(df: pd.DataFrame) -> pd.DataFrame:
    values = text_series(df, "call_type").replace("", "unknown")
    result = values.value_counts(dropna=False).rename_axis("call_type").reset_index(name="records")
    result["percentage"] = (result["records"] / max(len(df), 1) * 100).round(2)
    return result
