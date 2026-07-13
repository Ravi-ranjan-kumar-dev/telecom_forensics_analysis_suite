"""CCTV time-window based logical partitioning for normalized Tower Dump data."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

import pandas as pd


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

    mask = datetimes.between(window_start, window_end, inclusive="both")

    cgi_keys = {
        _cell_key(value)
        for value in cgi_group.get("cgi_values", [])
        if _cell_key(value)
    }

    if cgi_keys:
        cell_mask = pd.Series(False, index=df.index)

        for column in CELL_COLUMNS:
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
        [item for item in sightings if isinstance(item, dict)],
        key=lambda item: (
            str(item.get("cctv_timestamp", "")),
            str(item.get("sighting_id", "")),
        ),
    )

    partitions: dict[str, pd.DataFrame] = {}
    summary_rows: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    valid_sightings: list[dict[str, Any]] = []
    warnings: list[str] = []
    loaded_cell_keys = {
        _cell_key(value)
        for column in CELL_COLUMNS
        if column in df.columns
        for value in _clean_text(df[column])
        if _cell_key(value)
    }

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
        if pd.isna(start_time) or pd.isna(end_time) or start_time > end_time:
            status_rows.append({**base_status, "status": "INVALID_TIME_WINDOW", "included": False, "message": "Window start/end invalid hai."})
            continue

        if group_id in {"", "AUTO", "AUTO_ALL"}:
            group = {
                "group_id": "AUTO_ALL",
                "group_name": "All Loaded Dump CGI",
                "cgi_values": [],
            }
            group_id = "AUTO_ALL"
            warnings.append(
                f"{sighting_id}: TIME_ONLY_ALL_CELLS exploratory mode; "
                "location-confirmed result nahi hai."
            )
            status_name = "VALID_TIME_ONLY_ALL_CELLS"
        else:
            group = groups.get(group_id)
            if group is None:
                status_rows.append({**base_status, "status": "INVALID_CGI_GROUP", "included": False, "message": f"CGI group not found: {group_id}"})
                continue
            configured_keys = {
                _cell_key(value)
                for value in group.get("cgi_values", [])
                if _cell_key(value)
            }
            matched_keys = configured_keys.intersection(loaded_cell_keys)
            if not configured_keys:
                status_rows.append({**base_status, "status": "EMPTY_CGI_GROUP", "included": False, "message": f"CGI group {group_id} mein usable Cell ID nahi hai."})
                continue
            if not matched_keys:
                status_rows.append({**base_status, "status": "NO_MATCHING_LOADED_CGI", "included": False, "message": f"CGI group {group_id} ka koi Cell ID loaded data mein nahi mila."})
                continue
            group = {**group, "cgi_values": sorted(matched_keys)}
            status_name = "VALID_LOCATION_SCOPED"

        part = _filter_one_sighting(df, sighting, group)
        partitions[sighting_id] = part
        valid_record = dict(sighting)
        valid_record["cgi_group_id"] = group_id
        valid_sightings.append(valid_record)
        status_rows.append(
            {
                **base_status,
                "cgi_group_id": group_id,
                "status": status_name,
                "included": True,
                "resolved_cgi_count": len(group.get("cgi_values", [])),
                "resolved_cgi_values": ", ".join(map(str, group.get("cgi_values", []))),
                "message": (
                    "Time-only all loaded cells applied."
                    if group_id == "AUTO_ALL"
                    else "Time window and resolved CGI group both applied."
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
                "scope_mode": "TIME_ONLY_ALL_CELLS" if group_id == "AUTO_ALL" else "LOCATION_SCOPED",
                "cgi_count": len(group.get("cgi_values", [])),
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
