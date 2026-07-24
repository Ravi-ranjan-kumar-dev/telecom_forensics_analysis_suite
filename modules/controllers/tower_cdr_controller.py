"""Case-aware Tower CDR Dump workspace.

Case users enter only CCTV date and time. Sighting IDs, time windows and
CGI handling are automatic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from modules.enrichment.telecom_master_enrichment import (
    TOWER_CDR_PARTITION_SPECS,
    TOWER_CDR_TABLE_SPECS,
    enrich_analysis_bundle,
)

from modules.analysis.towerdump.window_partition import (
    create_sighting_partitions,
)
from modules.cases import (
    CaseError,
    attach_partition_report,
    case_evidence_dir,
    case_report_dir,
    list_cgi_groups,
    load_latest_partition_manifest,
    log_case_event,
    register_analysis_run,
    register_report,
    save_partition_run,
)
from modules.cases.date_time_partitions import (
    clear_date_time_parts,
    list_date_time_parts,
    print_date_time_parts,
    save_date_time_parts,
)
from modules.core.paths import (
    TOWER_CDR_DUMP_DATA_DIR,
    TOWER_DUMP_DATA_DIR,
)


SUPPORTED_SUFFIXES = {".csv", ".txt", ".tsv", ".xlsx", ".xls"}

TOWER_CDR_WORKFLOW = "tower_cdr"


def _tower_cdr_menu(case: dict[str, Any]) -> str:
    print("\n" + "=" * 78)
    print(
        f"TOWER CDR DUMP WORKSPACE | "
        f"{case.get('case_id', '')} | {case.get('case_name', '')}"
    )
    print("=" * 78)
    print("1. Run Complete Tower CDR Dump Analysis")
    print("2. New Date-Time Partition Analysis")
    print("3. List Current Date-Time Partitions")
    print("4. Re-run Partition Using Saved Date-Times")
    print("5. Clear Saved Date-Time Partitions")
    print("6. View Latest Partition Summary")
    print("0. Back to Case Workspace")

    return input("\nChoose Action: ").strip()


def _has_supported_files(directory: Path) -> bool:
    return directory.is_dir() and any(
        path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        for path in directory.rglob("*")
    )


def _input_folder(case_id: str) -> Path:
    canonical_case_input = case_evidence_dir(
        case_id,
        "tower_dump",
        "cdr",
    )
    legacy_case_input = case_evidence_dir(
        case_id,
        "tower_dump",
        "normal",
    )

    for candidate in (
        canonical_case_input,
        legacy_case_input,
        TOWER_CDR_DUMP_DATA_DIR / "input",
        TOWER_DUMP_DATA_DIR / "input",
    ):
        if _has_supported_files(candidate):
            return candidate

    return TOWER_CDR_DUMP_DATA_DIR / "input"


def _partition_records_from_parts(
    parts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert canonical Date-Time Parts into analysis-engine records.

    The analysis engine still accepts the legacy `sightings` structure.
    This adapter preserves compatibility without changing the user's
    pair-based Start/End workflow.
    """

    records: list[dict[str, Any]] = []

    for fallback_number, part in enumerate(
        parts,
        start=1,
    ):
        try:
            part_number = int(
                part.get(
                    "part_no",
                    fallback_number,
                )
            )
        except (TypeError, ValueError):
            part_number = fallback_number

        start_time = str(
            part.get(
                "start_time",
                "",
            )
        ).strip()

        end_time = str(
            part.get(
                "end_time",
                "",
            )
        ).strip()

        records.append(
            {
                "sighting_id": f"P{part_number}",
                "partition_order": part_number,
                "location_name": str(
                    part.get(
                        "part_name",
                        f"Part {part_number}",
                    )
                ),
                # Compatibility field only. The report hides this.
                "cctv_timestamp": start_time,
                "window_start": start_time,
                "window_end": end_time,
                "cgi_group_id": "AUTO_ALL",
                "source_types": ["NORMAL_CDR"],
                "scope_mode": "TIME_ONLY_ALL_CELLS",
                "spot_scope_mode": str(
                    part.get(
                        "spot_scope_mode",
                        "LEGACY_ALL_SPOTS",
                    )
                ),
                "spot_id": str(
                    part.get(
                        "spot_id",
                        "",
                    )
                ),
                "spot_name": str(
                    part.get(
                        "spot_name",
                        "",
                    )
                ),
                "spot_folder": str(
                    part.get(
                        "spot_folder",
                        "",
                    )
                ),
                "source_type": str(
                    part.get(
                        "source_type",
                        "NORMAL_CDR",
                    )
                ),
                "range_rule": str(
                    part.get(
                        "range_rule",
                        "start_time <= event_time < end_time",
                    )
                ),
                "notes": (
                    "Pair-based Date-Time Part. "
                    "Start included and End excluded."
                ),
            }
        )

    return records


def _collect_date_time_ranges() -> list[tuple[str, str]]:
    """Collect exact Start/End Date-Time pairs from the user."""

    print("\n" + "=" * 78)
    print("CREATE DATE-TIME PARTS")
    print("=" * 78)
    print(
        "Har Part ke liye Start Date-Time aur "
        "End Date-Time enter karein."
    )
    print("Date example : 11-06-2026")
    print("Time example : 13:00 or 13:00:00")
    print()
    print("Rule:")
    print("Part 1 Start + Part 1 End = Part 1")
    print("Part 2 Start + Part 2 End = Part 2")
    print("Blank Start Date = finish")
    print("=" * 78)

    ranges: list[tuple[str, str]] = []
    part_number = 1

    while True:
        print(f"\nPart {part_number}")

        start_date = input(
            "  Start Date (blank = finish): "
        ).strip()

        if not start_date:
            break

        start_time = input(
            "  Start Time: "
        ).strip()

        end_date = input(
            "  End Date  : "
        ).strip()

        end_time = input(
            "  End Time  : "
        ).strip()

        if not all(
            [
                start_time,
                end_date,
                end_time,
            ]
        ):
            print(
                "[-] Start aur End ke Date-Time "
                "dono required hain. Part dobara enter karein."
            )
            continue

        ranges.append(
            (
                f"{start_date} {start_time}",
                f"{end_date} {end_time}",
            )
        )

        part_number += 1

    return ranges



def _cached_tower_cdr_load_result(
    cache_payload: dict[str, Any],
    input_folder: Path,
) -> dict[str, Any]:
    """Convert verified staged Parquet into the normal loader contract."""

    dataframe = cache_payload.get(
        "dataframe"
    )

    if (
        not isinstance(
            dataframe,
            pd.DataFrame,
        )
        or dataframe.empty
    ):
        return {
            "df": pd.DataFrame(),
            "ok": False,
            "errors": [
                "Reusable Tower CDR dataframe empty hai."
            ],
        }

    fingerprint = cache_payload.get(
        "current_fingerprint",
        {},
    )

    fingerprint_files = (
        fingerprint.get(
            "files",
            [],
        )
        if isinstance(
            fingerprint,
            dict,
        )
        else []
    )

    file_summary_rows = []

    if (
        "source_relative_path"
        in dataframe.columns
    ):
        for relative_path, group in dataframe.groupby(
            "source_relative_path",
            dropna=False,
            sort=True,
        ):
            file_summary_rows.append(
                {
                    "file": str(
                        group.get(
                            "source_file",
                            pd.Series(
                                [Path(str(relative_path)).name]
                            ),
                        ).iloc[0]
                    ),
                    "relative_path": str(
                        relative_path
                    ),
                    "operator": str(
                        group.get(
                            "operator",
                            pd.Series([""]),
                        ).iloc[0]
                    ),
                    "searched_cell_id": str(
                        group.get(
                            "searched_cell_id",
                            pd.Series([""]),
                        ).iloc[0]
                    ),
                    "spot_id": str(
                        group.get(
                            "spot_id",
                            pd.Series([""]),
                        ).iloc[0]
                    ),
                    "spot_name": str(
                        group.get(
                            "spot_name",
                            pd.Series([""]),
                        ).iloc[0]
                    ),
                    "records": int(
                        len(group)
                    ),
                    "status": "CACHED_STAGE",
                    "warnings": "",
                    "errors": "",
                }
            )

    operators = sorted(
        value
        for value in dataframe.get(
            "operator",
            pd.Series(dtype="object"),
        )
        .fillna("")
        .astype(str)
        .str.strip()
        .unique()
        if value
    )

    cell_ids = sorted(
        value
        for value in dataframe.get(
            "searched_cell_id",
            pd.Series(dtype="object"),
        )
        .fillna("")
        .astype(str)
        .str.strip()
        .unique()
        if value
    )

    spot_summary_rows = []

    if "spot_id" in dataframe.columns:
        for spot_id, group in dataframe.groupby(
            "spot_id",
            dropna=False,
            sort=True,
        ):
            spot_summary_rows.append(
                {
                    "spot_id": str(
                        spot_id
                    ),
                    "spot_name": str(
                        group.get(
                            "spot_name",
                            pd.Series([""]),
                        ).iloc[0]
                    ),
                    "spot_folder": str(
                        group.get(
                            "spot_folder",
                            pd.Series([""]),
                        ).iloc[0]
                    ),
                    "records": int(
                        len(group)
                    ),
                    "file_count": int(
                        group.get(
                            "source_relative_path",
                            pd.Series(dtype="object"),
                        ).nunique()
                    ),
                }
            )

    potential_duplicate_records = 0

    for duplicate_column in (
        "potential_duplicate",
        "is_potential_duplicate",
    ):
        if duplicate_column in dataframe.columns:
            potential_duplicate_records = int(
                dataframe[
                    duplicate_column
                ]
                .fillna(False)
                .astype(bool)
                .sum()
            )
            break

    metadata = {
        "input_folder": str(
            input_folder
        ),
        "files_found": int(
            fingerprint.get(
                "file_count",
                len(file_summary_rows),
            )
            or 0
        ),
        "files_loaded": int(
            fingerprint.get(
                "file_count",
                len(file_summary_rows),
            )
            or 0
        ),
        "files_failed": 0,
        "records_before_dedup": int(
            len(dataframe)
        ),
        "records_after_dedup": int(
            len(dataframe)
        ),
        "potential_duplicate_records": (
            potential_duplicate_records
        ),
        "duplicates_removed": 0,
        "cache_reused": True,
        "cache_source": (
            "normalized.parquet"
        ),
        "spot_count": int(
            dataframe.get(
                "spot_id",
                pd.Series(dtype="object"),
            ).nunique()
        ),
        "spot_names": sorted(
            value
            for value in dataframe.get(
                "spot_name",
                pd.Series(dtype="object"),
            )
            .fillna("")
            .astype(str)
            .str.strip()
            .unique()
            if value
        ),
    }

    return {
        "df": dataframe,
        "files": [
            str(
                input_folder
                / str(
                    item.get(
                        "path",
                        "",
                    )
                )
            )
            for item in fingerprint_files
        ],
        "file_results": [],
        "file_summary": pd.DataFrame(
            file_summary_rows
        ),
        "spot_summary": pd.DataFrame(
            spot_summary_rows
        ),
        "operators": operators,
        "cell_ids": cell_ids,
        "metadata": metadata,
        "warnings": [
            (
                "Raw input files unchanged; "
                "verified normalized Parquet stage reused."
            )
        ],
        "errors": [],
        "rejected_rows": pd.DataFrame(),
        "cache_reused": True,
        "cache_reason": str(
            cache_payload.get(
                "reason",
                "INPUT_UNCHANGED",
            )
        ),
        "scalable_stage": dict(
            cache_payload.get(
                "manifest",
                {},
            )
        ),
        "ok": True,
    }

def _run_complete_analysis(
    case: dict[str, Any],
) -> dict[str, Any] | None:
    from modules.analysis.towerdump import build_tower_dump_analysis_bundle
    from modules.analysis.towerdump.duckdb_presence import (
        build_tower_cdr_duckdb_presence,
    )
    from modules.loader.tower_dump_loader import load_tower_dump_case
    from modules.pipeline.scalable_analysis_pipeline import (
        run_scalable_analysis_pipeline,
    )
    from modules.reporting.tower_dump_console import print_tower_dump_report
    from modules.reporting.tower_dump_excel import (
        generate_tower_dump_excel_report,
    )
    from modules.staging.tower_cdr_staging import (
        TOWER_CDR_DATASET,
        TOWER_CDR_TABLE,
        TOWER_CDR_WORKFLOW,
        load_reusable_tower_cdr_stage,
        save_tower_cdr_reuse_manifest,
    )

    case_id = str(case["case_id"])
    input_folder = _input_folder(case_id)
    print(f"[+] Tower CDR Dump input: {input_folder}")

    log_case_event(
        case_id,
        action="TOWER_CDR_DUMP_ANALYSIS_STARTED",
        details={"input_folder": str(input_folder)},
    )

    def _pipeline_loader(
        folder,
        **loader_kwargs,
    ):
        cache_payload = (
            load_reusable_tower_cdr_stage(
                case_id,
                folder,
            )
        )

        if cache_payload.get("reused"):
            cached_dataframe = (
                cache_payload.get(
                    "dataframe"
                )
            )

            print(
                "[+] Existing Tower CDR indexed "
                "data reused."
            )
            print(
                "[+] Raw input files unchanged; "
                "CSV/Excel parsing skipped."
            )
            print(
                f"[+] Cached records: "
                f"{len(cached_dataframe):,}"
            )

            return (
                _cached_tower_cdr_load_result(
                    cache_payload,
                    Path(folder),
                )
            )

        print(
            "[=] Tower CDR cache not reused: "
            f"{cache_payload.get('reason', 'UNKNOWN')}"
        )
        print(
            "[+] Raw files will be loaded and "
            "the cache will be refreshed."
        )

        return load_tower_dump_case(
            folder,
            **loader_kwargs,
        )

    try:
        pipeline_result = run_scalable_analysis_pipeline(
            case_id=case_id,
            workflow=TOWER_CDR_WORKFLOW,
            input_folder=input_folder,
            loader=_pipeline_loader,
            loader_kwargs={
                "enrich_cgi": True,
                "recursive": True,
                "remove_exact_duplicates": False,
            },
            table_name=TOWER_CDR_TABLE,
            dataset_name=TOWER_CDR_DATASET,
            dataframe_key="df",
            sql_analysis=build_tower_cdr_duckdb_presence,
            sql_analysis_kwargs={"top_limit": 200},
            status_title="TOWER CDR FAST ANALYSIS BACKEND READY",
            print_status=True,
        )

        load_result = pipeline_result.get("load_result", {})
        dataframe = pipeline_result.get("dataframe")

        if not isinstance(load_result, dict) or not load_result.get("ok"):
            errors = (
                load_result.get("errors", [])
                if isinstance(load_result, dict)
                else []
            )
            raise ValueError(
                "Tower CDR Dump load failed. "
                + " | ".join(map(str, errors))
            )

        if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
            raise ValueError("Koi valid Tower CDR Dump record load nahi hua.")

        cache_manifest = (
            save_tower_cdr_reuse_manifest(
                case_id,
                input_folder,
                dataframe,
            )
        )

        pipeline_result[
            "reuse_manifest"
        ] = cache_manifest

        sql_presence_tables = pipeline_result.get("sql_analysis", {}) or {}

        analysis = build_tower_dump_analysis_bundle(
            dataframe,
            presence_tables_override=sql_presence_tables,
        )

        status = analysis.get("status")
        if isinstance(status, pd.DataFrame):
            sql_rows = pipeline_result.get("sql_result_rows", {}) or {}
            sql_status = pd.DataFrame(
                [
                    {
                        "analysis": "tower_cdr_duckdb_sql_presence_engine",
                        "status": "COMPLETED",
                        "rows": int(sql_rows.get("subscriber_rollup", 0) or 0),
                        "duration_ms": pipeline_result.get("timings", {}).get(
                            "sql_analysis_ms",
                            0,
                        ),
                        "error": "",
                    }
                ]
            )

            analysis["status"] = pd.concat(
                [sql_status, status],
                ignore_index=True,
            )
            analysis["function_count"] = len(analysis["status"])
            analysis["completed_count"] = int(
                (analysis["status"]["status"] == "COMPLETED").sum()
            )
            analysis["failed_count"] = int(
                (analysis["status"]["status"] == "FAILED").sum()
            )


        analysis_results = analysis.get(
            "results",
            {},
        )

        if isinstance(
            analysis_results,
            dict,
        ):
            master_enrichment = enrich_analysis_bundle(
                analysis_results,
                table_specs=TOWER_CDR_TABLE_SPECS,
            )

            analysis[
                "results"
            ] = master_enrichment[
                "bundle"
            ]

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

            analysis[
                "results"
            ][
                "master_enrichment_summary"
            ] = master_enrichment[
                "summary"
            ]

            analysis[
                "results"
            ][
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

        result = {
            **load_result,
            "df": dataframe,
            "analysis": analysis,
            "scalable_pipeline": {
                "stage": pipeline_result.get("stage", {}),
                "sql_result_rows": pipeline_result.get("sql_result_rows", {}),
                "timings": pipeline_result.get("timings", {}),
                "pipeline_state_path": pipeline_result.get(
                    "pipeline_state_path",
                    "",
                ),
            },
        }

        print_tower_dump_report(result, row_limit=25)

        excel_path = generate_tower_dump_excel_report(
            result,
            output_dir=case_report_dir(case_id, "tower_cdr_dump"),
            case_name=case_id,
        )

        register_report(
            case_id,
            report_type="TOWER_CDR_DUMP",
            report_path=excel_path,
        )

        from modules.cases.latest_reports import save_latest_report

        save_latest_report(
            case_id,
            "tower_cdr_dump",
            title="Tower CDR Dump Analysis",
            report_path=excel_path,
            report_folder=case_report_dir(case_id, "tower_cdr_dump"),
            metadata={
                "input_records": len(dataframe),
                "analysis_completed": analysis.get("completed_count", 0),
                "analysis_failed": analysis.get("failed_count", 0),
            },
        )

        register_analysis_run(
            case_id,
            analysis_type="TOWER_CDR_DUMP",
            status="COMPLETED",
            input_records=len(dataframe),
            output_records=analysis.get("completed_count", 0),
            report_path=str(excel_path),
        )

        result["excel_report"] = str(excel_path)
        print(f"\n[+] Case report: {excel_path}")
        return result

    except Exception as error:
        register_analysis_run(
            case_id,
            analysis_type="TOWER_CDR_DUMP",
            status="FAILED",
            error_message=str(error),
        )
        print(f"[-] Tower Dump analysis failed: {error}")
        return None

def _run_partition_analysis(
    case: dict[str, Any],
) -> dict[str, Any] | None:
    from modules.loader.tower_dump_loader import load_tower_dump_case

    case_id = str(case["case_id"])
    parts = list_date_time_parts(
        case_id,
        TOWER_CDR_WORKFLOW,
    )
    sightings = _partition_records_from_parts(parts)

    if not sightings:
        print("[-] Pehle date-time part enter karein.")
        return None

    input_folder = _input_folder(case_id)
    print(f"[+] Loading Tower CDR Dump: {input_folder}")

    load_result = load_tower_dump_case(
        input_folder,
        enrich_cgi=True,
        recursive=True,
        remove_exact_duplicates=False,
    )

    dataframe = load_result.get("df")

    if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
        print("[-] Koi valid Tower CDR Dump record load nahi hua.")

        for error in load_result.get("errors", []):
            print(f"    {error}")

        return None

    print(
        f"[+] Loaded {len(dataframe):,} records. "
        f"Creating {len(sightings)} pair-based date-time partitions..."
    )

    try:
        from modules.staging.tower_cdr_staging import (
            print_tower_cdr_stage_summary,
            stage_tower_cdr_dataframe,
        )

        stage_payload = stage_tower_cdr_dataframe(
            case_id=case_id,
            dataframe=dataframe,
            input_folder=input_folder,
            stage_reason="tower_cdr_partition_analysis",
        )
        load_result["scalable_stage"] = stage_payload
        print_tower_cdr_stage_summary(stage_payload)

    except Exception as stage_error:
        print(
            "[-] Tower CDR scalable backend staging failed: "
            f"{type(stage_error).__name__}: {stage_error}"
        )
        print(
            "[!] Partition analysis continue hoga. "
            "Staging issue ko baad me fix kiya ja sakta hai."
        )

    result = create_sighting_partitions(
        dataframe,
        sightings=sightings,
        cgi_groups=list_cgi_groups(case_id),
    )

    # Reporting diagnostics are carried forward without re-running analysis.
    result["warnings"] = [
        *list(result.get("warnings", []) or []),
        *list(load_result.get("warnings", []) or []),
    ]
    result["errors"] = list(load_result.get("errors", []) or [])
    result["load_metadata"] = dict(load_result.get("metadata", {}) or {})
    result["operators"] = list(load_result.get("operators", []) or [])
    result["cell_ids"] = list(load_result.get("cell_ids", []) or [])
    result["rejected_rows"] = load_result.get("rejected_rows", pd.DataFrame())
    result["input_folder"] = str(input_folder)


    master_enrichment = enrich_analysis_bundle(
        result,
        table_specs=TOWER_CDR_PARTITION_SPECS,
    )

    result = master_enrichment[
        "bundle"
    ]

    result[
        "master_enrichment_summary"
    ] = master_enrichment[
        "summary"
    ]

    result[
        "master_enrichment_warnings"
    ] = master_enrichment[
        "warnings"
    ]

    if master_enrichment[
        "warnings"
    ]:
        result.setdefault(
            "warnings",
            [],
        ).extend(
            master_enrichment[
                "warnings"
            ]
        )

    summary = result["partition_summary"]

    print("\n" + "=" * 120)
    print("WINDOW-WISE PARTITION SUMMARY")
    print("=" * 120)

    if summary.empty:
        print("No partitions generated.")
    else:
        print(summary.to_string(index=False))

    n_of_m = result["n_of_m_candidates"]
    strict = result["strict_common_candidates"]

    print("\n" + "=" * 82)
    print("COMMON CANDIDATE SUMMARY")
    print("=" * 82)
    print(f"Total Date-Time Partitions : {result['total_sightings']}")
    print(f"Candidates in 2+      : {len(n_of_m):,}")
    print(f"Candidates in all     : {len(strict):,}")

    if not n_of_m.empty:
        columns = [
            column
            for column in (
                "subscriber_number",
                "match_ratio",
                "matched_sightings",
                "total_events",
                "operators",
            )
            if column in n_of_m.columns
        ]

        print("\nTop candidates:")
        print(
            n_of_m[columns]
            .head(50)
            .to_string(index=False)
        )

    # Internal CSV tables remain backend data. Full raw partitions are not
    # duplicated in simple mode.
    saved = save_partition_run(
        case_id,
        result,
        export_full_partitions=False,
    )

    try:
        from modules.reporting.tower_partition_excel import (
            generate_tower_partition_excel_report,
        )

        excel_path = generate_tower_partition_excel_report(
            result,
            case=case,
            sightings=sightings,
            output_dir=case_report_dir(case_id, "tower_cdr_dump"),
            input_folder=input_folder,
            saved=saved,
        )

        attach_partition_report(
            case_id,
            run_id=saved["run_id"],
            report_path=excel_path,
        )

        register_report(
            case_id,
            report_type="TOWER_CDR_DUMP_PARTITION",
            report_path=excel_path,
        )

        register_analysis_run(
            case_id,
            analysis_type="TOWER_CDR_DUMP_PARTITION",
            status="COMPLETED",
            input_records=len(dataframe),
            output_records=len(n_of_m),
            report_path=str(excel_path),
        )

    except Exception as error:
        register_analysis_run(
            case_id,
            analysis_type="TOWER_CDR_DUMP_PARTITION",
            status="COMPLETED_WITH_REPORT_ERROR",
            input_records=len(dataframe),
            output_records=len(n_of_m),
            report_path=saved["run_directory"],
            error_message=str(error),
        )

        print(
            f"[-] Consolidated Excel report failed: "
            f"{type(error).__name__}: {error}"
        )
        print(
            f"[+] Internal backend data preserved: "
            f"{saved['run_directory']}"
        )

        result["saved"] = saved
        result["excel_report"] = ""
        return result

    print("\n" + "=" * 82)
    print("PARTITION ANALYSIS COMPLETED")
    print("=" * 82)
    print(f"Dynamic Partitions : {result['total_sightings']}")
    print(f"Candidates in 2+   : {len(n_of_m):,}")
    print(f"Candidates in All  : {len(strict):,}")
    print(f"Excel Report       : {excel_path}")
    print(f"Backend Data       : {saved['run_directory']}")
    print("=" * 82)
    print("[+] Raw Tower CDR Dump files unchanged hain.")
    print("[+] User-facing output ek consolidated Excel workbook hai.")

    result["saved"] = saved
    result["excel_report"] = str(excel_path)
    return result



def _discover_partition_spots(
    case_id: str,
) -> list[dict[str, Any]]:
    """Discover deterministic investigation Spots from input folders."""

    from modules.loader.tower_dump_loader import (
        SUPPORTED_SUFFIXES,
    )
    from modules.loader.tower_spot_layout import (
        ROOT_SPOT_ID,
        build_tower_spot_layout,
    )

    input_folder = _input_folder(
        case_id
    )

    if (
        not input_folder.exists()
        or not input_folder.is_dir()
    ):
        return []

    files = sorted(
        path
        for path in input_folder.rglob("*")
        if (
            path.is_file()
            and path.suffix.lower()
            in SUPPORTED_SUFFIXES
            and not path.name.startswith(
                (
                    "~$",
                    ".",
                )
            )
        )
    )

    if not files:
        return []

    layout = build_tower_spot_layout(
        input_folder,
        files,
    )

    summary = [
        dict(item)
        for item in layout.get(
            "spot_summary",
            [],
        )
        if isinstance(item, dict)
    ]

    actual_spots = [
        item
        for item in summary
        if str(
            item.get(
                "spot_id",
                "",
            )
        ).strip() != ROOT_SPOT_ID
    ]

    # Legacy root files remain selectable when no
    # real Spot folder has been configured yet.
    return actual_spots or summary


def _collect_spot_date_time_specs(
    case_id: str,
) -> list[dict[str, Any]]:
    """Collect one or more Start/End ranges for selected Spots."""

    spots = _discover_partition_spots(
        case_id
    )

    if not spots:
        print(
            "[-] Tower CDR input folder mein "
            "koi supported dump file nahi mila."
        )
        return []

    specifications: list[
        dict[str, Any]
    ] = []

    while True:
        print("\n" + "=" * 78)
        print("SELECT SPOT FOR DATE-TIME PARTS")
        print("=" * 78)

        for index, spot in enumerate(
            spots,
            start=1,
        ):
            print(
                f"{index}. "
                f"{spot.get('spot_name')} "
                f"({spot.get('spot_id')}) | "
                f"Files: "
                f"{spot.get('files_found', 0)}"
            )

        print(
            "A. Apply Parts to all loaded Spots "
            "(intentional comparison)"
        )
        print(
            "0. Finish Spot-Part entry"
        )

        choice = input(
            "Choose Spot: "
        ).strip()

        if choice == "0":
            break

        if choice.lower() == "a":
            selected = {
                "spot_id": "ALL_SPOTS",
                "spot_name": (
                    "ALL LOADED SPOTS"
                ),
                "spot_folder": "",
            }
            scope_mode = "ALL_SPOTS"

        else:
            try:
                selected_index = int(
                    choice
                )
            except ValueError:
                print(
                    "[-] Invalid Spot choice."
                )
                continue

            if not (
                1
                <= selected_index
                <= len(spots)
            ):
                print(
                    "[-] Selected Spot number "
                    "available nahi hai."
                )
                continue

            selected = spots[
                selected_index - 1
            ]

            scope_mode = (
                "SELECTED_SPOT_ONLY"
            )

        selected_spot_id = str(
            selected.get(
                "spot_id",
                "",
            )
        ).strip()

        selected_spot_name = str(
            selected.get(
                "spot_name",
                "",
            )
        ).strip()

        selected_spot_folder = str(
            selected.get(
                "spot_folder",
                "",
            )
        ).strip()

        print("\n" + "-" * 78)
        print(
            "Selected Spot: "
            f"{selected_spot_name} "
            f"({selected_spot_id})"
        )
        print("-" * 78)

        ranges = _collect_date_time_ranges()

        if not ranges:
            print(
                "[-] Is Spot ke liye koi "
                "Date-Time Part enter nahi hua."
            )
            continue

        for spot_part_number, (
            start_time,
            end_time,
        ) in enumerate(
            ranges,
            start=1,
        ):
            specifications.append(
                {
                    "part_name": (
                        f"{selected_spot_name} "
                        f"- Part "
                        f"{spot_part_number}"
                    ),
                    "spot_part_no": (
                        spot_part_number
                    ),
                    "spot_scope_mode": (
                        scope_mode
                    ),
                    "spot_id": (
                        selected_spot_id
                    ),
                    "spot_name": (
                        selected_spot_name
                    ),
                    "spot_folder": (
                        selected_spot_folder
                    ),
                    "start_time": (
                        start_time
                    ),
                    "end_time": (
                        end_time
                    ),
                    "source_type": (
                        "NORMAL_CDR"
                    ),
                }
            )

        print(
            f"[+] {len(ranges)} Part(s) "
            f"{selected_spot_name} ke saath "
            "mapped."
        )

    return specifications


def _new_partition_workflow(
    case: dict[str, Any],
) -> dict[str, Any] | None:
    from modules.cases.date_time_partitions import (
        save_spot_date_time_parts,
    )

    case_id = str(case["case_id"])

    part_specs = (
        _collect_spot_date_time_specs(
            case_id
        )
    )

    if not part_specs:
        print(
            "[-] Koi Spot-aware "
            "Date-Time Part enter nahi hua."
        )
        return None

    payload = save_spot_date_time_parts(
        case_id,
        TOWER_CDR_WORKFLOW,
        part_specs,
    )

    total_parts = int(
        payload.get(
            "parts_count",
            0,
        )
    )

    selected_spot_count = len(
        {
            (
                str(
                    item.get(
                        "spot_scope_mode",
                        "",
                    )
                ),
                str(
                    item.get(
                        "spot_id",
                        "",
                    )
                ),
            )
            for item in part_specs
        }
    )

    print(
        f"\n[+] {total_parts} Spot-aware "
        "Date-Time Part(s) saved."
    )

    print(
        f"[+] Spot scopes used: "
        f"{selected_spot_count}"
    )

    print_date_time_parts(
        case_id,
        TOWER_CDR_WORKFLOW,
    )

    return _run_partition_analysis(
        case
    )


def _show_latest(case_id: str) -> None:
    manifest = load_latest_partition_manifest(case_id)

    if not manifest:
        print("[-] Koi partition run available nahi hai.")
        return

    print("\n" + "=" * 90)
    print(f"LATEST PARTITION RUN: {manifest.get('run_id', '')}")
    print("=" * 90)
    print(f"Created At          : {manifest.get('created_at', '')}")
    print(f"Total Input Records : {manifest.get('total_input_records', 0)}")
    print(f"Total Sightings     : {manifest.get('total_sightings', 0)}")

    for item in manifest.get("partition_summary", []):
        print(
            f"- {item.get('sighting_id')} | "
            f"{item.get('cctv_timestamp')} | "
            f"records={item.get('filtered_records', 0)} | "
            f"subscribers={item.get('unique_subscribers', 0)} | "
            f"cells={item.get('unique_searched_cells', 0)}"
        )

    print(
        f"Consolidated Report : "
        f"{manifest.get('consolidated_excel_report', 'Not generated')}"
    )
    print(
        f"Backend Run Data    : "
        f"{manifest.get('run_id', '')}"
    )


def handle_tower_cdr_workspace(
    case: dict[str, Any],
) -> dict[str, Any] | None:
    case_id = str(case["case_id"])

    while True:
        try:
            choice = _tower_cdr_menu(case)

            if choice == "1":
                _run_complete_analysis(case)

            elif choice == "2":
                _new_partition_workflow(case)

            elif choice == "3":
                print_date_time_parts(case_id, TOWER_CDR_WORKFLOW)

            elif choice == "4":
                _run_partition_analysis(case)

            elif choice == "5":
                clear_date_time_parts(case_id, TOWER_CDR_WORKFLOW)
                print("[+] Saved pair-based Date-Time Parts cleared.")

            elif choice == "6":
                _show_latest(case_id)

            elif choice == "0":
                return None

            else:
                print("[-] Invalid choice. Select 0 to 6.")

        except CaseError as error:
            print(f"[-] Configuration error: {error}")

        except ValueError as error:
            print(f"[-] Invalid value: {error}")

        except KeyboardInterrupt:
            print("\n[-] Returning to Tower CDR Dump workspace.")

        except EOFError:
            return None

        except Exception as error:
            print(
                f"[-] Tower CDR Dump workspace error: "
                f"{type(error).__name__}: {error}"
            )
