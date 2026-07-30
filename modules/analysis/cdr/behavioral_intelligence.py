"""Rule-based behavioral observations for CDR lead generation."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from modules.analysis.cdr.activity import hourly_activity
from modules.analysis.cdr.contacts import top_contacts
from modules.analysis.cdr.imei import imei_summary
from modules.analysis.cdr.location import frequent_locations
from modules.analysis.cdr.rules import HIGH_VOLUME_REVIEW_THRESHOLD, RULESET_VERSION


def behavioral_intelligence(df: pd.DataFrame) -> pd.DataFrame:
    """Return neutral observations that require independent corroboration.

    The function intentionally avoids inferring identity, intent, criminality,
    relationship type or exact location from telecom frequency data alone.
    """
    columns = ["Indicator", "Observation", "Caution"]
    if df is None or df.empty:
        return pd.DataFrame(
            [["Data availability", "No call records were supplied.", "No behavioral inference can be made."]],
            columns=columns,
        )

    observations: list[dict[str, str]] = []

    def add_observation(indicator: str, observation: str, caution: str) -> None:
        observations.append(
            {
                "Indicator": indicator,
                "Observation": observation,
                "Caution": caution,
            }
        )

    def run_component(name: str, function: Callable[[], None]) -> None:
        try:
            function()
        except Exception as error:
            add_observation(
                "Analysis availability",
                f"{name} could not be calculated ({type(error).__name__}).",
                "Review source columns and the analysis-status sheet before relying on this section.",
            )

    def contact_observation() -> None:
        contacts = top_contacts(df, limit=1)
        if contacts.empty:
            return
        row = contacts.iloc[0]
        add_observation(
            "Highest-frequency contact",
            f"{row['Contact']} appears in {int(row['Total Calls'])} communication record(s).",
            "Frequency alone does not establish relationship, intent or participation.",
        )

    def activity_observation() -> None:
        hourly = hourly_activity(df)
        if hourly.empty:
            return
        row = hourly.loc[
            hourly["Total Events"].idxmax()
        ]
        time_window = row.get(
            "Time Window",
            f"{int(row['Hour']):02d}:00-{int(row['Hour']):02d}:59",
        )
        add_observation(
            "Peak recorded hour",
            (
                f"The largest hourly count is in {time_window} "
                f"with {int(row['Total Events'])} event(s)."
            ),
            "This is a descriptive traffic pattern and requires event-context corroboration.",
        )

    def location_observation() -> None:
        towers = frequent_locations(
            df,
            top_n=1,
        )

        if not towers.empty:
            row = towers.iloc[0]

            add_observation(
                "Most frequently recorded cell site",
                (
                    f"Cell ID {row['Cell ID']} appears in "
                    f"{int(row['Total Events'])} event(s)."
                ),
                (
                    "A cell-site record is a network association, "
                    "not proof of exact handset or person location."
                ),
            )
            return

        # Strict tower validation can reject placeholders, malformed
        # identifiers or operator-specific values. Preserve the
        # limitation instead of silently omitting location guidance.
        if "first_cell_id" not in df.columns:
            return

        raw_cells = (
            df["first_cell_id"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        raw_cells = raw_cells.loc[
            ~raw_cells.isin(
                {
                    "",
                    "nan",
                    "None",
                    "<NA>",
                }
            )
        ]

        if raw_cells.empty:
            return

        counts = raw_cells.value_counts()
        most_common_cell = str(
            counts.index[0]
        )
        event_count = int(
            counts.iloc[0]
        )

        add_observation(
            "Recorded cell-site identifier",
            (
                f"Unvalidated Cell ID {most_common_cell} appears "
                f"in {event_count} event(s)."
            ),
            (
                "This identifier did not pass strict tower validation. "
                "A cell-site record is a network association and is "
                "not proof of exact handset or person location."
            ),
        )

    def device_observation() -> None:
        required = {"imei", "b_party", "first_cell_id", "call_duration"}
        if not required.issubset(df.columns):
            return
        imeis = imei_summary(df)
        if len(imeis) > 1:
            add_observation(
                "Multiple recorded IMEIs",
                f"The dataset contains {len(imeis)} distinct non-blank IMEI value(s).",
                "Possible causes include device change, dual-device use, data quality issues or identifier handling; verify against source records.",
            )

    run_component("Highest-frequency contact", contact_observation)
    run_component("Hourly activity", activity_observation)
    run_component("Cell-site frequency", location_observation)
    run_component("IMEI summary", device_observation)

    total = len(df)
    if total > HIGH_VOLUME_REVIEW_THRESHOLD:
        add_observation(
            "High record volume",
            f"The dataset contains {total} rows, above the review threshold of {HIGH_VOLUME_REVIEW_THRESHOLD}.",
            "Record volume alone does not indicate criminal, organized or transactional activity.",
        )

    if not observations:
        add_observation(
            "No configured indicator triggered",
            "The configured descriptive rules did not produce an observation.",
            "Absence of a configured indicator does not prove absence of relevant activity.",
        )

    result = pd.DataFrame(observations, columns=columns)
    result.attrs["ruleset"] = RULESET_VERSION
    return result
