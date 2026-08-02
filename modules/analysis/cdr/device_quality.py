from __future__ import annotations

from typing import Any

import pandas as pd


DEVICE_SUMMARY_COLUMNS = [
    "Device Key",
    "IMEI",
    "imei",
    "Observed IMEI Values",
    "Valid IMEI",
    "Invalid IMEI Values",
    "IMEI Status",
    "First Seen",
    "Last Seen",
    "Total Events",
    "Unique Human Contacts",
    "Unique Valid Towers",
    "Total Duration (Sec)",
    "Most Used Valid Tower",
    "Most Human Contacted",
]

CHANGE_COLUMNS = [
    "Date",
    "Time",
    "Change Type",
    "Old IMEI",
    "New IMEI",
    "Old Device Key",
    "New Device Key",
    "Old IMSI",
    "New IMSI",
    "Tower",
    "Contact",
    "Event",
    "Interpretation",
]


def _clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""

    text = str(value).strip()

    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]

    return text


def imei_digits(value: Any) -> str:
    'Return normalized digits without changing the source value.'

    return "".join(
        character
        for character in _clean_text(value)
        if character.isdigit()
    )


def imei_is_valid(value: Any) -> bool:
    'Return True only for a valid 15-digit Luhn IMEI.'

    digits = imei_digits(value)

    if len(digits) != 15:
        return False

    total = 0

    for index, character in enumerate(reversed(digits)):
        number = int(character)

        if index % 2 == 1:
            number *= 2

            if number > 9:
                number -= 9

        total += number

    return total % 10 == 0


def imei_status(value: Any) -> str:
    'Classify an observed equipment identifier.'

    digits = imei_digits(value)

    if len(digits) == 15:
        return "VALID_IMEI" if imei_is_valid(digits) else "INVALID_IMEI"

    if len(digits) == 16:
        return "IMEISV"

    return "NON_STANDARD_IDENTIFIER"


def imei_device_key(value: Any) -> str:
    'Return a probable device key while preserving the raw identifier.'

    digits = imei_digits(value)

    if len(digits) in {15, 16}:
        return digits[:14]

    return digits or _clean_text(value)


def _event_datetime(data: pd.DataFrame) -> pd.Series:
    if "_event_datetime" in data.columns:
        return pd.to_datetime(
            data["_event_datetime"],
            errors="coerce",
        )

    date_text = (
        data["call_date"].fillna("").astype(str)
        if "call_date" in data.columns
        else pd.Series("", index=data.index)
    )
    time_text = (
        data["call_time"].fillna("").astype(str)
        if "call_time" in data.columns
        else pd.Series("", index=data.index)
    )

    return pd.to_datetime(
        date_text.str.strip() + " " + time_text.str.strip(),
        format="mixed",
        errors="coerce",
        dayfirst=True,
    )


def _human_mobile(value: Any) -> str:
    digits = imei_digits(value)

    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[-10:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[-10:]

    if len(digits) == 10 and digits[0] in "6789":
        return digits

    return ""


def _valid_tower(value: Any) -> str:
    text = _clean_text(value)

    if text.casefold() in {
        "",
        "0",
        "nan",
        "none",
        "<na>",
        "n/a",
        "na",
    }:
        return ""

    return text


def _join_unique(values: pd.Series) -> str:
    result: list[str] = []

    for value in values:
        text = _clean_text(value)

        if text and text not in result:
            result.append(text)

    return ", ".join(result)


def _group_status(values: pd.Series) -> str:
    statuses = {
        _clean_text(value)
        for value in values
        if _clean_text(value)
    }

    if {"VALID_IMEI", "INVALID_IMEI"}.issubset(statuses):
        return "Valid IMEI with invalid observed variant"

    if "VALID_IMEI" in statuses:
        return "Valid IMEI"

    if "IMEISV" in statuses:
        return "IMEISV device identifier"

    if "INVALID_IMEI" in statuses:
        return "Invalid IMEI only"

    return "Non-standard device identifier"


def _prepare(dataframe: pd.DataFrame) -> pd.DataFrame:
    if (
        dataframe is None
        or dataframe.empty
        or "imei" not in dataframe.columns
    ):
        return pd.DataFrame()

    data = dataframe.copy()
    data["_raw_imei"] = data["imei"].map(_clean_text)
    data = data.loc[data["_raw_imei"].ne("")].copy()

    if data.empty:
        return pd.DataFrame()

    data["_device_key"] = data["_raw_imei"].map(imei_device_key)
    data["_imei_status"] = data["_raw_imei"].map(imei_status)
    data["_event_datetime"] = _event_datetime(data)
    data["_duration"] = (
        pd.to_numeric(
            data["call_duration"],
            errors="coerce",
        ).fillna(0)
        if "call_duration" in data.columns
        else 0
    )
    data["_human_contact"] = (
        data["b_party"].map(_human_mobile)
        if "b_party" in data.columns
        else ""
    )
    data["_valid_tower"] = (
        data["first_cell_id"].map(_valid_tower)
        if "first_cell_id" in data.columns
        else ""
    )

    return data


def device_summary(dataframe: pd.DataFrame) -> pd.DataFrame:
    'Return one row per probable device key.'

    data = _prepare(dataframe)

    if data.empty:
        return pd.DataFrame(columns=DEVICE_SUMMARY_COLUMNS)

    result = (
        data.groupby("_device_key", dropna=False)
        .agg(
            **{
                "Observed IMEI Values": (
                    "_raw_imei",
                    _join_unique,
                ),
                "IMEI Status": (
                    "_imei_status",
                    _group_status,
                ),
                "First Seen": (
                    "_event_datetime",
                    "min",
                ),
                "Last Seen": (
                    "_event_datetime",
                    "max",
                ),
                "Total Events": (
                    "_raw_imei",
                    "size",
                ),
                "Unique Human Contacts": (
                    "_human_contact",
                    lambda values: (
                        values.replace("", pd.NA)
                        .dropna()
                        .nunique()
                    ),
                ),
                "Unique Valid Towers": (
                    "_valid_tower",
                    lambda values: (
                        values.replace("", pd.NA)
                        .dropna()
                        .nunique()
                    ),
                ),
                "Total Duration (Sec)": (
                    "_duration",
                    "sum",
                ),
            }
        )
        .reset_index()
        .rename(columns={"_device_key": "Device Key"})
    )

    valid = (
        data.loc[data["_imei_status"].eq("VALID_IMEI")]
        .groupby("_device_key")["_raw_imei"]
        .agg(_join_unique)
        .reset_index(name="Valid IMEI")
        .rename(columns={"_device_key": "Device Key"})
    )
    invalid = (
        data.loc[data["_imei_status"].eq("INVALID_IMEI")]
        .groupby("_device_key")["_raw_imei"]
        .agg(_join_unique)
        .reset_index(name="Invalid IMEI Values")
        .rename(columns={"_device_key": "Device Key"})
    )

    tower_counts = (
        data.loc[data["_valid_tower"].ne("")]
        .groupby(["_device_key", "_valid_tower"])
        .size()
        .reset_index(name="_count")
        .sort_values(
            ["_device_key", "_count", "_valid_tower"],
            ascending=[True, False, True],
        )
        .drop_duplicates("_device_key")
        .rename(
            columns={
                "_device_key": "Device Key",
                "_valid_tower": "Most Used Valid Tower",
            }
        )
        [["Device Key", "Most Used Valid Tower"]]
    )

    contact_counts = (
        data.loc[data["_human_contact"].ne("")]
        .groupby(["_device_key", "_human_contact"])
        .size()
        .reset_index(name="_count")
        .sort_values(
            ["_device_key", "_count", "_human_contact"],
            ascending=[True, False, True],
        )
        .drop_duplicates("_device_key")
        .rename(
            columns={
                "_device_key": "Device Key",
                "_human_contact": "Most Human Contacted",
            }
        )
        [["Device Key", "Most Human Contacted"]]
    )

    for extra in (
        valid,
        invalid,
        tower_counts,
        contact_counts,
    ):
        result = result.merge(extra, on="Device Key", how="left")

    for column in (
        "Valid IMEI",
        "Invalid IMEI Values",
        "Most Used Valid Tower",
        "Most Human Contacted",
    ):
        result[column] = result[column].fillna("")

    representative = (
        result["Observed IMEI Values"]
        .astype(str)
        .str.split(", ")
        .str[0]
    )
    result["IMEI"] = result["Valid IMEI"].where(
        result["Valid IMEI"].astype(str).str.strip().ne(""),
        representative,
    )
    result["imei"] = result["IMEI"]

    return (
        result[DEVICE_SUMMARY_COLUMNS]
        .sort_values(
            ["Total Events", "Device Key"],
            ascending=[False, True],
            ignore_index=True,
        )
    )


def device_intelligence(dataframe: pd.DataFrame) -> pd.DataFrame:
    'Compatibility name for the canonical device summary.'

    return device_summary(dataframe)


def device_change_review(dataframe: pd.DataFrame) -> pd.DataFrame:
    'Separate device, SIM and raw identifier changes.'

    if (
        dataframe is None
        or dataframe.empty
        or (
            "imei" not in dataframe.columns
            and "imsi" not in dataframe.columns
        )
    ):
        return pd.DataFrame(columns=CHANGE_COLUMNS)

    data = dataframe.copy()
    data["_event_datetime"] = _event_datetime(data)
    data["_source_order"] = range(len(data))
    data["_raw_imei"] = (
        data["imei"].map(_clean_text)
        if "imei" in data.columns
        else ""
    )
    data["_raw_imsi"] = (
        data["imsi"].map(_clean_text)
        if "imsi" in data.columns
        else ""
    )
    data["_device_key"] = data["_raw_imei"].map(imei_device_key)

    data = data.loc[
        data["_event_datetime"].notna()
        & (
            data["_raw_imei"].ne("")
            | data["_raw_imsi"].ne("")
        )
    ].sort_values(
        ["_event_datetime", "_source_order"],
        kind="mergesort",
    )

    if len(data) < 2:
        return pd.DataFrame(columns=CHANGE_COLUMNS)

    data["_previous_imei"] = data["_raw_imei"].shift(1)
    data["_previous_device_key"] = data["_device_key"].shift(1)
    data["_previous_imsi"] = data["_raw_imsi"].shift(1)

    raw_change = (
        data["_previous_imei"].fillna("").ne("")
        & data["_raw_imei"].ne("")
        & data["_raw_imei"].ne(data["_previous_imei"])
    )
    device_change = (
        data["_previous_device_key"].fillna("").ne("")
        & data["_device_key"].ne("")
        & data["_device_key"].ne(data["_previous_device_key"])
    )
    sim_change = (
        data["_previous_imsi"].fillna("").ne("")
        & data["_raw_imsi"].ne("")
        & data["_raw_imsi"].ne(data["_previous_imsi"])
    )
    variant = raw_change & ~device_change
    relevant = device_change | sim_change | variant

    changes = data.loc[relevant].copy()

    if changes.empty:
        return pd.DataFrame(columns=CHANGE_COLUMNS)

    change_type = pd.Series("", index=data.index, dtype="string")
    change_type.loc[variant] = "Identifier Variant"
    change_type.loc[device_change & ~sim_change] = "Device Change"
    change_type.loc[sim_change & ~device_change] = "SIM Change"
    change_type.loc[device_change & sim_change] = "Device and SIM Change"

    interpretation = {
        "Identifier Variant": (
            "Raw IMEI values changed but share the same probable "
            "device key. This is not counted as a device change."
        ),
        "Device Change": (
            "The probable device key changed. Verify against source "
            "records and handset evidence."
        ),
        "SIM Change": (
            "The IMSI changed while the probable device key remained "
            "the same. Verify subscriber and SIM records."
        ),
        "Device and SIM Change": (
            "Both the probable device key and IMSI changed. Verify "
            "against source and acquisition records."
        ),
    }

    changes["Date"] = changes["_event_datetime"].dt.strftime("%d-%m-%Y")
    changes["Time"] = changes["_event_datetime"].dt.strftime("%H:%M:%S")
    changes["Change Type"] = change_type.loc[changes.index]
    changes["Old IMEI"] = changes["_previous_imei"]
    changes["New IMEI"] = changes["_raw_imei"]
    changes["Old Device Key"] = changes["_previous_device_key"]
    changes["New Device Key"] = changes["_device_key"]
    changes["Old IMSI"] = changes["_previous_imsi"]
    changes["New IMSI"] = changes["_raw_imsi"]

    sim_changed_rows = sim_change.loc[changes.index].fillna(False)
    changes.loc[
        ~sim_changed_rows,
        ["Old IMSI", "New IMSI"],
    ] = ""
    changes["Tower"] = (
        changes["first_cell_id"]
        if "first_cell_id" in changes.columns
        else "N/A"
    )
    changes["Contact"] = (
        changes["b_party"]
        if "b_party" in changes.columns
        else "N/A"
    )
    changes["Event"] = (
        changes["call_type"]
        if "call_type" in changes.columns
        else "N/A"
    )
    changes["Interpretation"] = changes["Change Type"].map(interpretation)

    return changes[CHANGE_COLUMNS].reset_index(drop=True)


def split_change_review(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    'Return confirmed changes and raw identifier variants separately.'

    if (
        not isinstance(frame, pd.DataFrame)
        or frame.empty
        or "Change Type" not in frame.columns
    ):
        empty = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
        return empty, pd.DataFrame()

    variants = frame.loc[
        frame["Change Type"].eq("Identifier Variant")
    ].copy()
    confirmed = frame.loc[
        ~frame["Change Type"].eq("Identifier Variant")
    ].copy()

    return confirmed, variants
