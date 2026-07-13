"""Shared CCTV sighting-to-CGI resolution for dump partition engines."""

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
