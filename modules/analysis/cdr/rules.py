"""Versioned, transparent CDR prioritization rules.

These constants are analyst-configurable heuristics, not probabilities or
validated risk scores. Reports must disclose the version and formula.
"""
from __future__ import annotations

RULESET_VERSION = "CDR-RULES-1.0"

CONTACT_EVENT_WEIGHT = 2.0
CONTACT_DURATION_MINUTE_WEIGHT = 1.0
CONTACT_UNIQUE_TOWER_WEIGHT = 3.0
CONTACT_SCORE_FORMULA = (
    "Total_Events*2 + Total_Duration_seconds/60 + Unique_Towers*3"
)

NETWORK_EVENT_WEIGHT = 5.0
NETWORK_DURATION_MINUTE_WEIGHT = 1.0
NETWORK_STRENGTH_FORMULA = "Total_Events*5 + Total_Duration_seconds/60"

LATE_NIGHT_START_HOUR = 0
LATE_NIGHT_END_HOUR = 4
HIGH_DAILY_ACTIVITY_THRESHOLD = 50
HIGH_CONTACT_DIVERSITY_THRESHOLD = 100
MULTIPLE_IMEI_THRESHOLD = 1
HIGH_VOLUME_REVIEW_THRESHOLD = 3_000

HOME_WINDOW = "22:00-06:00"
WORK_WINDOW = "09:00-18:00"
