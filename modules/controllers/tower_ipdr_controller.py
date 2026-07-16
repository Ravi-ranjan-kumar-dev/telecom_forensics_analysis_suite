"""Case-aware multi-cell Tower IPDR/NAT workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from modules.analysis.toweripdr import (
    create_tower_ipdr_partitions,
    run_tower_ipdr_analysis,
)
from modules.cases import (
    CaseError,
    case_evidence_dir,
    case_report_dir,
    clear_sightings,
    list_sightings,
    list_cgi_groups,
    log_case_event,
    register_analysis_run,
    register_evidence,
    register_report,
    replace_simple_sightings,
)
from modules.cases.tower_ipdr_store import (
    attach_tower_ipdr_report,
    load_latest_tower_ipdr_manifest,
    save_tower_ipdr_run,
)
from modules.cases.date_time_partitions import (
    clear_date_time_parts,
    list_date_time_parts,
    print_date_time_parts,
    print_date_time_part_warnings,
    save_date_time_parts,
)
from modules.core.paths import TOWER_IPDR_DUMP_DATA_DIR
from modules.loader.tower_ipdr_loader import load_tower_ipdr_case
from modules.staging.tower_ipdr_staging import (
    count_tower_ipdr_events,
    import_tower_ipdr_folder_to_duckdb,
    tower_ipdr_cell_counts,
    tower_ipdr_database_path,
    tower_ipdr_manifest_path,
    tower_ipdr_minute_count,
    tower_ipdr_time_count,
    tower_ipdr_uncommon_in_minute,
    tower_ipdr_investigation_summary,
    print_tower_ipdr_investigation_summary,
    tower_ipdr_range_investigation_summary,
    export_tower_ipdr_partwise_range_report,
    export_tower_ipdr_excel_workbook_from_manifest,
    save_tower_ipdr_partwise_latest_report,
)
from modules.reporting.tower_ipdr_console import (
    print_tower_ipdr_analysis,
    print_tower_ipdr_partition,
)


SUPPORTED_SUFFIXES = {".csv", ".txt"}
TOWER_IPDR_WORKFLOW = "tower_ipdr"



def _tower_ipdr_input_fingerprint() -> dict:
    """Return a simple fingerprint of Tower IPDR input files.

    This is used only to decide whether backend data needs refresh.
    It avoids unnecessary reload when input files are unchanged.
    """

    from pathlib import Path

    input_dir = Path("data/tower_dump/ipdr/input")
    allowed_suffixes = {".csv", ".txt", ".xlsx", ".xls"}

    files = []
    total_size = 0

    if input_dir.exists():
        for file_path in sorted(input_dir.rglob("*")):
            if not file_path.is_file():
                continue

            if file_path.suffix.lower() not in allowed_suffixes:
                continue

            stat = file_path.stat()
            relative_path = file_path.relative_to(input_dir).as_posix()

            files.append(
                {
                    "path": relative_path,
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
            total_size += stat.st_size

    return {
        "input_dir": str(input_dir),
        "file_count": len(files),
        "total_size": total_size,
        "files": files,
    }


def _tower_ipdr_fingerprint_path(case_id: str):
    from pathlib import Path

    path = Path("cases") / "active" / str(case_id) / "staging" / "tower_ipdr"
    path.mkdir(parents=True, exist_ok=True)
    return path / "input_fingerprint.json"


def _read_tower_ipdr_saved_fingerprint(case_id: str) -> dict:
    import json

    path = _tower_ipdr_fingerprint_path(case_id)

    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_tower_ipdr_input_fingerprint(case_id: str, fingerprint: dict) -> None:
    import json

    path = _tower_ipdr_fingerprint_path(case_id)
    path.write_text(
        json.dumps(fingerprint, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _tower_ipdr_database_has_rows(case_id: str) -> bool:
    try:
        from modules.staging.tower_ipdr_staging import count_tower_ipdr_events

        return int(count_tower_ipdr_events(case_id)) > 0
    except Exception:
        return False


def _ensure_tower_ipdr_data_ready(case_id: str, load_function) -> bool:
    """Ensure Tower IPDR backend data is ready before analysis/report.

    Returns True when data is ready, False when no input files are available
    or load failed.
    """

    current_fingerprint = _tower_ipdr_input_fingerprint()
    saved_fingerprint = _read_tower_ipdr_saved_fingerprint(case_id)

    print("[+] Tower IPDR data status check ho raha hai...")

    if current_fingerprint.get("file_count", 0) <= 0:
        print("[-] Tower IPDR input folder me koi supported file nahi mili.")
        print("    Folder: data/tower_dump/ipdr/input")
        return False

    database_ready = _tower_ipdr_database_has_rows(case_id)
    fingerprint_same = current_fingerprint == saved_fingerprint

    if database_ready and fingerprint_same:
        print("[OK] Existing Tower IPDR data fresh hai. Reload ki zarurat nahi.")
        return True

    if not database_ready:
        print("[!] Tower IPDR backend database ready nahi hai.")
    elif not fingerprint_same:
        old_count = saved_fingerprint.get("file_count", 0)
        new_count = current_fingerprint.get("file_count", 0)
        print("[!] Tower IPDR input files me change mila.")
        print(f"    Previous files: {old_count}")
        print(f"    Current files : {new_count}")

    print("[+] Backend load/refresh start ho raha hai...")
    load_function(case_id)

    if not _tower_ipdr_database_has_rows(case_id):
        print("[-] Tower IPDR backend load ke baad bhi data ready nahi hua.")
        return False

    _save_tower_ipdr_input_fingerprint(case_id, current_fingerprint)
    print("[OK] Tower IPDR backend data ready hai.")
    return True

def _menu(case: dict[str, Any]) -> str:
    print("" + "=" * 78)
    print(
        f"TOWER IPDR DUMP ANALYSIS | "
        f"{case.get('case_id', '')} | "
        f"{case.get('case_name', '')}"
    )
    print("=" * 78)
    print("1. Run Complete Tower IPDR Dump Analysis")
    print("2. Create Date-Time Parts")
    print("3. Part-wise Analysis")
    print("4. View / Export Latest Report")
    print("0. Back to Tower Dump Analysis")
    return input("Choose Action: ").strip()

def _has_files(directory: Path) -> bool:
    return directory.is_dir() and any(
        path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        for path in directory.rglob("*")
    )


def _input_folder(case_id: str) -> Path:
    case_folder = case_evidence_dir(case_id, "tower_dump", "ipdr")

    if _has_files(case_folder):
        return case_folder

    return TOWER_IPDR_DUMP_DATA_DIR / "input"


def _collect_date_time_pairs() -> list[tuple[str, str]]:
    print("\n" + "=" * 72)
    print("ENTER DATE-TIME PARTITIONS")
    print("=" * 72)
    print("Date example : 11-06-2026")
    print("Time example : 20:10 or 20:10:00")
    print("Input complete hone par next Date blank chhodkar Enter dabayein.")

    pairs: list[tuple[str, str]] = []
    number = 1

    while True:
        date_value = input(
            f"\nPartition {number} - Date (blank = finish): "
        ).strip()

        if not date_value:
            break

        time_value = input(f"Partition {number} - Time: ").strip()

        if not time_value:
            print("[-] Time required hai. Entry dobara karein.")
            continue

        pairs.append((date_value, time_value))
        number += 1

    return pairs


def _print_sightings(case_id: str) -> None:
    sightings = list_sightings(case_id)

    print("\n" + "=" * 92)
    print("SAVED DATE-TIME PARTITIONS")
    print("=" * 92)

    if not sightings:
        print("No date-time partitions configured.")
        return

    print(
        f"{'#':<4}{'Partition':<12}"
        f"{'Partition Time':<24}"
        f"{'Start Time':<24}"
        f"{'End Time':<24}"
    )
    print("-" * 92)

    for index, item in enumerate(sightings, start=1):
        print(
            f"{index:<4}"
            f"{'P' + str(index):<12}"
            f"{str(item.get('date-time_timestamp', '')):<24}"
            f"{str(item.get('window_start', '')):<24}"
            f"{str(item.get('window_end', '')):<24}"
        )


def _load(case_id: str) -> tuple[dict[str, Any], Path]:
    input_folder = _input_folder(case_id)
    print(f"[+] Tower IPDR Dump input folder: {input_folder}")

    load_result = load_tower_ipdr_case(input_folder, recursive=True)

    if not load_result.get("ok"):
        print(
            "[-] Supported Tower IPDR dump load nahi hua "
            "(current parser: Jio CELL ID_IPDRNAT)."
        )

        for error in load_result.get("errors", []):
            print(f"    ERROR: {error}")

        for warning in load_result.get("warnings", []):
            print(f"    WARNING: {warning}")

        raise ValueError("Tower IPDR loading failed.")

    for file_result in load_result.get("file_results", []):
        if not file_result.get("ok"):
            continue

        register_evidence(
            case_id,
            evidence_type="TOWER_IPDR_DUMP",
            source_file=file_result.get("file", ""),
            operator=(file_result.get("metadata", {}) or {}).get("operator", "Jio"),
            source_category="TOWER_IPDR_NAT",
        )

    return load_result, input_folder


def _execute(
    case: dict[str, Any],
    *,
    use_partitions: bool,
) -> dict[str, Any] | None:
    case_id = str(case["case_id"])
    analysis_type = (
        "TOWER_IPDR_DUMP_PARTITION"
        if use_partitions
        else "TOWER_IPDR_DUMP"
    )

    log_case_event(
        case_id,
        action=(
            "TOWER_IPDR_PARTITION_ANALYSIS_STARTED"
            if use_partitions
            else "TOWER_IPDR_ANALYSIS_STARTED"
        ),
    )

    try:
        load_result, input_folder = _load(case_id)
        dataframe = load_result.get("df")

        if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
            raise ValueError("Normalized Tower IPDR DataFrame unavailable.")

        sightings: list[dict[str, Any]] = []
        uncommon_window_start = None
        uncommon_window_end = None

        if use_partitions:
            sightings = list_sightings(case_id)

            if not sightings:
                raise CaseError("Date-time partitions configured nahi hain.")

            for sighting in sightings:
                window_start = sighting.get("window_start")
                window_end = sighting.get("window_end")

                if window_start and window_end:
                    uncommon_window_start = str(window_start)
                    uncommon_window_end = str(window_end)
                    break

        analysis = run_tower_ipdr_analysis(
            dataframe,
            file_summary=load_result.get("file_summary"),
            uncommon_window_start=uncommon_window_start,
            uncommon_window_end=uncommon_window_end,
        )
        analysis["rejected_rows"] = load_result.get("rejected_rows", pd.DataFrame())
        print_tower_ipdr_analysis(analysis, row_limit=20)

        partition = None

        if use_partitions:
            partition = create_tower_ipdr_partitions(
                dataframe,
                sightings=sightings,
                cgi_groups=list_cgi_groups(case_id),
            )
            print_tower_ipdr_partition(partition, row_limit=50)

        saved = save_tower_ipdr_run(
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

        from modules.reporting.tower_ipdr_excel import (
            generate_tower_ipdr_excel_report,
        )

        excel_path = generate_tower_ipdr_excel_report(
            case=case,
            load_result=load_result,
            analysis=analysis,
            partition=partition,
            output_dir=case_report_dir(case_id, "tower_ipdr_dump"),
            saved=saved,
        )

        attach_tower_ipdr_report(
            case_id,
            run_id=saved["run_id"],
            report_path=excel_path,
        )
        register_report(
            case_id,
            report_type="TOWER_IPDR_DUMP",
            report_path=excel_path,
        )

        output_records = (
            len(partition.get("event_n_of_m_candidates", []))
            if isinstance(partition, dict)
            else len(analysis.get("subscriber_multi_cell_candidates", []))
        )
        register_analysis_run(
            case_id,
            analysis_type=analysis_type,
            status="COMPLETED",
            input_records=len(dataframe),
            output_records=output_records,
            report_path=str(excel_path),
        )

        print("\n" + "=" * 78)
        print("TOWER IPDR DUMP ANALYSIS COMPLETED")
        print("=" * 78)
        print(f"Input Events   : {len(dataframe):,}")
        print(f"Searched Cells : {analysis.get('total_cells', 0):,}")
        print(
            "Multi-cell Subs: "
            f"{len(analysis.get('subscriber_multi_cell_candidates', [])):,}"
        )
        print(f"Backend Run    : {saved['run_directory']}")

        if isinstance(partition, dict):
            print(f"Partitions     : {partition.get('total_partitions', 0)}")
            print(
                "Event N-of-M   : "
                f"{len(partition.get('event_n_of_m_candidates', [])):,}"
            )
            print(
                "Allocation N/M : "
                f"{len(partition.get('allocation_n_of_m_candidates', [])):,}"
            )

        print(f"Excel Report   : {excel_path}")
        print("=" * 78)

        return {
            "load": load_result,
            "analysis": analysis,
            "partition": partition,
            "saved": saved,
            "excel_report": str(excel_path),
        }

    except Exception as error:
        register_analysis_run(
            case_id,
            analysis_type=analysis_type,
            status="FAILED",
            error_message=str(error),
        )
        print(
            f"[-] Tower IPDR analysis failed: "
            f"{type(error).__name__}: {error}"
        )
        return None


def _new_partition(case: dict[str, Any]) -> dict[str, Any] | None:
    pairs = _collect_date_time_pairs()

    if not pairs:
        print("[-] Koi date-time enter nahi hua.")
        return None

    case_id = str(case["case_id"])

    replace_simple_sightings(
        case_id,
        pairs,
        minutes_before=0,
        minutes_after=0,
    )

    _print_sightings(case_id)
    print("[+] Date-time partitions saved. Fast SQL query ke liye options 5, 6, 7 use karein.")

    return {
        "case_id": case_id,
        "partitions": list_sightings(case_id),
    }


def _print_dataframe(title: str, dataframe: pd.DataFrame, *, max_rows: int = 20) -> None:
    print("" + "=" * 78)
    print(title)
    print("=" * 78)

    if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
        print("No records found.")
        return

    print(dataframe.head(max_rows).to_string(index=False))


def _import_staging(case: dict[str, Any]) -> None:
    case_id = str(case["case_id"])
    input_folder = _input_folder(case_id)

    print(f"[+] Tower IPDR staging input folder: {input_folder}")

    summary = import_tower_ipdr_folder_to_duckdb(
        case_id,
        input_folder,
        recursive=True,
        force_rebuild=True,
    )

    print("" + "=" * 78)
    print("TOWER IPDR STAGING IMPORT COMPLETED")
    print("=" * 78)
    print(f"Candidate Files : {summary.get('candidate_files', 0):,}")
    print(f"Loaded Files    : {summary.get('loaded_files', 0):,}")
    print(f"Skipped Files   : {summary.get('skipped_files', 0):,}")
    print(f"Failed Files    : {summary.get('failed_files', 0):,}")
    print(f"Rows This Run   : {summary.get('rows_loaded_this_run', 0):,}")
    print(f"Rows In DB      : {summary.get('total_rows_in_database', 0):,}")
    print(f"Database        : {summary.get('database_path', '')}")
    print(f"Manifest        : {summary.get('manifest_path', '')}")

    _print_dataframe(
        "TOP CELL COUNTS",
        tower_ipdr_cell_counts(case_id).head(20),
        max_rows=20,
    )


def _show_staging_status(case_id: str) -> None:
    database_path = tower_ipdr_database_path(case_id)
    manifest_path = tower_ipdr_manifest_path(case_id)
    row_count = count_tower_ipdr_events(case_id)

    print("" + "=" * 78)
    print("TOWER IPDR STAGING STATUS")
    print("=" * 78)
    print(f"Database Exists : {database_path.exists()}")
    print(f"Manifest Exists : {manifest_path.exists()}")
    print(f"Database Path   : {database_path}")
    print(f"Manifest Path   : {manifest_path}")
    print(f"Rows In DB      : {row_count:,}")

    if row_count:
        _print_dataframe(
            "TOP CELL COUNTS",
            tower_ipdr_cell_counts(case_id).head(20),
            max_rows=20,
        )


def _saved_partition_times(case_id: str) -> list[str]:
    values: list[str] = []

    for item in list_sightings(case_id):
        value = item.get("date-time_timestamp") or item.get("window_start") or ""
        value = str(value).strip()

        if value:
            values.append(value)

    return values


def _ask_partition_time(case_id: str) -> str:
    saved_times = _saved_partition_times(case_id)

    if saved_times:
        _print_sightings(case_id)
        print("Saved partition number enter karein, ya exact date-time type karein.")
        print("Blank Enter = first saved partition.")

    value = input("Date-time partition (number/date-time): ").strip()

    if not value and saved_times:
        return saved_times[0]

    if value.isdigit() and saved_times:
        index = int(value)

        if 1 <= index <= len(saved_times):
            return saved_times[index - 1]

    if not value:
        raise CaseError("Date-time partition required hai.")

    return value


def _run_exact_partition_query(case: dict[str, Any]) -> None:
    case_id = str(case["case_id"])
    partition_time = _ask_partition_time(case_id)

    _print_dataframe(
        f"EXACT DATE-TIME PARTITION | {partition_time}",
        tower_ipdr_time_count(case_id, partition_time),
    )


def _run_minute_partition_query(case: dict[str, Any]) -> None:
    case_id = str(case["case_id"])
    partition_time = _ask_partition_time(case_id)

    _print_dataframe(
        f"SAME-MINUTE DATE-TIME PARTITION | {partition_time}",
        tower_ipdr_minute_count(case_id, partition_time),
    )


def _run_minute_uncommon_query(case: dict[str, Any]) -> None:
    case_id = str(case["case_id"])
    partition_time = _ask_partition_time(case_id)

    _print_dataframe(
        f"SAME-MINUTE UNCOMMON LEADS | {partition_time}",
        tower_ipdr_uncommon_in_minute(case_id, partition_time, limit=50),
        max_rows=50,
    )


def _run_legacy_full_analysis(case: dict[str, Any]) -> None:
    print("[WARNING] यह legacy full pandas analysis है.")
    print("[WARNING] Large Tower IPDR dump पर यह ज्यादा time और memory ले सकता है.")
    confirm = input("Run legacy full pandas analysis? Type YES to continue: ").strip()

    if confirm != "YES":
        print("[+] Legacy analysis cancelled.")
        return

    _execute(case, use_partitions=False)


def _partition_menu(case: dict[str, Any]) -> None:
    case_id = str(case["case_id"])

    while True:
        print("\n" + "=" * 78)
        print("DATE-TIME PARTITIONING")
        print("=" * 78)
        print("1. Add / Replace Date-Time Partitions")
        print("2. List Date-Time Partitions")
        print("3. Clear Date-Time Partitions")
        print("0. Back")

        choice = input("\nChoose Action: ").strip()

        if choice == "1":
            _new_partition(case)
        elif choice == "2":
            _print_sightings(case_id)
        elif choice == "3":
            clear_sightings(case_id)
            print("[+] Saved date-time partitions cleared.")
        elif choice == "0":
            return
        else:
            print("[-] Invalid choice. Select 0 to 3.")


def _run_fast_partition_analysis(case: dict[str, Any]) -> None:
    case_id = str(case["case_id"])

    if count_tower_ipdr_events(case_id) <= 0:
        print("[-] Tower IPDR dump loaded nahi hai.")
        print("[+] Pehle option 1: Run Complete Tower IPDR Dump Analysis chalakar backend data ready karein.")
        return

    partition_time = _ask_partition_time(case_id)

    result = tower_ipdr_investigation_summary(
        case_id,
        partition_time,
        mode="same_minute",
        lead_limit=50,
    )

    print_tower_ipdr_investigation_summary(
        result,
        max_leads=10,
    )


def _advanced_menu(case: dict[str, Any]) -> None:
    case_id = str(case["case_id"])

    while True:
        print("\n" + "=" * 78)
        print("ADVANCED TOWER IPDR TOOLS")
        print("=" * 78)
        print("1. Exact-second Query Only")
        print("2. Same-minute Query Only")
        print("3. Same-minute Uncommon Leads Only")
        print("4. Legacy Full Pandas Analysis")
        print("5. View Latest Legacy Tower IPDR Run")
        print("0. Back")

        choice = input("\nChoose Action: ").strip()

        if choice == "1":
            _run_exact_partition_query(case)
        elif choice == "2":
            _run_minute_partition_query(case)
        elif choice == "3":
            _run_minute_uncommon_query(case)
        elif choice == "4":
            _run_legacy_full_analysis(case)
        elif choice == "5":
            _show_latest(case_id)
        elif choice == "0":
            return
        else:
            print("[-] Invalid choice. Select 0 to 5.")



def _collect_date_time_ranges() -> list[tuple[str, str]]:
    print("\n" + "=" * 78)
    print("CREATE DATE-TIME PARTS")
    print("=" * 78)
    print("Har part ke liye Start Date-Time aur End Date-Time enter karein.")
    print("Example Date : 2026-06-11")
    print("Example Time : 20:00:00")
    print()
    print("Rule:")
    print("Part 1 Start + Part 1 End = Part 1")
    print("Part 2 Start + Part 2 End = Part 2")
    print("Blank Start Date = finish")
    print("=" * 78)

    ranges: list[tuple[str, str]] = []
    part_no = 1

    while True:
        print(f"\nPart {part_no}")

        start_date = input("  Start Date (blank = finish): ").strip()
        if not start_date:
            break

        start_time = input("  Start Time: ").strip()
        if not start_time:
            print("[-] Start Time required hai. Is part ko dobara enter karein.")
            continue

        end_date = input("  End Date  : ").strip()
        if not end_date:
            print("[-] End Date required hai. Is part ko dobara enter karein.")
            continue

        end_time = input("  End Time  : ").strip()
        if not end_time:
            print("[-] End Time required hai. Is part ko dobara enter karein.")
            continue

        ranges.append(
            (
                f"{start_date} {start_time}",
                f"{end_date} {end_time}",
            )
        )
        part_no += 1

    return ranges



def _run_complete_tower_ipdr_analysis(case: dict[str, Any]) -> None:
    """Run total Tower IPDR analysis on the full loaded backend dataset.

    This is different from Part-wise Analysis.
    Complete Analysis = full database analysis.
    Part-wise Analysis = saved Date-Time Parts analysis.
    """

    case_id = str(case["case_id"])

    if not _ensure_tower_ipdr_data_ready(
        case_id,
        lambda _case_id: _import_staging(case),
    ):
        return

    print("[+] Complete Tower IPDR total analysis start ho raha hai...")

    from datetime import datetime
    from pathlib import Path

    import duckdb
    import pandas as pd

    from modules.staging.tower_ipdr_staging import tower_ipdr_database_path

    db_path = tower_ipdr_database_path(case_id)

    if not Path(db_path).exists():
        print("[-] Tower IPDR database nahi mila.")
        print(f"    Database: {db_path}")
        return

    run_id = datetime.now().strftime("tower_ipdr_complete_%Y%m%d_%H%M%S")
    report_dir = (
        Path("cases")
        / "active"
        / case_id
        / "reports"
        / "tower_dump"
        / "ipdr"
        / "complete"
        / run_id
    )
    report_dir.mkdir(parents=True, exist_ok=True)

    excel_path = report_dir / "tower_ipdr_complete_analysis.xlsx"
    summary_path = report_dir / "tower_ipdr_complete_summary.txt"

    con = duckdb.connect(str(db_path), read_only=True)

    try:
        columns = [
            row[1]
            for row in con.execute("PRAGMA table_info('tower_ipdr_events')").fetchall()
        ]

        def has(column: str) -> bool:
            return column in columns

        def q(column: str) -> str:
            return '"' + column.replace('"', '""') + '"'

        def text_column(column: str) -> str:
            if has(column):
                return f"NULLIF(TRIM(CAST({q(column)} AS VARCHAR)), '')"
            return "NULL"

        def count_distinct(column: str) -> str:
            return f"COUNT(DISTINCT {text_column(column)})" if has(column) else "0"

        subscriber = text_column("subscriber_number")
        searched_cell = text_column("searched_cell_id")
        imei = text_column("imei")
        imsi = text_column("imsi")
        source_file = text_column("source_file")

        if has("event_time"):
            event_ts = 'TRY_CAST("event_time" AS TIMESTAMP)'
        elif has("event_datetime"):
            event_ts = 'TRY_CAST("event_datetime" AS TIMESTAMP)'
        elif has("start_time"):
            event_ts = 'TRY_CAST("start_time" AS TIMESTAMP)'
        else:
            event_ts = "NULL"

        def read_sql(sql: str) -> pd.DataFrame:
            return con.execute(sql).fetchdf()

        summary = read_sql(
            f"""
            SELECT 'Total Events' AS metric, CAST(COUNT(*) AS VARCHAR) AS value FROM tower_ipdr_events
            UNION ALL SELECT 'Unique Subscribers', CAST({count_distinct('subscriber_number')} AS VARCHAR) FROM tower_ipdr_events
            UNION ALL SELECT 'Unique IMEI', CAST({count_distinct('imei')} AS VARCHAR) FROM tower_ipdr_events
            UNION ALL SELECT 'Unique IMSI', CAST({count_distinct('imsi')} AS VARCHAR) FROM tower_ipdr_events
            UNION ALL SELECT 'Unique Searched Cells', CAST({count_distinct('searched_cell_id')} AS VARCHAR) FROM tower_ipdr_events
            UNION ALL SELECT 'Unique Source Files', CAST({count_distinct('source_file')} AS VARCHAR) FROM tower_ipdr_events
            UNION ALL SELECT 'First Event Time', CAST(MIN({event_ts}) AS VARCHAR) FROM tower_ipdr_events
            UNION ALL SELECT 'Last Event Time', CAST(MAX({event_ts}) AS VARCHAR) FROM tower_ipdr_events
            """
        )

        cell_summary = read_sql(
            f"""
            SELECT
                {searched_cell} AS searched_cell_id,
                COUNT(*) AS event_count,
                COUNT(DISTINCT {subscriber}) AS subscriber_count,
                COUNT(DISTINCT {imei}) AS imei_count,
                COUNT(DISTINCT {imsi}) AS imsi_count,
                MIN({event_ts}) AS first_seen,
                MAX({event_ts}) AS last_seen
            FROM tower_ipdr_events
            WHERE {searched_cell} IS NOT NULL
            GROUP BY 1
            ORDER BY event_count DESC
            LIMIT 500
            """
        )

        top_subscribers = read_sql(
            f"""
            SELECT
                {subscriber} AS subscriber_number,
                COUNT(*) AS event_count,
                COUNT(DISTINCT {searched_cell}) AS cells_seen,
                COUNT(DISTINCT {imei}) AS imei_count,
                COUNT(DISTINCT {imsi}) AS imsi_count,
                MIN({event_ts}) AS first_seen,
                MAX({event_ts}) AS last_seen
            FROM tower_ipdr_events
            WHERE {subscriber} IS NOT NULL
            GROUP BY 1
            ORDER BY event_count DESC
            LIMIT 1000
            """
        )

        repeat_presence = top_subscribers.query("event_count >= 2").head(500).copy()

        rare_presence = read_sql(
            f"""
            SELECT
                {subscriber} AS subscriber_number,
                COUNT(*) AS event_count,
                COUNT(DISTINCT {searched_cell}) AS cells_seen,
                COUNT(DISTINCT {imei}) AS imei_count,
                COUNT(DISTINCT {imsi}) AS imsi_count,
                MIN({event_ts}) AS first_seen,
                MAX({event_ts}) AS last_seen
            FROM tower_ipdr_events
            WHERE {subscriber} IS NOT NULL
            GROUP BY 1
            HAVING COUNT(*) <= 2
            ORDER BY event_count ASC, first_seen ASC
            LIMIT 500
            """
        )

        multi_cell_presence = read_sql(
            f"""
            SELECT
                {subscriber} AS subscriber_number,
                COUNT(*) AS event_count,
                COUNT(DISTINCT {searched_cell}) AS cells_seen,
                STRING_AGG(DISTINCT CAST({searched_cell} AS VARCHAR), ', ') AS searched_cells,
                COUNT(DISTINCT {imei}) AS imei_count,
                COUNT(DISTINCT {imsi}) AS imsi_count,
                MIN({event_ts}) AS first_seen,
                MAX({event_ts}) AS last_seen
            FROM tower_ipdr_events
            WHERE {subscriber} IS NOT NULL
              AND {searched_cell} IS NOT NULL
            GROUP BY 1
            HAVING COUNT(DISTINCT {searched_cell}) >= 2
            ORDER BY cells_seen DESC, event_count DESC
            LIMIT 500
            """
        )

        shared_imei = read_sql(
            f"""
            SELECT
                {imei} AS imei,
                COUNT(*) AS event_count,
                COUNT(DISTINCT {subscriber}) AS subscriber_count,
                STRING_AGG(DISTINCT CAST({subscriber} AS VARCHAR), ', ') AS subscribers,
                COUNT(DISTINCT {searched_cell}) AS cells_seen,
                MIN({event_ts}) AS first_seen,
                MAX({event_ts}) AS last_seen
            FROM tower_ipdr_events
            WHERE {imei} IS NOT NULL
              AND {subscriber} IS NOT NULL
            GROUP BY 1
            HAVING COUNT(DISTINCT {subscriber}) >= 2
            ORDER BY subscriber_count DESC, event_count DESC
            LIMIT 500
            """
        )

        shared_imsi = read_sql(
            f"""
            SELECT
                {imsi} AS imsi,
                COUNT(*) AS event_count,
                COUNT(DISTINCT {subscriber}) AS subscriber_count,
                STRING_AGG(DISTINCT CAST({subscriber} AS VARCHAR), ', ') AS subscribers,
                COUNT(DISTINCT {searched_cell}) AS cells_seen,
                MIN({event_ts}) AS first_seen,
                MAX({event_ts}) AS last_seen
            FROM tower_ipdr_events
            WHERE {imsi} IS NOT NULL
              AND {subscriber} IS NOT NULL
            GROUP BY 1
            HAVING COUNT(DISTINCT {subscriber}) >= 2
            ORDER BY subscriber_count DESC, event_count DESC
            LIMIT 500
            """
        )

        if event_ts != "NULL":
            hourly_activity = read_sql(
                f"""
                SELECT
                    STRFTIME({event_ts}, '%H') AS hour,
                    COUNT(*) AS event_count,
                    COUNT(DISTINCT {subscriber}) AS subscriber_count,
                    COUNT(DISTINCT {searched_cell}) AS cell_count
                FROM tower_ipdr_events
                WHERE {event_ts} IS NOT NULL
                GROUP BY 1
                ORDER BY 1
                """
            )
        else:
            hourly_activity = pd.DataFrame(
                columns=["hour", "event_count", "subscriber_count", "cell_count"]
            )

        source_file_summary = read_sql(
            f"""
            SELECT
                {source_file} AS source_file,
                COUNT(*) AS event_count,
                COUNT(DISTINCT {subscriber}) AS subscriber_count,
                COUNT(DISTINCT {searched_cell}) AS cell_count,
                MIN({event_ts}) AS first_seen,
                MAX({event_ts}) AS last_seen
            FROM tower_ipdr_events
            WHERE {source_file} IS NOT NULL
            GROUP BY 1
            ORDER BY event_count DESC
            LIMIT 1000
            """
        )

        checks = []
        total_events = int(
            con.execute("SELECT COUNT(*) FROM tower_ipdr_events").fetchone()[0] or 0
        )

        def missing_count(column: str) -> int:
            if not has(column):
                return total_events
            return int(
                con.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM tower_ipdr_events
                    WHERE {text_column(column)} IS NULL
                    """
                ).fetchone()[0]
                or 0
            )

        for label, column in [
            ("Missing subscriber number", "subscriber_number"),
            ("Missing searched cell", "searched_cell_id"),
            ("Missing IMEI", "imei"),
            ("Missing IMSI", "imsi"),
            ("Missing source file", "source_file"),
        ]:
            rows = missing_count(column)
            percentage = round((rows / total_events * 100), 4) if total_events else 0
            checks.append(
                {
                    "check": label,
                    "rows": rows,
                    "percentage": percentage,
                }
            )

        data_quality = pd.DataFrame(checks)

        priority_leads = top_subscribers.copy()

        if not priority_leads.empty:
            priority_leads["priority_score"] = (
                priority_leads["event_count"].clip(upper=100)
                + (priority_leads["cells_seen"].clip(upper=10) * 10)
                + ((priority_leads["imei_count"] > 1).astype(int) * 20)
                + ((priority_leads["imsi_count"] > 1).astype(int) * 20)
            )

            def priority(value: int) -> str:
                if value >= 120:
                    return "High"
                if value >= 70:
                    return "Medium"
                return "Low"

            def reason(row) -> str:
                reasons = []
                if row.get("cells_seen", 0) >= 2:
                    reasons.append("multi-cell presence")
                if row.get("event_count", 0) >= 10:
                    reasons.append("repeat/high activity")
                if row.get("imei_count", 0) >= 2:
                    reasons.append("multiple IMEI")
                if row.get("imsi_count", 0) >= 2:
                    reasons.append("multiple IMSI")
                return ", ".join(reasons) or "low/normal activity"

            priority_leads["priority"] = priority_leads["priority_score"].map(priority)
            priority_leads["confidence"] = priority_leads["cells_seen"].map(
                lambda value: "High" if value >= 2 else "Medium"
            )
            priority_leads["why_important"] = priority_leads.apply(reason, axis=1)
            priority_leads["next_action"] = (
                "Verify with IPDR details, CDR/SDR/CAF, IMEI/IMSI, tower location and field input."
            )
            priority_leads = priority_leads.sort_values(
                ["priority_score", "cells_seen", "event_count"],
                ascending=False,
            ).head(500)

        sheets = {
            "1. Executive Summary": summary,
            "2. Cell Summary": cell_summary,
            "3. Top Subscribers": top_subscribers,
            "4. Repeat Presence": repeat_presence,
            "5. Rare Presence": rare_presence,
            "6. Multi Cell Presence": multi_cell_presence,
            "7. Priority Leads": priority_leads,
            "8. Shared IMEI": shared_imei,
            "9. Shared IMSI": shared_imsi,
            "10. Hourly Activity": hourly_activity,
            "11. Source Files": source_file_summary,
            "12. Data Quality": data_quality,
        }

        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            for sheet_name, dataframe in sheets.items():
                if dataframe is None:
                    dataframe = pd.DataFrame()
                dataframe.to_excel(writer, sheet_name=sheet_name[:31], index=False)

        summary_lines = [
            "=" * 78,
            "TOWER IPDR COMPLETE ANALYSIS",
            "=" * 78,
            f"Case ID      : {case_id}",
            f"Run ID       : {run_id}",
            f"Database     : {db_path}",
            f"Report Folder: {report_dir}",
            f"Excel Report : {excel_path}",
            "",
            "EXECUTIVE SUMMARY",
            "-" * 78,
        ]

        for _, row in summary.iterrows():
            summary_lines.append(f"{row['metric']}: {row['value']}")

        summary_lines.extend(
            [
                "",
                "IMPORTANT LEADS",
                "-" * 78,
            ]
        )

        if priority_leads.empty:
            summary_lines.append("No priority leads found.")
        else:
            display_columns = [
                column
                for column in [
                    "subscriber_number",
                    "priority",
                    "confidence",
                    "priority_score",
                    "event_count",
                    "cells_seen",
                    "imei_count",
                    "imsi_count",
                    "first_seen",
                    "last_seen",
                    "why_important",
                    "next_action",
                ]
                if column in priority_leads.columns
            ]
            summary_lines.append(
                priority_leads[display_columns].head(50).to_string(index=False)
            )

        summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

        def _summary_value(metric_name: str) -> str:
            matched = summary.loc[summary["metric"] == metric_name, "value"]
            if matched.empty:
                return "0"

            value = str(matched.iloc[0])
            try:
                numeric_value = float(value)
                if numeric_value.is_integer():
                    return f"{int(numeric_value):,}"
            except Exception:
                pass

            return value

        def _count_rows(dataframe) -> str:
            try:
                return f"{len(dataframe):,}"
            except Exception:
                return "0"

        def _summary_value(metric_name: str) -> str:
            matched = summary.loc[summary["metric"] == metric_name, "value"]
            if matched.empty:
                return "0"

            value = str(matched.iloc[0])
            try:
                numeric_value = float(value)
                if numeric_value.is_integer():
                    return f"{int(numeric_value):,}"
            except Exception:
                pass

            return value

        def _count_rows(dataframe) -> str:
            try:
                return f"{len(dataframe):,}"
            except Exception:
                return "0"

        print("=" * 78)
        print("TOWER IPDR COMPLETE ANALYSIS GENERATED")
        print("=" * 78)
        print()
        print("QUICK INVESTIGATION SUMMARY")
        print("-" * 78)
        print(f"Total Events        : {_summary_value('Total Events')}")
        print(f"Unique Subscribers  : {_summary_value('Unique Subscribers')}")
        print(f"Unique IMEI         : {_summary_value('Unique IMEI')}")
        print(f"Unique IMSI         : {_summary_value('Unique IMSI')}")
        print(f"Unique Cells        : {_summary_value('Unique Searched Cells')}")
        print(f"Priority Leads      : {_count_rows(priority_leads)}")
        print(f"Multi-Cell Leads    : {_count_rows(multi_cell_presence)}")
        print(f"Rare Presence Leads : {_count_rows(rare_presence)}")
        print(f"Shared IMEI         : {_count_rows(shared_imei)}")
        print(f"Shared IMSI         : {_count_rows(shared_imsi)}")
        print()

        print("TOP PRIORITY LEADS")
        print("-" * 78)
        if priority_leads.empty:
            print("No priority leads found.")
        else:
            console_columns = [
                column
                for column in [
                    "subscriber_number",
                    "priority",
                    "confidence",
                    "priority_score",
                    "event_count",
                    "cells_seen",
                    "imei_count",
                    "imsi_count",
                    "why_important",
                ]
                if column in priority_leads.columns
            ]

            with pd.option_context(
                "display.max_columns",
                20,
                "display.max_colwidth",
                60,
                "display.width",
                180,
            ):
                print(priority_leads[console_columns].head(10).to_string(index=False))

        print()
        print("REPORT FILES")
        print("-" * 78)
        print(f"Report Folder : {report_dir}")
        print(f"Main Summary  : {summary_path}")
        print(f"Excel Report  : {excel_path}")
        print("=" * 78)

    finally:
        con.close()

def _create_date_time_parts(case: dict[str, Any]) -> None:
    case_id = str(case["case_id"])

    ranges = _collect_date_time_ranges()

    if not ranges:
        print("[-] Koi Date-Time Part enter nahi kiya gaya.")
        return

    payload = save_date_time_parts(
        case_id,
        TOWER_IPDR_WORKFLOW,
        ranges,
    )

    print_date_time_parts(case_id, TOWER_IPDR_WORKFLOW)
    print_date_time_part_warnings(case_id, TOWER_IPDR_WORKFLOW)

    print("\n[+] Date-Time Parts saved.")
    print(f"[+] Total Parts: {payload.get('parts_count', 0)}")
    print("[+] Ab option 3: Part-wise Analysis chalayein.")


def _run_partwise_analysis(case: dict[str, Any]) -> None:
    case_id = str(case["case_id"])
    parts = list_date_time_parts(case_id, TOWER_IPDR_WORKFLOW)

    if not parts:
        print("[-] Date-Time Parts saved nahi hain.")
        print("[+] Pehle option 2: Create Date-Time Parts chalayein.")
        return

    if count_tower_ipdr_events(case_id) <= 0:
        print("[-] Tower IPDR dump loaded nahi hai.")
        print("[+] Pehle option 1: Load Dump Data chalayein.")
        return

    print_date_time_parts(case_id, TOWER_IPDR_WORKFLOW)

    print("" + "=" * 78)
    print("PART-WISE TOWER IPDR ANALYSIS")
    print("=" * 78)
    print("A. Analyze All Date-Time Parts")
    print("0. Back")

    for part in parts:
        print(
            f"{part.get('part_no')}. "
            f"{part.get('part_name')} | "
            f"{part.get('start_time')} to {part.get('end_time')}"
        )

    choice = input("Choose Part Number or A: ").strip().lower()

    if choice == "0":
        return

    selected_parts = []

    if choice == "a":
        selected_parts = parts
    else:
        try:
            selected_no = int(choice)
        except ValueError:
            print("[-] Invalid choice.")
            return

        selected_parts = [
            part for part in parts
            if int(part.get("part_no", -1)) == selected_no
        ]

        if not selected_parts:
            print("[-] Selected part nahi mila.")
            return

    for part in selected_parts:
        print("" + "#" * 78)
        print(f"{part.get('part_name')} ANALYSIS")
        print("#" * 78)
        print(f"Period: {part.get('start_time')} to {part.get('end_time')}")

        result = tower_ipdr_range_investigation_summary(
            case_id,
            str(part.get("start_time")),
            str(part.get("end_time")),
            lead_limit=50,
        )

        print_tower_ipdr_investigation_summary(
            result,
            max_leads=10,
        )


def _view_or_export_report(case: dict[str, Any]) -> None:
    case_id = str(case["case_id"])
    parts = list_date_time_parts(case_id, TOWER_IPDR_WORKFLOW)

    print("" + "=" * 78)
    print("VIEW / EXPORT REPORT")
    print("=" * 78)

    if not parts:
        print("[-] Date-Time Parts available nahi hain.")
        print("[+] Pehle option 2: Create Date-Time Parts chalayein.")
        return

    if count_tower_ipdr_events(case_id) <= 0:
        print("[-] Tower IPDR dump loaded nahi hai.")
        print("[+] Pehle option 1: Load Dump Data chalayein.")
        return

    print_date_time_parts(case_id, TOWER_IPDR_WORKFLOW)
    print_date_time_part_warnings(case_id, TOWER_IPDR_WORKFLOW)

    print("1. Export Part-wise Investigation Report")
    print("0. Back")

    choice = input("Choose Action: ").strip()

    if choice == "0":
        return

    if choice != "1":
        print("[-] Invalid choice. Select 0 or 1.")
        return

    print("[+] Report export start ho raha hai...")
    print("[+] Har Date-Time Part par analysis chalega aur report save hogi.")

    manifest = export_tower_ipdr_partwise_range_report(
        case_id,
        parts,
        lead_limit=50,
        max_leads_in_text=20,
    )

    excel_path = export_tower_ipdr_excel_workbook_from_manifest(
        manifest,
        max_rows_per_sheet=50000,
    )

    saved_files = manifest.get("saved_files", {})
    saved_files["excel_workbook"] = excel_path
    manifest["saved_files"] = saved_files

    latest_report_path = save_tower_ipdr_partwise_latest_report(
        case_id,
        manifest,
    )
    saved_files["latest_report"] = str(latest_report_path)
    manifest["saved_files"] = saved_files

    print("[+] Part-wise investigation report generated successfully.")
    print(f"[+] Report Folder : {manifest.get('output_dir')}")
    print(f"[+] Main Report   : {saved_files.get('investigation_summary_all_parts')}")
    print(f"[+] Summary CSV   : {saved_files.get('all_parts_summary')}")
    print(f"[+] Excel Report  : {saved_files.get('excel_workbook')}")
    print(f"[+] Manifest      : {saved_files.get('manifest')}")



def _show_latest(case_id: str) -> None:
    manifest = load_latest_tower_ipdr_manifest(case_id)

    if not manifest:
        print("[-] Koi Tower IPDR run available nahi hai.")
        return

    print("\n" + "=" * 78)
    print(f"LATEST TOWER IPDR RUN: {manifest.get('run_id', '')}")
    print("=" * 78)
    print(f"Created At      : {manifest.get('created_at', '')}")
    print(f"Input Folder    : {manifest.get('input_folder', '')}")
    print(f"Events          : {manifest.get('record_count', 0)}")
    print(f"Searched Cells  : {manifest.get('cell_count', 0)}")
    print(f"Partitions      : {manifest.get('partition_count', 0)}")
    print(f"Actual Rule     : {manifest.get('actual_event_rule', '')}")
    print(f"Allocation Rule : {manifest.get('allocation_overlap_rule', '')}")
    print(f"Report Status   : {manifest.get('report_status', '')}")
    print(
        "Excel Report    : "
        f"{manifest.get('user_facing_report', 'Not generated')}"
    )
    print(f"Backend tables  : {len(manifest.get('saved_files', {}))}")
    print("=" * 78)


def handle_tower_ipdr_workspace(
    case: dict[str, Any],
) -> dict[str, Any] | None:
    case_id = str(case["case_id"])

    while True:
        try:
            choice = _menu(case)

            if choice == "1":
                _run_complete_tower_ipdr_analysis(case)

            elif choice == "2":
                _create_date_time_parts(case)

            elif choice == "3":
                case_id = str(case["case_id"])
                if _ensure_tower_ipdr_data_ready(
                    case_id,
                    lambda _case_id: _import_staging(case),
                ):
                    _run_partwise_analysis(case)

            elif choice == "4":
                _view_or_export_report(case)

            elif choice == "0":
                return None

            else:
                print("[-] Invalid choice. Select 0 to 4.")

        except KeyboardInterrupt:
            print("\n[-] Returning to Tower IPDR workspace.")

        except EOFError:
            return None

        except Exception as error:
            print(
                f"[-] Tower IPDR workspace error: "
                f"{type(error).__name__}: {error}"
            )