"""Case-aware IMEI and device investigation workspace.

The controller reuses existing CDR, IPDR and GPRS loaders and the tested
unified IMEI analysis service. It does not implement duplicate parsing or
source-specific analysis logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from modules.analysis.device import (
    build_unified_imei_investigation,
)
from modules.cases import (
    case_report_dir,
    log_case_event,
    register_analysis_run,
    register_report,
    register_target,
)
from modules.loader.telecom_identifiers import (
    normalize_imei,
)
from modules.reporting import (
    generate_imei_device_report,
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
