"""Common Spot scope resolver for Tower Dump partitions.

This module applies only the investigation-Spot boundary. Source-specific
time and CGI/Cell rules remain inside the CDR, GPRS and Tower IPDR engines.

Backward compatibility:
    Old partition records without Spot fields use all loaded Spots and are
    explicitly labelled LEGACY_ALL_SPOTS.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


SELECTED_SPOT_ONLY = "SELECTED_SPOT_ONLY"
ALL_SPOTS = "ALL_SPOTS"
LEGACY_ALL_SPOTS = "LEGACY_ALL_SPOTS"


def _clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""

    text = str(value).strip()

    if text.lower() in {
        "",
        "nan",
        "none",
        "<na>",
        "null",
    }:
        return ""

    return text


def _normalise_key(value: object) -> str:
    return _clean_text(value).casefold()


def loaded_spot_summary(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Return one row per loaded investigation Spot."""

    columns = [
        "spot_id",
        "spot_name",
        "spot_folder",
        "records",
    ]

    if (
        not isinstance(dataframe, pd.DataFrame)
        or dataframe.empty
        or "spot_id" not in dataframe.columns
    ):
        return pd.DataFrame(columns=columns)

    work = dataframe.copy()

    for column in (
        "spot_id",
        "spot_name",
        "spot_folder",
    ):
        if column not in work.columns:
            work[column] = ""

        work[column] = (
            work[column]
            .map(_clean_text)
        )

    work = work.loc[
        work["spot_id"].ne("")
    ].copy()

    if work.empty:
        return pd.DataFrame(columns=columns)

    return (
        work.groupby(
            [
                "spot_id",
                "spot_name",
                "spot_folder",
            ],
            dropna=False,
            observed=True,
            sort=True,
        )
        .size()
        .reset_index(name="records")
    )


def resolve_partition_spot_scope(
    dataframe: pd.DataFrame,
    partition: dict[str, Any],
) -> dict[str, Any]:
    """Resolve and validate the Spot selected for one partition.

    Supported partition fields:
        spot_scope_mode
        spot_id
        spot_name

    Rules:
        SELECTED_SPOT_ONLY:
            Only rows belonging to the requested Spot are returned.

        ALL_SPOTS:
            Every loaded Spot is included intentionally.

        Missing Spot fields:
            Legacy compatibility mode. Every loaded Spot is included,
            but the result is labelled LEGACY_ALL_SPOTS.
    """

    if not isinstance(dataframe, pd.DataFrame):
        return {
            "valid": False,
            "status": "INVALID_DATAFRAME",
            "spot_scope_mode": "INVALID",
            "spot_id": "",
            "spot_name": "",
            "spot_folder": "",
            "dataframe": pd.DataFrame(),
            "mask": pd.Series(dtype=bool),
            "loaded_spot_count": 0,
            "message": "Valid Tower Dump DataFrame उपलब्ध नहीं है।",
        }

    requested_mode = _clean_text(
        partition.get(
            "spot_scope_mode",
            partition.get(
                "partition_spot_scope",
                "",
            ),
        )
    ).upper()

    requested_spot_id = _clean_text(
        partition.get("spot_id", "")
    )

    requested_spot_name = _clean_text(
        partition.get("spot_name", "")
    )

    spot_summary = loaded_spot_summary(
        dataframe
    )

    loaded_spot_count = len(spot_summary)

    explicit_all_modes = {
        ALL_SPOTS,
        "ALL",
        "AUTO_ALL",
        "TIME_ONLY_ALL_SPOTS",
    }

    has_explicit_spot = bool(
        requested_spot_id
        or requested_spot_name
    )

    if (
        requested_mode in explicit_all_modes
    ):
        mask = pd.Series(
            True,
            index=dataframe.index,
            dtype=bool,
        )

        return {
            "valid": True,
            "status": "VALID_ALL_SPOTS",
            "spot_scope_mode": ALL_SPOTS,
            "spot_id": "ALL_SPOTS",
            "spot_name": "ALL LOADED SPOTS",
            "spot_folder": "",
            "dataframe": dataframe.copy(),
            "mask": mask,
            "loaded_spot_count": loaded_spot_count,
            "message": (
                "Date-Time Part सभी loaded Spots पर "
                "जानबूझकर लागू किया गया।"
            ),
        }

    if not has_explicit_spot:
        mask = pd.Series(
            True,
            index=dataframe.index,
            dtype=bool,
        )

        return {
            "valid": True,
            "status": "VALID_LEGACY_ALL_SPOTS",
            "spot_scope_mode": LEGACY_ALL_SPOTS,
            "spot_id": "ALL_SPOTS",
            "spot_name": "ALL LOADED SPOTS",
            "spot_folder": "",
            "dataframe": dataframe.copy(),
            "mask": mask,
            "loaded_spot_count": loaded_spot_count,
            "message": (
                "पुराने Part में Spot configured नहीं था; "
                "backward compatibility के लिए सभी Spots "
                "शामिल किए गए।"
            ),
        }

    if (
        "spot_id" not in dataframe.columns
        and "spot_name" not in dataframe.columns
    ):
        return {
            "valid": False,
            "status": "SPOT_COLUMNS_MISSING",
            "spot_scope_mode": SELECTED_SPOT_ONLY,
            "spot_id": requested_spot_id,
            "spot_name": requested_spot_name,
            "spot_folder": "",
            "dataframe": dataframe.iloc[0:0].copy(),
            "mask": pd.Series(
                False,
                index=dataframe.index,
                dtype=bool,
            ),
            "loaded_spot_count": loaded_spot_count,
            "message": (
                "Selected Spot लागू नहीं हुआ क्योंकि "
                "loaded data में Spot columns नहीं हैं।"
            ),
        }

    spot_id_series = (
        dataframe.get(
            "spot_id",
            pd.Series(
                "",
                index=dataframe.index,
                dtype="string",
            ),
        )
        .map(_normalise_key)
    )

    spot_name_series = (
        dataframe.get(
            "spot_name",
            pd.Series(
                "",
                index=dataframe.index,
                dtype="string",
            ),
        )
        .map(_normalise_key)
    )

    if requested_spot_id:
        mask = spot_id_series.eq(
            _normalise_key(
                requested_spot_id
            )
        )
        match_basis = "spot_id"
    else:
        mask = spot_name_series.eq(
            _normalise_key(
                requested_spot_name
            )
        )
        match_basis = "spot_name"

    scoped = dataframe.loc[
        mask
    ].copy()

    if scoped.empty:
        available = ", ".join(
            (
                spot_summary[
                    "spot_id"
                ].astype(str)
                + " = "
                + spot_summary[
                    "spot_name"
                ].astype(str)
            ).tolist()
        )

        return {
            "valid": False,
            "status": "SELECTED_SPOT_NOT_LOADED",
            "spot_scope_mode": SELECTED_SPOT_ONLY,
            "spot_id": requested_spot_id,
            "spot_name": requested_spot_name,
            "spot_folder": "",
            "dataframe": scoped,
            "mask": mask,
            "loaded_spot_count": loaded_spot_count,
            "message": (
                "Selected Spot loaded data में नहीं मिला। "
                f"Available Spots: {available}"
            ),
        }

    resolved_spot_id = _clean_text(
        scoped.get(
            "spot_id",
            pd.Series(dtype="string"),
        ).iloc[0]
    )

    resolved_spot_name = _clean_text(
        scoped.get(
            "spot_name",
            pd.Series(dtype="string"),
        ).iloc[0]
    )

    resolved_spot_folder = _clean_text(
        scoped.get(
            "spot_folder",
            pd.Series(dtype="string"),
        ).iloc[0]
    )

    return {
        "valid": True,
        "status": "VALID_SELECTED_SPOT",
        "spot_scope_mode": SELECTED_SPOT_ONLY,
        "spot_id": resolved_spot_id,
        "spot_name": resolved_spot_name,
        "spot_folder": resolved_spot_folder,
        "dataframe": scoped,
        "mask": mask,
        "loaded_spot_count": loaded_spot_count,
        "selected_record_count": len(scoped),
        "match_basis": match_basis,
        "message": (
            f"Date-Time Part applied only to "
            f"{resolved_spot_name} ({resolved_spot_id})."
        ),
    }
