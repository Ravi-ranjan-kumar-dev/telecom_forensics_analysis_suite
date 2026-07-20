"""Shared date-time partition and CGI-scope resolution for dump analysis engines."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


def clean_text(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .replace({"nan": "", "None": "", "<NA>": ""})
    )


def cell_key(value: Any) -> str:
    """Canonical comparison key while preserving raw CGI values elsewhere."""

    return re.sub(r"[^A-Z0-9]", "", str(value or "").strip().upper())


def group_map(cgi_groups: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    return {
        str(group.get("group_id", "")).strip().upper(): group
        for group in (cgi_groups or [])
        if isinstance(group, dict) and str(group.get("group_id", "")).strip()
    }


def loaded_cell_map(df: pd.DataFrame, column: str = "searched_cell_id") -> dict[str, str]:
    if column not in df.columns:
        return {}

    output: dict[str, str] = {}
    for raw in clean_text(df[column]):
        key = cell_key(raw)
        if key and key not in output:
            output[key] = raw
    return output


def infer_active_cell_scope(
    df: pd.DataFrame,
    *,
    window_start: Any,
    window_end: Any,
    loaded_cells: dict[str, str] | None = None,
    time_column: str = "call_datetime",
    cell_column: str = "searched_cell_id",
) -> dict[str, Any]:
    """Infer searched cells active inside one Date-Time Part.

    Important:
    - Highest-count cell ko automatically single location nahi maana jata.
    - Part ke sabhi active searched cells preserve kiye jate hain.
    """

    if not isinstance(df, pd.DataFrame):
        return {
            "valid": False,
            "status": "INVALID_DATAFRAME",
            "scope_mode": "INVALID",
            "group_id": "AUTO_ACTIVE",
            "cell_keys": set(),
            "cell_values": [],
            "scope_confidence": "LOW",
            "location_confirmed": False,
            "scope_basis": "Valid Tower Dump DataFrame available nahi hai.",
            "loaded_cell_count": 0,
            "resolved_cell_count": 0,
            "message": "Automatic CGI scope resolve nahi hua.",
        }

    resolved_loaded_cells = (
        dict(loaded_cells)
        if loaded_cells is not None
        else loaded_cell_map(df, cell_column)
    )

    loaded_count = len(resolved_loaded_cells)

    if time_column not in df.columns:
        return {
            "valid": False,
            "status": "MISSING_TIME_COLUMN",
            "scope_mode": "INVALID",
            "group_id": "AUTO_ACTIVE",
            "cell_keys": set(),
            "cell_values": [],
            "scope_confidence": "LOW",
            "location_confirmed": False,
            "scope_basis": f"Missing column: {time_column}",
            "loaded_cell_count": loaded_count,
            "resolved_cell_count": 0,
            "message": "Event Date-Time column missing hai.",
        }

    if cell_column not in df.columns:
        return {
            "valid": False,
            "status": "MISSING_SEARCHED_CELL_COLUMN",
            "scope_mode": "INVALID",
            "group_id": "AUTO_ACTIVE",
            "cell_keys": set(),
            "cell_values": [],
            "scope_confidence": "LOW",
            "location_confirmed": False,
            "scope_basis": f"Missing column: {cell_column}",
            "loaded_cell_count": loaded_count,
            "resolved_cell_count": 0,
            "message": "Searched Cell ID column missing hai.",
        }

    start_time = pd.to_datetime(
        window_start,
        errors="coerce",
    )
    end_time = pd.to_datetime(
        window_end,
        errors="coerce",
    )

    if (
        pd.isna(start_time)
        or pd.isna(end_time)
        or start_time >= end_time
    ):
        return {
            "valid": False,
            "status": "INVALID_TIME_WINDOW",
            "scope_mode": "INVALID",
            "group_id": "AUTO_ACTIVE",
            "cell_keys": set(),
            "cell_values": [],
            "scope_confidence": "LOW",
            "location_confirmed": False,
            "scope_basis": "Invalid Start/End Date-Time range",
            "loaded_cell_count": loaded_count,
            "resolved_cell_count": 0,
            "message": "Valid Start aur End Date-Time required hai.",
        }

    datetimes = pd.to_datetime(
        df[time_column],
        errors="coerce",
    )

    time_mask = (
        datetimes.ge(start_time)
        & datetimes.lt(end_time)
    )

    active_frame = df.loc[time_mask]
    active_cells = loaded_cell_map(
        active_frame,
        cell_column,
    )

    active_keys = set(active_cells)
    active_values = sorted(active_cells.values())
    active_count = len(active_keys)

    if active_count == 0:
        return {
            "valid": False,
            "status": "NO_ACTIVE_SEARCHED_CELLS",
            "scope_mode": "AUTO_ACTIVE_CELLS",
            "group_id": "AUTO_ACTIVE",
            "cell_keys": set(),
            "cell_values": [],
            "scope_confidence": "LOW",
            "location_confirmed": False,
            "scope_basis": (
                "Selected Date-Time Part mein searched-cell "
                "activity nahi mili."
            ),
            "loaded_cell_count": loaded_count,
            "resolved_cell_count": 0,
            "message": (
                "Selected Date-Time Part mein active "
                "searched Cell ID nahi mila."
            ),
        }

    if active_count == 1:
        confidence = "HIGH"
        basis = (
            "Selected Date-Time Part mein sirf ek "
            "searched cell active tha."
        )

    elif loaded_count > 0 and active_count < loaded_count:
        confidence = "MEDIUM"
        basis = (
            f"Selected Date-Time Part mein {active_count} of "
            f"{loaded_count} loaded searched cells active the."
        )

    else:
        confidence = "LOW"
        basis = (
            f"Selected Date-Time Part mein sabhi {active_count} "
            "loaded searched cells active the; koi unique "
            "location safely infer nahi hui."
        )

    return {
        "valid": True,
        "status": "VALID_AUTO_ACTIVE_CELLS",
        "scope_mode": "AUTO_ACTIVE_CELLS",
        "group_id": "AUTO_ACTIVE",
        "cell_keys": active_keys,
        "cell_values": active_values,
        "scope_confidence": confidence,
        "location_confirmed": False,
        "scope_basis": basis,
        "loaded_cell_count": loaded_count,
        "resolved_cell_count": active_count,
        "message": (
            "Date-Time Part ke active searched cells "
            "automatically selected hue. Location independently "
            "confirmed nahi hai."
        ),
    }

def resolve_sighting_scope(
    sighting: dict[str, Any],
    *,
    cgi_groups: list[dict[str, Any]] | None,
    loaded_cells: dict[str, str],
    source_type: str,
) -> dict[str, Any]:
    """Resolve one sighting into a validated set of loaded searched cells."""

    source_type = str(source_type).strip().upper()
    configured_sources = {
        str(value).strip().upper()
        for value in sighting.get("source_types", [])
        if str(value).strip()
    }

    if configured_sources and source_type not in configured_sources:
        return {
            "valid": False,
            "status": "SOURCE_TYPE_NOT_SELECTED",
            "scope_mode": "EXCLUDED",
            "group_id": str(sighting.get("cgi_group_id", "")).strip().upper(),
            "cell_keys": set(),
            "cell_values": [],
            "message": f"Sighting source_types mein {source_type} selected nahi hai.",
        }

    group_id = str(sighting.get("cgi_group_id", "")).strip().upper()
    groups = group_map(cgi_groups)

    if group_id in {"", "AUTO", "AUTO_ALL"}:
        return {
            "valid": True,
            "status": "VALID_TIME_ONLY_ALL_CELLS",
            "scope_mode": "TIME_ONLY_ALL_CELLS",
            "group_id": "AUTO_ALL",
            "cell_keys": set(loaded_cells),
            "cell_values": sorted(loaded_cells.values()),
            "message": (
                "Explicit CGI group configured nahi tha; all loaded searched cells "
                "use kiye gaye. Result ko location-confirmed na maana jaye."
            ),
        }

    group = groups.get(group_id)
    if group is None:
        return {
            "valid": False,
            "status": "INVALID_CGI_GROUP",
            "scope_mode": "INVALID",
            "group_id": group_id,
            "cell_keys": set(),
            "cell_values": [],
            "message": f"CGI group not found: {group_id}",
        }

    configured: dict[str, str] = {}
    for value in group.get("cgi_values", []):
        key = cell_key(value)
        if key and key not in configured:
            configured[key] = str(value).strip()

    if not configured:
        return {
            "valid": False,
            "status": "EMPTY_CGI_GROUP",
            "scope_mode": "INVALID",
            "group_id": group_id,
            "cell_keys": set(),
            "cell_values": [],
            "message": f"CGI group {group_id} mein koi usable Cell ID nahi hai.",
        }

    matched_keys = set(configured).intersection(loaded_cells)
    if not matched_keys:
        return {
            "valid": False,
            "status": "NO_MATCHING_LOADED_CGI",
            "scope_mode": "LOCATION_SCOPED",
            "group_id": group_id,
            "cell_keys": set(),
            "cell_values": [],
            "configured_cell_values": sorted(configured.values()),
            "message": (
                f"CGI group {group_id} ka koi Cell ID loaded dataset mein nahi mila."
            ),
        }

    return {
        "valid": True,
        "status": "VALID_LOCATION_SCOPED",
        "scope_mode": "LOCATION_SCOPED",
        "group_id": group_id,
        "cell_keys": matched_keys,
        "cell_values": sorted(loaded_cells[key] for key in matched_keys),
        "configured_cell_values": sorted(configured.values()),
        "message": "Time window aur resolved CGI group dono apply hue.",
    }


def cell_mask(
    df: pd.DataFrame,
    allowed_keys: set[str],
    *,
    column: str = "searched_cell_id",
) -> pd.Series:
    if column not in df.columns:
        return pd.Series(False, index=df.index)
    if not allowed_keys:
        return pd.Series(False, index=df.index)
    return clean_text(df[column]).map(cell_key).isin(allowed_keys)
