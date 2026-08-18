from __future__ import annotations

from pathlib import Path

import pandas as pd

from modules.pipeline.scalable_analysis_pipeline import (
    run_scalable_analysis_pipeline,
)
from modules.staging import scalable_store


def _normalized_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "subscriber_number": [
                "9000000001",
                "9000000002",
            ],
            "event_time": pd.to_datetime(
                [
                    "2026-08-18 10:00:00",
                    "2026-08-18 10:05:00",
                ]
            ),
            "source_relative_path": [
                "Spot A/source.csv",
                "Spot A/source.csv",
            ],
            "spot_id": [
                "SPOT-01",
                "SPOT-01",
            ],
            "spot_name": [
                "Spot A",
                "Spot A",
            ],
        }
    )


def _load_result(
    dataframe: pd.DataFrame,
    source: Path,
) -> dict:
    return {
        "ok": True,
        "df": dataframe.copy(),
        "files": [
            str(source)
        ],
        "file_results": [
            {
                "ok": True,
                "file": str(source),
            }
        ],
        "file_summary": pd.DataFrame(
            [
                {
                    "source_file": str(source),
                    "records": len(dataframe),
                }
            ]
        ),
        "spot_summary": pd.DataFrame(
            [
                {
                    "spot_id": "SPOT-01",
                    "spot_name": "Spot A",
                    "records": len(dataframe),
                }
            ]
        ),
        "rejected_rows": pd.DataFrame(
            columns=[
                "source_file",
                "reason",
            ]
        ),
        "operators": [
            "TEST"
        ],
        "cell_ids": [
            "CELL-01"
        ],
        "metadata": {
            "records": len(dataframe),
        },
        "warnings": [],
        "errors": [],
    }


def test_normalized_pipeline_cache_skips_loader_and_stage_rewrite(
    tmp_path: Path,
    monkeypatch,
):
    active_cases = tmp_path / "cases" / "active"
    monkeypatch.setattr(
        scalable_store,
        "ACTIVE_CASES_DIR",
        active_cases,
    )

    input_folder = tmp_path / "input"
    spot_folder = input_folder / "Spot A"
    spot_folder.mkdir(
        parents=True
    )
    source = spot_folder / "source.csv"
    source.write_text(
        "first-version\n",
        encoding="utf-8",
    )
    dataframe = _normalized_frame()
    loader_calls = 0

    def loader(
        _folder,
        **_kwargs,
    ):
        nonlocal loader_calls
        loader_calls += 1
        return _load_result(
            dataframe,
            source,
        )

    common_kwargs = {
        "case_id": "CACHE-001",
        "workflow": "cache_test",
        "input_folder": input_folder,
        "loader": loader,
        "table_name": "cache_events",
        "dataset_name": "normalized",
        "dataframe_key": "df",
        "normalized_cache_key": "cache-test-v1",
        "required_cached_columns": (
            "subscriber_number",
            "event_time",
            "source_relative_path",
            "spot_id",
            "spot_name",
        ),
        "print_status": False,
    }

    first = run_scalable_analysis_pipeline(
        **common_kwargs
    )
    second = run_scalable_analysis_pipeline(
        **common_kwargs
    )

    assert loader_calls == 1
    assert first[
        "stage_reused"
    ] is False
    assert second[
        "normalized_cache_reused"
    ] is True
    assert second[
        "stage_reused"
    ] is True
    assert second[
        "timings"
    ][
        "stage_ms"
    ] == 0.0
    assert second[
        "load_result"
    ][
        "cache_reused"
    ] is True
    assert second[
        "load_result"
    ][
        "metadata"
    ][
        "cache_source"
    ] == "normalized.parquet"

    pd.testing.assert_frame_equal(
        second[
            "load_result"
        ][
            "file_summary"
        ],
        first[
            "load_result"
        ][
            "file_summary"
        ],
        check_dtype=False,
    )
    pd.testing.assert_frame_equal(
        second[
            "dataframe"
        ],
        dataframe,
        check_dtype=False,
    )


def test_normalized_pipeline_cache_invalidates_when_input_changes(
    tmp_path: Path,
    monkeypatch,
):
    active_cases = tmp_path / "cases" / "active"
    monkeypatch.setattr(
        scalable_store,
        "ACTIVE_CASES_DIR",
        active_cases,
    )

    input_folder = tmp_path / "input"
    input_folder.mkdir()
    source = input_folder / "source.csv"
    source.write_text(
        "first-version\n",
        encoding="utf-8",
    )
    dataframe = _normalized_frame()
    loader_calls = 0

    def loader(
        _folder,
        **_kwargs,
    ):
        nonlocal loader_calls
        loader_calls += 1
        return _load_result(
            dataframe,
            source,
        )

    common_kwargs = {
        "case_id": "CACHE-002",
        "workflow": "cache_test",
        "input_folder": input_folder,
        "loader": loader,
        "table_name": "cache_events",
        "normalized_cache_key": "cache-test-v1",
        "required_cached_columns": (
            "subscriber_number",
            "event_time",
        ),
        "print_status": False,
    }

    run_scalable_analysis_pipeline(
        **common_kwargs
    )
    source.write_text(
        "second-version-with-a-different-size\n",
        encoding="utf-8",
    )
    second = run_scalable_analysis_pipeline(
        **common_kwargs
    )

    assert loader_calls == 2
    assert second[
        "normalized_cache_reused"
    ] is False
    assert second[
        "normalized_cache_reason"
    ] == "INPUT_FILES_CHANGED"


def test_normalized_pipeline_cache_is_bound_to_selected_spots(
    tmp_path: Path,
    monkeypatch,
):
    active_cases = tmp_path / "cases" / "active"
    monkeypatch.setattr(
        scalable_store,
        "ACTIVE_CASES_DIR",
        active_cases,
    )

    input_folder = tmp_path / "input"
    spot_a = input_folder / "Spot A"
    spot_b = input_folder / "Spot B"
    spot_a.mkdir(
        parents=True
    )
    spot_b.mkdir()
    source_a = spot_a / "source.csv"
    source_b = spot_b / "source.csv"
    source_a.write_text(
        "spot-a\n",
        encoding="utf-8",
    )
    source_b.write_text(
        "spot-b\n",
        encoding="utf-8",
    )
    dataframe = _normalized_frame()
    loader_calls = 0

    def loader(
        _folder,
        **_kwargs,
    ):
        nonlocal loader_calls
        loader_calls += 1
        return _load_result(
            dataframe,
            source_a,
        )

    base_kwargs = {
        "case_id": "CACHE-003",
        "workflow": "cache_test",
        "input_folder": input_folder,
        "loader": loader,
        "table_name": "cache_events",
        "normalized_cache_key": "cache-test-v1",
        "required_cached_columns": (
            "subscriber_number",
            "event_time",
        ),
        "print_status": False,
    }

    run_scalable_analysis_pipeline(
        **base_kwargs,
        fingerprint_kwargs={
            "selected_spot_folders": (
                "Spot A",
            ),
            "include_root_files": False,
        },
    )
    reused = run_scalable_analysis_pipeline(
        **base_kwargs,
        fingerprint_kwargs={
            "selected_spot_folders": (
                "Spot A",
            ),
            "include_root_files": False,
        },
    )
    changed = run_scalable_analysis_pipeline(
        **base_kwargs,
        fingerprint_kwargs={
            "selected_spot_folders": (
                "Spot B",
            ),
            "include_root_files": False,
        },
    )

    assert loader_calls == 2
    assert reused[
        "normalized_cache_reused"
    ] is True
    assert changed[
        "normalized_cache_reused"
    ] is False
    assert changed[
        "normalized_cache_reason"
    ] == "INPUT_FILES_CHANGED"
