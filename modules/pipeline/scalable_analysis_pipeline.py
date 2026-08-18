"""
Common scalable analysis pipeline.

Purpose:
- Provide one reusable path for heavy telecom workflows.
- Loader creates normalized DataFrame.
- DataFrame is staged to Parquet and DuckDB.
- SQL analysis function runs on staged DuckDB data.
- Latest pipeline state is saved for GUI/report reuse.

User-facing output should remain Excel/GUI only.
DuckDB, Parquet and JSON files are internal backend/cache files.
"""

from __future__ import annotations

import inspect
import json
import os
import time
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

from modules.loader.tower_spot_layout import (
    normalize_selected_spot_folders,
    select_tower_evidence_files,
)
from modules.pipeline.normalized_stage_cache import (
    load_reusable_normalized_stage,
    normalized_cache_manifest_path,
    save_reusable_normalized_stage,
    validate_normalized_stage,
)
from modules.staging.scalable_store import (
    case_staging_root,
    stage_dataframe_to_parquet_and_duckdb,
)


DEFAULT_SUPPORTED_SUFFIXES = {".csv", ".txt", ".tsv", ".xlsx", ".xls"}


@dataclass(frozen=True)
class ScalablePipelineConfig:
    """Configuration for one scalable workflow."""

    case_id: str
    workflow: str
    table_name: str
    dataset_name: str = "normalized"
    dataframe_key: str = "df"


@dataclass(frozen=True)
class ScalablePipelineTimings:
    """Execution timings in milliseconds."""

    load_ms: float
    stage_ms: float
    sql_analysis_ms: float
    total_ms: float


def build_input_fingerprint(
    input_folder: str | Path,
    supported_suffixes: set[str] | None = None,
    *,
    selected_spot_folders: Iterable[str] | None = None,
    include_root_files: bool = True,
) -> dict[str, Any]:
    """
    Build fingerprint of input files.

    This helps decide whether backend staged data belongs to the current input.
    """

    root = Path(input_folder)
    suffixes = supported_suffixes or DEFAULT_SUPPORTED_SUFFIXES
    files: list[dict[str, Any]] = []

    normalized_selection: tuple[str, ...] | None = None

    if root.is_dir():
        if selected_spot_folders is not None:
            normalized_selection = normalize_selected_spot_folders(
                root,
                selected_spot_folders,
            )

        candidates = [
            path
            for path in root.rglob("*")
            if (
                path.is_file()
                and path.suffix.lower()
                in suffixes
            )
        ]
        selected_files = select_tower_evidence_files(
            root,
            candidates,
            selected_spot_folders=normalized_selection,
            include_root_files=include_root_files,
        )

        for path in selected_files:
            stat = path.stat()
            files.append(
                {
                    "path": str(
                        path.relative_to(
                            root
                        )
                    ),
                    "size": int(
                        stat.st_size
                    ),
                    "mtime_ns": int(
                        stat.st_mtime_ns
                    ),
                }
            )

    return {
        "input_folder": str(root),
        "selected_spot_folders": (
            list(
                normalized_selection
            )
            if normalized_selection is not None
            else None
        ),
        "include_root_files": bool(
            include_root_files
        ),
        "file_count": len(files),
        "total_size": sum(item["size"] for item in files),
        "files": files,
    }


def latest_pipeline_state_path(case_id: str, workflow: str) -> Path:
    """Return latest pipeline state JSON path."""

    return case_staging_root(case_id, workflow) / "pipeline" / "latest_pipeline.json"


def _json_safe(value: Any) -> Any:
    """Convert common Python objects to JSON-safe values."""

    if is_dataclass(value):
        return asdict(value)

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, pd.DataFrame):
        return {
            "type": "DataFrame",
            "rows": int(len(value)),
            "columns": list(map(str, value.columns)),
        }

    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]

    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def write_latest_pipeline_state(
    case_id: str,
    workflow: str,
    payload: dict[str, Any],
) -> Path:
    """Save latest pipeline state for GUI/report reuse."""

    path = latest_pipeline_state_path(case_id, workflow)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(payload), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def read_latest_pipeline_state(
    case_id: str,
    workflow: str,
) -> dict[str, Any] | None:
    """Read latest pipeline state if available."""

    path = latest_pipeline_state_path(case_id, workflow)

    if not path.exists():
        return None

    return json.loads(path.read_text(encoding="utf-8"))


def _call_loader(
    loader: Callable[..., Any],
    input_folder: str | Path,
    loader_kwargs: dict[str, Any] | None,
) -> Any:
    """Call a loader using the common convention: loader(input_folder, **kwargs)."""

    return loader(input_folder, **(loader_kwargs or {}))


def _extract_dataframe(
    load_result: Any,
    dataframe_key: str,
) -> pd.DataFrame:
    """Extract normalized DataFrame from loader result."""

    if isinstance(load_result, pd.DataFrame):
        return load_result

    if isinstance(load_result, dict):
        dataframe = load_result.get(dataframe_key)

        if isinstance(dataframe, pd.DataFrame):
            return dataframe

    raise ValueError(
        f"Loader did not return a pandas DataFrame using key {dataframe_key!r}."
    )


def _call_sql_analysis(
    sql_analysis: Callable[..., Any],
    candidate_kwargs: dict[str, Any],
) -> Any:
    """
    Call SQL analysis function using only supported keyword arguments.

    This lets different modules use slightly different analysis signatures,
    for example:
    - build_tower_cdr_duckdb_presence(case_id, top_limit=200)
    - future_analysis(case_id, workflow, table_name, duckdb_path)
    """

    signature = inspect.signature(sql_analysis)
    parameters = signature.parameters

    accepts_var_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )

    if accepts_var_kwargs:
        return sql_analysis(**candidate_kwargs)

    supported_kwargs = {
        key: value
        for key, value in candidate_kwargs.items()
        if key in parameters
    }

    try:
        return sql_analysis(**supported_kwargs)
    except TypeError:
        return sql_analysis(candidate_kwargs["case_id"])


def _row_summary(value: Any) -> Any:
    """Return row-count summary for DataFrame/dict results."""

    if isinstance(value, pd.DataFrame):
        return int(len(value))

    if isinstance(value, dict):
        output: dict[str, Any] = {}

        for key, item in value.items():
            if isinstance(item, pd.DataFrame):
                output[key] = int(len(item))
            else:
                output[key] = _row_summary(item)

        return output

    if isinstance(value, list):
        return len(value)

    return None


def print_pipeline_backend_status(
    payload: dict[str, Any],
    *,
    title: str = "FAST ANALYSIS BACKEND READY",
) -> None:
    """
    Print user-friendly scalable backend status.

    Normal mode hides DuckDB/Parquet/JSON paths.
    Developer can show paths using:
    TELECOM_DEBUG_BACKEND=1 python3 -u main.py
    """

    debug_backend = os.environ.get("TELECOM_DEBUG_BACKEND") == "1"
    stage = payload.get("stage", {}) or {}
    fingerprint = payload.get("input_fingerprint", {}) or {}
    timings = payload.get("timings", {}) or {}

    print()
    print(title)
    print("-" * 78)
    print(f"Records indexed : {int(stage.get('record_count', 0)):,}")
    print(f"Columns indexed : {int(stage.get('column_count', 0)):,}")
    print(f"Input files     : {int(fingerprint.get('file_count', 0)):,}")
    print(
        "Index status    : "
        + (
            "Verified existing index reused"
            if payload.get(
                "stage_reused"
            )
            else "Index refreshed from normalized data"
        )
    )
    print("Speed mode      : DuckDB SQL + Parquet internal backend")
    print("User output     : Excel / GUI report only")

    if timings:
        print(f"Load time ms    : {timings.get('load_ms', 0)}")
        print(f"Stage time ms   : {timings.get('stage_ms', 0)}")
        print(f"SQL time ms     : {timings.get('sql_analysis_ms', 0)}")

    print("-" * 78)

    if debug_backend:
        print("DEBUG BACKEND FILES")
        print("-" * 78)
        print(f"Parquet file    : {stage.get('parquet_path', '')}")
        print(f"DuckDB file     : {stage.get('duckdb_path', '')}")
        print(f"Manifest        : {stage.get('manifest_path', '')}")
        print(f"Pipeline state  : {payload.get('pipeline_state_path', '')}")
        print("-" * 78)


def run_scalable_analysis_pipeline(
    *,
    case_id: str,
    workflow: str,
    input_folder: str | Path,
    loader: Callable[..., Any],
    table_name: str,
    dataset_name: str = "normalized",
    dataframe_key: str = "df",
    loader_kwargs: dict[str, Any] | None = None,
    sql_analysis: Callable[..., Any] | None = None,
    sql_analysis_kwargs: dict[str, Any] | None = None,
    supported_suffixes: set[str] | None = None,
    fingerprint_kwargs: dict[str, Any] | None = None,
    normalized_cache_key: str | None = None,
    required_cached_columns: Iterable[str] | None = None,
    status_title: str = "FAST ANALYSIS BACKEND READY",
    print_status: bool = True,
) -> dict[str, Any]:
    """
    Run common scalable workflow.

    Returns a dict containing:
    - ok
    - load_result
    - dataframe
    - stage
    - sql_analysis
    - timings
    - pipeline_state_path
    """

    total_started = time.perf_counter()

    config = ScalablePipelineConfig(
        case_id=str(case_id),
        workflow=str(workflow),
        table_name=str(table_name),
        dataset_name=str(dataset_name),
        dataframe_key=str(dataframe_key),
    )

    fingerprint = build_input_fingerprint(
        input_folder=input_folder,
        supported_suffixes=supported_suffixes,
        **(
            fingerprint_kwargs
            or {}
        ),
    )

    normalized_cache_key = str(
        normalized_cache_key
        or ""
    ).strip()
    required_columns = tuple(
        str(column)
        for column in (
            required_cached_columns
            or ()
        )
    )

    load_started = time.perf_counter()
    cache_lookup: dict[str, Any] = {
        "reused": False,
        "reason": "CACHE_DISABLED",
    }

    if normalized_cache_key:
        cache_lookup = (
            load_reusable_normalized_stage(
                case_id=str(
                    case_id
                ),
                workflow=str(
                    workflow
                ),
                table_name=str(
                    table_name
                ),
                dataset_name=str(
                    dataset_name
                ),
                cache_key=(
                    normalized_cache_key
                ),
                input_fingerprint=(
                    fingerprint
                ),
                required_columns=(
                    required_columns
                ),
                dataframe_key=str(
                    dataframe_key
                ),
            )
        )

    normalized_cache_reused = bool(
        cache_lookup.get(
            "reused",
            False,
        )
    )
    stage_reused = (
        normalized_cache_reused
    )
    stage_payload: dict[str, Any] | None = (
        dict(
            cache_lookup.get(
                "stage",
                {},
            )
        )
        if normalized_cache_reused
        else None
    )

    if normalized_cache_reused:
        load_result = cache_lookup[
            "load_result"
        ]
        dataframe = cache_lookup[
            "dataframe"
        ]
        print(
            "[+] Raw input files unchanged; "
            "normalized cache reused."
        )
        print(
            "[+] Raw parsing and backend index rewrite skipped."
        )

    else:
        cache_reason = str(
            cache_lookup.get(
                "reason",
                "CACHE_NOT_REUSED",
            )
        )

        if (
            normalized_cache_key
            and cache_reason
            != "CACHE_MANIFEST_NOT_FOUND"
        ):
            print(
                "[=] Normalized cache not reused: "
                f"{cache_reason}"
            )

        load_result = _call_loader(
            loader,
            input_folder,
            loader_kwargs,
        )
        dataframe = _extract_dataframe(
            load_result,
            dataframe_key,
        )

        if dataframe.empty:
            raise ValueError(
                "Loaded DataFrame is empty. Nothing to stage or analyze."
            )

        if (
            isinstance(
                load_result,
                dict,
            )
            and bool(
                load_result.get(
                    "cache_reused",
                    False,
                )
            )
        ):
            try:
                stage_payload = (
                    validate_normalized_stage(
                        case_id=str(
                            case_id
                        ),
                        workflow=str(
                            workflow
                        ),
                        table_name=str(
                            table_name
                        ),
                        dataset_name=str(
                            dataset_name
                        ),
                        dataframe=dataframe,
                        required_columns=(
                            required_columns
                        ),
                    )
                )
                stage_reused = True
                print(
                    "[+] Verified backend index already matches "
                    "the cached normalized data."
                )
                print(
                    "[+] Duplicate Parquet and DuckDB rewrite skipped."
                )

            except Exception as error:
                print(
                    "[=] Existing backend index could not be reused: "
                    f"{type(error).__name__}: {error}"
                )

    if dataframe.empty:
        raise ValueError(
            "Loaded DataFrame is empty. Nothing to stage or analyze."
        )

    load_ms = round(
        (
            time.perf_counter()
            - load_started
        )
        * 1000,
        2,
    )

    if stage_payload is None:
        stage_started = time.perf_counter()
        stage_result = (
            stage_dataframe_to_parquet_and_duckdb(
                case_id=case_id,
                workflow=workflow,
                dataframe=dataframe,
                table_name=table_name,
                dataset_name=dataset_name,
            )
        )
        stage_ms = round(
            (
                time.perf_counter()
                - stage_started
            )
            * 1000,
            2,
        )
        stage_payload = asdict(
            stage_result
        )

    else:
        stage_ms = 0.0

    cache_manifest_path = (
        str(
            normalized_cache_manifest_path(
                str(
                    case_id
                ),
                str(
                    workflow
                ),
            )
        )
        if normalized_cache_reused
        else ""
    )

    if (
        normalized_cache_key
        and not normalized_cache_reused
    ):
        try:
            cache_manifest_path = str(
                save_reusable_normalized_stage(
                    case_id=str(
                        case_id
                    ),
                    workflow=str(
                        workflow
                    ),
                    cache_key=(
                        normalized_cache_key
                    ),
                    input_fingerprint=(
                        fingerprint
                    ),
                    load_result=(
                        load_result
                    ),
                )
            )

        except Exception as error:
            print(
                "[!] Normalized reuse cache could not be saved. "
                "Current analysis will continue: "
                f"{type(error).__name__}: {error}"
            )

    sql_result: Any = {}
    sql_ms = 0.0

    if sql_analysis is not None:
        sql_started = time.perf_counter()
        sql_result = _call_sql_analysis(
            sql_analysis,
            {
                "case_id": str(case_id),
                "workflow": str(workflow),
                "table_name": str(table_name),
                "dataset_name": str(dataset_name),
                "input_folder": str(input_folder),
                "stage": stage_payload,
                **(sql_analysis_kwargs or {}),
            },
        )
        sql_ms = round((time.perf_counter() - sql_started) * 1000, 2)

    total_ms = round((time.perf_counter() - total_started) * 1000, 2)

    timings = asdict(
        ScalablePipelineTimings(
            load_ms=load_ms,
            stage_ms=stage_ms,
            sql_analysis_ms=sql_ms,
            total_ms=total_ms,
        )
    )

    payload: dict[str, Any] = {
        "ok": True,
        "case_id": str(case_id),
        "workflow": str(workflow),
        "config": asdict(config),
        "input_folder": str(input_folder),
        "input_fingerprint": fingerprint,
        "stage": stage_payload,
        "stage_reused": bool(
            stage_reused
        ),
        "normalized_cache_reused": bool(
            normalized_cache_reused
        ),
        "normalized_cache_reason": str(
            cache_lookup.get(
                "reason",
                "",
            )
        ),
        "normalized_cache_manifest_path": (
            cache_manifest_path
        ),
        "sql_result_rows": _row_summary(sql_result),
        "timings": timings,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }

    pipeline_state = write_latest_pipeline_state(case_id, workflow, payload)
    payload["pipeline_state_path"] = str(pipeline_state)
    write_latest_pipeline_state(case_id, workflow, payload)

    if print_status:
        print_pipeline_backend_status(payload, title=status_title)

    return {
        **payload,
        "load_result": load_result,
        "dataframe": dataframe,
        "sql_analysis": sql_result,
    }
