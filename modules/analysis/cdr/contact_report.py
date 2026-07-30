from __future__ import annotations

from typing import Any

import pandas as pd

from modules.analysis.cdr.contacts import top_contacts
from modules.database.cgi_repository import normalize_cgi
from modules.enrichment.cgi_address_enrichment import (
    lookup_cgi_addresses,
)


def _contact_key(value: Any) -> str:
    text = str(value if value is not None else "").strip()

    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]

    digits = "".join(
        character
        for character in text
        if character.isdigit()
    )

    if len(digits) == 12 and digits.startswith("91"):
        return digits[-10:]

    if len(digits) == 11 and digits.startswith("0"):
        return digits[-10:]

    return digits or text


def build_full_contact_summary(
    data: pd.DataFrame,
    contact_summary: pd.DataFrame,
) -> pd.DataFrame:
    'Add target-serving CGI fields to the complete contact summary.'

    if (
        not isinstance(contact_summary, pd.DataFrame)
        or contact_summary.empty
    ):
        return pd.DataFrame()

    output = contact_summary.copy()
    contact_column = next(
        (
            column
            for column in (
                "Other Party",
                "Contact",
                "b_party",
            )
            if column in output.columns
        ),
        None,
    )

    if contact_column is None or "b_party" not in data.columns:
        return output

    human = top_contacts(
        data,
        limit=max(
            int(data["b_party"].nunique(dropna=True)),
            1,
        ),
    )
    human_keys = (
        {
            _contact_key(value)
            for value in human["Contact"]
        }
        if (
            isinstance(human, pd.DataFrame)
            and not human.empty
            and "Contact" in human.columns
        )
        else set()
    )

    output["_contact_key"] = output[contact_column].map(_contact_key)

    if human_keys:
        output = output.loc[
            output["_contact_key"].isin(human_keys)
        ].copy()

    source_columns = [
        column
        for column in (
            "b_party",
            "first_cell_id",
            "call_date",
            "call_time",
        )
        if column in data.columns
    ]
    work = data[source_columns].copy()
    work["_contact_key"] = work["b_party"].map(_contact_key)

    if human_keys:
        work = work.loc[
            work["_contact_key"].isin(human_keys)
        ].copy()

    work["_cgi"] = (
        work["first_cell_id"].map(normalize_cgi)
        if "first_cell_id" in work.columns
        else ""
    )
    work["_source_order"] = range(len(work))

    date_text = (
        work["call_date"].fillna("").astype(str)
        if "call_date" in work.columns
        else pd.Series("", index=work.index)
    )
    time_text = (
        work["call_time"].fillna("").astype(str)
        if "call_time" in work.columns
        else pd.Series("", index=work.index)
    )
    work["_event_datetime"] = pd.to_datetime(
        date_text.str.strip() + " " + time_text.str.strip(),
        format="mixed",
        errors="coerce",
        dayfirst=True,
    )

    tower_rows = work.loc[
        work["_cgi"].fillna("").astype(str).str.strip().ne("")
    ].copy()

    if tower_rows.empty:
        output["Unique Target Towers"] = 0
        output["Most Used Target CGI"] = ""
        output["Most Used CGI Events"] = 0
        output["Last Interaction CGI"] = ""
    else:
        unique_towers = (
            tower_rows.groupby("_contact_key")["_cgi"]
            .nunique()
            .reset_index(name="Unique Target Towers")
        )
        top_tower = (
            tower_rows.groupby(
                ["_contact_key", "_cgi"],
                dropna=False,
            )
            .size()
            .reset_index(name="Most Used CGI Events")
            .sort_values(
                [
                    "_contact_key",
                    "Most Used CGI Events",
                    "_cgi",
                ],
                ascending=[True, False, True],
            )
            .drop_duplicates("_contact_key")
            .rename(columns={"_cgi": "Most Used Target CGI"})
        )
        last_tower = (
            tower_rows.sort_values(
                ["_event_datetime", "_source_order"],
                kind="mergesort",
                na_position="first",
            )
            .drop_duplicates("_contact_key", keep="last")
            [["_contact_key", "_cgi"]]
            .rename(columns={"_cgi": "Last Interaction CGI"})
        )
        metrics = (
            unique_towers.merge(
                top_tower,
                on="_contact_key",
                how="outer",
            )
            .merge(
                last_tower,
                on="_contact_key",
                how="outer",
            )
        )
        output = output.merge(
            metrics,
            on="_contact_key",
            how="left",
        )

    keys: set[str] = set()

    for column in (
        "Most Used Target CGI",
        "Last Interaction CGI",
    ):
        if column in output.columns:
            keys.update(
                str(value).strip()
                for value in output[column].dropna()
                if str(value).strip()
            )

    lookup = (
        lookup_cgi_addresses(keys)
        if keys
        else pd.DataFrame()
    )
    fields = {
        "site_name": "Site Name",
        "address": "Tower Address",
        "latitude": "Latitude",
        "longitude": "Longitude",
    }

    for cgi_column, label in (
        ("Most Used Target CGI", "Most Used"),
        ("Last Interaction CGI", "Last Interaction"),
    ):
        expected = [
            f"{label} {display}"
            for display in fields.values()
        ]

        if (
            not lookup.empty
            and "cgi" in lookup.columns
            and cgi_column in output.columns
        ):
            selected = lookup[
                ["cgi", *fields.keys()]
            ].copy()
            selected = selected.rename(
                columns={
                    "cgi": cgi_column,
                    **{
                        source: f"{label} {display}"
                        for source, display in fields.items()
                    },
                }
            )
            output = output.merge(
                selected,
                on=cgi_column,
                how="left",
            )
        else:
            for column in expected:
                output[column] = ""

    for column in (
        "Unique Target Towers",
        "Most Used CGI Events",
    ):
        if column in output.columns:
            output[column] = (
                pd.to_numeric(
                    output[column],
                    errors="coerce",
                )
                .fillna(0)
                .astype(int)
            )

    return (
        output.drop(
            columns=["_contact_key"],
            errors="ignore",
        )
        .reset_index(drop=True)
    )

# BEGIN CDR FINAL PRESENTATION PATCH
_build_full_contact_summary_base_final = build_full_contact_summary

FULL_CONTACT_PRESENTATION_COLUMNS = (
    "Other Party",
    "Name",
    "Father Name",
    "SDR Address",
    "SDR Operator",
    "SDR Circle",
    "SDR Lookup Status",
    "Total Calls",
    "Total Duration",
    "Avg. Call Duration",
    "Out Count",
    "IN Count",
    "Out SMS Count",
    "In SMS Count",
    "First Call Time",
    "Last Call Time",
    "Unique Target Towers",
    "Most Used Target CGI",
    "Most Used CGI Events",
    "Most Used CGI Lookup Status",
    "Most Used Site Name",
    "Most Used Tower Address",
    "Most Used Latitude",
    "Most Used Longitude",
    "Last Interaction CGI",
    "Last Interaction CGI Lookup Status",
    "Last Interaction Site Name",
    "Last Interaction Tower Address",
    "Last Interaction Latitude",
    "Last Interaction Longitude",
)


def _report_text(value) -> str:
    """Return a clean display value without changing source evidence."""

    if value is None or pd.isna(value):
        return ""

    text = str(value).strip()

    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]

    return text


def _fill_blank_display_values(
    frame: pd.DataFrame,
    target_column: str,
    source_column: str,
) -> None:
    """Fill only blank report values from one lookup column."""

    if source_column not in frame.columns:
        return

    if target_column not in frame.columns:
        frame[target_column] = ""

    current = frame[target_column].map(_report_text)
    incoming = frame[source_column].map(_report_text)

    frame[target_column] = current.where(
        current.ne(""),
        incoming,
    )


def _add_sdr_presentation_fields(
    frame: pd.DataFrame,
    contact_column: str,
) -> pd.DataFrame:
    """Add one bulk SDR lookup result per displayed contact."""

    output = frame.copy()

    for column in (
        "Name",
        "Father Name",
        "SDR Address",
        "SDR Operator",
        "SDR Circle",
        "SDR Lookup Status",
    ):
        if column not in output.columns:
            output[column] = ""

    try:
        from modules.enrichment.sdr_subscriber_enrichment import (
            lookup_sdr_subscribers,
            normalize_mobile_number,
        )

        output["_report_mobile_key"] = output[
            contact_column
        ].map(
            normalize_mobile_number
        )

        lookup = lookup_sdr_subscribers(
            output["_report_mobile_key"]
            .dropna()
            .unique()
        )
        lookup_failed = False
    except Exception:
        output["_report_mobile_key"] = output[
            contact_column
        ].map(
            lambda value: _contact_key(value)
        )
        lookup = pd.DataFrame()
        lookup_failed = True

    nonblank_mobile = (
        output["_report_mobile_key"]
        .fillna("")
        .astype(str)
        .str.strip()
        .ne("")
    )

    output["SDR Lookup Status"] = "NOT_PROVIDED"
    output.loc[
        nonblank_mobile,
        "SDR Lookup Status",
    ] = (
        "LOOKUP_ERROR"
        if lookup_failed
        else "NOT_FOUND"
    )

    if (
        isinstance(lookup, pd.DataFrame)
        and not lookup.empty
        and "lookup_mobile" in lookup.columns
    ):
        selected = lookup.copy()
        selected["_report_mobile_key"] = selected[
            "lookup_mobile"
        ].map(
            lambda value: _report_text(value)
        )

        source_columns = {
            "subscriber_name": "_report_sdr_name",
            "father_name": "_report_sdr_father",
            "subscriber_address": "_report_sdr_address",
            "operator": "_report_sdr_operator",
            "circle": "_report_sdr_circle",
            "sdr_found": "_report_sdr_found",
        }

        available = [
            "_report_mobile_key",
            *[
                column
                for column in source_columns
                if column in selected.columns
            ],
        ]

        selected = (
            selected[available]
            .drop_duplicates(
                "_report_mobile_key",
                keep="first",
            )
            .rename(
                columns=source_columns
            )
        )

        output = output.merge(
            selected,
            on="_report_mobile_key",
            how="left",
        )

        _fill_blank_display_values(
            output,
            "Name",
            "_report_sdr_name",
        )
        _fill_blank_display_values(
            output,
            "Father Name",
            "_report_sdr_father",
        )
        _fill_blank_display_values(
            output,
            "SDR Address",
            "_report_sdr_address",
        )
        _fill_blank_display_values(
            output,
            "SDR Operator",
            "_report_sdr_operator",
        )
        _fill_blank_display_values(
            output,
            "SDR Circle",
            "_report_sdr_circle",
        )

        if "_report_sdr_found" in output.columns:
            found_text = (
                output["_report_sdr_found"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
            )
            found_mask = found_text.isin(
                {
                    "YES",
                    "TRUE",
                    "1",
                    "FOUND",
                }
            )
        else:
            found_mask = pd.Series(
                False,
                index=output.index,
            )

            for column in (
                "Name",
                "Father Name",
                "SDR Address",
                "SDR Operator",
                "SDR Circle",
            ):
                found_mask = (
                    found_mask
                    | output[column]
                    .map(_report_text)
                    .ne("")
                )

        output.loc[
            found_mask,
            "SDR Lookup Status",
        ] = "FOUND"

    return output


def _add_cgi_presentation_fields(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    """Add site, address, coordinates and transparent CGI status."""

    output = frame.copy()

    field_map = {
        "site_name": "Site Name",
        "address": "Tower Address",
        "latitude": "Latitude",
        "longitude": "Longitude",
    }

    pairs = (
        (
            "Most Used Target CGI",
            "Most Used",
        ),
        (
            "Last Interaction CGI",
            "Last Interaction",
        ),
    )

    lookup_values: set[str] = set()

    for cgi_column, label in pairs:
        if cgi_column not in output.columns:
            output[cgi_column] = ""

        for display_name in field_map.values():
            report_column = f"{label} {display_name}"

            if report_column not in output.columns:
                output[report_column] = pd.NA

        status_column = f"{label} CGI Lookup Status"

        if status_column not in output.columns:
            output[status_column] = "NOT_PROVIDED"

        normalized = output[cgi_column].map(
            normalize_cgi
        )
        output[f"_report_{label}_cgi_key"] = normalized

        lookup_values.update(
            value
            for value in normalized
            if _report_text(value)
        )

    try:
        lookup = (
            lookup_cgi_addresses(
                sorted(lookup_values)
            )
            if lookup_values
            else pd.DataFrame()
        )
        lookup_failed = False
    except Exception:
        lookup = pd.DataFrame()
        lookup_failed = True

    if (
        isinstance(lookup, pd.DataFrame)
        and not lookup.empty
        and "cgi" in lookup.columns
    ):
        lookup = lookup.copy()
        lookup["_report_cgi_key"] = lookup[
            "cgi"
        ].map(
            normalize_cgi
        )
        lookup = lookup.drop_duplicates(
            "_report_cgi_key",
            keep="first",
        )
    else:
        lookup = pd.DataFrame()

    for cgi_column, label in pairs:
        key_column = f"_report_{label}_cgi_key"
        status_column = f"{label} CGI Lookup Status"

        nonblank_cgi = (
            output[key_column]
            .fillna("")
            .astype(str)
            .str.strip()
            .ne("")
        )

        output[status_column] = "NOT_PROVIDED"
        output.loc[
            nonblank_cgi,
            status_column,
        ] = (
            "LOOKUP_ERROR"
            if lookup_failed
            else "NOT_FOUND"
        )

        if lookup.empty:
            continue

        selected_columns = [
            "_report_cgi_key",
            *[
                source
                for source in field_map
                if source in lookup.columns
            ],
        ]
        selected = lookup[selected_columns].rename(
            columns={
                source: f"_report_{label}_{source}"
                for source in field_map
                if source in lookup.columns
            }
        )

        output = output.merge(
            selected,
            left_on=key_column,
            right_on="_report_cgi_key",
            how="left",
        )

        found_mask = output[
            "_report_cgi_key"
        ].notna()

        for source, display_name in field_map.items():
            lookup_column = f"_report_{label}_{source}"
            report_column = f"{label} {display_name}"

            _fill_blank_display_values(
                output,
                report_column,
                lookup_column,
            )

        output.loc[
            found_mask,
            status_column,
        ] = "FOUND"

        output = output.drop(
            columns=[
                "_report_cgi_key",
            ],
            errors="ignore",
        )

    return output


def build_full_contact_summary(
    data: pd.DataFrame,
    contact_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Return complete contact, SDR and target-serving CGI details."""

    output = _build_full_contact_summary_base_final(
        data,
        contact_summary,
    )

    if (
        not isinstance(output, pd.DataFrame)
        or output.empty
    ):
        return output

    contact_column = next(
        (
            column
            for column in (
                "Other Party",
                "Contact",
                "b_party",
            )
            if column in output.columns
        ),
        None,
    )

    if contact_column is None:
        return output

    if contact_column != "Other Party":
        output = output.rename(
            columns={
                contact_column: "Other Party",
            }
        )

    output = _add_sdr_presentation_fields(
        output,
        "Other Party",
    )
    output = _add_cgi_presentation_fields(
        output
    )

    for column in FULL_CONTACT_PRESENTATION_COLUMNS:
        if column not in output.columns:
            if column.endswith("Lookup Status"):
                output[column] = "NOT_PROVIDED"
            elif column in (
                "Unique Target Towers",
                "Most Used CGI Events",
            ):
                output[column] = 0
            else:
                output[column] = pd.NA

    technical_columns = [
        column
        for column in output.columns
        if str(column).startswith(
            "_report_"
        )
    ]

    output = output.drop(
        columns=technical_columns,
        errors="ignore",
    )

    additional_columns = [
        column
        for column in output.columns
        if column
        not in FULL_CONTACT_PRESENTATION_COLUMNS
    ]

    return output[
        [
            *FULL_CONTACT_PRESENTATION_COLUMNS,
            *additional_columns,
        ]
    ].reset_index(
        drop=True
    )
# END CDR FINAL PRESENTATION PATCH
