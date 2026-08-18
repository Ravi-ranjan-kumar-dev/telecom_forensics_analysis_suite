"""Tower Dump GUI Date-Time Partitioning tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


os.environ.setdefault(
    "QT_QPA_PLATFORM",
    "offscreen",
)

from gui.app import build_application
from gui.pages.tower_dump_page import TowerDumpPage
from gui.widgets.date_time_partition_dialog import (
    DateTimePartitionDialog,
)
from gui.workers.tower_dump_worker import (
    TowerDumpWorker,
    collect_tower_report_paths,
)
from modules.cases import date_time_partitions
from modules.controllers import (
    app_controller,
    tower_cdr_controller,
    tower_dump_controller,
    tower_gprs_controller,
    tower_ipdr_controller,
)


def _spot(
    spot_id: str = "SPOT-01",
    spot_name: str = "First Spot",
) -> dict[str, object]:
    return {
        "spot_id": spot_id,
        "spot_name": spot_name,
        "spot_folder": spot_name,
        "files_found": 1,
    }


def _part(
    *,
    spot_id: str = "SPOT-01",
    spot_name: str = "First Spot",
    start_time: str = "2026-08-18 10:00:00",
    end_time: str = "2026-08-18 10:30:00",
) -> dict[str, object]:
    return {
        "part_no": 1,
        "part_name": "Part 1",
        "spot_id": spot_id,
        "spot_name": spot_name,
        "spot_folder": spot_name,
        "start_time": start_time,
        "end_time": end_time,
    }


def test_partition_dialog_returns_exact_spot_aware_pair():
    build_application(
        [
            "tower-partition-dialog-test",
        ]
    )
    dialog = DateTimePartitionDialog(
        source_type="ipdr",
        spots=[
            _spot(),
        ],
        existing_parts=[
            _part(),
        ],
    )

    specifications = dialog.part_specs()

    assert specifications == [
        {
            "part_name": "Part 1",
            "spot_part_no": 1,
            "spot_scope_mode": "SELECTED_SPOT_ONLY",
            "spot_id": "SPOT-01",
            "spot_name": "First Spot",
            "spot_folder": "First Spot",
            "start_time": "2026-08-18 10:00:00",
            "end_time": "2026-08-18 10:30:00",
            "source_type": "TOWER_IPDR",
        }
    ]

    dialog.close()


def test_partition_dialog_rejects_end_before_start():
    build_application(
        [
            "tower-partition-dialog-validation-test",
        ]
    )
    dialog = DateTimePartitionDialog(
        source_type="cdr",
        spots=[
            _spot(),
        ],
        existing_parts=[
            _part(
                start_time="2026-08-18 10:30:00",
                end_time="2026-08-18 10:00:00",
            ),
        ],
    )

    with pytest.raises(
        ValueError,
        match="End Date-Time must be later",
    ):
        dialog.part_specs()

    dialog.close()


def test_unified_controller_saves_canonical_half_open_parts(
    tmp_path: Path,
    monkeypatch,
):
    target = tmp_path / "tower_ipdr_date_time_parts.json"
    monkeypatch.setattr(
        date_time_partitions,
        "date_time_partition_path",
        lambda _case_id, _workflow: target,
    )

    payload = tower_dump_controller.save_tower_dump_date_time_parts(
        {
            "case_id": "DEV-WORKSPACE",
        },
        source_type="ipdr",
        part_specs=[
            _part(),
        ],
    )
    loaded = tower_dump_controller.list_tower_dump_date_time_parts(
        {
            "case_id": "DEV-WORKSPACE",
        },
        source_type="ipdr",
    )

    assert payload["parts_count"] == 1
    assert payload["range_rule"] == (
        "start_time <= event_time < end_time"
    )
    assert payload["overlap_warnings"] == []
    assert loaded[0]["spot_id"] == "SPOT-01"
    assert loaded[0]["start_time"] == (
        "2026-08-18 10:00:00"
    )
    assert loaded[0]["end_time"] == (
        "2026-08-18 10:30:00"
    )


def test_overlap_warning_applies_only_to_intersecting_spot_scopes(
    tmp_path: Path,
    monkeypatch,
):
    target = tmp_path / "tower_cdr_date_time_parts.json"
    monkeypatch.setattr(
        date_time_partitions,
        "date_time_partition_path",
        lambda _case_id, _workflow: target,
    )

    first = _part(
        spot_id="SPOT-01",
        spot_name="First Spot",
    )
    second = _part(
        spot_id="SPOT-02",
        spot_name="Second Spot",
        start_time="2026-08-18 10:15:00",
        end_time="2026-08-18 10:45:00",
    )

    payload = tower_dump_controller.save_tower_dump_date_time_parts(
        {
            "case_id": "DEV-WORKSPACE",
        },
        source_type="cdr",
        part_specs=[
            first,
            second,
        ],
    )

    assert payload["overlap_warnings"] == []

    second["spot_id"] = "SPOT-01"
    second["spot_name"] = "First Spot"
    payload = tower_dump_controller.save_tower_dump_date_time_parts(
        {
            "case_id": "DEV-WORKSPACE",
        },
        source_type="cdr",
        part_specs=[
            first,
            second,
        ],
    )

    assert len(
        payload["overlap_warnings"]
    ) == 1


@pytest.mark.parametrize(
    ("source_type", "module", "attribute_name"),
    [
        (
            "cdr",
            tower_cdr_controller,
            "_run_partition_analysis",
        ),
        (
            "gprs",
            tower_gprs_controller,
            "_execute",
        ),
        (
            "ipdr",
            tower_ipdr_controller,
            "run_tower_ipdr_saved_parts",
        ),
    ],
)
def test_unified_partition_dispatch_uses_gui_folder_and_spots(
    tmp_path: Path,
    monkeypatch,
    source_type,
    module,
    attribute_name,
):
    observed = {}

    monkeypatch.setattr(
        tower_dump_controller,
        "list_tower_dump_date_time_parts",
        lambda case, *, source_type: [
            _part(),
        ],
    )

    def fake_run(
        case,
        **kwargs,
    ):
        observed["case"] = case
        observed.update(
            kwargs
        )
        return {
            "excel_report": "parts.xlsx",
        }

    monkeypatch.setattr(
        module,
        attribute_name,
        fake_run,
    )
    case = {
        "case_id": "DEV-WORKSPACE",
    }

    result = tower_dump_controller.run_tower_dump_partition_analysis(
        case,
        source_type=source_type,
        input_folder=tmp_path,
        selected_spot_folders=[
            "First Spot",
        ],
        include_root_files=False,
    )

    assert result == {
        "excel_report": "parts.xlsx",
    }
    assert observed["case"] is case
    assert observed["input_folder"] == tmp_path.resolve()
    assert observed["selected_spot_folders"] == (
        "First Spot",
    )
    assert observed["include_root_files"] is False

    if source_type == "gprs":
        assert observed["use_partitions"] is True


def test_unified_partition_dispatch_rejects_stale_spot_mapping(
    tmp_path: Path,
    monkeypatch,
):
    first = tmp_path / "First Spot"
    second = tmp_path / "Second Spot"
    first.mkdir()
    second.mkdir()
    (
        first
        / "first.csv"
    ).write_text(
        "header\n",
        encoding="utf-8",
    )
    (
        second
        / "second.csv"
    ).write_text(
        "header\n",
        encoding="utf-8",
    )

    stale_part = _part(
        spot_id="SPOT-01",
        spot_name="Second Spot",
    )
    stale_part["spot_scope_mode"] = (
        "SELECTED_SPOT_ONLY"
    )
    monkeypatch.setattr(
        tower_dump_controller,
        "list_tower_dump_date_time_parts",
        lambda case, *, source_type: [
            stale_part,
        ],
    )

    with pytest.raises(
        ValueError,
        match="saved Spot mapping does not match",
    ):
        tower_dump_controller.run_tower_dump_partition_analysis(
            {
                "case_id": "DEV-WORKSPACE",
            },
            source_type="ipdr",
            input_folder=tmp_path,
        )


def test_worker_runs_partition_controller_and_collects_ipdr_reports(
    tmp_path: Path,
    monkeypatch,
):
    build_application(
        [
            "tower-partition-worker-test",
        ]
    )
    case = {
        "case_id": "DEV-WORKSPACE",
    }
    workbook = tmp_path / "parts.xlsx"
    text_report = tmp_path / "parts.txt"
    observed = {}

    monkeypatch.setattr(
        app_controller,
        "get_direct_analysis_workspace",
        lambda: case,
    )

    def fake_run(
        selected_case,
        **kwargs,
    ):
        observed["case"] = selected_case
        observed.update(
            kwargs
        )
        return {
            "saved_files": {
                "excel_workbook": workbook,
                "investigation_summary_all_parts": text_report,
            }
        }

    monkeypatch.setattr(
        tower_dump_controller,
        "run_tower_dump_partition_analysis",
        fake_run,
    )
    worker = TowerDumpWorker(
        source_type="ipdr",
        input_folder=tmp_path,
        analysis_mode="partition",
    )
    completed = []
    failures = []
    worker.completed.connect(
        completed.append
    )
    worker.failed.connect(
        failures.append
    )

    worker.run()

    assert failures == []
    assert observed["case"] is case
    assert observed["source_type"] == "ipdr"
    assert completed[0]["analysis_mode"] == "partition"
    assert completed[0]["report_paths"] == [
        str(
            workbook.resolve()
        ),
        str(
            text_report.resolve()
        ),
    ]


def test_tower_page_partition_spots_follow_checked_folders(
    tmp_path: Path,
):
    build_application(
        [
            "tower-partition-page-test",
        ]
    )
    first = tmp_path / "First Spot"
    second = tmp_path / "Second Spot"
    first.mkdir()
    second.mkdir()
    (
        first
        / "first.csv"
    ).write_text(
        "header\n",
        encoding="utf-8",
    )
    (
        second
        / "second.csv"
    ).write_text(
        "header\n",
        encoding="utf-8",
    )

    page = TowerDumpPage()
    page.set_mode(
        "ipdr"
    )
    page.set_selected_folder(
        tmp_path
    )
    page.set_selected_spots(
        [
            "Second Spot",
        ]
    )

    spots = page._available_partition_spots()

    assert len(spots) == 1
    assert spots[0]["spot_name"] == "Second Spot"
    assert spots[0]["spot_id"] == "SPOT-02"

    page.close()


def test_nested_partwise_report_paths_keep_excel_first(
    tmp_path: Path,
):
    workbook = tmp_path / "parts.xlsx"
    text_report = tmp_path / "parts.txt"

    assert collect_tower_report_paths(
        {
            "saved_files": {
                "excel_workbook": workbook,
                "investigation_summary_all_parts": text_report,
            }
        }
    ) == [
        str(
            workbook.resolve()
        ),
        str(
            text_report.resolve()
        ),
    ]
