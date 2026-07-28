"""Case-aware IMEI and device investigation workspace.

The controller reuses existing CDR, IPDR and GPRS loaders and the tested
unified IMEI analysis service. It does not implement duplicate parsing or
source-specific analysis logic.
"""

from __future__ import annotations


from pathlib import Path
from typing import Any

import pandas as pd

from modules.controllers.device_evidence_batch import (
    load_dedicated_evidence_inventory,
)

from modules.analysis.device import (
    build_unified_imei_investigation,
)
from modules.analysis.device.imei_common import (
    build_common_imei_cdr_analysis,
)
from modules.analysis.device.imei_ipdr_common import (
    build_common_imei_ipdr_analysis,
)
from modules.cases import (
    case_report_dir,
    log_case_event,
    register_analysis_run,
    register_report,
    register_target,
)
from modules.loader.imei_evidence_loader import (
    SUPPORTED_SUFFIXES as IMEI_EVIDENCE_SUFFIXES,
    inspect_imei_evidence_file,
    normalize_imei_cdr_file,
    normalize_imei_gprs_file,
    normalize_imei_ipdr_file,
)
from modules.loader.telecom_identifiers import (
    normalize_imei,
)
from modules.reporting import (
    generate_imei_common_report,
    generate_imei_device_report,
)
from modules.reporting import (
    generate_imei_ipdr_common_report,
)
SUPPORTED_EVIDENCE_SUFFIXES = {
    ".csv",
    ".txt",
    ".tsv",
    ".xlsx",
    ".xls",
}

MODE_CONFIG = {
    "cdr": {
        "title": "IMEI CDR Analysis",
        "analysis_type": "IMEI_CDR_ANALYSIS",
        "report_type": "IMEI_CDR_ANALYSIS",
    },
    "ipdr": {
        "title": "IMEI IPDR Analysis",
        "analysis_type": "IMEI_IPDR_ANALYSIS",
        "report_type": "IMEI_IPDR_ANALYSIS",
    },
    "gprs": {
        "title": "IMEI GPRS Analysis",
        "analysis_type": "IMEI_GPRS_ANALYSIS",
        "report_type": "IMEI_GPRS_ANALYSIS",
    },
    "unified": {
        "title": "Unified IMEI Analysis",
        "analysis_type": "UNIFIED_IMEI_ANALYSIS",
        "report_type": "UNIFIED_IMEI_ANALYSIS",
    },
}


def _menu(
    case: dict[str, Any],
) -> str:
    print("\n" + "=" * 78)
    print(
        "IMEI / DEVICE ANALYSIS | "
        f"{case.get('case_id', '')} | "
        f"{case.get('case_name', '')}"
    )
    print("=" * 78)
    print("1. IMEI CDR Analysis")
    print("2. IMEI IPDR Analysis")
    print("3. IMEI GPRS Analysis")
    print("4. Unified IMEI Analysis")
    print("0. Back to Analysis Workspace")

    return input(
        "\nChoose Action: "
    ).strip()


def _prompt_imei() -> str:
    print("\n" + "=" * 72)
    print("ENTER DEVICE IDENTIFIER")
    print("=" * 72)
    print(
        "Enter the exact 15-digit IMEI or "
        "16-digit IMEISV."
    )

    return input(
        "\nIMEI / IMEISV: "
    ).strip()


def _folder_has_supported_files(
    folder: Path,
) -> bool:
    return (
        folder.is_dir()
        and any(
            path.is_file()
            and path.suffix.lower()
            in SUPPORTED_EVIDENCE_SUFFIXES
            for path in folder.rglob("*")
        )
    )



PROJECT_ROOT = Path(
    __file__
).resolve().parents[
    2
]


def resolve_imei_cdr_input_folder(
    case_id: str,
) -> Path:
    """Return the canonical dedicated IMEI CDR input folder."""

    del case_id

    return (
        PROJECT_ROOT
        / "data"
        / "device"
        / "imei"
        / "cdr"
    )


def resolve_imei_ipdr_input_folder(
    case_id: str,
) -> Path:
    """Return the canonical dedicated IMEI IPDR input folder."""

    del case_id

    return (
        PROJECT_ROOT
        / "data"
        / "device"
        / "imei"
        / "ipdr"
    )


def resolve_imei_gprs_input_folder(
    case_id: str,
) -> Path:
    """Return the canonical dedicated IMEI GPRS input folder."""

    del case_id

    return (
        PROJECT_ROOT
        / "data"
        / "device"
        / "imei"
        / "gprs"
    )
def _load_dedicated_imei_cdr_inventory(
    case_id: str,
) -> dict[str, Any]:
    """Load dedicated CDR evidence through the reusable inventory layer."""

    inventory = load_dedicated_evidence_inventory(
        folder=resolve_imei_cdr_input_folder(
            case_id
        ),
        expected_source_type="CDR",
        supported_suffixes=IMEI_EVIDENCE_SUFFIXES,
        inspect_file=inspect_imei_evidence_file,
        normalize_file=normalize_imei_cdr_file,
    )

    return {
        **inventory,
        "supported_cdr_content_groups": inventory[
            "supported_content_groups"
        ],
        "non_cdr_acquisitions": inventory[
            "non_source_acquisitions"
        ],
        "duplicate_cdr_acquisitions": inventory[
            "duplicate_source_acquisitions"
        ],
    }


def _load_dedicated_imei_ipdr_inventory(
    case_id: str,
) -> dict[str, Any]:
    """Load dedicated IPDR evidence through the reusable inventory layer."""

    inventory = load_dedicated_evidence_inventory(
        folder=resolve_imei_ipdr_input_folder(
            case_id
        ),
        expected_source_type="IPDR",
        supported_suffixes=IMEI_EVIDENCE_SUFFIXES,
        inspect_file=inspect_imei_evidence_file,
        normalize_file=normalize_imei_ipdr_file,
    )

    return {
        **inventory,
        "supported_ipdr_content_groups": inventory[
            "supported_content_groups"
        ],
        "non_ipdr_acquisitions": inventory[
            "non_source_acquisitions"
        ],
        "duplicate_ipdr_acquisitions": inventory[
            "duplicate_source_acquisitions"
        ],
    }


def _load_dedicated_imei_gprs_inventory(
    case_id: str,
) -> dict[str, Any]:
    """Load dedicated GPRS evidence through the reusable inventory layer."""

    inventory = load_dedicated_evidence_inventory(
        folder=resolve_imei_gprs_input_folder(
            case_id
        ),
        expected_source_type="GPRS",
        supported_suffixes=IMEI_EVIDENCE_SUFFIXES,
        inspect_file=inspect_imei_evidence_file,
        normalize_file=normalize_imei_gprs_file,
    )

    return {
        **inventory,
        "supported_gprs_content_groups": inventory[
            "supported_content_groups"
        ],
        "non_gprs_acquisitions": inventory[
            "non_source_acquisitions"
        ],
        "duplicate_gprs_acquisitions": inventory[
            "duplicate_source_acquisitions"
        ],
    }
def _dedicated_cdr_payload(
    dataframe: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    """Convert canonical dedicated CDR rows to the CDR analysis contract."""

    if (
        not isinstance(
            dataframe,
            pd.DataFrame,
        )
        or dataframe.empty
    ):
        return {}

    if "target" in dataframe.columns:
        targets = (
            dataframe[
                "target"
            ]
            .astype(
                "string"
            )
            .fillna(
                ""
            )
            .str.strip()
        )

    else:
        targets = pd.Series(
            "",
            index=dataframe.index,
            dtype="string",
        )

    result: dict[
        str,
        dict[str, Any],
    ] = {}

    distinct_targets = sorted(
        {
            value
            for value in targets
            if value
        }
    )

    for target in distinct_targets:
        subset = dataframe.loc[
            targets.eq(
                target
            )
        ].copy(
            deep=True
        )

        result[
            target
        ] = {
            "df": subset,
        }

    missing_target = targets.eq(
        ""
    )

    if missing_target.any():
        result[
            "UNKNOWN_TARGET"
        ] = {
            "df": dataframe.loc[
                missing_target
            ].copy(
                deep=True
            ),
        }

    return result


def _build_empty_no_data_imei_analysis(
    identifier: str,
    *,
    source_key: str = "cdr",
) -> dict[str, Any]:
    """Build an investigator result for a valid empty operator report."""

    source_key = str(
        source_key
    ).strip().lower()

    source_config = {
        "cdr": {
            "name": "CDR",
            "evidence_unit": "CDR records",
            "record_label": "CDR event rows",
        },
        "ipdr": {
            "name": "IPDR",
            "evidence_unit": "IPDR records",
            "record_label": "IPDR record rows",
        },
        "gprs": {
            "name": "GPRS",
            "evidence_unit": "GPRS sessions",
            "record_label": "GPRS session rows",
        },
    }

    if source_key not in source_config:
        raise ValueError(
            f"Unsupported empty-report source: {source_key}"
        )

    selected = source_config[
        source_key
    ]

    message = (
        f"A valid dedicated IMEI {selected['name']} report "
        "was received, but the operator report contains "
        "no result records."
    )

    source_results: dict[
        str,
        dict[str, Any],
    ] = {}

    summary_rows = []

    for key in (
        "cdr",
        "ipdr",
        "gprs",
    ):
        config = source_config[
            key
        ]

        is_selected = (
            key == source_key
        )

        status = (
            "EMPTY_NO_DATA"
            if is_selected
            else "NO_INPUT"
        )

        source_message = (
            message
            if is_selected
            else (
                f"No {config['name']} evidence selected."
            )
        )

        summary_rows.append(
            {
                "Evidence Source": config[
                    "name"
                ],
                "Status": status,
                "Evidence Unit": config[
                    "evidence_unit"
                ],
                "Matched Count": 0,
                "Message": source_message,
            }
        )

        payload = {
            "status": status,
            "message": source_message,
            "timeline": pd.DataFrame(),
        }

        if key == "cdr":
            payload[
                "towers"
            ] = pd.DataFrame()

        else:
            payload[
                "cells"
            ] = pd.DataFrame()

        source_results[
            key
        ] = payload

    return {
        "requested_imei": identifier,
        "overall_status": "EMPTY_NO_DATA",
        "message": message,
        "source_summary": pd.DataFrame(
            summary_rows
        ),
        "associated_identities": pd.DataFrame(),
        "cross_source_timeline": pd.DataFrame(),
        "cdr": source_results[
            "cdr"
        ],
        "ipdr": source_results[
            "ipdr"
        ],
        "gprs": source_results[
            "gprs"
        ],
        "review_indicators": pd.DataFrame(
            [
                {
                    "Evidence Source": selected[
                        "name"
                    ],
                    "Indicator": (
                        "Valid empty operator report"
                    ),
                    "Observation": (
                        "The report query was recognized, "
                        f"but no {selected['record_label']} "
                        "were supplied."
                    ),
                    "Caution": (
                        "This is not the same as failing to find "
                        "an identifier in loaded event data."
                    ),
                }
            ]
        ),
        "data_quality": pd.DataFrame(
            [
                {
                    "Evidence Source": selected[
                        "name"
                    ],
                    "Check": "Valid empty report",
                    "Count": 1,
                    "Meaning": (
                        "Operator evidence contains no result records."
                    ),
                }
            ]
        ),
    }
def _run_auto_single_imei_source(
    *,
    case: dict[str, Any],
    source_key: str,
    identifier: str,
    dataframe: pd.DataFrame,
    acquisition_manifest: pd.DataFrame,
) -> dict[str, Any]:
    """Run one automatically detected dedicated IMEI source analysis."""

    source_key = str(
        source_key
    ).strip().lower()

    source_config = {
        "cdr": {
            "name": "CDR",
            "analysis_type": "IMEI_CDR_ANALYSIS",
            "report_type": "IMEI_CDR_ANALYSIS",
            "event_prefix": "IMEI_CDR_AUTO_SINGLE",
        },
        "ipdr": {
            "name": "IPDR",
            "analysis_type": "IMEI_IPDR_ANALYSIS",
            "report_type": "IMEI_IPDR_ANALYSIS",
            "event_prefix": "IMEI_IPDR_AUTO_SINGLE",
        },
        "gprs": {
            "name": "GPRS",
            "analysis_type": "IMEI_GPRS_ANALYSIS",
            "report_type": "IMEI_GPRS_ANALYSIS",
            "event_prefix": "IMEI_GPRS_AUTO_SINGLE",
        },
    }

    if source_key not in source_config:
        raise ValueError(
            f"Unsupported automatic IMEI source: {source_key}"
        )

    config = source_config[
        source_key
    ]

    case_id = str(
        case.get(
            "case_id",
            "",
        )
    ).strip()

    device_manifest = pd.DataFrame()

    if (
        isinstance(
            acquisition_manifest,
            pd.DataFrame,
        )
        and not acquisition_manifest.empty
        and "Query Identifier"
        in acquisition_manifest.columns
    ):
        manifest_mask = (
            acquisition_manifest[
                "Query Identifier"
            ]
            .astype(
                str
            )
            .str.strip()
            .eq(
                identifier
            )
        )

        if "Source Type" in acquisition_manifest.columns:
            manifest_mask = (
                manifest_mask
                & acquisition_manifest[
                    "Source Type"
                ]
                .astype(
                    str
                )
                .str.strip()
                .str.upper()
                .eq(
                    source_key.upper()
                )
            )

        device_manifest = (
            acquisition_manifest.loc[
                manifest_mask
            ]
            .reset_index(
                drop=True
            )
            .copy(
                deep=True
            )
        )

    register_target(
        case_id,
        target_type="IMEI",
        target_value=identifier,
        description=(
            "Automatically detected dedicated "
            f"IMEI {config['name']} query"
        ),
    )

    log_case_event(
        case_id,
        action=(
            config[
                "event_prefix"
            ]
            + "_STARTED"
        ),
        details={
            "requested_imei": identifier,
            "input_records": len(
                dataframe
            ),
        },
    )

    inspection_statuses = set()

    if (
        not device_manifest.empty
        and "Inspection Status"
        in device_manifest.columns
    ):
        inspection_statuses = {
            value
            for value in (
                device_manifest[
                    "Inspection Status"
                ]
                .astype(
                    str
                )
                .str.upper()
                .str.strip()
            )
            if value
        }

    valid_empty_report = (
        (
            not isinstance(
                dataframe,
                pd.DataFrame,
            )
            or dataframe.empty
        )
        and bool(
            inspection_statuses
        )
        and inspection_statuses.issubset(
            {
                "EMPTY_NO_DATA",
            }
        )
    )

    if valid_empty_report:
        analysis = _build_empty_no_data_imei_analysis(
            identifier,
            source_key=source_key,
        )

    else:
        source_arguments = {
            "loaded_cdrs": None,
            "ipdr_dataframe": None,
            "gprs_dataframe": None,
        }

        if source_key == "cdr":
            source_arguments[
                "loaded_cdrs"
            ] = _dedicated_cdr_payload(
                dataframe
            )

        elif source_key == "ipdr":
            source_arguments[
                "ipdr_dataframe"
            ] = dataframe

        else:
            source_arguments[
                "gprs_dataframe"
            ] = dataframe

        analysis = build_unified_imei_investigation(
            identifier,
            **source_arguments,
        )

    analysis[
        "acquisition_manifest"
    ] = device_manifest

    _print_source_summary(
        analysis
    )

    report_path = None

    if str(
        analysis.get(
            "overall_status",
            "",
        )
    ).upper() in {
        "FOUND",
        "PARTIAL",
        "EMPTY_NO_DATA",
    }:
        report_path = generate_imei_device_report(
            case=case,
            analysis=analysis,
            output_dir=case_report_dir(
                case_id,
                "imei_device",
            ),
        )

    if report_path:
        register_report(
            case_id,
            report_type=config[
                "report_type"
            ],
            report_path=report_path,
        )

        if valid_empty_report:
            print(
                "[+] Empty-report IMEI "
                f"{config['name']} workbook: {report_path}"
            )

        else:
            print(
                "[+] Single IMEI "
                f"{config['name']} report: {report_path}"
            )

    else:
        print(
            f"[INFO] {identifier}: no investigator workbook "
            "was created."
        )

    timeline = analysis.get(
        "cross_source_timeline"
    )

    output_records = (
        len(
            timeline
        )
        if isinstance(
            timeline,
            pd.DataFrame,
        )
        else 0
    )

    overall_status = str(
        analysis.get(
            "overall_status",
            "",
        )
    ).upper()

    run_status = (
        "FAILED"
        if overall_status == "ERROR"
        else "COMPLETED"
    )

    register_analysis_run(
        case_id,
        analysis_type=config[
            "analysis_type"
        ],
        status=run_status,
        input_records=len(
            dataframe
        ),
        output_records=output_records,
        report_path=str(
            report_path or ""
        ),
        **(
            {
                "error_message": str(
                    analysis.get(
                        "message",
                        "",
                    )
                )
            }
            if run_status == "FAILED"
            else {}
        ),
    )

    log_case_event(
        case_id,
        action=(
            config[
                "event_prefix"
            ]
            + "_"
            + run_status
        ),
        details={
            "requested_imei": identifier,
            "input_records": len(
                dataframe
            ),
            "output_records": output_records,
            "overall_status": overall_status,
            "report_created": bool(
                report_path
            ),
        },
    )

    return {
        "identifier": identifier,
        "analysis": analysis,
        "report": report_path,
        "input_records": len(
            dataframe
        ),
        "output_records": output_records,
    }


def _run_auto_single_imei_cdr(
    *,
    case: dict[str, Any],
    identifier: str,
    dataframe: pd.DataFrame,
    acquisition_manifest: pd.DataFrame,
) -> dict[str, Any]:
    """Run one automatically detected dedicated IMEI CDR analysis."""

    return _run_auto_single_imei_source(
        case=case,
        source_key="cdr",
        identifier=identifier,
        dataframe=dataframe,
        acquisition_manifest=acquisition_manifest,
    )


def _run_auto_single_imei_ipdr(
    *,
    case: dict[str, Any],
    identifier: str,
    dataframe: pd.DataFrame,
    acquisition_manifest: pd.DataFrame,
) -> dict[str, Any]:
    """Run one automatically detected dedicated IMEI IPDR analysis."""

    return _run_auto_single_imei_source(
        case=case,
        source_key="ipdr",
        identifier=identifier,
        dataframe=dataframe,
        acquisition_manifest=acquisition_manifest,
    )


def _run_auto_single_imei_gprs(
    *,
    case: dict[str, Any],
    identifier: str,
    dataframe: pd.DataFrame,
    acquisition_manifest: pd.DataFrame,
) -> dict[str, Any]:
    """Run one automatically detected dedicated IMEI GPRS analysis."""

    return _run_auto_single_imei_source(
        case=case,
        source_key="gprs",
        identifier=identifier,
        dataframe=dataframe,
        acquisition_manifest=acquisition_manifest,
    )

def _execute_auto_detected_imei_cdr(
    case: dict[str, Any],
) -> dict[str, Any]:
    """Run all single analyses and common analysis when applicable."""

    case_id = str(
        case.get(
            "case_id",
            "",
        )
    ).strip()

    inventory = _load_dedicated_imei_cdr_inventory(
        case_id
    )

    identifiers = inventory[
        "identifiers"
    ]

    print("\n" + "=" * 78)
    print("DEDICATED IMEI CDR AUTO-DETECTION")
    print("=" * 78)
    print(
        f"Input Folder             : {inventory['folder']}"
    )
    print(
        f"Physical Acquisitions    : {inventory['files_found']}"
    )
    print(
        "All Content Groups      : "
        f"{inventory.get('all_content_groups', 0)}"
    )
    print(
        "Supported CDR Groups    : "
        f"{inventory.get('supported_cdr_content_groups', 0)}"
    )
    print(
        "Non-CDR Acquisitions    : "
        f"{inventory.get('non_cdr_acquisitions', 0)}"
    )
    print(
        "Duplicate CDR Copies    : "
        f"{inventory.get('duplicate_cdr_acquisitions', 0)}"
    )
    print(
        f"Detected Identifiers     : {len(identifiers)}"
    )
    print(
        "Analytical CDR Records  : "
        f"{inventory['analytical_records']:,}"
    )

    for warning in inventory.get(
        "warnings",
        [],
    ):
        print(
            f"[WARNING] {warning}"
        )

    for error in inventory.get(
        "errors",
        [],
    ):
        print(
            f"[WARNING] {error}"
        )

    if not identifiers:
        print(
            "[-] No supported report-query IMEI/IMEISV "
            "could be detected."
        )
        print(
            "[INFO] Manual entry will be used only as fallback."
        )

        return _execute(
            case,
            mode="cdr",
        )

    if len(
        identifiers
    ) == 1:
        print(
            "[+] One unique identifier detected. "
            "Starting automatic single analysis."
        )

    else:
        print(
            f"[+] {len(identifiers)} unique identifiers detected."
        )
        print(
            "[+] Running one single analysis per identifier "
            "and one common cross-device analysis."
        )

    single_results = []

    for index, identifier in enumerate(
        identifiers,
        start=1,
    ):
        print("\n" + "-" * 78)
        print(
            f"SINGLE IMEI ANALYSIS "
            f"{index}/{len(identifiers)}: {identifier}"
        )
        print("-" * 78)

        result = _run_auto_single_imei_cdr(
            case=case,
            identifier=identifier,
            dataframe=inventory[
                "device_frames"
            ].get(
                identifier,
                pd.DataFrame(),
            ),
            acquisition_manifest=inventory[
                "acquisition_manifest"
            ],
        )

        single_results.append(
            result
        )

    common_result = None

    if len(
        identifiers
    ) > 1:
        print("\n" + "=" * 78)
        print("COMMON / CROSS-DEVICE IMEI ANALYSIS")
        print("=" * 78)

        common_analysis = build_common_imei_cdr_analysis(
            inventory[
                "device_frames"
            ],
            inventory[
                "acquisition_manifest"
            ],
        )

        common_report = generate_imei_common_report(
            case=case,
            analysis=common_analysis,
            output_dir=case_report_dir(
                case_id,
                "imei_device",
            ),
        )

        if common_report:
            register_report(
                case_id,
                report_type="IMEI_CDR_COMMON_ANALYSIS",
                report_path=common_report,
            )

            print(
                f"[+] Common IMEI report: {common_report}"
            )

        register_analysis_run(
            case_id,
            analysis_type="IMEI_CDR_COMMON_ANALYSIS",
            status=(
                "COMPLETED"
                if common_analysis.get(
                    "status"
                )
                == "FOUND"
                else "FAILED"
            ),
            input_records=inventory[
                "analytical_records"
            ],
            output_records=len(
                common_analysis.get(
                    "cross_device_timeline",
                    pd.DataFrame(),
                )
            ),
            report_path=str(
                common_report or ""
            ),
        )

        log_case_event(
            case_id,
            action="IMEI_CDR_COMMON_ANALYSIS_COMPLETED",
            details={
                "identifier_count": len(
                    identifiers
                ),
                "device_family_count": int(
                    common_analysis.get(
                        "device_family_count",
                        0,
                    )
                    or 0
                ),
                "input_records": inventory[
                    "analytical_records"
                ],
                "report_created": bool(
                    common_report
                ),
            },
        )

        common_result = {
            "analysis": common_analysis,
            "report": common_report,
        }

    return {
        "mode": "cdr",
        "automatic_detection": True,
        "identifiers": identifiers,
        "inventory": inventory,
        "single_results": single_results,
        "common_result": common_result,
        "input_records": inventory[
            "analytical_records"
        ],
    }


def _execute_auto_detected_imei_ipdr(
    case: dict[str, Any],
) -> dict[str, Any]:
    """Run automatic single and common IMEI IPDR analyses."""

    case_id = str(
        case.get(
            "case_id",
            "",
        )
    ).strip()

    inventory = _load_dedicated_imei_ipdr_inventory(
        case_id
    )

    identifiers = inventory[
        "identifiers"
    ]

    print("\n" + "=" * 78)
    print("DEDICATED IMEI IPDR AUTO-DETECTION")
    print("=" * 78)
    print(
        f"Input Folder             : {inventory['folder']}"
    )
    print(
        f"Physical Acquisitions    : {inventory['files_found']}"
    )
    print(
        "All Content Groups      : "
        f"{inventory.get('all_content_groups', 0)}"
    )
    print(
        "Supported IPDR Groups   : "
        f"{inventory.get('supported_ipdr_content_groups', 0)}"
    )
    print(
        "Non-IPDR Acquisitions   : "
        f"{inventory.get('non_ipdr_acquisitions', 0)}"
    )
    print(
        "Duplicate IPDR Copies   : "
        f"{inventory.get('duplicate_ipdr_acquisitions', 0)}"
    )
    print(
        f"Detected Identifiers     : {len(identifiers)}"
    )
    print(
        "Analytical IPDR Records : "
        f"{inventory['analytical_records']:,}"
    )

    for warning in inventory.get(
        "warnings",
        [],
    ):
        print(
            f"[WARNING] {warning}"
        )

    for error in inventory.get(
        "errors",
        [],
    ):
        print(
            f"[WARNING] {error}"
        )

    if not identifiers:
        print(
            "[-] No supported IPDR report-query IMEI/IMEISV "
            "could be detected."
        )
        print(
            "[INFO] Manual entry will be used only as fallback."
        )

        return _execute(
            case,
            mode="ipdr",
        )

    if len(
        identifiers
    ) == 1:
        print(
            "[+] One unique IPDR identifier detected. "
            "Starting automatic single analysis."
        )

    else:
        print(
            f"[+] {len(identifiers)} unique IPDR identifiers detected."
        )
        print(
            "[+] Running one single IPDR analysis per identifier "
            "and one common cross-device IPDR analysis."
        )

    single_results = []

    for index, identifier in enumerate(
        identifiers,
        start=1,
    ):
        print("\n" + "-" * 78)
        print(
            f"SINGLE IMEI IPDR ANALYSIS "
            f"{index}/{len(identifiers)}: {identifier}"
        )
        print("-" * 78)

        result = _run_auto_single_imei_ipdr(
            case=case,
            identifier=identifier,
            dataframe=inventory[
                "device_frames"
            ].get(
                identifier,
                pd.DataFrame(),
            ),
            acquisition_manifest=inventory[
                "acquisition_manifest"
            ],
        )

        single_results.append(
            result
        )

    common_result = None

    if len(
        identifiers
    ) > 1:
        print("\n" + "=" * 78)
        print("COMMON / CROSS-DEVICE IMEI IPDR ANALYSIS")
        print("=" * 78)

        common_analysis = build_common_imei_ipdr_analysis(
            inventory[
                "device_frames"
            ],
            inventory[
                "acquisition_manifest"
            ],
        )

        common_report = generate_imei_ipdr_common_report(
            case=case,
            analysis=common_analysis,
            output_dir=case_report_dir(
                case_id,
                "imei_device",
            ),
        )

        if common_report:
            register_report(
                case_id,
                report_type="IMEI_IPDR_COMMON_ANALYSIS",
                report_path=common_report,
            )

            print(
                "[+] Common IMEI IPDR report: "
                f"{common_report}"
            )

        else:
            print(
                "[INFO] Common IMEI IPDR workbook "
                "was not created."
            )

        common_status = str(
            common_analysis.get(
                "status",
                "",
            )
        ).upper()

        run_status = (
            "COMPLETED"
            if common_status == "FOUND"
            else "FAILED"
        )

        cross_device_timeline = common_analysis.get(
            "cross_device_timeline"
        )

        common_output_records = (
            len(
                cross_device_timeline
            )
            if isinstance(
                cross_device_timeline,
                pd.DataFrame,
            )
            else 0
        )

        register_analysis_run(
            case_id,
            analysis_type="IMEI_IPDR_COMMON_ANALYSIS",
            status=run_status,
            input_records=inventory[
                "analytical_records"
            ],
            output_records=common_output_records,
            report_path=str(
                common_report or ""
            ),
            **(
                {
                    "error_message": str(
                        common_analysis.get(
                            "message",
                            "",
                        )
                    )
                }
                if run_status == "FAILED"
                else {}
            ),
        )

        log_case_event(
            case_id,
            action=(
                "IMEI_IPDR_COMMON_ANALYSIS_"
                + run_status
            ),
            details={
                "identifier_count": len(
                    identifiers
                ),
                "device_family_count": int(
                    common_analysis.get(
                        "device_family_count",
                        0,
                    )
                    or 0
                ),
                "data_bearing_identifier_count": int(
                    common_analysis.get(
                        "data_bearing_device_count",
                        0,
                    )
                    or 0
                ),
                "empty_report_count": int(
                    common_analysis.get(
                        "empty_report_count",
                        0,
                    )
                    or 0
                ),
                "input_records": inventory[
                    "analytical_records"
                ],
                "output_records": common_output_records,
                "report_created": bool(
                    common_report
                ),
            },
        )

        common_result = {
            "analysis": common_analysis,
            "report": common_report,
            "input_records": inventory[
                "analytical_records"
            ],
            "output_records": common_output_records,
        }

    return {
        "mode": "ipdr",
        "automatic_detection": True,
        "identifiers": identifiers,
        "inventory": inventory,
        "single_results": single_results,
        "common_result": common_result,
        "input_records": inventory[
            "analytical_records"
        ],
    }


def _execute_auto_detected_imei_gprs(
    case: dict[str, Any],
) -> dict[str, Any]:
    """Run automatic single IMEI GPRS analyses."""

    case_id = str(
        case.get(
            "case_id",
            "",
        )
    ).strip()

    inventory = _load_dedicated_imei_gprs_inventory(
        case_id
    )

    identifiers = inventory[
        "identifiers"
    ]

    print("\n" + "=" * 78)
    print("DEDICATED IMEI GPRS AUTO-DETECTION")
    print("=" * 78)

    print(
        f"Input Folder             : {inventory['folder']}"
    )
    print(
        f"Physical Acquisitions    : {inventory['files_found']}"
    )
    print(
        "All Content Groups      : "
        f"{inventory.get('all_content_groups', 0)}"
    )
    print(
        "Supported GPRS Groups   : "
        f"{inventory.get('supported_gprs_content_groups', 0)}"
    )
    print(
        "Non-GPRS Acquisitions   : "
        f"{inventory.get('non_gprs_acquisitions', 0)}"
    )
    print(
        "Duplicate GPRS Copies   : "
        f"{inventory.get('duplicate_gprs_acquisitions', 0)}"
    )
    print(
        f"Detected Identifiers     : {len(identifiers)}"
    )
    print(
        "Analytical GPRS Sessions: "
        f"{inventory['analytical_records']:,}"
    )

    for warning in inventory.get(
        "warnings",
        [],
    ):
        print(
            f"[WARNING] {warning}"
        )

    for error in inventory.get(
        "errors",
        [],
    ):
        print(
            f"[WARNING] {error}"
        )

    if not identifiers:
        print(
            "[-] No supported GPRS report-query "
            "IMEI/IMEISV could be detected."
        )
        print(
            "[INFO] Manual entry will be used only as fallback."
        )

        return _execute(
            case,
            mode="gprs",
        )

    if len(
        identifiers
    ) == 1:
        print(
            "[+] One unique GPRS identifier detected. "
            "Starting automatic single analysis."
        )

    else:
        print(
            f"[+] {len(identifiers)} unique GPRS "
            "identifiers detected."
        )
        print(
            "[+] Running one single GPRS analysis "
            "per identifier."
        )
        print(
            "[INFO] Common GPRS analysis is not run "
            "in this phase."
        )

    single_results = []

    for index, identifier in enumerate(
        identifiers,
        start=1,
    ):
        print("\n" + "-" * 78)
        print(
            f"SINGLE IMEI GPRS ANALYSIS "
            f"{index}/{len(identifiers)}: {identifier}"
        )
        print("-" * 78)

        result = _run_auto_single_imei_gprs(
            case=case,
            identifier=identifier,
            dataframe=inventory[
                "device_frames"
            ].get(
                identifier,
                pd.DataFrame(),
            ),
            acquisition_manifest=inventory[
                "acquisition_manifest"
            ],
        )

        single_results.append(
            result
        )

    return {
        "mode": "gprs",
        "automatic_detection": True,
        "identifiers": identifiers,
        "inventory": inventory,
        "single_results": single_results,
        "common_result": None,
        "input_records": inventory[
            "analytical_records"
        ],
    }

def _load_cdr_evidence(
    case_id: str,
) -> dict[str, dict[str, Any]]:
    del case_id

    from modules.controllers.cdr_controller import (
        run_multiple,
    )

    loaded = run_multiple()

    if not isinstance(
        loaded,
        dict,
    ):
        raise TypeError(
            "Multiple CDR loader returned an invalid result."
        )

    result = {
        str(target): dict(info)
        for target, info in loaded.items()
        if (
            isinstance(
                info,
                dict,
            )
            and isinstance(
                info.get(
                    "df"
                ),
                pd.DataFrame,
            )
            and not info[
                "df"
            ].empty
        )
    }

    if not result:
        raise ValueError(
            "No valid CDR targets were loaded from "
            "the Multiple CDR input folder."
        )

    return result


def _load_ipdr_evidence(
    case_id: str,
) -> pd.DataFrame:
    from modules.controllers.ipdr_case_controller import (
        resolve_ipdr_input_folder,
    )
    from modules.loader.ipdr_loader import (
        load_ipdr_case,
    )

    frames: list[pd.DataFrame] = []
    load_errors: list[str] = []

    for mode in (
        "single",
        "multiple",
    ):
        folder = resolve_ipdr_input_folder(
            case_id,
            mode,
        )

        if not _folder_has_supported_files(
            folder
        ):
            continue

        result = load_ipdr_case(
            folder,
            recursive=True,
        )

        for warning in result.get(
            "warnings",
            [],
        ) or []:
            print(
                f"[WARNING] {mode.title()} IPDR: "
                f"{warning}"
            )

        if not result.get(
            "ok"
        ):
            load_errors.extend(
                str(error)
                for error in result.get(
                    "errors",
                    [],
                ) or []
            )
            continue

        dataframe = result.get(
            "data"
        )

        if (
            isinstance(
                dataframe,
                pd.DataFrame,
            )
            and not dataframe.empty
        ):
            frames.append(
                dataframe.copy()
            )

    if not frames:
        message = (
            "; ".join(
                load_errors
            )
            or (
                "No normalized IPDR event records "
                "were available."
            )
        )

        raise ValueError(
            message
        )

    return pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )


def _load_gprs_evidence(
    case_id: str,
) -> pd.DataFrame:
    from modules.controllers.tower_gprs_controller import (
        resolve_gprs_input_folder,
    )
    from modules.loader.gprs_dump_loader import (
        load_gprs_dump_case,
    )

    folder = resolve_gprs_input_folder(
        case_id
    )

    if not _folder_has_supported_files(
        folder
    ):
        raise FileNotFoundError(
            "No supported Tower GPRS input file was found."
        )

    result = load_gprs_dump_case(
        folder,
        recursive=True,
    )

    for warning in result.get(
        "warnings",
        [],
    ) or []:
        print(
            f"[WARNING] GPRS: {warning}"
        )

    if not result.get(
        "ok"
    ):
        message = "; ".join(
            str(error)
            for error in result.get(
                "errors",
                [],
            ) or []
        )

        raise ValueError(
            message
            or "Tower GPRS loading failed."
        )

    dataframe = result.get(
        "df"
    )

    if (
        not isinstance(
            dataframe,
            pd.DataFrame,
        )
        or dataframe.empty
    ):
        raise ValueError(
            "Normalized GPRS session data is unavailable."
        )

    return dataframe.copy()


def _record_count(
    source_name: str,
    payload: Any,
) -> int:
    if (
        source_name == "cdr"
        and isinstance(
            payload,
            dict,
        )
    ):
        return sum(
            len(
                info[
                    "df"
                ]
            )
            for info in payload.values()
            if (
                isinstance(
                    info,
                    dict,
                )
                and isinstance(
                    info.get(
                        "df"
                    ),
                    pd.DataFrame,
                )
            )
        )

    if isinstance(
        payload,
        pd.DataFrame,
    ):
        return len(
            payload
        )

    return 0


def _load_selected_sources(
    *,
    case_id: str,
    mode: str,
) -> tuple[
    dict[str, Any],
    int,
    dict[str, str],
]:
    payloads: dict[str, Any] = {
        "cdr": None,
        "ipdr": None,
        "gprs": None,
    }

    load_errors: dict[str, str] = {}
    input_records = 0

    loaders = {
        "cdr": _load_cdr_evidence,
        "ipdr": _load_ipdr_evidence,
        "gprs": _load_gprs_evidence,
    }

    selected_sources = (
        tuple(
            loaders
        )
        if mode == "unified"
        else (
            mode,
        )
    )

    for source_name in selected_sources:
        loader = loaders[
            source_name
        ]

        try:
            payload = loader(
                case_id
            )

            payloads[
                source_name
            ] = payload

            input_records += _record_count(
                source_name,
                payload,
            )

        except Exception as error:
            load_errors[
                source_name.upper()
            ] = (
                f"{type(error).__name__}: {error}"
            )

            print(
                f"[WARNING] {source_name.upper()} "
                "evidence could not be loaded."
            )
            print(
                f"          {type(error).__name__}: "
                f"{error}"
            )

    return (
        payloads,
        input_records,
        load_errors,
    )


def _apply_load_errors(
    analysis: dict[str, Any],
    load_errors: dict[str, str],
) -> dict[str, Any]:
    if not load_errors:
        return analysis

    result = dict(
        analysis
    )

    source_summary = result.get(
        "source_summary"
    )

    if isinstance(
        source_summary,
        pd.DataFrame,
    ):
        source_summary = source_summary.copy()

        for source_name in load_errors:
            mask = (
                source_summary[
                    "Evidence Source"
                ]
                .astype(
                    str
                )
                .str.upper()
                .eq(
                    source_name
                )
            )

            source_summary.loc[
                mask,
                "Status",
            ] = "ERROR"

            source_summary.loc[
                mask,
                "Matched Count",
            ] = 0

            source_summary.loc[
                mask,
                "Message",
            ] = (
                "Source loading failed. "
                "See the technical log."
            )

        result[
            "source_summary"
        ] = source_summary

    for source_name, technical_error in (
        load_errors.items()
    ):
        result[
            source_name.lower()
        ] = {
            "status": "ERROR",
            "message": (
                "Source loading failed. "
                "See the technical log."
            ),
            "technical_error": technical_error,
            "timeline": pd.DataFrame(),
        }

    found_count = 0

    if isinstance(
        result.get(
            "source_summary"
        ),
        pd.DataFrame,
    ):
        found_count = int(
            result[
                "source_summary"
            ][
                "Status"
            ]
            .astype(
                str
            )
            .str.upper()
            .eq(
                "FOUND"
            )
            .sum()
        )

    if found_count:
        result[
            "overall_status"
        ] = "PARTIAL"

        result[
            "message"
        ] = (
            "IMEI investigation completed with "
            "one or more unavailable evidence sources."
        )

    else:
        result[
            "overall_status"
        ] = "ERROR"

        result[
            "message"
        ] = (
            "Selected evidence sources could not "
            "be loaded."
        )

    result[
        "controller_load_errors"
    ] = dict(
        load_errors
    )

    return result


def _print_source_summary(
    analysis: dict[str, Any],
) -> None:
    """Print source-specific IMEI evidence counts."""

    print("\n" + "=" * 78)
    print("IMEI / DEVICE INVESTIGATION RESULT")
    print("=" * 78)

    print(
        "Requested IMEI : "
        f"{analysis.get('requested_imei', '')}"
    )

    print(
        "Overall Status : "
        f"{analysis.get('overall_status', '')}"
    )

    summary = analysis.get(
        "source_summary"
    )

    if (
        isinstance(
            summary,
            pd.DataFrame,
        )
        and not summary.empty
    ):
        for record in summary.to_dict(
            orient="records"
        ):
            source_name = str(
                record.get(
                    "Evidence Source",
                    "",
                )
            )

            status = str(
                record.get(
                    "Status",
                    "",
                )
            )

            matched_count = record.get(
                "Matched Count",
                0,
            )

            evidence_unit = str(
                record.get(
                    "Evidence Unit",
                    "",
                )
            )

            print(
                f"{source_name:<6} | "
                f"{status:<10} | "
                f"{str(matched_count):>8} | "
                f"{evidence_unit}"
            )

    print(
        "Note           : CDR records, IPDR records "
        "and GPRS sessions remain separate."
    )

    print("=" * 78)


def _execute(
    case: dict[str, Any],
    *,
    mode: str,
    requested_imei: Any | None = None,
) -> dict[str, Any]:
    mode = str(
        mode
    ).strip().lower()

    if mode not in MODE_CONFIG:
        raise ValueError(
            f"Unsupported IMEI analysis mode: {mode}"
        )

    entered_value = (
        requested_imei
        if requested_imei is not None
        else _prompt_imei()
    )

    normalized_imei = normalize_imei(
        entered_value
    )

    if not normalized_imei:
        analysis = (
            build_unified_imei_investigation(
                entered_value
            )
        )

        print(
            "[-] Enter a valid exact 15-digit "
            "IMEI or 16-digit IMEISV."
        )

        return {
            "mode": mode,
            "analysis": analysis,
            "report": None,
            "input_records": 0,
        }

    case_id = str(
        case.get(
            "case_id",
            "",
        )
    ).strip()

    config = MODE_CONFIG[
        mode
    ]

    log_case_event(
        case_id,
        action=(
            f"{config['analysis_type']}_STARTED"
        ),
        details={
            "requested_imei": normalized_imei,
        },
    )

    try:
        register_target(
            case_id,
            target_type="IMEI",
            target_value=normalized_imei,
            description=config[
                "title"
            ],
        )

        (
            payloads,
            input_records,
            load_errors,
        ) = _load_selected_sources(
            case_id=case_id,
            mode=mode,
        )

        analysis = (
            build_unified_imei_investigation(
                normalized_imei,
                loaded_cdrs=payloads[
                    "cdr"
                ],
                ipdr_dataframe=payloads[
                    "ipdr"
                ],
                gprs_dataframe=payloads[
                    "gprs"
                ],
            )
        )

        analysis = _apply_load_errors(
            analysis,
            load_errors,
        )

        _print_source_summary(
            analysis
        )

        report_path = None

        if analysis.get(
            "overall_status"
        ) in {
            "FOUND",
            "PARTIAL",
        }:
            report_path = (
                generate_imei_device_report(
                    case=case,
                    analysis=analysis,
                    output_dir=case_report_dir(
                        case_id,
                        "imei_device",
                    ),
                )
            )

        if report_path:
            register_report(
                case_id,
                report_type=config[
                    "report_type"
                ],
                report_path=report_path,
            )

            print(
                f"[+] IMEI report: {report_path}"
            )

        else:
            print(
                "[INFO] No IMEI workbook was created "
                "because no reportable matching evidence "
                "was available."
            )

        timeline = analysis.get(
            "cross_source_timeline"
        )

        output_records = (
            len(
                timeline
            )
            if isinstance(
                timeline,
                pd.DataFrame,
            )
            else 0
        )

        overall_status = str(
            analysis.get(
                "overall_status",
                "",
            )
        ).upper()

        run_status = (
            "FAILED"
            if overall_status == "ERROR"
            else "COMPLETED"
        )

        register_kwargs = {
            "analysis_type": config[
                "analysis_type"
            ],
            "status": run_status,
            "input_records": input_records,
            "output_records": output_records,
            "report_path": str(
                report_path or ""
            ),
        }

        if run_status == "FAILED":
            register_kwargs[
                "error_message"
            ] = str(
                analysis.get(
                    "message",
                    "IMEI analysis failed.",
                )
            )

        register_analysis_run(
            case_id,
            **register_kwargs,
        )

        log_case_event(
            case_id,
            action=(
                f"{config['analysis_type']}_"
                f"{run_status}"
            ),
            details={
                "requested_imei": normalized_imei,
                "input_records": input_records,
                "output_records": output_records,
                "report_created": bool(
                    report_path
                ),
            },
        )

        return {
            "mode": mode,
            "analysis": analysis,
            "report": report_path,
            "input_records": input_records,
        }

    except Exception as error:
        register_analysis_run(
            case_id,
            analysis_type=config[
                "analysis_type"
            ],
            status="FAILED",
            error_message=str(
                error
            ),
        )

        log_case_event(
            case_id,
            action=(
                f"{config['analysis_type']}_FAILED"
            ),
            details={
                "requested_imei": normalized_imei,
                "error_type": type(
                    error
                ).__name__,
            },
        )

        print(
            f"[-] {config['title']} failed."
        )
        print(
            f"    Error Type : "
            f"{type(error).__name__}"
        )
        print(
            f"    Message    : {error}"
        )

        return {
            "mode": mode,
            "analysis": {
                "requested_imei": normalized_imei,
                "overall_status": "ERROR",
                "message": str(
                    error
                ),
            },
            "report": None,
            "input_records": 0,
        }


def handle_imei_device_workspace(
    case: dict[str, Any],
) -> None:
    """Open the IMEI and device investigation submenu."""

    action_modes = {
        "1": "cdr",
        "2": "ipdr",
        "3": "gprs",
        "4": "unified",
    }

    while True:
        try:
            choice = _menu(
                case
            )

            if choice == "0":
                return

            mode = action_modes.get(
                choice
            )

            if mode is None:
                print(
                    "[-] Invalid choice. "
                    "Select 0, 1, 2, 3 or 4."
                )
                continue

            if mode == "cdr":
                _execute_auto_detected_imei_cdr(
                    case
                )

            elif mode == "ipdr":
                _execute_auto_detected_imei_ipdr(
                    case
                )

            elif mode == "gprs":
                _execute_auto_detected_imei_gprs(
                    case
                )

            else:
                _execute(
                    case,
                    mode=mode,
                )

        except KeyboardInterrupt:
            print(
                "\n[-] Returning to "
                "Analysis Workspace."
            )

        except EOFError:
            return
