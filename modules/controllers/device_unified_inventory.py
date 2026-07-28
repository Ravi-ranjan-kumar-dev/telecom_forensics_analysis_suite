
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from modules.controllers.device_evidence_batch import (
    load_dedicated_evidence_inventory,
)


SOURCE_TYPES = (
    "CDR",
    "IPDR",
    "GPRS",
)

SUPPORTED_IDENTIFIER_LENGTHS = {
    14,
    15,
    16,
}


def device_family(
    value: Any,
) -> str:
    """Return the preserved identifier's 14-digit device family."""

    digits = re.sub(
        r"\D",
        "",
        str(
            value or ""
        ),
    )

    if len(
        digits
    ) not in SUPPORTED_IDENTIFIER_LENGTHS:
        return ""

    return digits[
        :14
    ]


def _text_series(
    dataframe: pd.DataFrame,
    column: str,
) -> pd.Series:
    if column not in dataframe.columns:
        return pd.Series(
            "",
            index=dataframe.index,
            dtype="string",
        )

    return (
        dataframe[
            column
        ]
        .astype(
            "string"
        )
        .fillna(
            ""
        )
        .str.strip()
    )


def _manifest(
    inventory: Mapping[str, Any],
) -> pd.DataFrame:
    value = inventory.get(
        "acquisition_manifest"
    )

    return (
        value.copy(
            deep=True
        )
        if isinstance(
            value,
            pd.DataFrame,
        )
        else pd.DataFrame()
    )


def _source_folder(
    relative_path: Any,
) -> str:
    text = str(
        relative_path or ""
    ).replace(
        "\\",
        "/",
    ).strip(
        "/"
    )

    return (
        text.split(
            "/",
            1,
        )[
            0
        ].upper()
        if text
        else ""
    )


def _source_manifest_index(
    inventory: Mapping[str, Any],
) -> pd.DataFrame:
    manifest = _manifest(
        inventory
    )

    if (
        manifest.empty
        or "Source Path"
        not in manifest.columns
    ):
        return pd.DataFrame()

    return (
        manifest.drop_duplicates(
            subset=[
                "Source Path",
            ],
            keep="first",
        )
        .set_index(
            "Source Path",
            drop=False,
        )
    )


def _build_root_manifest(
    source_inventories: Mapping[
        str,
        Mapping[str, Any],
    ],
) -> pd.DataFrame:
    base = pd.DataFrame()

    for source_name in SOURCE_TYPES:
        candidate = _manifest(
            source_inventories.get(
                source_name,
                {},
            )
        )

        if not candidate.empty:
            base = candidate
            break

    if base.empty:
        return pd.DataFrame()

    base = base.reset_index(
        drop=True
    ).copy(
        deep=True
    )

    if "Source Path" not in base.columns:
        return pd.DataFrame()

    base[
        "Physical Source Folder"
    ] = _text_series(
        base,
        "Relative Path",
    ).map(
        _source_folder
    )

    source_fields = (
        "Analysis Content Role",
        "Analysis Duplicate Of",
        "Records Normalized",
        "Rejected Lines",
        "Message",
    )

    for source_name in SOURCE_TYPES:
        source_index = _source_manifest_index(
            source_inventories.get(
                source_name,
                {},
            )
        )

        for field in source_fields:
            temporary_column = (
                f"__{source_name}_{field}"
            )

            if (
                source_index.empty
                or field not in source_index.columns
            ):
                base[
                    temporary_column
                ] = pd.NA
                continue

            mapping = source_index[
                field
            ].to_dict()

            base[
                temporary_column
            ] = base[
                "Source Path"
            ].map(
                mapping
            )

    actual_source = _text_series(
        base,
        "Source Type",
    ).str.upper()

    for field in source_fields:
        selected = pd.Series(
            pd.NA,
            index=base.index,
            dtype="object",
        )

        for source_name in SOURCE_TYPES:
            mask = actual_source.eq(
                source_name
            )

            selected.loc[
                mask
            ] = base.loc[
                mask,
                f"__{source_name}_{field}",
            ]

        base[
            field
        ] = selected

    base[
        "Analysis Content Role"
    ] = (
        _text_series(
            base,
            "Analysis Content Role",
        )
        .str.upper()
        .where(
            actual_source.isin(
                SOURCE_TYPES
            ),
            "EXCLUDED_UNSUPPORTED_OR_ERROR",
        )
    )

    base[
        "Analysis Duplicate Of"
    ] = _text_series(
        base,
        "Analysis Duplicate Of",
    )

    base[
        "Records Normalized"
    ] = pd.to_numeric(
        base[
            "Records Normalized"
        ],
        errors="coerce",
    ).fillna(
        0
    ).astype(
        int
    )

    base[
        "Rejected Lines"
    ] = pd.to_numeric(
        base[
            "Rejected Lines"
        ],
        errors="coerce",
    ).fillna(
        0
    ).astype(
        int
    )

    base[
        "Message"
    ] = _text_series(
        base,
        "Message",
    )

    query_identifiers = _text_series(
        base,
        "Query Identifier",
    )

    valid_identifier = query_identifiers.str.fullmatch(
        r"\d{14,16}",
        na=False,
    )

    analysis_roles = _text_series(
        base,
        "Analysis Content Role",
    ).str.upper()

    eligible = (
        actual_source.isin(
            SOURCE_TYPES
        )
        & valid_identifier
        & analysis_roles.isin(
            {
                "PRIMARY_CONTENT",
                "DUPLICATE_CONTENT",
            }
        )
    )

    sha_values = _text_series(
        base,
        "SHA-256",
    )

    relative_paths = _text_series(
        base,
        "Relative Path",
    )

    source_paths = _text_series(
        base,
        "Source Path",
    )

    eligible_frame = pd.DataFrame(
        {
            "Source Type": actual_source,
            "SHA-256": sha_values,
        },
        index=base.index,
    ).loc[
        eligible
        & sha_values.ne(
            ""
        )
    ]

    for (
        source_name,
        digest,
    ), group in eligible_frame.groupby(
        [
            "Source Type",
            "SHA-256",
        ],
        sort=True,
        dropna=False,
    ):
        group_indexes = list(
            group.index
        )

        matching_folder_indexes = [
            index
            for index in group_indexes
            if str(
                base.at[
                    index,
                    "Physical Source Folder",
                ]
            ).upper()
            == str(
                source_name
            ).upper()
        ]

        candidates = (
            matching_folder_indexes
            if matching_folder_indexes
            else group_indexes
        )

        primary_index = sorted(
            candidates,
            key=lambda index: (
                str(
                    relative_paths.loc[
                        index
                    ]
                ).lower(),
                str(
                    source_paths.loc[
                        index
                    ]
                ).lower(),
            ),
        )[
            0
        ]

        primary_path = str(
            source_paths.loc[
                primary_index
            ]
        )

        normalized_count = int(
            pd.to_numeric(
                base.loc[
                    group_indexes,
                    "Records Normalized",
                ],
                errors="coerce",
            ).fillna(
                0
            ).max()
            or 0
        )

        base.loc[
            group_indexes,
            "Analysis Content Role",
        ] = "DUPLICATE_CONTENT"

        base.loc[
            group_indexes,
            "Analysis Duplicate Of",
        ] = primary_path

        base.loc[
            group_indexes,
            "Records Normalized",
        ] = 0

        base.at[
            primary_index,
            "Analysis Content Role",
        ] = "PRIMARY_CONTENT"

        base.at[
            primary_index,
            "Analysis Duplicate Of",
        ] = ""

        base.at[
            primary_index,
            "Records Normalized",
        ] = normalized_count

    sha_group_size = sha_values.groupby(
        sha_values
    ).transform(
        "size"
    )

    folder_group_count = (
        base.assign(
            __sha=sha_values,
            __folder=_text_series(
                base,
                "Physical Source Folder",
            ),
        )
        .groupby(
            "__sha",
            dropna=False,
        )[
            "__folder"
        ]
        .transform(
            "nunique"
        )
    )

    base[
        "Cross-Folder Duplicate"
    ] = (
        sha_values.ne(
            ""
        )
        & sha_group_size.gt(
            1
        )
        & folder_group_count.gt(
            1
        )
    ).map(
        {
            True: "YES",
            False: "NO",
        }
    )

    temporary_columns = [
        column
        for column in base.columns
        if column.startswith(
            "__"
        )
    ]

    if temporary_columns:
        base = base.drop(
            columns=temporary_columns
        )

    return (
        base.sort_values(
            [
                "Relative Path",
                "Source File",
            ],
            kind="stable",
            na_position="last",
        )
        .reset_index(
            drop=True
        )
    )


def _deduplicate_messages(
    values: list[str],
) -> list[str]:
    seen = set()
    result = []

    for value in values:
        cleaned = str(
            value or ""
        ).strip()

        if (
            not cleaned
            or cleaned in seen
        ):
            continue

        seen.add(
            cleaned
        )

        result.append(
            cleaned
        )

    return result


def load_unified_device_inventory(
    *,
    folder: str | Path,
    supported_suffixes,
    inspect_file: Callable[..., dict[str, Any]],
    normalizers: Mapping[
        str,
        Callable[..., dict[str, Any]],
    ],
) -> dict[str, Any]:
    """Load all dedicated IMEI evidence through one root inventory."""

    root = Path(
        folder
    ).expanduser().resolve()

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    source_inventories: dict[
        str,
        dict[str, Any],
    ] = {}

    for source_name in SOURCE_TYPES:
        normalizer = normalizers.get(
            source_name
        )

        if not callable(
            normalizer
        ):
            raise ValueError(
                f"Missing {source_name} IMEI normalizer."
            )

        source_inventories[
            source_name
        ] = load_dedicated_evidence_inventory(
            folder=root,
            expected_source_type=source_name,
            supported_suffixes=supported_suffixes,
            inspect_file=inspect_file,
            normalize_file=normalizer,
        )

    manifest = _build_root_manifest(
        source_inventories
    )

    identifiers = sorted(
        {
            str(
                identifier
            ).strip()
            for source_name in SOURCE_TYPES
            for identifier in source_inventories[
                source_name
            ].get(
                "identifiers",
                [],
            )
            if device_family(
                identifier
            )
        }
    )

    source_frames = {
        source_name: {
            str(
                identifier
            ).strip(): (
                dataframe.copy(
                    deep=True
                )
                if isinstance(
                    dataframe,
                    pd.DataFrame,
                )
                else pd.DataFrame()
            )
            for identifier, dataframe in source_inventories[
                source_name
            ].get(
                "device_frames",
                {},
            ).items()
        }
        for source_name in SOURCE_TYPES
    }

    source_record_counts = {
        source_name: int(
            source_inventories[
                source_name
            ].get(
                "analytical_records",
                0,
            )
            or 0
        )
        for source_name in SOURCE_TYPES
    }

    if manifest.empty:
        all_content_groups = 0
        repeated_content_groups = 0
        cross_folder_content_groups = 0
        duplicate_acquisitions = 0

    else:
        sha_values = _text_series(
            manifest,
            "SHA-256",
        )

        nonempty_sha = sha_values.loc[
            sha_values.ne(
                ""
            )
        ]

        all_content_groups = int(
            nonempty_sha.nunique()
        )

        group_sizes = nonempty_sha.value_counts()

        repeated_content_groups = int(
            group_sizes.gt(
                1
            ).sum()
        )

        duplicate_acquisitions = int(
            (
                group_sizes
                - 1
            ).clip(
                lower=0
            ).sum()
        )

        cross_folder_content_groups = int(
            manifest.loc[
                sha_values.ne(
                    ""
                )
            ]
            .assign(
                __sha=sha_values.loc[
                    sha_values.ne(
                        ""
                    )
                ].values,
                __folder=_text_series(
                    manifest.loc[
                        sha_values.ne(
                            ""
                        )
                    ],
                    "Physical Source Folder",
                ).values,
            )
            .groupby(
                "__sha"
            )[
                "__folder"
            ]
            .nunique()
            .gt(
                1
            )
            .sum()
        )

    warnings = _deduplicate_messages(
        [
            f"{source_name}: {warning}"
            for source_name in SOURCE_TYPES
            for warning in source_inventories[
                source_name
            ].get(
                "warnings",
                [],
            )
        ]
    )

    errors = _deduplicate_messages(
        [
            f"{source_name}: {error}"
            for source_name in SOURCE_TYPES
            for error in source_inventories[
                source_name
            ].get(
                "errors",
                [],
            )
        ]
    )

    return {
        "folder": root,
        "files_found": len(
            manifest
        ),
        "identifiers": identifiers,
        "source_frames": source_frames,
        "source_inventories": source_inventories,
        "acquisition_manifest": manifest,
        "all_content_groups": all_content_groups,
        "repeated_content_groups": repeated_content_groups,
        "cross_folder_content_groups": (
            cross_folder_content_groups
        ),
        "duplicate_acquisitions": duplicate_acquisitions,
        "source_record_counts": source_record_counts,
        "warnings": warnings,
        "errors": errors,
    }


def _family_frame(
    values: Mapping[
        str,
        pd.DataFrame,
    ],
    identifier: str,
) -> pd.DataFrame:
    family = device_family(
        identifier
    )

    frames = [
        dataframe.copy(
            deep=True
        )
        for query_identifier, dataframe in values.items()
        if (
            device_family(
                query_identifier
            )
            == family
            and isinstance(
                dataframe,
                pd.DataFrame,
            )
            and not dataframe.empty
        )
    ]

    if not frames:
        return pd.DataFrame()

    return pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )


def build_unified_identifier_scope(
    inventory: Mapping[str, Any],
    identifier: str,
) -> dict[str, Any]:
    """Build one source-separated scope for a query identifier family."""

    family = device_family(
        identifier
    )

    if not family:
        return {
            "identifier": "",
            "device_family": "",
            "source_frames": {
                "cdr": pd.DataFrame(),
                "ipdr": pd.DataFrame(),
                "gprs": pd.DataFrame(),
            },
            "acquisition_manifest": pd.DataFrame(),
            "empty_sources": set(),
        }

    manifest_value = inventory.get(
        "acquisition_manifest"
    )

    manifest = (
        manifest_value.copy(
            deep=True
        )
        if isinstance(
            manifest_value,
            pd.DataFrame,
        )
        else pd.DataFrame()
    )

    if (
        not manifest.empty
        and "Query Identifier"
        in manifest.columns
    ):
        query_families = _text_series(
            manifest,
            "Query Identifier",
        ).map(
            device_family
        )

        manifest = (
            manifest.loc[
                query_families.eq(
                    family
                )
            ]
            .reset_index(
                drop=True
            )
            .copy(
                deep=True
            )
        )

    else:
        manifest = pd.DataFrame()

    source_frame_mapping = inventory.get(
        "source_frames",
        {}
    )

    source_frames = {
        source_name.lower(): _family_frame(
            (
                source_frame_mapping.get(
                    source_name,
                    {}
                )
                if isinstance(
                    source_frame_mapping,
                    Mapping,
                )
                else {}
            ),
            identifier,
        )
        for source_name in SOURCE_TYPES
    }

    empty_sources = set()

    if not manifest.empty:
        source_types = _text_series(
            manifest,
            "Source Type",
        ).str.upper()

        statuses = _text_series(
            manifest,
            "Inspection Status",
        ).str.upper()

        roles = _text_series(
            manifest,
            "Analysis Content Role",
        ).str.upper()

        eligible_roles = roles.isin(
            {
                "PRIMARY_CONTENT",
                "DUPLICATE_CONTENT",
            }
        )

        for source_name in SOURCE_TYPES:
            source_rows = (
                source_types.eq(
                    source_name
                )
                & eligible_roles
            )

            if (
                source_frames[
                    source_name.lower()
                ].empty
                and source_rows.any()
                and statuses.loc[
                    source_rows
                ].eq(
                    "EMPTY_NO_DATA"
                ).any()
            ):
                empty_sources.add(
                    source_name
                )

    return {
        "identifier": str(
            identifier
        ).strip(),
        "device_family": family,
        "source_frames": source_frames,
        "acquisition_manifest": manifest,
        "empty_sources": empty_sources,
    }
