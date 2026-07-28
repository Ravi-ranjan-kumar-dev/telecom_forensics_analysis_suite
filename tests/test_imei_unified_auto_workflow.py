
from __future__ import annotations

from pathlib import Path

import pandas as pd

from modules.analysis.device import (
    build_unified_imei_investigation,
)
from modules.controllers import (
    device_unified_inventory,
    imei_device_controller,
)


IMEI_15 = "862261072892730"
IMEISV_16 = "8622610728927300"
GPRS_IMEI = "861679062132757"


def _physical_manifest() -> pd.DataFrame:
    rows = [
        {
            "Relative Path": "cdr/a.csv",
            "Source File": "a.csv",
            "Source Path": "/evidence/root/cdr/a.csv",
            "SHA-256": "a" * 64,
            "Acquisition Content Role": "PRIMARY_CONTENT",
            "Duplicate Of": "",
            "Analysis Content Role": "",
            "Analysis Duplicate Of": "",
            "Format": "CDR_FORMAT",
            "Operator": "Test",
            "Source Type": "CDR",
            "Query Identifier": IMEISV_16,
            "Query Identifier Type": "IMEISV16",
            "Inspection Status": "HAS_DATA",
            "Records Declared": 1,
            "Records Normalized": 0,
            "Rejected Lines": 0,
            "Message": "",
        },
        {
            "Relative Path": "ipdr/b.csv",
            "Source File": "b.csv",
            "Source Path": "/evidence/root/ipdr/b.csv",
            "SHA-256": "b" * 64,
            "Acquisition Content Role": "PRIMARY_CONTENT",
            "Duplicate Of": "",
            "Analysis Content Role": "",
            "Analysis Duplicate Of": "",
            "Format": "IPDR_FORMAT",
            "Operator": "Test",
            "Source Type": "IPDR",
            "Query Identifier": IMEI_15,
            "Query Identifier Type": "IMEI15",
            "Inspection Status": "HAS_DATA",
            "Records Declared": 1,
            "Records Normalized": 0,
            "Rejected Lines": 0,
            "Message": "",
        },
        {
            "Relative Path": "gprs/b.csv",
            "Source File": "b.csv",
            "Source Path": "/evidence/root/gprs/b.csv",
            "SHA-256": "b" * 64,
            "Acquisition Content Role": "DUPLICATE_CONTENT",
            "Duplicate Of": "/evidence/root/ipdr/b.csv",
            "Analysis Content Role": "",
            "Analysis Duplicate Of": "",
            "Format": "IPDR_FORMAT",
            "Operator": "Test",
            "Source Type": "IPDR",
            "Query Identifier": IMEI_15,
            "Query Identifier Type": "IMEI15",
            "Inspection Status": "HAS_DATA",
            "Records Declared": 1,
            "Records Normalized": 0,
            "Rejected Lines": 0,
            "Message": "",
        },
        {
            "Relative Path": "cdr/c.csv",
            "Source File": "c.csv",
            "Source Path": "/evidence/root/cdr/c.csv",
            "SHA-256": "c" * 64,
            "Acquisition Content Role": "PRIMARY_CONTENT",
            "Duplicate Of": "",
            "Analysis Content Role": "",
            "Analysis Duplicate Of": "",
            "Format": "GPRS_FORMAT",
            "Operator": "Test",
            "Source Type": "GPRS",
            "Query Identifier": GPRS_IMEI,
            "Query Identifier Type": "IMEI15",
            "Inspection Status": "HAS_DATA",
            "Records Declared": 1,
            "Records Normalized": 0,
            "Rejected Lines": 0,
            "Message": "",
        },
    ]

    return pd.DataFrame(
        rows
    )


def _source_inventory(
    source_name: str,
) -> dict:
    manifest = _physical_manifest()

    source_types = (
        manifest[
            "Source Type"
        ]
        .astype(
            str
        )
        .str.upper()
    )

    manifest[
        "Analysis Content Role"
    ] = "EXCLUDED_NON_" + source_name

    manifest[
        "Records Normalized"
    ] = 0

    if source_name == "CDR":
        manifest.loc[
            source_types.eq(
                "CDR"
            ),
            "Analysis Content Role",
        ] = "PRIMARY_CONTENT"

        manifest.loc[
            source_types.eq(
                "CDR"
            ),
            "Records Normalized",
        ] = 1

        identifiers = [
            IMEISV_16,
        ]

        frames = {
            IMEISV_16: pd.DataFrame(
                [
                    {
                        "target": "9000000001",
                    }
                ]
            )
        }

    elif source_name == "IPDR":
        ipdr_indexes = list(
            manifest.index[
                source_types.eq(
                    "IPDR"
                )
            ]
        )

        manifest.loc[
            ipdr_indexes,
            "Analysis Content Role",
        ] = "DUPLICATE_CONTENT"

        # Deliberately make the wrong-folder copy primary.
        manifest.at[
            ipdr_indexes[
                1
            ],
            "Analysis Content Role",
        ] = "PRIMARY_CONTENT"

        manifest.at[
            ipdr_indexes[
                1
            ],
            "Records Normalized",
        ] = 1

        manifest.at[
            ipdr_indexes[
                0
            ],
            "Analysis Duplicate Of",
        ] = manifest.at[
            ipdr_indexes[
                1
            ],
            "Source Path",
        ]

        identifiers = [
            IMEI_15,
        ]

        frames = {
            IMEI_15: pd.DataFrame(
                [
                    {
                        "imei": IMEISV_16,
                    }
                ]
            )
        }

    else:
        manifest.loc[
            source_types.eq(
                "GPRS"
            ),
            "Analysis Content Role",
        ] = "PRIMARY_CONTENT"

        manifest.loc[
            source_types.eq(
                "GPRS"
            ),
            "Records Normalized",
        ] = 1

        identifiers = [
            GPRS_IMEI,
        ]

        frames = {
            GPRS_IMEI: pd.DataFrame(
                [
                    {
                        "imei": GPRS_IMEI,
                    }
                ]
            )
        }

    return {
        "folder": Path(
            "/evidence/root"
        ),
        "files_found": len(
            manifest
        ),
        "identifiers": identifiers,
        "device_frames": frames,
        "acquisition_manifest": manifest,
        "all_content_groups": 3,
        "supported_content_groups": len(
            identifiers
        ),
        "non_source_acquisitions": (
            len(
                manifest
            )
            - int(
                source_types.eq(
                    source_name
                ).sum()
            )
        ),
        "duplicate_source_acquisitions": 1
        if source_name == "IPDR"
        else 0,
        "analytical_records": 1,
        "warnings": [],
        "errors": [],
    }


def test_root_inventory_is_content_based_and_cross_folder_safe(
    monkeypatch,
    tmp_path: Path,
):
    calls = []

    def fake_loader(
        *,
        folder,
        expected_source_type,
        supported_suffixes,
        inspect_file,
        normalize_file,
    ):
        calls.append(
            (
                Path(
                    folder
                ),
                expected_source_type,
            )
        )

        return _source_inventory(
            expected_source_type
        )

    monkeypatch.setattr(
        device_unified_inventory,
        "load_dedicated_evidence_inventory",
        fake_loader,
    )

    result = (
        device_unified_inventory
        .load_unified_device_inventory(
            folder=tmp_path,
            supported_suffixes={
                ".csv",
            },
            inspect_file=lambda path: {},
            normalizers={
                "CDR": lambda path, **kwargs: {},
                "IPDR": lambda path, **kwargs: {},
                "GPRS": lambda path, **kwargs: {},
            },
        )
    )

    assert [
        source
        for _, source in calls
    ] == [
        "CDR",
        "IPDR",
        "GPRS",
    ]

    assert all(
        folder == tmp_path.resolve()
        for folder, _ in calls
    )

    assert result[
        "files_found"
    ] == 4

    assert result[
        "all_content_groups"
    ] == 3

    assert result[
        "cross_folder_content_groups"
    ] == 1

    assert set(
        result[
            "identifiers"
        ]
    ) == {
        IMEI_15,
        IMEISV_16,
        GPRS_IMEI,
    }

    manifest = result[
        "acquisition_manifest"
    ]

    ipdr_group = manifest.loc[
        manifest[
            "SHA-256"
        ].eq(
            "b" * 64
        )
    ]

    primary = ipdr_group.loc[
        ipdr_group[
            "Analysis Content Role"
        ].eq(
            "PRIMARY_CONTENT"
        )
    ]

    assert len(
        primary
    ) == 1

    assert primary.iloc[
        0
    ][
        "Relative Path"
    ] == "ipdr/b.csv"

    assert primary.iloc[
        0
    ][
        "Records Normalized"
    ] == 1

    assert GPRS_IMEI in result[
        "source_frames"
    ][
        "GPRS"
    ]


def test_identifier_scope_joins_same_device_family():
    inventory = {
        "source_frames": {
            "CDR": {
                IMEISV_16: pd.DataFrame(
                    [
                        {
                            "source": "cdr",
                        }
                    ]
                )
            },
            "IPDR": {
                IMEI_15: pd.DataFrame(
                    [
                        {
                            "source": "ipdr",
                        }
                    ]
                )
            },
            "GPRS": {},
        },
        "acquisition_manifest": pd.DataFrame(
            [
                {
                    "Query Identifier": IMEISV_16,
                    "Source Type": "CDR",
                    "Inspection Status": "HAS_DATA",
                    "Analysis Content Role": "PRIMARY_CONTENT",
                },
                {
                    "Query Identifier": IMEI_15,
                    "Source Type": "IPDR",
                    "Inspection Status": "HAS_DATA",
                    "Analysis Content Role": "PRIMARY_CONTENT",
                },
            ]
        ),
    }

    scope = (
        device_unified_inventory
        .build_unified_identifier_scope(
            inventory,
            IMEI_15,
        )
    )

    assert scope[
        "device_family"
    ] == IMEI_15[
        :14
    ]

    assert len(
        scope[
            "source_frames"
        ][
            "cdr"
        ]
    ) == 1

    assert len(
        scope[
            "source_frames"
        ][
            "ipdr"
        ]
    ) == 1

    assert len(
        scope[
            "acquisition_manifest"
        ]
    ) == 2


def test_valid_empty_source_updates_unified_status():
    analysis = build_unified_imei_investigation(
        IMEI_15
    )

    result = (
        imei_device_controller
        ._apply_unified_empty_sources(
            analysis,
            {
                "GPRS",
            },
        )
    )

    assert result[
        "overall_status"
    ] == "EMPTY_NO_DATA"

    summary = result[
        "source_summary"
    ].set_index(
        "Evidence Source"
    )

    assert summary.loc[
        "GPRS",
        "Status",
    ] == "EMPTY_NO_DATA"

    assert summary.loc[
        "CDR",
        "Status",
    ] == "NO_INPUT"

    assert summary.loc[
        "IPDR",
        "Status",
    ] == "NO_INPUT"


def _patch_services(
    monkeypatch,
    tmp_path: Path,
):
    calls = {
        "targets": [],
        "reports": [],
        "runs": [],
        "events": [],
    }

    monkeypatch.setattr(
        imei_device_controller,
        "case_report_dir",
        lambda case_id, report_type: tmp_path,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "register_target",
        lambda *args, **kwargs: calls[
            "targets"
        ].append(
            (
                args,
                kwargs,
            )
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "register_report",
        lambda *args, **kwargs: calls[
            "reports"
        ].append(
            (
                args,
                kwargs,
            )
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "register_analysis_run",
        lambda *args, **kwargs: calls[
            "runs"
        ].append(
            (
                args,
                kwargs,
            )
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "log_case_event",
        lambda *args, **kwargs: calls[
            "events"
        ].append(
            (
                args,
                kwargs,
            )
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_print_source_summary",
        lambda analysis: None,
    )

    return calls


def _found_analysis(
    identifier: str,
) -> dict:
    timeline = pd.DataFrame(
        [
            {
                "Evidence Source": "CDR",
            }
        ]
    )

    return {
        "requested_imei": identifier,
        "overall_status": "FOUND",
        "message": "Found.",
        "source_summary": pd.DataFrame(
            [
                {
                    "Evidence Source": "CDR",
                    "Status": "FOUND",
                    "Evidence Unit": "CDR records",
                    "Matched Count": 1,
                    "Message": "Found.",
                },
                {
                    "Evidence Source": "IPDR",
                    "Status": "NO_INPUT",
                    "Evidence Unit": "IPDR records",
                    "Matched Count": 0,
                    "Message": "No input.",
                },
                {
                    "Evidence Source": "GPRS",
                    "Status": "NO_INPUT",
                    "Evidence Unit": "GPRS sessions",
                    "Matched Count": 0,
                    "Message": "No input.",
                },
            ]
        ),
        "associated_identities": pd.DataFrame(),
        "cross_source_timeline": timeline,
        "cdr": {
            "status": "FOUND",
            "timeline": timeline,
            "towers": pd.DataFrame(),
        },
        "ipdr": {
            "status": "NO_INPUT",
            "timeline": pd.DataFrame(),
            "cells": pd.DataFrame(),
        },
        "gprs": {
            "status": "NO_INPUT",
            "timeline": pd.DataFrame(),
            "cells": pd.DataFrame(),
        },
        "review_indicators": pd.DataFrame(),
        "data_quality": pd.DataFrame(),
    }


def test_automatic_unified_runs_without_manual_prompt(
    monkeypatch,
    tmp_path: Path,
):
    calls = _patch_services(
        monkeypatch,
        tmp_path,
    )

    cdr_frame = pd.DataFrame(
        [
            {
                "target": "9000000001",
            }
        ]
    )

    inventory = {
        "folder": tmp_path,
        "files_found": 1,
        "identifiers": [
            IMEI_15,
        ],
        "source_frames": {
            "CDR": {
                IMEI_15: cdr_frame,
            },
            "IPDR": {},
            "GPRS": {},
        },
        "acquisition_manifest": pd.DataFrame(
            [
                {
                    "Query Identifier": IMEI_15,
                    "Source Type": "CDR",
                    "Inspection Status": "HAS_DATA",
                    "Analysis Content Role": "PRIMARY_CONTENT",
                }
            ]
        ),
        "all_content_groups": 1,
        "repeated_content_groups": 0,
        "cross_folder_content_groups": 0,
        "duplicate_acquisitions": 0,
        "source_record_counts": {
            "CDR": 1,
            "IPDR": 0,
            "GPRS": 0,
        },
        "warnings": [],
        "errors": [],
    }

    monkeypatch.setattr(
        imei_device_controller,
        "_load_unified_imei_inventory",
        lambda case_id: inventory,
    )

    captured = {}

    def fake_builder(
        requested_imei,
        **kwargs,
    ):
        captured[
            "requested_imei"
        ] = requested_imei

        captured.update(
            kwargs
        )

        return _found_analysis(
            requested_imei
        )

    monkeypatch.setattr(
        imei_device_controller,
        "build_unified_imei_investigation",
        fake_builder,
    )

    report = tmp_path / "unified.xlsx"

    monkeypatch.setattr(
        imei_device_controller,
        "generate_imei_device_report",
        lambda **kwargs: report,
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_execute",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "Manual unified workflow must not run."
            )
        ),
    )

    result = (
        imei_device_controller
        ._execute_auto_detected_imei_unified(
            {
                "case_id": "CASE-001",
            }
        )
    )

    assert result[
        "identifiers"
    ] == [
        IMEI_15,
    ]

    assert len(
        result[
            "single_results"
        ]
    ) == 1

    assert captured[
        "requested_imei"
    ] == IMEI_15

    assert captured[
        "loaded_cdrs"
    ] is not None

    assert captured[
        "ipdr_dataframe"
    ] is None

    assert captured[
        "gprs_dataframe"
    ] is None

    assert calls[
        "reports"
    ][
        0
    ][
        1
    ][
        "report_type"
    ] == "UNIFIED_IMEI_ANALYSIS"


def test_missing_unified_identifier_uses_manual_fallback(
    monkeypatch,
    tmp_path: Path,
):
    inventory = {
        "folder": tmp_path,
        "files_found": 0,
        "identifiers": [],
        "source_frames": {
            "CDR": {},
            "IPDR": {},
            "GPRS": {},
        },
        "acquisition_manifest": pd.DataFrame(),
        "all_content_groups": 0,
        "repeated_content_groups": 0,
        "cross_folder_content_groups": 0,
        "duplicate_acquisitions": 0,
        "source_record_counts": {
            "CDR": 0,
            "IPDR": 0,
            "GPRS": 0,
        },
        "warnings": [],
        "errors": [],
    }

    monkeypatch.setattr(
        imei_device_controller,
        "_load_unified_imei_inventory",
        lambda case_id: inventory,
    )

    captured = {}

    def fake_execute(
        case,
        *,
        mode,
        requested_imei=None,
    ):
        captured[
            "mode"
        ] = mode

        return {
            "manual": True,
        }

    monkeypatch.setattr(
        imei_device_controller,
        "_execute",
        fake_execute,
    )

    result = (
        imei_device_controller
        ._execute_auto_detected_imei_unified(
            {
                "case_id": "CASE-001",
            }
        )
    )

    assert captured[
        "mode"
    ] == "unified"

    assert result[
        "manual"
    ] is True


def test_menu_option_four_routes_to_automatic_unified(
    monkeypatch,
):
    choices = iter(
        [
            "4",
            "0",
        ]
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_menu",
        lambda case: next(
            choices
        ),
    )

    calls = []

    monkeypatch.setattr(
        imei_device_controller,
        "_execute_auto_detected_imei_unified",
        lambda case: calls.append(
            case
        ),
    )

    monkeypatch.setattr(
        imei_device_controller,
        "_execute",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "Manual unified workflow must not be selected."
            )
        ),
    )

    case = {
        "case_id": "CASE-001",
    }

    imei_device_controller.handle_imei_device_workspace(
        case
    )

    assert calls == [
        case,
    ]
