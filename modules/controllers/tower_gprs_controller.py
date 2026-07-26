"""Case-aware Tower GPRS Dump workspace.

The current parser supports the uploaded Airtel GPRS session format.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from modules.enrichment.telecom_master_enrichment import (
    TOWER_GPRS_PARTITION_SPECS,
    TOWER_GPRS_TABLE_SPECS,
    enrich_analysis_bundle,
)

from modules.analysis.gprsdump import (
    create_gprs_partitions,
    run_gprs_analysis,
)
from modules.cases import (
    CaseError,
    case_evidence_dir,
    clear_sightings,
    list_sightings,
    list_cgi_groups,
    log_case_event,
    register_analysis_run,
    register_evidence,
    register_report,
    case_report_dir,
    replace_simple_sightings,
)
from modules.cases.gprs_store import (
    attach_gprs_report,
    load_latest_gprs_manifest,
    save_gprs_run,
)
from modules.core.paths import (
    GPRS_DUMP_DATA_DIR,
    TOWER_GPRS_DUMP_DATA_DIR,
)
from modules.loader.gprs_dump_loader import load_gprs_dump_case
from modules.reporting.tower_gprs_console import (
    print_gprs_analysis,
    print_gprs_partition,
)


SUPPORTED_SUFFIXES = {".csv", ".txt"}



def _menu(case: dict[str, Any]) -> str:
    """Print the Tower GPRS workspace menu."""

    print("\n" + "=" * 78)
    print(
        f"TOWER GPRS DUMP WORKSPACE | "
        f"{case.get('case_id', '')} | "
        f"{case.get('case_name', '')}"
    )
    print("=" * 78)
    print(
        "1. Run Complete Tower GPRS "
        "Dump Analysis"
    )
    print(
        "2. Create Spot-based "
        "Date-Time Parts"
    )
    print(
        "3. List Saved Spot-based Parts"
    )
    print(
        "4. Analyze Saved Parts"
    )
    print(
        "5. Clear Saved GPRS Parts"
    )
    print(
        "6. View Latest GPRS Run"
    )
    print(
        "0. Back to Case Workspace"
    )

    return input(
        "\nChoose Action: "
    ).strip()



def _has_files(directory: Path) -> bool:
    return directory.is_dir() and any(
        path.is_file()
        and path.suffix.lower() in SUPPORTED_SUFFIXES
        for path in directory.rglob("*")
    )


def _input_folder(case_id: str) -> Path:
    canonical_case_folder = case_evidence_dir(
        case_id,
        "tower_dump",
        "gprs",
    )
    legacy_case_folder = case_evidence_dir(
        case_id,
        "gprs_dump",
    )

    for candidate in (
        canonical_case_folder,
        legacy_case_folder,
        TOWER_GPRS_DUMP_DATA_DIR / "input",
        GPRS_DUMP_DATA_DIR / "input",
    ):
        if _has_files(candidate):
            return candidate

    return TOWER_GPRS_DUMP_DATA_DIR / "input"

def resolve_gprs_input_folder(
    case_id: str,
) -> Path:
    """Return the canonical Tower GPRS input folder."""

    return _input_folder(
        case_id
    )



def _parse_gprs_part_datetime(
    date_value: str,
    time_value: str,
) -> str:
    """Parse investigator-entered date and time."""

    from datetime import datetime

    raw_value = (
        f"{str(date_value).strip()} "
        f"{str(time_value).strip()}"
    ).strip()

    formats = (
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    )

    for date_format in formats:
        try:
            parsed = datetime.strptime(
                raw_value,
                date_format,
            )

            return parsed.strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        except ValueError:
            continue

    raise ValueError(
        "Invalid date or time. "
        "Use DD-MM-YYYY and HH:MM."
    )


def _available_gprs_spots(
    case_id: str,
) -> list[dict[str, Any]]:
    """Return available Tower GPRS Spots with accurate file counts."""

    from modules.loader.tower_spot_layout import (
        build_tower_spot_layout,
    )

    input_folder = _input_folder(
        case_id
    )

    if not input_folder.is_dir():
        return []

    files = sorted(
        path
        for path in input_folder.rglob("*")
        if (
            path.is_file()
            and path.suffix.lower()
            in SUPPORTED_SUFFIXES
        )
    )

    if not files:
        return []

    layout = build_tower_spot_layout(
        input_folder,
        files,
    )

    assignments = layout.get(
        "assignments",
        {},
    )

    spot_records: dict[
        str,
        dict[str, Any],
    ] = {}

    for assignment in assignments.values():
        if not isinstance(
            assignment,
            dict,
        ):
            continue

        spot_id = str(
            assignment.get(
                "spot_id",
                "",
            )
            or ""
        ).strip()

        if not spot_id:
            continue

        record = spot_records.setdefault(
            spot_id,
            {
                "spot_id": spot_id,
                "spot_name": str(
                    assignment.get(
                        "spot_name",
                        spot_id,
                    )
                    or spot_id
                ),
                "spot_folder": str(
                    assignment.get(
                        "spot_folder",
                        "",
                    )
                    or ""
                ),
                "file_count": 0,
            },
        )

        record["file_count"] += 1

    return sorted(
        spot_records.values(),
        key=lambda item: (
            str(
                item.get(
                    "spot_id",
                    "",
                )
            ),
            str(
                item.get(
                    "spot_name",
                    "",
                )
            ),
        ),
    )



def _select_gprs_spot(
    spots: list[dict[str, Any]],
    part_number: int,
) -> dict[str, Any]:
    """Ask the investigator to select one Spot."""

    print()
    print(
        f"SELECT SPOT FOR PART {part_number}"
    )
    print("-" * 72)

    for index, spot in enumerate(
        spots,
        start=1,
    ):
        print(
            f"{index}. "
            f"{spot.get('spot_id')} | "
            f"{spot.get('spot_name')} | "
            f"Files: "
            f"{spot.get('file_count', 0)}"
        )

    while True:
        value = input(
            "Choose Spot number: "
        ).strip()

        try:
            selected_index = int(
                value
            )
        except ValueError:
            print(
                "[-] Enter a valid Spot number."
            )
            continue

        if (
            1
            <= selected_index
            <= len(spots)
        ):
            return dict(
                spots[
                    selected_index - 1
                ]
            )

        print(
            "[-] Selected Spot was not found."
        )


def _parts_to_gprs_sightings(
    parts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert saved Parts to GPRS analysis scopes."""

    sightings: list[
        dict[str, Any]
    ] = []

    for index, part in enumerate(
        parts,
        start=1,
    ):
        part_number = int(
            part.get(
                "part_no",
                index,
            )
            or index
        )

        start_time = str(
            part.get(
                "start_time",
                "",
            )
            or ""
        )

        end_time = str(
            part.get(
                "end_time",
                "",
            )
            or ""
        )

        sightings.append(
            {
                "sighting_id": (
                    f"GPRS-PART-"
                    f"{part_number:02d}"
                ),
                "part_no": part_number,
                "part_name": str(
                    part.get(
                        "part_name",
                        f"Part {part_number}",
                    )
                ),
                "location_name": str(
                    part.get(
                        "spot_name",
                        "",
                    )
                    or part.get(
                        "spot_id",
                        "",
                    )
                ),
                "cctv_timestamp": start_time,
                "window_start": start_time,
                "window_end": end_time,
                "minutes_before": 0,
                "minutes_after": 0,
                "cgi_group_id": "AUTO_ALL",
                "spot_id": str(
                    part.get(
                        "spot_id",
                        "",
                    )
                    or ""
                ),
                "spot_name": str(
                    part.get(
                        "spot_name",
                        "",
                    )
                    or ""
                ),
                "spot_folder": str(
                    part.get(
                        "spot_folder",
                        "",
                    )
                    or ""
                ),
                "spot_scope_mode": str(
                    part.get(
                        "spot_scope_mode",
                        "SELECTED_SPOT_ONLY",
                    )
                    or "SELECTED_SPOT_ONLY"
                ),
            }
        )

    return sightings



def _collect_date_time_pairs(
    spots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collect exact Start-End Parts with Spot selection."""

    print("\n" + "=" * 72)
    print(
        "CREATE GPRS DATE-TIME PARTS"
    )
    print("=" * 72)
    print(
        "Date format : DD-MM-YYYY"
    )
    print(
        "Time format : HH:MM or HH:MM:SS"
    )
    print(
        "Each Part requires Start, End "
        "and one selected Spot."
    )
    print(
        "Leave the next Start Date blank "
        "when all Parts are entered."
    )

    parts: list[
        dict[str, Any]
    ] = []

    part_number = 1

    while True:
        print()
        print(
            f"PART {part_number}"
        )
        print("-" * 72)

        start_date = input(
            "Start Date "
            "(blank = finish): "
        ).strip()

        if not start_date:
            break

        start_clock = input(
            "Start Time: "
        ).strip()

        if not start_clock:
            print(
                "[-] Start Time is required."
            )
            continue

        end_date = input(
            "End Date "
            "(blank = same date): "
        ).strip()

        if not end_date:
            end_date = start_date

        end_clock = input(
            "End Time: "
        ).strip()

        if not end_clock:
            print(
                "[-] End Time is required."
            )
            continue

        try:
            start_time = (
                _parse_gprs_part_datetime(
                    start_date,
                    start_clock,
                )
            )

            end_time = (
                _parse_gprs_part_datetime(
                    end_date,
                    end_clock,
                )
            )

        except ValueError as error:
            print(
                f"[-] {error}"
            )
            continue

        start_value = pd.Timestamp(
            start_time
        )

        end_value = pd.Timestamp(
            end_time
        )

        if end_value <= start_value:
            print(
                "[-] End Date-Time must be "
                "later than Start Date-Time."
            )
            continue

        selected_spot = (
            _select_gprs_spot(
                spots,
                part_number,
            )
        )

        parts.append(
            {
                "start_time": start_time,
                "end_time": end_time,
                "spot_id": str(
                    selected_spot.get(
                        "spot_id",
                        "",
                    )
                    or ""
                ),
                "spot_name": str(
                    selected_spot.get(
                        "spot_name",
                        "",
                    )
                    or ""
                ),
                "spot_folder": str(
                    selected_spot.get(
                        "spot_folder",
                        "",
                    )
                    or ""
                ),
                "spot_scope_mode": (
                    "SELECTED_SPOT_ONLY"
                ),
            }
        )

        print(
            "[+] Part added: "
            f"{start_time} to {end_time} | "
            f"{selected_spot.get('spot_id')}"
        )

        part_number += 1

    return parts




def _print_sightings(
    case_id: str,
) -> None:
    """Print saved Spot-based GPRS Parts."""

    from modules.cases.date_time_partitions import (
        list_date_time_parts,
    )

    parts = list_date_time_parts(
        case_id,
        "tower_gprs",
    )

    print("\n" + "=" * 92)
    print(
        "SAVED GPRS DATE-TIME PARTS"
    )
    print("=" * 92)

    if not parts:
        print(
            "No Spot-based GPRS Parts are saved."
        )
        print("=" * 92)
        return

    print(
        "Session Rule : "
        "session_start < Part End "
        "AND session_end > Part Start"
    )
    print(
        "Spot Rule    : "
        "Only the selected Spot is included"
    )
    print(
        f"Total Parts  : {len(parts)}"
    )

    for part in parts:
        print()
        print(
            f"{part.get('part_name', 'Part')}"
        )
        print(
            "  Spot  : "
            f"{part.get('spot_id', '')}"
            + (
                f" | {part.get('spot_name')}"
                if part.get(
                    "spot_name"
                )
                else ""
            )
        )
        print(
            "  Scope : "
            f"{part.get('spot_scope_mode', '')}"
        )
        print(
            "  Start : "
            f"{part.get('start_time', '')}"
        )
        print(
            "  End   : "
            f"{part.get('end_time', '')}"
        )

    print("=" * 92)



def _load(case_id: str) -> tuple[dict[str, Any], Path]:
    input_folder = _input_folder(case_id)
    print(f"[+] Tower GPRS Dump input folder: {input_folder}")

    load_result = load_gprs_dump_case(
        input_folder,
        recursive=True,
    )

    if not load_result.get("ok"):
        print("[-] Supported Tower GPRS Dump data could not be loaded (current parser: Airtel GPRS session format).")

        for error in load_result.get("errors", []):
            print(f"    ERROR: {error}")

        for warning in load_result.get("warnings", []):
            print(f"    WARNING: {warning}")

        raise ValueError("Tower GPRS Dump loading failed.")

    for file_result in load_result.get("file_results", []):
        if not file_result.get("ok"):
            continue

        register_evidence(
            case_id,
            evidence_type="TOWER_GPRS_DUMP",
            source_file=file_result.get("file", ""),
            operator=(file_result.get("metadata", {}) or {}).get("operator", ""),
            source_category="TOWER_GPRS_SESSION",
        )

    return load_result, input_folder


def _separate_gprs_identifier_leads(
    analysis: dict[str, Any],
    *,
    limit: int = 200,
) -> dict[str, Any]:
    """Separate valid Indian MSISDN leads from other identifiers."""

    import re

    lead_keys = (
        "gprs_common_numbers",
        "gprs_uncommon_numbers",
        "gprs_multi_cell_presence",
        "gprs_device_consistency",
        "gprs_suspicious_timing",
        "gprs_priority_leads",
    )

    non_standard_frames: list[
        pd.DataFrame
    ] = []

    for key in lead_keys:
        frame = analysis.get(
            key
        )

        if (
            not isinstance(
                frame,
                pd.DataFrame,
            )
            or frame.empty
            or "subscriber_number"
            not in frame.columns
        ):
            continue

        work = frame.copy()

        identifiers = (
            work["subscriber_number"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        valid_mask = identifiers.str.fullmatch(
            r"[6-9]\d{9}",
            na=False,
        )

        valid = work.loc[
            valid_mask
        ].copy()

        analysis[key] = valid.head(
            limit
        ).reset_index(
            drop=True
        )

        non_standard = work.loc[
            ~valid_mask
            & identifiers.ne("")
        ].copy()

        if non_standard.empty:
            continue

        non_standard.insert(
            0,
            "source_analysis",
            key,
        )
        non_standard.insert(
            1,
            "identifier_type",
            "NON_STANDARD_SUBSCRIBER_ID",
        )

        non_standard_frames.append(
            non_standard
        )

    if non_standard_frames:
        combined = pd.concat(
            non_standard_frames,
            ignore_index=True,
            sort=False,
        )

        sort_columns = [
            column
            for column in (
                "priority_score",
                "match_count",
                "session_count",
                "cells_seen",
                "total_volume",
            )
            if column in combined.columns
        ]

        if sort_columns:
            combined = combined.sort_values(
                sort_columns,
                ascending=[
                    False
                    for _ in sort_columns
                ],
                na_position="last",
            )

        combined = combined.drop_duplicates(
            subset=["subscriber_number"],
            keep="first",
        ).head(
            limit
        ).reset_index(
            drop=True
        )

    else:
        combined = pd.DataFrame()

    analysis[
        "gprs_non_standard_leads"
    ] = combined

    return analysis


def _execute(
    case: dict[str, Any],
    *,
    use_partitions: bool,
) -> dict[str, Any] | None:
    from modules.analysis.gprsdump.duckdb_presence import (
        build_tower_gprs_duckdb_presence,
    )
    from modules.pipeline.scalable_analysis_pipeline import (
        run_scalable_analysis_pipeline,
    )
    from modules.staging.tower_gprs_staging import (
        TOWER_GPRS_DATASET,
        TOWER_GPRS_TABLE,
        TOWER_GPRS_WORKFLOW,
    )

    case_id = str(case["case_id"])

    log_case_event(
        case_id,
        action=(
            "TOWER_GPRS_PARTITION_ANALYSIS_STARTED"
            if use_partitions
            else "TOWER_GPRS_ANALYSIS_STARTED"
        ),
    )

    try:
        input_folder = _input_folder(case_id)
        print(f"[+] Tower GPRS Dump input folder: {input_folder}")

        pipeline_result = run_scalable_analysis_pipeline(
            case_id=case_id,
            workflow=TOWER_GPRS_WORKFLOW,
            input_folder=input_folder,
            loader=load_gprs_dump_case,
            loader_kwargs={
                "recursive": True,
            },
            table_name=TOWER_GPRS_TABLE,
            dataset_name=TOWER_GPRS_DATASET,
            dataframe_key="df",
            sql_analysis=build_tower_gprs_duckdb_presence,
            sql_analysis_kwargs={"top_limit": 500},
            supported_suffixes=SUPPORTED_SUFFIXES,
            status_title="TOWER GPRS FAST ANALYSIS BACKEND READY",
            print_status=True,
        )

        load_result = pipeline_result.get("load_result", {})
        dataframe = pipeline_result.get("dataframe")

        if not isinstance(load_result, dict) or not load_result.get("ok"):
            print("[-] Supported Tower GPRS Dump data could not be loaded (current parser: Airtel GPRS session format).")

            for error in load_result.get("errors", []):
                print(f"    ERROR: {error}")

            for warning in load_result.get("warnings", []):
                print(f"    WARNING: {warning}")

            raise ValueError("Tower GPRS Dump loading failed.")

        if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
            raise ValueError("Normalized GPRS DataFrame unavailable.")

        for file_result in load_result.get("file_results", []):
            if not file_result.get("ok"):
                continue

            register_evidence(
                case_id,
                evidence_type="TOWER_GPRS_DUMP",
                source_file=file_result.get("file", ""),
                operator=(file_result.get("metadata", {}) or {}).get("operator", ""),
                source_category="TOWER_GPRS_SESSION",
            )

        analysis = run_gprs_analysis(
            dataframe,
            file_summary=load_result.get("file_summary"),
        )

        sql_presence = pipeline_result.get("sql_analysis", {}) or {}

        if isinstance(sql_presence, dict):
            for key in (
                "gprs_common_numbers",
                "gprs_uncommon_numbers",
                "gprs_multi_cell_presence",
                "gprs_device_consistency",
                "gprs_suspicious_timing",
                "gprs_priority_leads",
            ):
                value = sql_presence.get(key)
                if isinstance(value, pd.DataFrame):
                    analysis[key] = value

            analysis["duckdb_sql_presence_status"] = pd.DataFrame(
                [
                    {
                        "analysis": "tower_gprs_duckdb_sql_presence_engine",
                        "status": "COMPLETED",
                        "rows": int(
                            (pipeline_result.get("sql_result_rows", {}) or {})
                            .get("subscriber_rollup", 0)
                            or 0
                        ),
                        "duration_ms": (
                            pipeline_result.get("timings", {}) or {}
                        ).get("sql_analysis_ms", 0),
                        "error": "",
                    }
                ]
            )

        analysis = _separate_gprs_identifier_leads(
            analysis,
            limit=200,
        )

        analysis["rejected_rows"] = load_result.get("rejected_rows", pd.DataFrame())
        analysis["scalable_pipeline"] = {
            "stage": pipeline_result.get("stage", {}),
            "sql_result_rows": pipeline_result.get("sql_result_rows", {}),
            "timings": pipeline_result.get("timings", {}),
            "pipeline_state_path": pipeline_result.get("pipeline_state_path", ""),
        }

        print_gprs_analysis(analysis, row_limit=20)

        partition = None

        if use_partitions:
            from modules.cases.date_time_partitions import (
                list_date_time_parts,
            )

            parts = list_date_time_parts(
                case_id,
                "tower_gprs",
            )

            if not parts:
                raise CaseError(
                    "No Spot-based GPRS Parts "
                    "are configured."
                )

            sightings = (
                _parts_to_gprs_sightings(
                    parts
                )
            )

            partition = create_gprs_partitions(
                dataframe,
                sightings=sightings,
                cgi_groups=list_cgi_groups(
                    case_id
                ),
            )

            print_gprs_partition(
                partition,
                row_limit=50,
            )


        combined_tables: dict[str, Any] = {}
        combined_specs: dict[
            str,
            dict[str, tuple[str, ...]],
        ] = {}

        for table_key, specification in (
            TOWER_GPRS_TABLE_SPECS.items()
        ):
            if table_key in analysis:
                combined_key = (
                    f"analysis::{table_key}"
                )

                combined_tables[
                    combined_key
                ] = analysis[
                    table_key
                ]

                combined_specs[
                    combined_key
                ] = dict(
                    specification
                )

        if isinstance(
            partition,
            dict,
        ):
            for table_key, specification in (
                TOWER_GPRS_PARTITION_SPECS.items()
            ):
                if table_key in partition:
                    combined_key = (
                        f"partition::{table_key}"
                    )

                    combined_tables[
                        combined_key
                    ] = partition[
                        table_key
                    ]

                    combined_specs[
                        combined_key
                    ] = dict(
                        specification
                    )

        master_enrichment = enrich_analysis_bundle(
            combined_tables,
            table_specs=combined_specs,
        )

        for combined_key, dataframe_value in (
            master_enrichment[
                "bundle"
            ].items()
        ):
            scope, table_key = combined_key.split(
                "::",
                1,
            )

            if scope == "analysis":
                analysis[
                    table_key
                ] = dataframe_value

            elif (
                scope == "partition"
                and isinstance(
                    partition,
                    dict,
                )
            ):
                partition[
                    table_key
                ] = dataframe_value

        analysis[
            "master_enrichment_summary"
        ] = master_enrichment[
            "summary"
        ]

        analysis[
            "master_enrichment_warnings"
        ] = master_enrichment[
            "warnings"
        ]

        if master_enrichment[
            "warnings"
        ]:
            load_result.setdefault(
                "warnings",
                [],
            ).extend(
                master_enrichment[
                    "warnings"
                ]
            )

        saved = save_gprs_run(
            case_id,
            analysis=analysis,
            partition=partition,
            input_folder=input_folder,
            source_files=[
                result.get("file", "")
                for result in load_result.get("file_results", [])
                if result.get("ok")
            ],
            warnings=load_result.get("warnings", []),
            errors=load_result.get("errors", []),
        )

        output_records = (
            len(partition.get("n_of_m_candidates", []))
            if isinstance(partition, dict)
            else len(analysis.get("subscriber_summary", []))
        )

        from modules.reporting.tower_gprs_excel import (
            generate_tower_gprs_excel_report,
        )

        excel_path = generate_tower_gprs_excel_report(
            case=case,
            load_result=load_result,
            analysis=analysis,
            partition=partition,
            output_dir=case_report_dir(
                case_id,
                "tower_gprs_dump",
            ),
            saved=saved,
        )

        attach_gprs_report(
            case_id,
            run_id=saved["run_id"],
            report_path=excel_path,
        )

        register_report(
            case_id,
            report_type="TOWER_GPRS_DUMP",
            report_path=excel_path,
        )

        from modules.cases.latest_reports import save_latest_report

        save_latest_report(
            case_id,
            "tower_gprs_dump",
            title="Tower GPRS Dump Analysis",
            report_path=excel_path,
            report_folder=case_report_dir(case_id, "tower_gprs_dump"),
            metadata={
                "input_records": len(dataframe),
                "sql_engine_ms": (
                    pipeline_result.get("timings", {}) or {}
                ).get("sql_analysis_ms", 0),
                "partition_report": bool(partition),
            },
        )

        register_analysis_run(
            case_id,
            analysis_type=(
                "TOWER_GPRS_DUMP_PARTITION"
                if use_partitions
                else "TOWER_GPRS_DUMP"
            ),
            status="COMPLETED",
            input_records=len(dataframe),
            output_records=output_records,
            report_path=str(excel_path),
        )

        print("\n" + "=" * 78)
        print("TOWER GPRS DUMP ANALYSIS COMPLETED")
        print("=" * 78)
        print(f"Input Records : {len(dataframe):,}")
        print(f"Backend Run   : {saved['run_directory']}")

        timings = pipeline_result.get("timings", {}) or {}
        print(f"SQL Engine ms : {timings.get('sql_analysis_ms', 0)}")
        print("Speed Mode    : DuckDB SQL + Parquet internal backend")
        print("User Output   : Excel report only")

        if isinstance(partition, dict):
            print(
                f"Partitions    : "
                f"{partition.get('total_partitions', 0)}"
            )
            print(
                f"Candidates 2+: "
                f"{len(partition.get('n_of_m_candidates', [])):,}"
            )
            print(
                f"Strict Common : "
                f"{len(partition.get('strict_common_candidates', [])):,}"
            )


        if isinstance(partition, dict):
            non_standard_presence = partition.get(
                "non_standard_subscriber_presence"
            )

            if isinstance(
                non_standard_presence,
                pd.DataFrame,
            ):
                strict_non_standard = 0

                if (
                    not non_standard_presence.empty
                    and "presence_class"
                    in non_standard_presence.columns
                ):
                    strict_non_standard = int(
                        non_standard_presence[
                            "presence_class"
                        ]
                        .eq(
                            "STRICT_COMMON_NON_STANDARD"
                        )
                        .sum()
                    )

                print(
                    "Part Nonstandard: "
                    f"{len(non_standard_presence):,}"
                )
                print(
                    "Strict Nonstandard: "
                    f"{strict_non_standard:,}"
                )
        print(f"Excel Report  : {excel_path}")
        print("=" * 78)

        return {
            "load": load_result,
            "analysis": analysis,
            "partition": partition,
            "saved": saved,
            "excel_report": str(excel_path),
            "scalable_pipeline": pipeline_result,
        }

    except Exception as error:
        register_analysis_run(
            case_id,
            analysis_type=(
                "TOWER_GPRS_DUMP_PARTITION"
                if use_partitions
                else "TOWER_GPRS_DUMP"
            ),
            status="FAILED",
            error_message=str(error),
        )
        print(
            f"[-] GPRS analysis failed: "
            f"{type(error).__name__}: {error}"
        )
        return None


def _new_partition(
    case: dict[str, Any],
) -> dict[str, Any] | None:
    """Create and analyze Spot-based Start-End Parts."""

    from modules.cases.date_time_partitions import (
        save_date_time_parts,
    )

    case_id = str(
        case["case_id"]
    )

    spots = _available_gprs_spots(
        case_id
    )

    if not spots:
        print(
            "[-] No Tower GPRS Spot folders "
            "were found."
        )
        print(
            "[+] Place source files inside "
            "spot_1, spot_2 and similar folders."
        )
        return None

    parts = _collect_date_time_pairs(
        spots
    )

    if not parts:
        print(
            "[-] No Date-Time Part was entered."
        )
        return None

    payload = save_date_time_parts(
        case_id,
        "tower_gprs",
        parts,
    )

    _print_sightings(
        case_id
    )

    print(
        "[+] Spot-based GPRS Parts saved."
    )
    print(
        "[+] Total Parts: "
        f"{payload.get('parts_count', 0)}"
    )

    return _execute(
        case,
        use_partitions=True,
    )



def _show_latest(case_id: str) -> None:
    manifest = load_latest_gprs_manifest(case_id)

    if not manifest:
        print("[-] Koi GPRS run available nahi hai.")
        return

    print("\n" + "=" * 78)
    print(f"LATEST TOWER GPRS RUN: {manifest.get('run_id', '')}")
    print("=" * 78)
    print(f"Created At      : {manifest.get('created_at', '')}")
    print(f"Input Folder    : {manifest.get('input_folder', '')}")
    print(f"Records         : {manifest.get('record_count', 0)}")
    print(f"Partitions      : {manifest.get('partition_count', 0)}")
    print(f"Overlap Rule    : {manifest.get('overlap_rule', '')}")
    print(f"Report Status   : {manifest.get('report_status', '')}")
    print(
        f"Excel Report    : "
        f"{manifest.get('user_facing_report', 'Not generated')}"
    )
    print(
        "Backend tables : "
        f"{len(manifest.get('saved_files', {}))}"
    )
    print("=" * 78)



def handle_tower_gprs_workspace(
    case: dict[str, Any],
) -> dict[str, Any] | None:
    """Run the Tower GPRS workspace."""

    from modules.cases.date_time_partitions import (
        clear_date_time_parts,
    )

    case_id = str(
        case["case_id"]
    )

    while True:
        try:
            choice = _menu(
                case
            )

            if choice == "1":
                _execute(
                    case,
                    use_partitions=False,
                )

            elif choice == "2":
                _new_partition(
                    case
                )

            elif choice == "3":
                _print_sightings(
                    case_id
                )

            elif choice == "4":
                _execute(
                    case,
                    use_partitions=True,
                )

            elif choice == "5":
                removed = (
                    clear_date_time_parts(
                        case_id,
                        "tower_gprs",
                    )
                )

                if removed:
                    print(
                        "[+] Saved GPRS Parts "
                        "were cleared."
                    )
                else:
                    print(
                        "[=] No saved GPRS Parts "
                        "were available."
                    )

            elif choice == "6":
                _show_latest(
                    case_id
                )

            elif choice == "0":
                return None

            else:
                print(
                    "[-] Invalid choice. "
                    "Select 0 to 6."
                )

        except KeyboardInterrupt:
            print(
                "\n[-] Returning to "
                "the GPRS workspace."
            )

        except EOFError:
            return None

        except Exception as error:
            print(
                "[-] GPRS workspace error: "
                f"{type(error).__name__}: "
                f"{error}"
            )
