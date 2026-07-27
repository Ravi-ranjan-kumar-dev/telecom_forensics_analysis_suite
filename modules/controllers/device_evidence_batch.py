
"""Reusable inventory layer for dedicated device-evidence folders."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd


VALID_DEVICE_IDENTIFIER_LENGTHS = {
    14,
    15,
    16,
}


InspectionFunction = Callable[
    [Path],
    Mapping[str, Any],
]

NormalizationFunction = Callable[
    ...,
    Mapping[str, Any],
]


def _sha256_file(
    path: Path,
) -> str:
    """Calculate SHA-256 without modifying the evidence file."""

    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as handle:
        while True:
            block = handle.read(
                1024 * 1024
            )

            if not block:
                break

            digest.update(
                block
            )

    return digest.hexdigest()


def _empty_inventory(
    folder: Path,
) -> dict[str, Any]:
    """Return the stable inventory contract for a missing/empty folder."""

    return {
        "folder": folder,
        "files_found": 0,
        "identifiers": [],
        "device_frames": {},
        "acquisition_manifest": pd.DataFrame(),
        "all_content_groups": 0,
        "supported_content_groups": 0,
        "unique_content_groups": 0,
        "non_source_acquisitions": 0,
        "duplicate_source_acquisitions": 0,
        "analytical_records": 0,
        "warnings": [],
        "errors": [],
    }


def _identifier_is_valid(
    value: Any,
) -> bool:
    text = str(
        value or ""
    ).strip()

    return (
        text.isdigit()
        and len(
            text
        )
        in VALID_DEVICE_IDENTIFIER_LENGTHS
    )


def _supported_paths(
    folder: Path,
    supported_suffixes: Iterable[str],
) -> list[Path]:
    suffixes = {
        str(
            suffix
        ).strip().lower()
        for suffix in supported_suffixes
        if str(
            suffix
        ).strip()
    }

    if not folder.is_dir():
        return []

    return sorted(
        (
            path
            for path in folder.rglob(
                "*"
            )
            if (
                path.is_file()
                and path.suffix.lower()
                in suffixes
            )
        ),
        key=lambda path: str(
            path
        ).lower(),
    )


def load_dedicated_evidence_inventory(
    *,
    folder: str | Path,
    expected_source_type: str,
    supported_suffixes: Iterable[str],
    inspect_file: InspectionFunction,
    normalize_file: NormalizationFunction,
) -> dict[str, Any]:
    """Inspect acquisitions and normalize each supported content unit once.

    Physical acquisitions remain separate in the manifest. Identical
    supported content is normalized only once. The input folder and raw
    evidence files are never created, moved, renamed or modified here.
    """

    evidence_folder = Path(
        folder
    ).expanduser()

    source_type_expected = str(
        expected_source_type
    ).strip().upper()

    if not source_type_expected:
        raise ValueError(
            "Expected source type is required."
        )

    paths = _supported_paths(
        evidence_folder,
        supported_suffixes,
    )

    if not paths:
        return _empty_inventory(
            evidence_folder
        )

    acquisition_rows: list[
        dict[str, Any]
    ] = []

    all_content_representatives: dict[
        str,
        Path
    ] = {}

    supported_content_representatives: dict[
        str,
        Path
    ] = {}

    frames_by_identifier: dict[
        str,
        list[pd.DataFrame]
    ] = {}

    identifiers: set[str] = set()
    warnings: list[str] = []
    errors: list[str] = []

    for path in paths:
        digest = _sha256_file(
            path
        )

        try:
            inspection = dict(
                inspect_file(
                    path
                )
                or {}
            )

        except Exception as error:
            inspection = {
                "ok": False,
                "status": "ERROR",
                "source_type": "",
                "format_id": "",
                "operator": "",
                "query_identifier_normalized": "",
                "query_identifier_type": "",
                "record_count": 0,
                "rejected_line_count": 0,
                "message": str(
                    error
                ),
            }

            errors.append(
                f"{path.name}: inspection failed: {error}"
            )

        query_identifier = str(
            inspection.get(
                "query_identifier_normalized",
                "",
            )
            or ""
        ).strip()

        source_type = str(
            inspection.get(
                "source_type",
                "",
            )
            or ""
        ).strip().upper()

        acquisition_duplicate_of = (
            all_content_representatives.get(
                digest
            )
        )

        if acquisition_duplicate_of is None:
            all_content_representatives[
                digest
            ] = path

        row = {
            "Relative Path": (
                path.relative_to(
                    evidence_folder
                ).as_posix()
            ),
            "Source File": path.name,
            "Source Path": str(
                path.resolve()
            ),
            "SHA-256": digest,
            "Acquisition Content Role": (
                "DUPLICATE_CONTENT"
                if acquisition_duplicate_of is not None
                else "PRIMARY_CONTENT"
            ),
            "Duplicate Of": (
                str(
                    acquisition_duplicate_of.resolve()
                )
                if acquisition_duplicate_of is not None
                else ""
            ),
            "Analysis Content Role": "",
            "Analysis Duplicate Of": "",
            "Format": str(
                inspection.get(
                    "format_id",
                    "",
                )
                or ""
            ),
            "Operator": str(
                inspection.get(
                    "operator",
                    "",
                )
                or ""
            ),
            "Source Type": source_type,
            "Query Identifier": query_identifier,
            "Query Identifier Type": str(
                inspection.get(
                    "query_identifier_type",
                    "",
                )
                or ""
            ),
            "Inspection Status": str(
                inspection.get(
                    "status",
                    "",
                )
                or ""
            ),
            "Records Declared": int(
                inspection.get(
                    "record_count",
                    0,
                )
                or 0
            ),
            "Records Normalized": 0,
            "Rejected Lines": int(
                inspection.get(
                    "rejected_line_count",
                    0,
                )
                or 0
            ),
            "Message": str(
                inspection.get(
                    "message",
                    "",
                )
                or ""
            ),
        }

        if not inspection.get(
            "ok"
        ):
            row[
                "Analysis Content Role"
            ] = "EXCLUDED_UNSUPPORTED_OR_ERROR"

            acquisition_rows.append(
                row
            )

            continue

        if source_type != source_type_expected:
            row[
                "Analysis Content Role"
            ] = (
                f"EXCLUDED_NON_{source_type_expected}"
            )

            acquisition_rows.append(
                row
            )

            continue

        if not _identifier_is_valid(
            query_identifier
        ):
            row[
                "Analysis Content Role"
            ] = "EXCLUDED_INVALID_QUERY"

            errors.append(
                f"{path.name}: valid report-query "
                "IMEI/IMEISV could not be detected."
            )

            acquisition_rows.append(
                row
            )

            continue

        identifiers.add(
            query_identifier
        )

        frames_by_identifier.setdefault(
            query_identifier,
            [],
        )

        analysis_duplicate_of = (
            supported_content_representatives.get(
                digest
            )
        )

        if analysis_duplicate_of is not None:
            row[
                "Analysis Content Role"
            ] = "DUPLICATE_CONTENT"

            row[
                "Analysis Duplicate Of"
            ] = str(
                analysis_duplicate_of.resolve()
            )

            acquisition_rows.append(
                row
            )

            continue

        supported_content_representatives[
            digest
        ] = path

        row[
            "Analysis Content Role"
        ] = "PRIMARY_CONTENT"

        try:
            normalization = dict(
                normalize_file(
                    path,
                    inspection=inspection,
                )
                or {}
            )

        except Exception as error:
            normalization = {
                "status": "ERROR",
                "records_normalized": 0,
                "rejected_line_count": row[
                    "Rejected Lines"
                ],
                "warnings": [],
                "errors": [
                    str(
                        error
                    ),
                ],
                "message": str(
                    error
                ),
                "data": pd.DataFrame(),
            }

        row[
            "Records Normalized"
        ] = int(
            normalization.get(
                "records_normalized",
                0,
            )
            or 0
        )

        row[
            "Rejected Lines"
        ] = int(
            normalization.get(
                "rejected_line_count",
                row[
                    "Rejected Lines"
                ],
            )
            or 0
        )

        row[
            "Message"
        ] = str(
            normalization.get(
                "message",
                row[
                    "Message"
                ],
            )
            or ""
        )

        for warning in (
            normalization.get(
                "warnings",
                [],
            )
            or []
        ):
            warnings.append(
                f"{path.name}: {warning}"
            )

        for error in (
            normalization.get(
                "errors",
                [],
            )
            or []
        ):
            errors.append(
                f"{path.name}: {error}"
            )

        dataframe = normalization.get(
            "data"
        )

        if (
            isinstance(
                dataframe,
                pd.DataFrame,
            )
            and not dataframe.empty
        ):
            frames_by_identifier[
                query_identifier
            ].append(
                dataframe.copy(
                    deep=True
                )
            )

        acquisition_rows.append(
            row
        )

    device_frames = {
        identifier: (
            pd.concat(
                frames,
                ignore_index=True,
                sort=False,
            )
            if frames
            else pd.DataFrame()
        )
        for identifier, frames
        in frames_by_identifier.items()
    }

    manifest = pd.DataFrame(
        acquisition_rows
    )

    if manifest.empty:
        non_source_acquisitions = 0
        duplicate_source_acquisitions = 0

    else:
        source_types = (
            manifest[
                "Source Type"
            ]
            .astype(
                "string"
            )
            .fillna(
                ""
            )
            .str.strip()
            .str.upper()
        )

        analysis_roles = (
            manifest[
                "Analysis Content Role"
            ]
            .astype(
                "string"
            )
            .fillna(
                ""
            )
            .str.strip()
            .str.upper()
        )

        non_source_acquisitions = int(
            source_types.ne(
                source_type_expected
            ).sum()
        )

        duplicate_source_acquisitions = int(
            (
                source_types.eq(
                    source_type_expected
                )
                & analysis_roles.eq(
                    "DUPLICATE_CONTENT"
                )
            ).sum()
        )

    return {
        "folder": evidence_folder,
        "files_found": len(
            paths
        ),
        "identifiers": sorted(
            identifiers
        ),
        "device_frames": device_frames,
        "acquisition_manifest": manifest,
        "all_content_groups": len(
            all_content_representatives
        ),
        "supported_content_groups": len(
            supported_content_representatives
        ),
        "unique_content_groups": len(
            supported_content_representatives
        ),
        "non_source_acquisitions": (
            non_source_acquisitions
        ),
        "duplicate_source_acquisitions": (
            duplicate_source_acquisitions
        ),
        "analytical_records": int(
            sum(
                len(
                    dataframe
                )
                for dataframe
                in device_frames.values()
            )
        ),
        "warnings": warnings,
        "errors": errors,
    }


__all__ = [
    "load_dedicated_evidence_inventory",
]
