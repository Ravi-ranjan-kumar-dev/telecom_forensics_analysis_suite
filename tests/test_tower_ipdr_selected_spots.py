"""Selected-Spot contract tests for Tower IPDR."""

from __future__ import annotations

from pathlib import Path

from modules.staging import tower_ipdr_staging


def test_tower_ipdr_candidate_files_use_selected_spots(
    tmp_path: Path,
) -> None:
    selected = tmp_path / "Selected Spot"
    ignored = tmp_path / "Ignored Spot"
    operator_folder = selected / "Jio"

    operator_folder.mkdir(
        parents=True
    )
    ignored.mkdir()

    selected_file = operator_folder / "selected.csv"
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

    result = tower_ipdr_staging._candidate_files(
        tmp_path,
        selected_spot_folders=[
            "Selected Spot",
        ],
        include_root_files=False,
    )

    assert result == [
        selected_file.resolve(),
    ]

def test_tower_ipdr_fingerprint_includes_selection_identity(
    tmp_path: Path,
) -> None:
    from modules.controllers import (
        tower_ipdr_controller,
    )

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

    fingerprint = (
        tower_ipdr_controller
        ._tower_ipdr_input_fingerprint(
            tmp_path,
            selected_spot_folders=[
                "Second Spot",
            ],
            include_root_files=False,
        )
    )

    assert fingerprint["selected_spot_folders"] == [
        "Second Spot",
    ]
    assert fingerprint["include_root_files"] is False
    assert fingerprint["file_count"] == 1
    assert fingerprint["files"][0]["path"] == (
        "Second Spot/second.csv"
    )
