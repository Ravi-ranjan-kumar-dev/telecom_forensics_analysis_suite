import pandas as pd

from .datetime_utils import with_canonical_datetime


def analyze_activity(df):
    """Overall activity metrics summary."""
    if df is None or df.empty:
        return pd.DataFrame()

    duration = pd.to_numeric(df.get("call_duration", 0), errors="coerce").fillna(0)
    activity_summary = {
        "Metric": [
            "Total Records/Events",
            "Unique Interacted Numbers",
            "Most Active Counterparty",
            "Total Duration (Sec)",
            "Average Duration (Sec)",
        ],
        "Value": [
            len(df),
            df["b_party"].nunique() if "b_party" in df.columns else 0,
            (
                df["b_party"].mode().iloc[0]
                if "b_party" in df.columns and not df["b_party"].dropna().empty
                else "N/A"
            ),
            float(duration.sum()),
            round(float(duration.mean()), 2) if len(duration) else 0,
        ],
    }
    return pd.DataFrame(activity_summary)


def hourly_activity(df):
    """Hourly traffic pattern based on the canonical event timestamp."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["Hour", "Total Events"])

    data = with_canonical_datetime(df)
    data["Hour"] = data["_event_datetime"].dt.hour
    data = data.dropna(subset=["Hour"])
    return (
        data.groupby("Hour")
        .size()
        .reset_index(name="Total Events")
        .sort_values(by="Total Events", ascending=False, ignore_index=True)
    )


def daily_activity(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=["Date", "Total Events"])

    data = with_canonical_datetime(df)
    data = data.dropna(subset=["_event_datetime"])
    data["Date"] = data["_event_datetime"].dt.strftime("%d-%m-%Y")
    return (
        data.groupby("Date")
        .size()
        .reset_index(name="Total Events")
        .sort_values(by="Total Events", ascending=False, ignore_index=True)
    )


def weekly_activity(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=["ISO Year", "ISO Week", "Year-Week", "Total Events"])

    data = with_canonical_datetime(df).dropna(subset=["_event_datetime"])
    iso = data["_event_datetime"].dt.isocalendar()
    data["ISO Year"] = iso.year.astype("Int64")
    data["ISO Week"] = iso.week.astype("Int64")
    data["Year-Week"] = (
        data["ISO Year"].astype(str)
        + "-W"
        + data["ISO Week"].astype(str).str.zfill(2)
    )
    return (
        data.groupby(["ISO Year", "ISO Week", "Year-Week"], dropna=False)
        .size()
        .reset_index(name="Total Events")
        .sort_values(["ISO Year", "ISO Week"], ignore_index=True)
    )


def monthly_activity(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=["Year", "Month", "Year-Month", "Total Events"])

    data = with_canonical_datetime(df).dropna(subset=["_event_datetime"])
    data["Year"] = data["_event_datetime"].dt.year.astype("Int64")
    data["Month"] = data["_event_datetime"].dt.month.astype("Int64")
    data["Year-Month"] = data["_event_datetime"].dt.strftime("%Y-%m")
    return (
        data.groupby(["Year", "Month", "Year-Month"], dropna=False)
        .size()
        .reset_index(name="Total Events")
        .sort_values(["Year", "Month"], ignore_index=True)
    )
