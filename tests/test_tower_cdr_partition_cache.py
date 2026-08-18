from __future__ import annotations

from pathlib import Path

import pandas as pd

from modules.controllers import (
    tower_cdr_controller,
)
from modules.reporting import (
    tower_partition_excel,
)
from modules.staging import (
    tower_cdr_staging,
)


def test_partition_analysis_does_not_rewrite_verified_cdr_stage(
    tmp_path: Path,
    monkeypatch,
):
    dataframe = pd.DataFrame(
        {
            "subscriber_number": [
                "9000000001",
                "9000000002",
            ],
            "call_datetime": pd.to_datetime(
                [
                    "2026-08-18 10:05:00",
                    "2026-08-18 10:10:00",
                ]
            ),
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
    partition_result = {
        "partition_summary": pd.DataFrame(
            [
                {
                    "partition_id": "P1",
                    "records": 2,
                }
            ]
        ),
        "n_of_m_candidates": pd.DataFrame(),
        "strict_common_candidates": pd.DataFrame(),
        "total_sightings": 1,
        "warnings": [],
    }
    report_path = tmp_path / "partition.xlsx"

    monkeypatch.setattr(
        tower_cdr_controller,
        "list_date_time_parts",
        lambda *_args, **_kwargs: [
            {
                "part_no": 1,
                "part_name": "Part 1",
                "start_time": "2026-08-18 10:00:00",
                "end_time": "2026-08-18 11:00:00",
                "spot_id": "SPOT-01",
                "spot_name": "Spot A",
                "spot_scope_mode": "SELECTED_SPOT",
            }
        ],
    )
    monkeypatch.setattr(
        tower_cdr_controller,
        "_load_tower_cdr_with_reuse",
        lambda *_args, **_kwargs: {
            "ok": True,
            "df": dataframe,
            "cache_reused": True,
            "scalable_stage": {
                "record_count": len(
                    dataframe
                ),
                "column_count": len(
                    dataframe.columns
                ),
                "input_fingerprint": {
                    "file_count": 1
                },
            },
            "warnings": [],
            "errors": [],
            "metadata": {},
            "operators": [],
            "cell_ids": [],
            "rejected_rows": pd.DataFrame(),
        },
    )
    monkeypatch.setattr(
        tower_cdr_staging,
        "stage_tower_cdr_dataframe",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError(
                "A verified stage must not be rewritten."
            )
        ),
    )
    monkeypatch.setattr(
        tower_cdr_controller,
        "create_sighting_partitions",
        lambda *_args, **_kwargs: {
            key: (
                value.copy()
                if isinstance(
                    value,
                    pd.DataFrame,
                )
                else value
            )
            for key, value in partition_result.items()
        },
    )
    monkeypatch.setattr(
        tower_cdr_controller,
        "list_cgi_groups",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        tower_cdr_controller,
        "enrich_analysis_bundle",
        lambda bundle, **_kwargs: {
            "bundle": bundle,
            "summary": pd.DataFrame(),
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        tower_cdr_controller,
        "save_partition_run",
        lambda *_args, **_kwargs: {
            "run_id": "run-1",
            "run_directory": str(
                tmp_path / "backend"
            ),
        },
    )
    monkeypatch.setattr(
        tower_partition_excel,
        "generate_tower_partition_excel_report",
        lambda *_args, **_kwargs: report_path,
    )
    monkeypatch.setattr(
        tower_cdr_controller,
        "case_report_dir",
        lambda *_args, **_kwargs: tmp_path,
    )

    for function_name in (
        "attach_partition_report",
        "register_report",
        "register_analysis_run",
    ):
        monkeypatch.setattr(
            tower_cdr_controller,
            function_name,
            lambda *_args, **_kwargs: None,
        )

    result = (
        tower_cdr_controller
        ._run_partition_analysis(
            {
                "case_id": "CACHE-003",
            },
            input_folder=tmp_path,
            selected_spot_folders=(
                "Spot A",
            ),
            include_root_files=False,
        )
    )

    assert result is not None
    assert result[
        "excel_report"
    ] == str(
        report_path
    )
    assert result[
        "load_metadata"
    ] == {}
