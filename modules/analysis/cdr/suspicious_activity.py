import pandas as pd

from .datetime_utils import canonical_datetime
from .rules import (
    HIGH_CONTACT_DIVERSITY_THRESHOLD,
    HIGH_DAILY_ACTIVITY_THRESHOLD,
    LATE_NIGHT_END_HOUR,
    LATE_NIGHT_START_HOUR,
    MULTIPLE_IMEI_THRESHOLD,
    RULESET_VERSION,
)

def suspicious_activity(df):
    """Return rule-based review indicators without assigning intent or guilt."""
    if df is None or df.empty:
        return pd.DataFrame()

    data = df.copy()
    data["datetime"] = canonical_datetime(data)
    data = data.dropna(subset=["datetime"])
    data["_calendar_date"] = data["datetime"].dt.date

    indicators = []

    # Rule 1: Midnight Operations (00:00 - 04:00)
    night = data[(data["datetime"].dt.hour >= LATE_NIGHT_START_HOUR) & (data["datetime"].dt.hour < LATE_NIGHT_END_HOUR)]
    if not night.empty:
        indicators.append({"Type": "Late-Night Activity Indicator", "Count": len(night), "Remark": "Communication observed between 00:00-04:00; context required"})

    # Rule 2: Sudden Traffic Spikes (>50 operations in a single day)
    daily = data.groupby("_calendar_date").size().reset_index(name="Events")
    abnormal = daily[daily["Events"] > HIGH_DAILY_ACTIVITY_THRESHOLD]
    for _, row in abnormal.iterrows():
        indicators.append({
            "Type": "High Daily Activity Indicator",
            "Count": row["Events"],
            "Remark": (
                f"High event volume observed on {row['_calendar_date']}; "
                "requires contextual corroboration"
            ),
        })

    # Rule 3: Target Dispersal Range (>100 unique links)
    if "b_party" in data.columns:
        unique_contacts = data["b_party"].nunique()
        if unique_contacts > HIGH_CONTACT_DIVERSITY_THRESHOLD:
            indicators.append({"Type": "High Contact Diversity Dispersion", "Count": unique_contacts, "Remark": "A large number of unique contacts was observed; compare with case context and subscriber role"})

    # Rule 4: Device Hops Check
    if "imei" in data.columns:
        imeis = data["imei"].dropna().nunique()
        if imeis > MULTIPLE_IMEI_THRESHOLD:
            indicators.append({"Type": "Multiple Handset Usage Indicator", "Count": imeis, "Remark": "SIM identity observed with multiple IMEIs; verify device changes and source quality"})

    result = pd.DataFrame(indicators)
    if not result.empty:
        result["Ruleset"] = RULESET_VERSION
    return result