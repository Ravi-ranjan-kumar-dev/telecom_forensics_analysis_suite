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
    'Return a clear chronological 24-hour activity profile.'

    columns = [
        "Hour",
        "Time Window",
        "Total Events",
        "Activity Share (%)",
        "Activity Rank",
    ]

    if df is None or df.empty:
        return pd.DataFrame(columns=columns)

    data = with_canonical_datetime(df)
    data["Hour"] = data["_event_datetime"].dt.hour
    data = data.dropna(subset=["Hour"])

    if data.empty:
        return pd.DataFrame(columns=columns)

    counts = (
        data.groupby("Hour")
        .size()
        .rename("Total Events")
        .reindex(range(24), fill_value=0)
        .rename_axis("Hour")
        .reset_index()
    )
    counts["Total Events"] = counts["Total Events"].astype(int)
    total = int(counts["Total Events"].sum())
    counts["Time Window"] = counts["Hour"].map(
        lambda hour: f"{int(hour):02d}:00-{int(hour):02d}:59"
    )
    counts["Activity Share (%)"] = (
        counts["Total Events"]
        .div(total if total else 1)
        .mul(100)
        .round(2)
    )
    counts["Activity Rank"] = (
        counts["Total Events"]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    return counts[columns].sort_values(
        "Hour",
        ignore_index=True,
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
    """Return ISO-week activity with one investigator-friendly date range."""
    columns = [
        "ISO Year",
        "ISO Week",
        "Year-Week",
        "Date Range",
        "Total Events",
        "Active Days",
        "Average Events per Active Day",
    ]

    if df is None or df.empty:
        return pd.DataFrame(columns=columns)

    data = with_canonical_datetime(df).dropna(
        subset=["_event_datetime"]
    )

    if data.empty:
        return pd.DataFrame(columns=columns)

    iso = data["_event_datetime"].dt.isocalendar()
    data["ISO Year"] = iso.year.astype("Int64")
    data["ISO Week"] = iso.week.astype("Int64")
    data["_event_date"] = data["_event_datetime"].dt.date

    summary = (
        data.groupby(
            ["ISO Year", "ISO Week"],
            dropna=False,
        )
        .agg(
            **{
                "Total Events": ("_event_datetime", "size"),
                "Active Days": ("_event_date", "nunique"),
            }
        )
        .reset_index()
        .sort_values(
            ["ISO Year", "ISO Week"],
            ignore_index=True,
        )
    )

    summary["Year-Week"] = (
        summary["ISO Year"].astype(str)
        + "-W"
        + summary["ISO Week"].astype(str).str.zfill(2)
    )

    week_start = pd.to_datetime(
        summary["Year-Week"] + "-1",
        format="%G-W%V-%u",
        errors="coerce",
    )
    week_end = week_start + pd.Timedelta(days=6)

    summary["Date Range"] = (
        week_start.dt.strftime("%d-%m-%Y")
        + " to "
        + week_end.dt.strftime("%d-%m-%Y")
    )

    summary["Average Events per Active Day"] = (
        summary["Total Events"]
        .div(summary["Active Days"].replace(0, pd.NA))
        .round(2)
        .fillna(0)
    )

    return summary[columns]




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
