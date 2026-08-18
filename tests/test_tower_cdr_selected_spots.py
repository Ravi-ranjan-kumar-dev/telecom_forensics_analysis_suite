"""Selected-Spot contract tests for Tower CDR loading and cache."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from modules.loader import tower_dump_loader
from modules.staging.tower_cdr_staging import (
    tower_cdr_input_fingerprint,
)


def _fake_tower_result(path: str | Path, enrich_cgi: bool = True) -> dict:
    source = Path(path)

    return {
        "file": source.name,
        "operator": "test",
        "searched_cell_id": "CELL-1",
        "df": pd.DataFrame(
            [
                {
                    "subscriber_number": source.stem,
                    "operator": "test",
                    "searched_cell_id": "CELL-1",
                    "call_datetime": pd.Timestamp(
                        "2026-08-16 10:00:00"
                    ),
                    "source_file": source.name,
                }
            ]
        ),
        "metadata": {},
        "rejected_rows": pd.DataFrame(),
        "warnings": [],
        "errors": [],
        "ok": True,
    }


def test_tower_cdr_loader_uses_only_selected_spots(
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
        tower_dump_loader,
        "load_tower_dump",
        _fake_tower_result,
    )

    result = tower_dump_loader.load_tower_dump_case(
        tmp_path,
        enrich_cgi=False,
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
    assert set(
        result["df"]["spot_id"]
    ) == {
        "SPOT-02",
    }


def test_tower_cdr_fingerprint_includes_selection_identity(
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

    first_fingerprint = tower_cdr_input_fingerprint(
        tmp_path,
        selected_spot_folders=[
            "First Spot",
        ],
        include_root_files=False,
    )
    second_fingerprint = tower_cdr_input_fingerprint(
        tmp_path,
        selected_spot_folders=[
            "Second Spot",
        ],
        include_root_files=False,
    )

    assert first_fingerprint != second_fingerprint
    assert first_fingerprint["selected_spot_folders"] == [
        "First Spot",
    ]
    assert first_fingerprint["include_root_files"] is False
    assert first_fingerprint["file_count"] == 1
    assert first_fingerprint["files"][0]["path"] == (
        "First Spot/first.csv"
    )


def test_tower_cdr_loader_enriches_the_combined_batch_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    first = tmp_path / "First Spot"
    second = tmp_path / "Second Spot"
    first.mkdir()
    second.mkdir()

    for path in (
        first / "first.csv",
        second / "second.csv",
    ):
        path.write_text(
            "header\n",
            encoding="utf-8",
        )

    file_enrichment_flags: list[bool] = []
    batch_sizes: list[int] = []

    def fake_load(
        path,
        enrich_cgi=True,
    ):
        file_enrichment_flags.append(
            bool(enrich_cgi)
        )
        return _fake_tower_result(
            path,
            enrich_cgi=enrich_cgi,
        )

    def fake_batch_enrichment(
        dataframe,
        _warnings,
    ):
        batch_sizes.append(
            len(dataframe)
        )
        enriched = dataframe.copy()
        enriched[
            "batch_enriched"
        ] = True
        return enriched

    monkeypatch.setattr(
        tower_dump_loader,
        "load_tower_dump",
        fake_load,
    )
    monkeypatch.setattr(
        tower_dump_loader,
        "_safe_cgi_enrichment",
        fake_batch_enrichment,
    )

    result = tower_dump_loader.load_tower_dump_case(
        tmp_path,
        enrich_cgi=True,
        include_root_files=False,
    )

    assert result[
        "ok"
    ] is True
    assert file_enrichment_flags == [
        False,
        False,
    ]
    assert batch_sizes == [
        2
    ]
    assert result[
        "df"
    ][
        "batch_enriched"
    ].all()
