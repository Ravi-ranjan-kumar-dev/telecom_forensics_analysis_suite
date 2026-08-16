"""Selected-Spot contract tests for Tower GPRS."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from modules.loader import gprs_dump_loader
from modules.pipeline.scalable_analysis_pipeline import (
    build_input_fingerprint,
)


def _fake_gprs_result(path: str | Path) -> dict:
    source = Path(path)
    row = {
        column: pd.NA
        for column in gprs_dump_loader.NORMALIZED_COLUMNS
    }
    row.update(
        {
            "subscriber_number": source.stem,
            "session_start": pd.Timestamp(
                "2026-08-16 10:00:00"
            ),
            "source_file": source.name,
        }
    )

    return {
        "ok": True,
        "has_records": True,
        "data_status": "LOADED",
        "df": pd.DataFrame(
            [
                row,
            ],
            columns=gprs_dump_loader.NORMALIZED_COLUMNS,
        ),
        "file": str(
            source
        ),
        "source_format": "AIRTEL_GPRS_SESSION",
        "metadata": {
            "operator": "AIRTEL",
            "records": 1,
        },
        "rejected_rows": pd.DataFrame(),
        "warnings": [],
        "errors": [],
    }


def test_gprs_loader_uses_only_selected_spots(
    tmp_path: Path,
    monkeypatch,
) -> None:
    selected = tmp_path / "Selected Spot"
    ignored = tmp_path / "Ignored Spot"

    selected.mkdir()
    ignored.mkdir()

    selected_file = selected / "selected.csv"
    ignored_file = ignored / "ignored.csv"
    root_file = tmp_path / "root.csv"

    for path in (
        selected_file,
        ignored_file,
        root_file,
    ):
        path.write_text(
            "header\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(
        gprs_dump_loader,
        "load_gprs_dump_file",
        _fake_gprs_result,
    )

    result = gprs_dump_loader.load_gprs_dump_case(
        tmp_path,
        selected_spot_folders=[
            "Selected Spot",
        ],
        include_root_files=False,
    )

    assert result["ok"] is True
    assert result["metadata"]["files_found"] == 1
    assert result["metadata"]["spot_names"] == [
        "Selected Spot",
    ]
    assert result["metadata"]["root_level_file_count"] == 0
    assert set(
        result["df"]["source_file"]
    ) == {
        selected_file.name,
    }


def test_common_fingerprint_uses_selected_gprs_spots(
    tmp_path: Path,
) -> None:
    first = tmp_path / "First Spot"
    second = tmp_path / "Second Spot"

    first.mkdir()
    second.mkdir()

    first_file = first / "first.csv"
    second_file = second / "second.csv"
    root_file = tmp_path / "root.csv"

    for path in (
        first_file,
        second_file,
        root_file,
    ):
        path.write_text(
            "header\n",
            encoding="utf-8",
        )

    fingerprint = build_input_fingerprint(
        tmp_path,
        supported_suffixes={
            ".csv",
        },
        selected_spot_folders=[
            "Second Spot",
        ],
        include_root_files=False,
    )

    assert fingerprint["selected_spot_folders"] == [
        "Second Spot",
    ]
    assert fingerprint["include_root_files"] is False
    assert fingerprint["file_count"] == 1
    assert fingerprint["files"][0]["path"] == (
        "Second Spot/second.csv"
    )
