
from pathlib import Path

import pandas as pd

from modules.controllers.device_evidence_batch import (
    load_dedicated_evidence_inventory,
)


SUPPORTED_SUFFIXES = {
    ".csv",
}


def _inspection(
    *,
    source_type: str,
    query_identifier: str,
    status: str = "HAS_DATA",
    ok: bool = True,
) -> dict:
    return {
        "ok": ok,
        "status": status,
        "source_type": source_type,
        "format_id": f"FORMAT_{source_type}",
        "operator": "Test Operator",
        "query_identifier_normalized": query_identifier,
        "query_identifier_type": (
            "IMEI15"
            if len(
                query_identifier
            )
            == 15
            else "IMEISV16"
        ),
        "record_count": (
            0
            if status == "EMPTY_NO_DATA"
            else 1
        ),
        "rejected_line_count": 0,
        "message": "Inspection complete.",
    }


def test_missing_folder_is_read_only(
    tmp_path: Path,
):
    folder = tmp_path / "missing"

    result = load_dedicated_evidence_inventory(
        folder=folder,
        expected_source_type="IPDR",
        supported_suffixes=SUPPORTED_SUFFIXES,
        inspect_file=lambda path: {},
        normalize_file=lambda path, inspection=None: {},
    )

    assert not folder.exists()

    assert result[
        "files_found"
    ] == 0

    assert result[
        "identifiers"
    ] == []

    assert result[
        "analytical_records"
    ] == 0


def test_inventory_preserves_acquisitions_and_normalizes_once(
    tmp_path: Path,
):
    first = tmp_path / "first.csv"
    duplicate = tmp_path / "duplicate.csv"
    non_source = tmp_path / "gprs.csv"

    first.write_bytes(
        b"same-ipdr-content"
    )

    duplicate.write_bytes(
        b"same-ipdr-content"
    )

    non_source.write_bytes(
        b"gprs-content"
    )

    query_identifier = "862261072892730"

    inspections = {
        "first.csv": _inspection(
            source_type="IPDR",
            query_identifier=query_identifier,
        ),
        "duplicate.csv": _inspection(
            source_type="IPDR",
            query_identifier=query_identifier,
        ),
        "gprs.csv": _inspection(
            source_type="GPRS",
            query_identifier=query_identifier,
        ),
    }

    normalization_calls = []

    def normalize_file(
        path: Path,
        *,
        inspection,
    ):
        normalization_calls.append(
            path.name
        )

        return {
            "status": "HAS_DATA",
            "records_normalized": 1,
            "rejected_line_count": 0,
            "warnings": [],
            "errors": [],
            "message": "Normalized.",
            "data": pd.DataFrame(
                [
                    {
                        "query_identifier_normalized": (
                            query_identifier
                        ),
                        "imei": "8622610728927300",
                    }
                ]
            ),
        }

    result = load_dedicated_evidence_inventory(
        folder=tmp_path,
        expected_source_type="IPDR",
        supported_suffixes=SUPPORTED_SUFFIXES,
        inspect_file=lambda path: inspections[
            path.name
        ],
        normalize_file=normalize_file,
    )

    assert result[
        "files_found"
    ] == 3

    assert result[
        "all_content_groups"
    ] == 2

    assert result[
        "supported_content_groups"
    ] == 1

    assert result[
        "non_source_acquisitions"
    ] == 1

    assert result[
        "duplicate_source_acquisitions"
    ] == 1

    assert result[
        "identifiers"
    ] == [
        query_identifier,
    ]

    assert result[
        "analytical_records"
    ] == 1

    assert len(
        normalization_calls
    ) == 1

    assert len(
        result[
            "acquisition_manifest"
        ]
    ) == 3


def test_empty_report_identifier_remains_available(
    tmp_path: Path,
):
    path = tmp_path / "empty.csv"

    path.write_text(
        "header-only",
        encoding="utf-8",
    )

    identifier = "862286069717070"

    result = load_dedicated_evidence_inventory(
        folder=tmp_path,
        expected_source_type="IPDR",
        supported_suffixes=SUPPORTED_SUFFIXES,
        inspect_file=lambda source_path: _inspection(
            source_type="IPDR",
            query_identifier=identifier,
            status="EMPTY_NO_DATA",
        ),
        normalize_file=lambda source_path, inspection=None: {
            "status": "EMPTY_NO_DATA",
            "records_normalized": 0,
            "rejected_line_count": 0,
            "warnings": [],
            "errors": [],
            "message": "Valid empty report.",
            "data": pd.DataFrame(),
        },
    )

    assert result[
        "identifiers"
    ] == [
        identifier,
    ]

    assert identifier in result[
        "device_frames"
    ]

    assert result[
        "device_frames"
    ][
        identifier
    ].empty

    manifest = result[
        "acquisition_manifest"
    ]

    assert manifest.iloc[
        0
    ][
        "Inspection Status"
    ] == "EMPTY_NO_DATA"

    assert manifest.iloc[
        0
    ][
        "Records Normalized"
    ] == 0
