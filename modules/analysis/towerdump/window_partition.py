"""Date-time and CGI-scoped logical partitioning for normalized Tower Dump data."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

import pandas as pd

from modules.analysis.partition_scope import (
    infer_active_cell_scope,
    loaded_cell_map,
)

from modules.analysis.common.uncommon_numbers import (
    find_uncommon_numbers,
)
from modules.analysis.towerdump.uncommon_presence import (
    TOWER_CDR_UNCOMMON_CONFIG,
)


CELL_COLUMNS = (
    "searched_cell_id",
    "first_cell_id",
    "last_cell_id",
)


def _clean_text(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .replace({"nan": "", "None": "", "<NA>": ""})
    )


def _cell_key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value).strip().upper())


def _group_map(
    cgi_groups: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        str(group.get("group_id", "")).strip().upper(): group
        for group in cgi_groups
        if isinstance(group, dict) and group.get("group_id")
    }


def _filter_one_sighting(
    df: pd.DataFrame,
    sighting: dict[str, Any],
    cgi_group: dict[str, Any],
) -> pd.DataFrame:
    if "call_datetime" not in df.columns:
        return pd.DataFrame(columns=df.columns)

    datetimes = pd.to_datetime(df["call_datetime"], errors="coerce")
    window_start = pd.to_datetime(sighting.get("window_start"), errors="coerce")
    window_end = pd.to_datetime(sighting.get("window_end"), errors="coerce")

    if pd.isna(window_start) or pd.isna(window_end):
        return pd.DataFrame(columns=df.columns)

    # Half-open range prevents one boundary event from appearing
    # in two adjoining partitions:
    #     window_start <= event_time < window_end
    mask = datetimes.between(
        window_start,
        window_end,
        inclusive="left",
    )

    cgi_keys = {
        _cell_key(value)
        for value in cgi_group.get("cgi_values", [])
        if _cell_key(value)
    }

    if cgi_keys:
        cell_mask = pd.Series(False, index=df.index)

        match_columns = tuple(
            cgi_group.get("match_columns")
            or CELL_COLUMNS
        )

        for column in match_columns:
            if column not in df.columns:
                continue

            keys = _clean_text(df[column]).map(_cell_key)
            cell_mask = cell_mask | keys.isin(cgi_keys)

        mask = mask & cell_mask

    filtered = df.loc[mask].copy()

    if filtered.empty:
        return filtered

    filtered.insert(0, "partition_sighting_id", sighting.get("sighting_id", ""))
    filtered.insert(1, "partition_location", sighting.get("location_name", ""))
    filtered.insert(2, "partition_window_start", sighting.get("window_start", ""))
    filtered.insert(3, "partition_window_end", sighting.get("window_end", ""))
    filtered.insert(4, "partition_cgi_group_id", sighting.get("cgi_group_id", ""))

    return filtered.reset_index(drop=False).rename(
        columns={"index": "source_row_index"}
    )


def _entity_presence(
    partitions: dict[str, pd.DataFrame],
    sightings: list[dict[str, Any]],
    entity_column: str,
) -> pd.DataFrame:
    total_sightings = len(sightings)
    sighting_ids = [
        str(item.get("sighting_id", ""))
        for item in sightings
    ]

    aggregate: dict[str, dict[str, Any]] = {}

    for sighting in sightings:
        sighting_id = str(sighting.get("sighting_id", ""))
        location = str(sighting.get("location_name", ""))
        part = partitions.get(sighting_id, pd.DataFrame())

        if part.empty or entity_column not in part.columns:
            continue

        values = _clean_text(part[entity_column])
        valid = part.loc[values.ne("")].copy()

        if valid.empty:
            continue

        valid["_entity"] = values.loc[values.ne("")]

        for entity, group in valid.groupby("_entity", sort=False):
            item = aggregate.setdefault(
                entity,
                {
                    "entity": entity,
                    "match_count": 0,
                    "matched_sightings": [],
                    "matched_locations": [],
                    "total_events": 0,
                    "operators": set(),
                    "first_seen": pd.NaT,
                    "last_seen": pd.NaT,
                },
            )

            item["match_count"] += 1
            item["matched_sightings"].append(sighting_id)
            item["matched_locations"].append(location)
            item["total_events"] += len(group)

            if "operator" in group.columns:
                item["operators"].update(
                    value
                    for value in _clean_text(group["operator"]).unique()
                    if value
                )

            if "call_datetime" in group.columns:
                dt = pd.to_datetime(group["call_datetime"], errors="coerce")
                if dt.notna().any():
                    first = dt.min()
                    last = dt.max()
                    if pd.isna(item["first_seen"]) or first < item["first_seen"]:
                        item["first_seen"] = first
                    if pd.isna(item["last_seen"]) or last > item["last_seen"]:
                        item["last_seen"] = last

    rows = []

    for item in aggregate.values():
        row = {
            entity_column: item["entity"],
            "match_count": item["match_count"],
            "total_sightings": total_sightings,
            "match_ratio": f"{item['match_count']}/{total_sightings}",
            "matched_sightings": ", ".join(item["matched_sightings"]),
            "matched_locations": ", ".join(item["matched_locations"]),
            "total_events": item["total_events"],
            "operators": ", ".join(sorted(item["operators"])),
            "first_seen": item["first_seen"],
            "last_seen": item["last_seen"],
        }

        matched = set(item["matched_sightings"])
        for sighting_id in sighting_ids:
            row[sighting_id] = 1 if sighting_id in matched else 0

        rows.append(row)

    if not rows:
        columns = [
            entity_column,
            "match_count",
            "total_sightings",
            "match_ratio",
            "matched_sightings",
            "matched_locations",
            "total_events",
            "operators",
            "first_seen",
            "last_seen",
            *sighting_ids,
        ]
        return pd.DataFrame(columns=columns)

    return pd.DataFrame(rows).sort_values(
        ["match_count", "total_events", entity_column],
        ascending=[False, False, True],
        ignore_index=True,
    )



# PARTITION_VISITOR_INTELLIGENCE_HELPERS

PARTITION_VISITOR_COLUMNS = [
    "partition_id",
    "partition_location",
    "partition_window_start",
    "partition_window_end",
    "partition_cgi_group_id",
    "scope_mode",
    "scope_confidence",
    "location_confirmed",
    "scope_basis",
    "resolved_cell_count",
    "resolved_cells",
    "loaded_cell_count",
    "subscriber_number",
    "visitor_type",
    "current_seen_count",
    "baseline_seen_count",
    "cells_seen",
    "imei_count",
    "imsi_count",
    "first_seen",
    "last_seen",
    "rarity_score",
    "priority",
    "confidence",
    "multi_cell_relevant",
    "why_important",
    "next_verification",
]


def _filter_cgi_scope(
    dataframe: pd.DataFrame,
    cgi_group: dict[str, Any],
) -> pd.DataFrame:
    """Return all records belonging to the resolved CGI scope.

    Time is deliberately not filtered here because the returned data
    is divided into current and baseline periods later.
    """

    if dataframe is None or dataframe.empty:
        return pd.DataFrame(columns=getattr(dataframe, "columns", []))

    cgi_keys = {
        _cell_key(value)
        for value in cgi_group.get("cgi_values", [])
        if _cell_key(value)
    }

    # AUTO_ALL / time-only mode uses all loaded cells.
    if not cgi_keys:
        return dataframe.copy()

    scope_mask = pd.Series(
        False,
        index=dataframe.index,
    )

    match_columns = tuple(
        cgi_group.get("match_columns")
        or CELL_COLUMNS
    )

    for column in match_columns:
        if column not in dataframe.columns:
            continue

        keys = _clean_text(
            dataframe[column]
        ).map(_cell_key)

        scope_mask = scope_mask | keys.isin(cgi_keys)

    return dataframe.loc[scope_mask].copy()


def _visitor_type(row: pd.Series) -> str:
    current_count = int(
        row.get("current_seen_count", 0) or 0
    )
    baseline_count = int(
        row.get("baseline_seen_count", 0) or 0
    )

    if baseline_count == 0:
        return "NEW VISITOR"

    if baseline_count <= 2 and current_count >= 2:
        return "RARE REPEAT VISITOR"

    if baseline_count <= 2:
        return "RARE VISITOR"

    if baseline_count <= 5 and current_count >= 2:
        return "REPEAT RELEVANT VISITOR"

    return "REGULAR / LOCAL PRESENCE"


def _visitor_confidence(row: pd.Series) -> str:
    current_count = int(
        row.get("current_seen_count", 0) or 0
    )
    baseline_count = int(
        row.get("baseline_seen_count", 0) or 0
    )
    cells_seen = int(
        row.get("cells_seen", 0) or 0
    )

    if (
        current_count >= 2
        and (
            baseline_count <= 2
            or cells_seen >= 2
        )
    ):
        return "HIGH"

    if (
        current_count >= 2
        or baseline_count <= 2
        or cells_seen >= 2
    ):
        return "MEDIUM"

    return "LOW"


def _visitor_priority(row: pd.Series) -> str:
    """Assign investigation priority for one partition visitor."""

    visitor_type = str(
        row.get("visitor_type", "")
    ).strip()

    current_count = int(
        row.get("current_seen_count", 0) or 0
    )

    cells_seen = int(
        row.get("cells_seen", 0) or 0
    )

    imei_count = int(
        row.get("imei_count", 0) or 0
    )

    imsi_count = int(
        row.get("imsi_count", 0) or 0
    )

    device_change = (
        imei_count >= 2
        or imsi_count >= 2
    )

    if visitor_type == "NEW VISITOR":
        if (
            current_count >= 2
            or cells_seen >= 2
            or device_change
        ):
            return "HIGH"

        return "MEDIUM"

    if visitor_type == "RARE REPEAT VISITOR":
        if (
            current_count >= 2
            or cells_seen >= 2
            or device_change
        ):
            return "HIGH"

        return "MEDIUM"

    if visitor_type == "REPEAT RELEVANT VISITOR":
        if (
            cells_seen >= 2
            or device_change
        ):
            return "HIGH"

        return "MEDIUM"

    if visitor_type == "RARE VISITOR":
        if (
            cells_seen >= 2
            or device_change
        ):
            return "HIGH"

        return "MEDIUM"

    if (
        cells_seen >= 2
        or device_change
    ):
        return "MEDIUM"

    return "LOW"


def _visitor_reason(row: pd.Series) -> str:
    visitor_type = str(
        row.get("visitor_type", "")
    ).strip()

    cells_seen = int(
        row.get("cells_seen", 0) or 0
    )
    imei_count = int(
        row.get("imei_count", 0) or 0
    )
    imsi_count = int(
        row.get("imsi_count", 0) or 0
    )

    reasons: list[str] = []

    if visitor_type == "NEW VISITOR":
        reasons.append(
            "Same CGI scope ke earlier/later baseline "
            "records mein nahi mila"
        )

    elif visitor_type in {
        "RARE VISITOR",
        "RARE REPEAT VISITOR",
    }:
        reasons.append(
            "Same CGI scope ke baseline mein bahut kam presence"
        )

    elif visitor_type == "REPEAT RELEVANT VISITOR":
        reasons.append(
            "Baseline presence kam thi, lekin selected "
            "partition mein repeat activity mili"
        )

    else:
        reasons.append(
            "Baseline mein regular presence mili; "
            "new visitor nahi hai"
        )

    if cells_seen >= 2:
        reasons.append(
            "selected period mein multiple cells par presence"
        )

    if imei_count >= 2:
        reasons.append(
            "multiple IMEI observed"
        )

    if imsi_count >= 2:
        reasons.append(
            "multiple IMSI observed"
        )

    return "; ".join(reasons)


def _normalise_partition_visitor_table(
    dataframe: pd.DataFrame,
    *,
    sighting: dict[str, Any],
) -> pd.DataFrame:
    if dataframe is None or dataframe.empty:
        return pd.DataFrame(
            columns=PARTITION_VISITOR_COLUMNS
        )

    output = dataframe.copy()

    if (
        "subscriber_number" not in output.columns
        and "entity" in output.columns
    ):
        output = output.rename(
            columns={
                "entity": "subscriber_number",
            }
        )

    for column in [
        "current_seen_count",
        "baseline_seen_count",
        "cells_seen",
        "imei_count",
        "imsi_count",
        "rarity_score",
    ]:
        if column not in output.columns:
            output[column] = 0

        output[column] = (
            pd.to_numeric(
                output[column],
                errors="coerce",
            )
            .fillna(0)
            .astype(int)
        )

    scope_values = {
        "scope_mode": str(
            sighting.get("scope_mode", "")
        ),
        "scope_confidence": str(
            sighting.get("scope_confidence", "")
        ),
        "location_confirmed": str(
            sighting.get("location_confirmed", "NO")
        ),
        "scope_basis": str(
            sighting.get("scope_basis", "")
        ),
        "resolved_cell_count": int(
            sighting.get("resolved_cell_count", 0) or 0
        ),
        "resolved_cells": str(
            sighting.get("resolved_cells", "")
        ),
        "loaded_cell_count": int(
            sighting.get("loaded_cell_count", 0) or 0
        ),
    }

    for column, value in scope_values.items():
        output[column] = value

    output["visitor_type"] = output.apply(
        _visitor_type,
        axis=1,
    )

    output["confidence"] = output.apply(
        _visitor_confidence,
        axis=1,
    )

    output["multi_cell_relevant"] = (
        output["cells_seen"]
        .ge(2)
        .map({
            True: "YES",
            False: "NO",
        })
    )

    output["priority"] = output.apply(
        _visitor_priority,
        axis=1,
    )

    output["why_important"] = output.apply(
        _visitor_reason,
        axis=1,
    )

    output["next_verification"] = (
        "Verify SDR/CAF identity, IMEI/IMSI continuity, "
        "call context, tower coverage and local/field information."
    )

    output.insert(
        0,
        "partition_cgi_group_id",
        str(
            sighting.get(
                "cgi_group_id",
                "",
            )
        ),
    )

    output.insert(
        0,
        "partition_window_end",
        sighting.get(
            "window_end",
            "",
        ),
    )

    output.insert(
        0,
        "partition_window_start",
        sighting.get(
            "window_start",
            "",
        ),
    )

    output.insert(
        0,
        "partition_location",
        str(
            sighting.get(
                "location_name",
                "",
            )
        ),
    )

    output.insert(
        0,
        "partition_id",
        str(
            sighting.get(
                "sighting_id",
                "",
            )
        ),
    )

    for column in PARTITION_VISITOR_COLUMNS:
        if column not in output.columns:
            output[column] = ""

    extra_columns = [
        column
        for column in output.columns
        if column not in PARTITION_VISITOR_COLUMNS
    ]

    output = output[
        PARTITION_VISITOR_COLUMNS
        + extra_columns
    ]

    sort_columns = [
        column
        for column in [
            "rarity_score",
            "current_seen_count",
            "cells_seen",
            "subscriber_number",
        ]
        if column in output.columns
    ]

    ascending = [
        False
        if column != "subscriber_number"
        else True
        for column in sort_columns
    ]

    if sort_columns:
        output = output.sort_values(
            sort_columns,
            ascending=ascending,
            ignore_index=True,
        )

    return output


def _build_partition_visitor_intelligence(
    dataframe: pd.DataFrame,
    *,
    sighting: dict[str, Any],
    cgi_group: dict[str, Any],
) -> pd.DataFrame:
    """Compare one partition with the same CGI scope outside its time range."""

    if (
        dataframe is None
        or dataframe.empty
        or "call_datetime" not in dataframe.columns
    ):
        return pd.DataFrame(
            columns=PARTITION_VISITOR_COLUMNS
        )

    window_start = pd.to_datetime(
        sighting.get("window_start"),
        errors="coerce",
    )

    window_end = pd.to_datetime(
        sighting.get("window_end"),
        errors="coerce",
    )

    if (
        pd.isna(window_start)
        or pd.isna(window_end)
        or window_start >= window_end
    ):
        return pd.DataFrame(
            columns=PARTITION_VISITOR_COLUMNS
        )

    scoped = _filter_cgi_scope(
        dataframe,
        cgi_group,
    )

    if scoped.empty:
        return pd.DataFrame(
            columns=PARTITION_VISITOR_COLUMNS
        )

    datetimes = pd.to_datetime(
        scoped["call_datetime"],
        errors="coerce",
    )

    current_mask = (
        datetimes.ge(window_start)
        & datetimes.lt(window_end)
    )

    valid_time_mask = datetimes.notna()

    current = scoped.loc[
        current_mask
    ].copy()

    baseline = scoped.loc[
        valid_time_mask
        & ~current_mask
    ].copy()

    comparison = find_uncommon_numbers(
        current,
        baseline,
        config=TOWER_CDR_UNCOMMON_CONFIG,
        min_score=0,
    )

    return _normalise_partition_visitor_table(
        comparison,
        sighting=sighting,
    )


def _combine_partition_visitor_tables(
    tables: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    usable = [
        dataframe
        for dataframe in tables.values()
        if isinstance(dataframe, pd.DataFrame)
        and not dataframe.empty
    ]

    if not usable:
        return pd.DataFrame(
            columns=PARTITION_VISITOR_COLUMNS
        )

    return pd.concat(
        usable,
        ignore_index=True,
        sort=False,
    )


def create_sighting_partitions(
    df: pd.DataFrame,
    *,
    sightings: list[dict[str, Any]],
    cgi_groups: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create logical partitions using only successfully validated sightings."""

    if not isinstance(df, pd.DataFrame):
        raise TypeError("Tower Dump DataFrame required hai.")

    groups = _group_map(cgi_groups)
    ordered_sightings = sorted(
        [
            item
            for item in sightings
            if isinstance(item, dict)
        ],
        key=lambda item: (
            (
                int(item.get("partition_order"))
                if str(
                    item.get(
                        "partition_order",
                        "",
                    )
                ).isdigit()
                else 10**9
            ),
            str(item.get("window_start", "")),
            str(item.get("sighting_id", "")),
        ),
    )

    partitions: dict[str, pd.DataFrame] = {}
    partition_visitor_tables: dict[str, pd.DataFrame] = {}
    summary_rows: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    valid_sightings: list[dict[str, Any]] = []
    warnings: list[str] = []
    loaded_cells = loaded_cell_map(
        df,
        "searched_cell_id",
    )
    loaded_cell_keys = set(loaded_cells)

    for sighting in ordered_sightings:
        sighting_id = str(sighting.get("sighting_id", "")).strip()
        group_id = str(sighting.get("cgi_group_id", "")).strip().upper()
        base_status = {
            "sighting_id": sighting_id,
            "location_name": sighting.get("location_name", ""),
            "cctv_timestamp": sighting.get("cctv_timestamp", ""),
            "window_start": sighting.get("window_start", ""),
            "window_end": sighting.get("window_end", ""),
            "cgi_group_id": group_id,
        }

        if not sighting_id:
            status_rows.append({**base_status, "status": "INVALID_SIGHTING_ID", "included": False, "message": "Sighting ID missing hai."})
            continue

        configured_sources = {
            str(value).strip().upper()
            for value in sighting.get("source_types", [])
            if str(value).strip()
        }
        if configured_sources and "NORMAL_CDR" not in configured_sources:
            status_rows.append({**base_status, "status": "SOURCE_TYPE_NOT_SELECTED", "included": False, "message": "Sighting source_types mein NORMAL_CDR selected nahi hai."})
            continue

        start_time = pd.to_datetime(sighting.get("window_start"), errors="coerce")
        end_time = pd.to_datetime(sighting.get("window_end"), errors="coerce")
        if pd.isna(start_time) or pd.isna(end_time) or start_time >= end_time:
            status_rows.append({**base_status, "status": "INVALID_TIME_WINDOW", "included": False, "message": "Window start/end invalid hai."})
            continue

        if group_id in {
            "",
            "AUTO",
            "AUTO_ALL",
            "AUTO_ACTIVE",
        }:
            scope = infer_active_cell_scope(
                df,
                window_start=start_time,
                window_end=end_time,
                loaded_cells=loaded_cells,
                time_column="call_datetime",
                cell_column="searched_cell_id",
            )

            if not scope.get("valid"):
                status_rows.append(
                    {
                        **base_status,
                        "cgi_group_id": "AUTO_ACTIVE",
                        "status": scope.get(
                            "status",
                            "INVALID_AUTO_SCOPE",
                        ),
                        "included": False,
                        "scope_mode": scope.get(
                            "scope_mode",
                            "INVALID",
                        ),
                        "scope_confidence": scope.get(
                            "scope_confidence",
                            "LOW",
                        ),
                        "location_confirmed": "NO",
                        "scope_basis": scope.get(
                            "scope_basis",
                            "",
                        ),
                        "message": scope.get(
                            "message",
                            "Automatic CGI scope resolve nahi hua.",
                        ),
                    }
                )
                continue

            group_id = str(
                scope.get(
                    "group_id",
                    "AUTO_ACTIVE",
                )
            )

            scope_mode = str(
                scope.get(
                    "scope_mode",
                    "AUTO_ACTIVE_CELLS",
                )
            )

            scope_confidence = str(
                scope.get(
                    "scope_confidence",
                    "LOW",
                )
            )

            location_confirmed = False

            scope_basis = str(
                scope.get(
                    "scope_basis",
                    "",
                )
            )

            resolved_cells = list(
                scope.get(
                    "cell_values",
                    [],
                )
            )

            loaded_cell_count = int(
                scope.get(
                    "loaded_cell_count",
                    len(loaded_cells),
                )
                or 0
            )

            group = {
                "group_id": group_id,
                "group_name": (
                    "Automatically Active Searched Cells"
                ),
                "cgi_values": resolved_cells,
                # Inferred values came from searched_cell_id,
                # therefore matching must remain on that column.
                "match_columns": ["searched_cell_id"],
            }

            status_name = str(
                scope.get(
                    "status",
                    "VALID_AUTO_ACTIVE_CELLS",
                )
            )

            warnings.append(
                f"{sighting_id}: {scope_confidence} scope confidence. "
                f"{scope_basis} "
                "Location independently confirmed nahi hai."
            )

        else:
            group = groups.get(group_id)

            if group is None:
                status_rows.append(
                    {
                        **base_status,
                        "status": "INVALID_CGI_GROUP",
                        "included": False,
                        "message": (
                            f"CGI group not found: {group_id}"
                        ),
                    }
                )
                continue

            configured_keys = {
                _cell_key(value)
                for value in group.get("cgi_values", [])
                if _cell_key(value)
            }

            matched_keys = configured_keys.intersection(
                loaded_cell_keys
            )

            if not configured_keys:
                status_rows.append(
                    {
                        **base_status,
                        "status": "EMPTY_CGI_GROUP",
                        "included": False,
                        "message": (
                            f"CGI group {group_id} mein "
                            "usable Cell ID nahi hai."
                        ),
                    }
                )
                continue

            if not matched_keys:
                status_rows.append(
                    {
                        **base_status,
                        "status": "NO_MATCHING_LOADED_CGI",
                        "included": False,
                        "message": (
                            f"CGI group {group_id} ka koi "
                            "Cell ID loaded data mein nahi mila."
                        ),
                    }
                )
                continue

            resolved_cells = sorted(
                loaded_cells[key]
                for key in matched_keys
            )

            group = {
                **group,
                "cgi_values": resolved_cells,
                "match_columns": list(CELL_COLUMNS),
            }

            scope_mode = "LOCATION_SCOPED"
            scope_confidence = "HIGH"
            location_confirmed = True
            scope_basis = (
                "Configured CGI group matched "
                "loaded searched cells."
            )
            loaded_cell_count = len(loaded_cells)
            status_name = "VALID_LOCATION_SCOPED"

        effective_sighting = dict(sighting)
        effective_sighting["cgi_group_id"] = group_id
        effective_sighting["scope_mode"] = scope_mode
        effective_sighting["scope_confidence"] = (
            scope_confidence
        )
        effective_sighting["location_confirmed"] = (
            "YES"
            if location_confirmed
            else "NO"
        )
        effective_sighting["scope_basis"] = scope_basis
        effective_sighting["resolved_cell_count"] = len(
            resolved_cells
        )
        effective_sighting["resolved_cells"] = ", ".join(
            map(str, resolved_cells)
        )
        effective_sighting["loaded_cell_count"] = (
            loaded_cell_count
        )

        part = _filter_one_sighting(
            df,
            effective_sighting,
            group,
        )
        partitions[sighting_id] = part

        partition_visitor_tables[sighting_id] = (
            _build_partition_visitor_intelligence(
                df,
                sighting=effective_sighting,
                cgi_group=group,
            )
        )

        valid_record = dict(effective_sighting)
        valid_sightings.append(valid_record)
        status_rows.append(
            {
                **base_status,
                "cgi_group_id": group_id,
                "status": status_name,
                "included": True,
                "scope_mode": scope_mode,
                "scope_confidence": scope_confidence,
                "location_confirmed": (
                    "YES"
                    if location_confirmed
                    else "NO"
                ),
                "scope_basis": scope_basis,
                "loaded_cell_count": loaded_cell_count,
                "resolved_cgi_count": len(
                    resolved_cells
                ),
                "resolved_cgi_values": ", ".join(
                    map(str, resolved_cells)
                ),
                "message": (
                    "Configured CGI scope applied."
                    if location_confirmed
                    else (
                        "Active searched cells automatically "
                        "selected; location independently "
                        "confirmed nahi hai."
                    )
                ),
            }
        )


        subscriber_count = (
            _clean_text(part["subscriber_number"]).replace("", pd.NA).nunique(dropna=True)
            if "subscriber_number" in part.columns else 0
        )
        imei_count = (
            _clean_text(part["imei"]).replace("", pd.NA).nunique(dropna=True)
            if "imei" in part.columns else 0
        )
        imsi_count = (
            _clean_text(part["imsi"]).replace("", pd.NA).nunique(dropna=True)
            if "imsi" in part.columns else 0
        )
        summary_rows.append(
            {
                "sighting_id": sighting_id,
                "location_name": sighting.get("location_name", ""),
                "cctv_timestamp": sighting.get("cctv_timestamp", ""),
                "window_start": sighting.get("window_start", ""),
                "window_end": sighting.get("window_end", ""),
                "cgi_group_id": group_id,
                "scope_mode": scope_mode,
                "scope_confidence": scope_confidence,
                "location_confirmed": (
                    "YES"
                    if location_confirmed
                    else "NO"
                ),
                "scope_basis": scope_basis,
                "loaded_cell_count": loaded_cell_count,
                "cgi_count": len(resolved_cells),
                "resolved_cgi_values": ", ".join(
                    map(str, resolved_cells)
                ),
                "filtered_records": len(part),
                "unique_subscribers": int(subscriber_count),
                "unique_imei": int(imei_count),
                "unique_imsi": int(imsi_count),
                "unique_searched_cells": int(
                    _clean_text(part["searched_cell_id"]).replace("", pd.NA).nunique(dropna=True)
                    if "searched_cell_id" in part.columns else 0
                ),
            }
        )

    partition_visitor_intelligence = (
        _combine_partition_visitor_tables(
            partition_visitor_tables
        )
    )

    new_visitors = partition_visitor_intelligence.loc[
        partition_visitor_intelligence["visitor_type"]
        .eq("NEW VISITOR")
    ].reset_index(drop=True)

    rare_visitors = partition_visitor_intelligence.loc[
        partition_visitor_intelligence["visitor_type"].isin(
            [
                "RARE VISITOR",
                "RARE REPEAT VISITOR",
            ]
        )
    ].reset_index(drop=True)

    repeat_relevant_visitors = partition_visitor_intelligence.loc[
        partition_visitor_intelligence["visitor_type"]
        .eq("REPEAT RELEVANT VISITOR")
    ].reset_index(drop=True)

    regular_local_presence = partition_visitor_intelligence.loc[
        partition_visitor_intelligence["visitor_type"]
        .eq("REGULAR / LOCAL PRESENCE")
    ].reset_index(drop=True)

    multi_cell_relevant = partition_visitor_intelligence.loc[
        partition_visitor_intelligence["multi_cell_relevant"]
        .eq("YES")
    ].reset_index(drop=True)

    # MEANINGFUL_PARTITION_PRIORITY_LEADS
    priority_leads = (
        partition_visitor_intelligence.loc[
            partition_visitor_intelligence["priority"].isin(
                [
                    "HIGH",
                    "MEDIUM",
                ]
            )
        ]
        .sort_values(
            [
                "rarity_score",
                "current_seen_count",
                "cells_seen",
            ],
            ascending=[
                False,
                False,
                False,
            ],
            ignore_index=True,
        )
    )

    subscriber_presence = _entity_presence(partitions, valid_sightings, "subscriber_number")
    imei_presence = _entity_presence(partitions, valid_sightings, "imei")
    imsi_presence = _entity_presence(partitions, valid_sightings, "imsi")
    total_sightings = len(valid_sightings)
    minimum = 1 if total_sightings <= 1 else 2
    n_of_m = (
        subscriber_presence.loc[subscriber_presence["match_count"] >= minimum].reset_index(drop=True)
        if not subscriber_presence.empty else subscriber_presence.copy()
    )
    strict_common = (
        subscriber_presence.loc[subscriber_presence["match_count"] == total_sightings].reset_index(drop=True)
        if total_sightings > 0 and not subscriber_presence.empty
        else subscriber_presence.head(0).copy()
    )

    return {
        "partitions": partitions,
        "partition_visitor_tables": partition_visitor_tables,
        "partition_visitor_intelligence": partition_visitor_intelligence,
        "new_visitors": new_visitors,
        "rare_visitors": rare_visitors,
        "repeat_relevant_visitors": repeat_relevant_visitors,
        "regular_local_presence": regular_local_presence,
        "multi_cell_relevant": multi_cell_relevant,
        "partition_priority_leads": priority_leads,
        "partition_summary": pd.DataFrame(summary_rows),
        "partition_status": pd.DataFrame(status_rows),
        "subscriber_presence": subscriber_presence,
        "n_of_m_candidates": n_of_m,
        "strict_common_candidates": strict_common,
        "imei_presence": imei_presence,
        "imsi_presence": imsi_presence,
        "total_sightings": total_sightings,
        "total_configured_sightings": len(ordered_sightings),
        "total_input_records": len(df),
        "warnings": warnings,
    }
