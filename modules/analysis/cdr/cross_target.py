"""Cross-target intelligence for multiple normalized CDR DataFrames.

The module identifies values shared by at least two targets:
- common contacted numbers
- direct target-to-target links
- common tower IDs
- common IMEIs
- common IMSIs
- target/item count matrices

Every section is generated independently. A malformed target DataFrame is
reported in the errors table without stopping analysis of the remaining files.
"""

from __future__ import annotations

import re
import traceback
from typing import Any

import pandas as pd


RESULT_COLUMNS = {
    "summary": ["Metric", "Value"],
    "target_overview": [
        "Target", "Source File", "Total Records", "From Date", "To Date",
        "Unique Contacts", "Unique Towers", "Unique IMEIs", "Unique IMSIs",
    ],
    "common_numbers": [
        "Common Number", "Linked Targets", "Target Count", "Total Events",
        "Outgoing Events", "Incoming Events", "SMS Events",
        "Total Duration (Sec)", "First Seen", "Last Seen",
        "Matches Investigated Target",
    ],
    "direct_target_links": [
        "Source Target", "Destination Target", "Total Events",
        "Outgoing Events", "Incoming Events", "SMS Events",
        "Total Duration (Sec)", "First Seen", "Last Seen",
    ],
    "common_towers": [
        "Common Tower ID", "Linked Targets", "Target Count", "Total Events",
        "Unique Contacts", "Night Events", "First Seen", "Last Seen",
    ],
    "common_imeis": [
        "Common IMEI", "Linked Targets", "Target Count", "Total Events",
        "Unique Contacts", "Unique Towers", "First Seen", "Last Seen",
    ],
    "common_imsis": [
        "Common IMSI", "Linked Targets", "Target Count", "Total Events",
        "Unique Contacts", "Unique IMEIs", "First Seen", "Last Seen",
    ],
    "source_files": ["Target", "Source File", "Records", "Target Detection Method"],
    "alerts": ["Severity", "Alert Type", "Observation"],
    "errors": ["Target / Section", "Error"],
}


def _empty_result(name: str) -> pd.DataFrame:
    return pd.DataFrame(columns=RESULT_COLUMNS.get(name, []))


def _normalise_number(value: Any) -> str | None:
    """Return a comparable mobile-number key using the last 10 digits."""
    if value is None or pd.isna(value):
        return None

    digits = re.sub(r"\D", "", str(value))
    if len(digits) < 10:
        return None

    return digits[-10:]


def _normalise_identifier(value: Any) -> str | None:
    """Clean a generic telecom identifier without destroying CGI separators."""
    if value is None or pd.isna(value):
        return None

    text = str(value).strip().strip("'\"")
    text = re.sub(r"\.0$", "", text)
    if not text or text.lower() in {"nan", "none", "null", "<na>"}:
        return None
    return text.upper()


def _normalise_imei(value: Any) -> str | None:
    """Normalise IMEI; 16-digit IMEISV values are compared by first 15 digits."""
    if value is None or pd.isna(value):
        return None

    digits = re.sub(r"\D", "", str(value))
    if len(digits) < 14:
        return None
    return digits[:15] if len(digits) >= 15 else digits


def _normalise_imsi(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None

    digits = re.sub(r"\D", "", str(value))
    if len(digits) < 10:
        return None
    return digits


def _normalise_number_series(series: pd.Series) -> pd.Series:
    """Vectorized equivalent of _normalise_number for large CDR frames."""

    digits = (
        series.astype(
            "string"
        )
        .fillna(
            ""
        )
        .str.replace(
            r"\D",
            "",
            regex=True,
        )
    )
    valid = digits.str.len().ge(
        10
    )
    return digits.str[-10:].where(
        valid,
        pd.NA,
    )


def _normalise_identifier_series(series: pd.Series) -> pd.Series:
    """Vectorized equivalent of _normalise_identifier."""

    text = (
        series.astype(
            "string"
        )
        .fillna(
            ""
        )
        .str.strip()
        .str.strip(
            "'\""
        )
        .str.replace(
            r"\.0$",
            "",
            regex=True,
        )
        .str.upper()
    )
    invalid = text.str.lower().isin(
        {
            "",
            "nan",
            "none",
            "null",
            "<na>",
        }
    )
    return text.where(
        ~invalid,
        pd.NA,
    )


def _normalise_imei_series(series: pd.Series) -> pd.Series:
    """Vectorized equivalent of _normalise_imei."""

    digits = (
        series.astype(
            "string"
        )
        .fillna(
            ""
        )
        .str.replace(
            r"\D",
            "",
            regex=True,
        )
    )
    lengths = digits.str.len()
    normalized = digits.where(
        lengths.lt(
            15
        ),
        digits.str[:15],
    )
    return normalized.where(
        lengths.ge(
            14
        ),
        pd.NA,
    )


def _normalise_imsi_series(series: pd.Series) -> pd.Series:
    """Vectorized equivalent of _normalise_imsi."""

    digits = (
        series.astype(
            "string"
        )
        .fillna(
            ""
        )
        .str.replace(
            r"\D",
            "",
            regex=True,
        )
    )
    return digits.where(
        digits.str.len().ge(
            10
        ),
        pd.NA,
    )


def _first_existing(data: pd.DataFrame, names: list[str], default: Any = pd.NA) -> pd.Series:
    for name in names:
        if name in data.columns:
            return data[name]
    return pd.Series(default, index=data.index, dtype="object")


def _prepare_target_frame(df: pd.DataFrame, target: str) -> pd.DataFrame:
    """Create a compact canonical frame used only by cross-target analysis."""

    # Keep only the derived fields consumed below.  Copying every raw source
    # column for every target multiplied memory and concat cost without adding
    # any cross-target evidence.
    source = df

    if not (
        isinstance(
            source.index,
            pd.RangeIndex,
        )
        and source.index.start == 0
        and source.index.step == 1
    ):
        source = source.reset_index(
            drop=True
        )
    data = pd.DataFrame(
        index=source.index
    )
    data["_row_id"] = range(len(data))
    data["_target"] = str(target).strip()
    data["_target_key"] = _normalise_number(target) or str(target).strip()

    if "datetime" in source.columns:
        parsed_datetime = pd.to_datetime(source["datetime"], errors="coerce", dayfirst=True)
    else:
        call_date = _first_existing(source, ["call_date"], "").astype("string").fillna("")
        call_time = _first_existing(source, ["call_time"], "").astype("string").fillna("")
        parsed_datetime = pd.to_datetime(
            call_date.str.strip() + " " + call_time.str.strip(),
            errors="coerce",
            dayfirst=True,
        )
    data["_datetime"] = parsed_datetime

    other_party = _first_existing(source, ["opposite_party", "b_party"])
    data["_other_number"] = _normalise_number_series(
        other_party
    )

    call_type = _first_existing(source, ["call_type"], "unknown").astype("string").fillna("unknown")
    data["_call_type"] = call_type.str.lower().str.strip()

    direction = _first_existing(source, ["call_direction"], "").astype("string").fillna("")
    data["_direction"] = direction.str.upper().str.strip()

    data["_duration"] = pd.to_numeric(
        _first_existing(source, ["call_duration"], 0), errors="coerce"
    ).fillna(0).clip(lower=0)

    data["_imei"] = _normalise_imei_series(
        _first_existing(source, ["imei"])
    )
    data["_imsi"] = _normalise_imsi_series(
        _first_existing(source, ["imsi"])
    )
    data["_first_tower"] = _normalise_identifier_series(
        _first_existing(source, ["first_cell_id", "cell_id"])
    )
    data["_last_tower"] = _normalise_identifier_series(
        _first_existing(source, ["last_cell_id"])
    )

    is_sms = data["_call_type"].str.contains("sms", na=False)
    data["_is_sms"] = is_sms
    data["_is_outgoing"] = (
        data["_call_type"].isin(["outgoing", "outgoing_call", "smsout", "outgoing_sms"])
        | data["_direction"].eq("OUTGOING")
    )
    data["_is_incoming"] = (
        data["_call_type"].isin(["incoming", "incoming_call", "smsin", "incoming_sms"])
        | data["_direction"].eq("INCOMING")
    )

    data["_hour"] = data["_datetime"].dt.hour
    data["_is_night"] = data["_hour"].ge(22) | data["_hour"].lt(6)
    return data


def _common_item_keys(
    events: pd.DataFrame,
    item_column: str,
    min_targets: int,
) -> set[str]:
    """Return item keys present for the configured number of targets."""

    if events.empty:
        return set()

    target_counts = events.groupby(
        item_column,
        sort=False,
        dropna=False,
    )[
        "_target"
    ].nunique()

    return set(
        target_counts.loc[
            target_counts.ge(
                min_targets
            )
        ].index.tolist()
    )


def _linked_target_labels(
    events: pd.DataFrame,
    item_column: str,
) -> pd.Series:
    """Build sorted linked-target labels after common items are filtered."""

    if events.empty:
        return pd.Series(
            dtype="string"
        )

    pairs = (
        events.loc[
            :,
            [
                item_column,
                "_target",
            ],
        ]
        .dropna()
        .drop_duplicates()
        .sort_values(
            [
                item_column,
                "_target",
            ],
            kind="stable",
        )
    )

    return pairs.groupby(
        item_column,
        sort=False,
        dropna=False,
    )[
        "_target"
    ].agg(
        ", ".join
    )


def _matrix(
    events: pd.DataFrame,
    item_column: str,
    item_header: str,
    common_items: set[str],
    targets: list[str],
) -> pd.DataFrame:
    if events.empty or not common_items:
        return pd.DataFrame(columns=[item_header, *targets, "Total Events", "Target Count"])

    work = events[events[item_column].isin(common_items)].copy()
    if work.empty:
        return pd.DataFrame(columns=[item_header, *targets, "Total Events", "Target Count"])

    pivot = pd.pivot_table(
        work,
        index=item_column,
        columns="_target",
        values="_row_id",
        aggfunc="count",
        fill_value=0,
    )

    for target in targets:
        if target not in pivot.columns:
            pivot[target] = 0

    pivot = pivot[targets]
    pivot["Total Events"] = pivot.sum(axis=1)
    pivot["Target Count"] = (pivot[targets] > 0).sum(axis=1)
    pivot = pivot.reset_index().rename(columns={item_column: item_header})
    return pivot.sort_values(["Target Count", "Total Events"], ascending=False).reset_index(drop=True)


def _build_contact_outputs(
    all_events: pd.DataFrame,
    target_key_to_label: dict[str, str],
    targets: list[str],
    min_targets: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    contacts = all_events[all_events["_other_number"].notna()].copy()
    if contacts.empty:
        return (
            _empty_result("common_numbers"),
            _empty_result("direct_target_links"),
            _matrix(contacts, "_other_number", "Common Number", set(), targets),
        )

    common_items = _common_item_keys(
        contacts,
        "_other_number",
        min_targets,
    )
    common_events = contacts.loc[
        contacts[
            "_other_number"
        ].isin(
            common_items
        )
    ].copy()

    common = common_events.groupby(
        "_other_number",
        sort=False,
        dropna=False,
    ).agg(
        **{
            "Target Count": ("_target", "nunique"),
            "Total Events": ("_row_id", "count"),
            "Outgoing Events": ("_is_outgoing", "sum"),
            "Incoming Events": ("_is_incoming", "sum"),
            "SMS Events": ("_is_sms", "sum"),
            "Total Duration (Sec)": ("_duration", "sum"),
            "First Seen": ("_datetime", "min"),
            "Last Seen": ("_datetime", "max"),
        }
    ).reset_index()
    common[
        "Linked Targets"
    ] = common[
        "_other_number"
    ].map(
        _linked_target_labels(
            common_events,
            "_other_number",
        )
    ).fillna(
        ""
    )
    common = common.rename(columns={"_other_number": "Common Number"})
    common["Matches Investigated Target"] = common["Common Number"].map(target_key_to_label).fillna("")
    common = common[RESULT_COLUMNS["common_numbers"]]
    common = common.sort_values(
        ["Target Count", "Total Events", "Total Duration (Sec)"],
        ascending=False,
    ).reset_index(drop=True)

    target_keys = set(target_key_to_label)
    direct = contacts[
        contacts["_other_number"].isin(target_keys)
        & contacts["_other_number"].ne(contacts["_target_key"])
    ].copy()

    if direct.empty:
        direct_result = _empty_result("direct_target_links")
    else:
        direct["_destination"] = direct["_other_number"].map(target_key_to_label)
        direct_result = direct.groupby(["_target", "_destination"], dropna=False).agg(
            **{
                "Total Events": ("_row_id", "count"),
                "Outgoing Events": ("_is_outgoing", "sum"),
                "Incoming Events": ("_is_incoming", "sum"),
                "SMS Events": ("_is_sms", "sum"),
                "Total Duration (Sec)": ("_duration", "sum"),
                "First Seen": ("_datetime", "min"),
                "Last Seen": ("_datetime", "max"),
            }
        ).reset_index().rename(
            columns={"_target": "Source Target", "_destination": "Destination Target"}
        )
        direct_result = direct_result[RESULT_COLUMNS["direct_target_links"]]
        direct_result = direct_result.sort_values("Total Events", ascending=False).reset_index(drop=True)

    matrix = _matrix(contacts, "_other_number", "Common Number", common_items, targets)
    return common, direct_result, matrix


def _tower_events(all_events: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    base_columns = [
        "_target", "_target_key", "_row_id", "_datetime", "_other_number",
        "_is_night", "_first_tower", "_last_tower",
    ]
    base = all_events[base_columns].copy()

    for column in ["_first_tower", "_last_tower"]:
        frame = base[["_target", "_target_key", "_row_id", "_datetime", "_other_number", "_is_night", column]].copy()
        frame = frame.rename(columns={column: "_tower"})
        frame = frame[frame["_tower"].notna()]
        frames.append(frame)

    if not frames:
        return pd.DataFrame(columns=["_target", "_row_id", "_tower"])

    towers = pd.concat(frames, ignore_index=True)
    return towers.drop_duplicates(["_target", "_row_id", "_tower"]).reset_index(drop=True)


def _build_tower_outputs(
    all_events: pd.DataFrame,
    targets: list[str],
    min_targets: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    towers = _tower_events(all_events)
    if towers.empty:
        return _empty_result("common_towers"), _matrix(towers, "_tower", "Common Tower ID", set(), targets)

    common_items = _common_item_keys(
        towers,
        "_tower",
        min_targets,
    )
    common_events = towers.loc[
        towers[
            "_tower"
        ].isin(
            common_items
        )
    ].copy()

    result = common_events.groupby(
        "_tower",
        sort=False,
        dropna=False,
    ).agg(
        **{
            "Target Count": ("_target", "nunique"),
            "Total Events": ("_row_id", "count"),
            "Unique Contacts": ("_other_number", "nunique"),
            "Night Events": ("_is_night", "sum"),
            "First Seen": ("_datetime", "min"),
            "Last Seen": ("_datetime", "max"),
        }
    ).reset_index()
    result[
        "Linked Targets"
    ] = result[
        "_tower"
    ].map(
        _linked_target_labels(
            common_events,
            "_tower",
        )
    ).fillna(
        ""
    )
    result = result.rename(columns={"_tower": "Common Tower ID"})
    result = result[RESULT_COLUMNS["common_towers"]]
    result = result.sort_values(["Target Count", "Total Events"], ascending=False).reset_index(drop=True)

    matrix = _matrix(towers, "_tower", "Common Tower ID", common_items, targets)
    return result, matrix


def _build_identifier_outputs(
    all_events: pd.DataFrame,
    identifier_column: str,
    result_name: str,
    item_header: str,
    targets: list[str],
    min_targets: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = all_events[all_events[identifier_column].notna()].copy()
    if work.empty:
        return _empty_result(result_name), _matrix(work, identifier_column, item_header, set(), targets)

    common_items = _common_item_keys(
        work,
        identifier_column,
        min_targets,
    )
    common_events = work.loc[
        work[
            identifier_column
        ].isin(
            common_items
        )
    ].copy()

    if identifier_column == "_imei":
        result = common_events.groupby(
            identifier_column,
            sort=False,
            dropna=False,
        ).agg(
            **{
                "Target Count": ("_target", "nunique"),
                "Total Events": ("_row_id", "count"),
                "Unique Contacts": ("_other_number", "nunique"),
                "Unique Towers": ("_first_tower", "nunique"),
                "First Seen": ("_datetime", "min"),
                "Last Seen": ("_datetime", "max"),
            }
        ).reset_index().rename(columns={identifier_column: item_header})
    else:
        result = common_events.groupby(
            identifier_column,
            sort=False,
            dropna=False,
        ).agg(
            **{
                "Target Count": ("_target", "nunique"),
                "Total Events": ("_row_id", "count"),
                "Unique Contacts": ("_other_number", "nunique"),
                "Unique IMEIs": ("_imei", "nunique"),
                "First Seen": ("_datetime", "min"),
                "Last Seen": ("_datetime", "max"),
            }
        ).reset_index().rename(columns={identifier_column: item_header})

    result[
        "Linked Targets"
    ] = result[
        item_header
    ].map(
        _linked_target_labels(
            common_events,
            identifier_column,
        )
    ).fillna(
        ""
    )
    result = result[RESULT_COLUMNS[result_name]]
    result = result.sort_values(["Target Count", "Total Events"], ascending=False).reset_index(drop=True)

    matrix = _matrix(work, identifier_column, item_header, common_items, targets)
    return result, matrix


def _target_overview(
    prepared: dict[str, pd.DataFrame],
    loaded_cdrs: dict[str, dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []

    for target, data in prepared.items():
        info = loaded_cdrs.get(target, {}) if isinstance(loaded_cdrs.get(target, {}), dict) else {}
        valid_dates = data["_datetime"].dropna()
        tower_values = pd.concat([data["_first_tower"], data["_last_tower"]], ignore_index=True).dropna()

        rows.append({
            "Target": target,
            "Source File": info.get("file", ""),
            "Total Records": len(data),
            "From Date": valid_dates.min() if not valid_dates.empty else pd.NaT,
            "To Date": valid_dates.max() if not valid_dates.empty else pd.NaT,
            "Unique Contacts": data["_other_number"].nunique(dropna=True),
            "Unique Towers": tower_values.nunique(dropna=True),
            "Unique IMEIs": data["_imei"].nunique(dropna=True),
            "Unique IMSIs": data["_imsi"].nunique(dropna=True),
        })

        source_rows.append({
            "Target": target,
            "Source File": info.get("file", ""),
            "Records": len(data),
            "Target Detection Method": info.get("target_method", ""),
        })

    return (
        pd.DataFrame(rows, columns=RESULT_COLUMNS["target_overview"]),
        pd.DataFrame(source_rows, columns=RESULT_COLUMNS["source_files"]),
    )


def _alerts(
    common_numbers: pd.DataFrame,
    direct_links: pd.DataFrame,
    common_towers: pd.DataFrame,
    common_imeis: pd.DataFrame,
    common_imsis: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, str]] = []

    if not common_imeis.empty:
        rows.append({
            "Severity": "HIGH",
            "Alert Type": "Shared Device",
            "Observation": f"{len(common_imeis)} IMEI value(s) are used by two or more investigated targets. Verify handset sharing, SIM swapping, or duplicate records.",
        })
    if not common_imsis.empty:
        rows.append({
            "Severity": "HIGH",
            "Alert Type": "Shared IMSI",
            "Observation": f"{len(common_imsis)} IMSI value(s) occur across multiple targets. Verify subscriber identity, porting history, and source-file accuracy.",
        })
    if not direct_links.empty:
        rows.append({
            "Severity": "MEDIUM",
            "Alert Type": "Direct Target Link",
            "Observation": f"{len(direct_links)} directed target-to-target communication link(s) were identified.",
        })
    if not common_numbers.empty:
        rows.append({
            "Severity": "REVIEW",
            "Alert Type": "Common Contacts",
            "Observation": f"{len(common_numbers)} contacted number(s) are linked with at least two targets.",
        })
    if not common_towers.empty:
        rows.append({
            "Severity": "REVIEW",
            "Alert Type": "Common Towers",
            "Observation": f"{len(common_towers)} tower ID(s) are present in at least two targets. Shared tower use alone does not prove co-location; compare timestamps and tower coverage.",
        })

    if not rows:
        rows.append({
            "Severity": "INFO",
            "Alert Type": "No Shared Indicators",
            "Observation": "No common contact, tower, IMEI, IMSI, or direct target link met the configured minimum-target threshold.",
        })

    return pd.DataFrame(rows, columns=RESULT_COLUMNS["alerts"])


def _build_common_contact_map_rows(
    all_events: pd.DataFrame,
    common_numbers: pd.DataFrame,
) -> pd.DataFrame:
    """Build one compact target/contact table for the common contact map."""

    columns = [
        "Target",
        "Other Party",
        "Total Events",
        "Most Used Target CGI",
        "Most Used CGI Events",
        "Last Interaction CGI",
        "Last Call Time",
    ]

    if (
        all_events.empty
        or not isinstance(common_numbers, pd.DataFrame)
        or common_numbers.empty
        or "Common Number" not in common_numbers.columns
    ):
        return pd.DataFrame(columns=columns)

    common_keys = set(
        common_numbers["Common Number"]
        .dropna()
        .astype(str)
    )
    contacts = all_events[
        all_events["_other_number"].isin(common_keys)
    ].copy()

    if contacts.empty:
        return pd.DataFrame(columns=columns)

    total_events = (
        contacts.groupby(
            ["_target", "_other_number"],
            dropna=False,
        )
        .size()
        .reset_index(name="Total Events")
    )

    tower_rows = contacts[
        contacts["_first_tower"].notna()
    ].copy()

    if tower_rows.empty:
        most_used = pd.DataFrame(
            columns=[
                "_target",
                "_other_number",
                "Most Used Target CGI",
                "Most Used CGI Events",
            ]
        )
    else:
        most_used = (
            tower_rows.groupby(
                ["_target", "_other_number", "_first_tower"],
                dropna=False,
            )
            .size()
            .reset_index(name="Most Used CGI Events")
            .sort_values(
                [
                    "_target",
                    "_other_number",
                    "Most Used CGI Events",
                    "_first_tower",
                ],
                ascending=[True, True, False, True],
                kind="stable",
            )
            .drop_duplicates(
                ["_target", "_other_number"],
                keep="first",
            )
            .rename(
                columns={
                    "_first_tower": "Most Used Target CGI",
                }
            )
        )

    last_rows = (
        contacts.sort_values(
            ["_target", "_other_number", "_datetime", "_row_id"],
            kind="stable",
            na_position="first",
        )
        .drop_duplicates(
            ["_target", "_other_number"],
            keep="last",
        )
        [["_target", "_other_number", "_first_tower", "_datetime"]]
        .rename(
            columns={
                "_first_tower": "Last Interaction CGI",
                "_datetime": "Last Call Time",
            }
        )
    )

    result = total_events.merge(
        most_used,
        on=["_target", "_other_number"],
        how="left",
        sort=False,
    ).merge(
        last_rows,
        on=["_target", "_other_number"],
        how="left",
        sort=False,
    )

    return (
        result.rename(
            columns={
                "_target": "Target",
                "_other_number": "Other Party",
            }
        )
        .loc[:, columns]
        .sort_values(
            ["Total Events", "Target", "Other Party"],
            ascending=[False, True, True],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _build_multi_target_movement_rows(
    all_events: pd.DataFrame,
) -> pd.DataFrame:
    """Build chronological per-target tower changes for a combined route map."""

    columns = [
        "Target",
        "call_date",
        "call_time",
        "first_cell_id",
        "b_party",
        "call_type",
    ]
    movement = all_events[
        all_events["_first_tower"].notna()
        & all_events["_datetime"].notna()
    ].copy()

    if movement.empty:
        return pd.DataFrame(columns=columns)

    movement = movement.sort_values(
        ["_target", "_datetime", "_row_id"],
        kind="stable",
    )
    previous = movement.groupby(
        "_target",
        sort=False,
    )["_first_tower"].shift()
    movement = movement[
        previous.isna()
        | movement[
            "_first_tower"
        ].ne(
            previous
        ).fillna(
            False
        )
    ].copy()

    return pd.DataFrame(
        {
            "Target": movement["_target"].astype(str),
            "call_date": movement["_datetime"].dt.strftime("%d-%m-%Y"),
            "call_time": movement["_datetime"].dt.strftime("%H:%M:%S"),
            "first_cell_id": movement["_first_tower"].astype(str),
            "b_party": movement["_other_number"].fillna("").astype(str),
            "call_type": movement["_call_type"].fillna("").astype(str),
        },
        columns=columns,
    ).reset_index(drop=True)


def build_cross_target_analysis(
    loaded_cdrs: dict[str, dict[str, Any]],
    min_targets: int = 2,
) -> dict[str, Any]:
    """Build the complete multiple-CDR cross-target intelligence bundle.

    Args:
        loaded_cdrs: Controller output in the form
            {target: {"df": DataFrame, "file": "..."}}.
        min_targets: Minimum number of distinct targets required for an item
            to be treated as common. The default is 2.
    """
    result: dict[str, Any] = {}
    errors: list[dict[str, str]] = []

    if not isinstance(loaded_cdrs, dict) or len(loaded_cdrs) < 2:
        message = "At least two target CDR DataFrames are required for cross-target analysis."
        result.update({name: _empty_result(name) for name in RESULT_COLUMNS})
        result["errors"] = pd.DataFrame(
            [{"Target / Section": "input", "Error": message}],
            columns=RESULT_COLUMNS["errors"],
        )
        return result

    min_targets = max(2, int(min_targets))
    prepared: dict[str, pd.DataFrame] = {}

    for raw_target, target_info in loaded_cdrs.items():
        target = str(raw_target).strip()
        try:
            if not isinstance(target_info, dict):
                raise TypeError("Target information must be a dictionary.")
            df = target_info.get("df")
            if df is None or not isinstance(df, pd.DataFrame) or df.empty:
                raise ValueError("DataFrame is empty or invalid.")
            prepared[target] = _prepare_target_frame(df, target)
        except Exception as error:
            errors.append({
                "Target / Section": target,
                "Error": f"{type(error).__name__}: {error}",
            })
            print(f"[-] Cross-target preparation failed for {target}: {type(error).__name__}: {error}")
            print(traceback.format_exc(limit=2).rstrip())

    if len(prepared) < 2:
        message = "Fewer than two valid target DataFrames remained after validation."
        errors.append({"Target / Section": "input", "Error": message})
        result.update({name: _empty_result(name) for name in RESULT_COLUMNS})
        result["errors"] = pd.DataFrame(errors, columns=RESULT_COLUMNS["errors"])
        return result

    targets = sorted(prepared)
    concat_frames = []

    for frame in prepared.values():
        clean_frame = frame.copy()
        clean_frame.attrs = {}
        concat_frames.append(clean_frame)

    all_events = pd.concat(
        concat_frames,
        ignore_index=True,
        sort=False,
    )

    all_events.attrs = {}
    target_key_to_label = {
        (_normalise_number(target) or target): target
        for target in targets
    }

    try:
        common_numbers, direct_links, contact_matrix = _build_contact_outputs(
            all_events, target_key_to_label, targets, min_targets
        )
    except Exception as error:
        errors.append({"Target / Section": "contacts", "Error": f"{type(error).__name__}: {error}"})
        common_numbers = _empty_result("common_numbers")
        direct_links = _empty_result("direct_target_links")
        contact_matrix = pd.DataFrame(columns=["Common Number", *targets, "Total Events", "Target Count"])

    try:
        common_towers, tower_matrix = _build_tower_outputs(all_events, targets, min_targets)
    except Exception as error:
        errors.append({"Target / Section": "towers", "Error": f"{type(error).__name__}: {error}"})
        common_towers = _empty_result("common_towers")
        tower_matrix = pd.DataFrame(columns=["Common Tower ID", *targets, "Total Events", "Target Count"])

    try:
        common_imeis, imei_matrix = _build_identifier_outputs(
            all_events, "_imei", "common_imeis", "Common IMEI", targets, min_targets
        )
    except Exception as error:
        errors.append({"Target / Section": "imei", "Error": f"{type(error).__name__}: {error}"})
        common_imeis = _empty_result("common_imeis")
        imei_matrix = pd.DataFrame(columns=["Common IMEI", *targets, "Total Events", "Target Count"])

    try:
        common_imsis, imsi_matrix = _build_identifier_outputs(
            all_events, "_imsi", "common_imsis", "Common IMSI", targets, min_targets
        )
    except Exception as error:
        errors.append({"Target / Section": "imsi", "Error": f"{type(error).__name__}: {error}"})
        common_imsis = _empty_result("common_imsis")
        imsi_matrix = pd.DataFrame(columns=["Common IMSI", *targets, "Total Events", "Target Count"])

    try:
        target_overview, source_files = _target_overview(prepared, loaded_cdrs)
    except Exception as error:
        errors.append({"Target / Section": "overview", "Error": f"{type(error).__name__}: {error}"})
        target_overview = _empty_result("target_overview")
        source_files = _empty_result("source_files")

    try:
        common_contact_map = _build_common_contact_map_rows(
            all_events,
            common_numbers,
        )
    except Exception as error:
        errors.append({
            "Target / Section": "common contact map",
            "Error": f"{type(error).__name__}: {error}",
        })
        common_contact_map = pd.DataFrame()

    try:
        movement_route_events = _build_multi_target_movement_rows(
            all_events
        )
    except Exception as error:
        errors.append({
            "Target / Section": "movement route",
            "Error": f"{type(error).__name__}: {error}",
        })
        movement_route_events = pd.DataFrame()

    summary = pd.DataFrame([
        {"Metric": "Targets Analyzed", "Value": len(prepared)},
        {"Metric": "Total Records", "Value": len(all_events)},
        {"Metric": "Common Numbers", "Value": len(common_numbers)},
        {"Metric": "Direct Target Links", "Value": len(direct_links)},
        {"Metric": "Common Towers", "Value": len(common_towers)},
        {"Metric": "Common IMEIs", "Value": len(common_imeis)},
        {"Metric": "Common IMSIs", "Value": len(common_imsis)},
        {"Metric": "Minimum Targets Threshold", "Value": min_targets},
    ], columns=RESULT_COLUMNS["summary"])

    result.update({
        "summary": summary,
        "target_overview": target_overview,
        "common_numbers": common_numbers,
        "direct_target_links": direct_links,
        "common_towers": common_towers,
        "common_imeis": common_imeis,
        "common_imsis": common_imsis,
        "contact_matrix": contact_matrix,
        "tower_matrix": tower_matrix,
        "imei_matrix": imei_matrix,
        "imsi_matrix": imsi_matrix,
        "source_files": source_files,
        "common_contact_map": common_contact_map,
        "movement_route_events": movement_route_events,
        "alerts": _alerts(common_numbers, direct_links, common_towers, common_imeis, common_imsis),
        "errors": pd.DataFrame(errors, columns=RESULT_COLUMNS["errors"]),
    })
    return result
