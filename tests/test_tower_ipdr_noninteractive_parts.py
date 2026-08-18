"""Non-interactive Tower IPDR saved-Part analysis tests."""

from __future__ import annotations

from modules.controllers import (
    tower_ipdr_controller,
)


def test_run_tower_ipdr_saved_parts_returns_report_manifest(
    monkeypatch,
) -> None:
    parts = [
        {
            "part_no": 1,
            "part_name": "Part 1",
            "spot_id": "SPOT-01",
            "spot_name": "First Spot",
            "start_time": "2026-08-16 10:00:00",
            "end_time": "2026-08-16 10:30:00",
        },
        {
            "part_no": 2,
            "part_name": "Part 2",
            "spot_id": "SPOT-02",
            "spot_name": "Second Spot",
            "start_time": "2026-08-16 11:00:00",
            "end_time": "2026-08-16 11:30:00",
        },
    ]
    observed = {
        "summaries": [],
    }

    monkeypatch.setattr(
        tower_ipdr_controller,
        "list_date_time_parts",
        lambda case_id, workflow: parts,
    )
    monkeypatch.setattr(
        tower_ipdr_controller,
        "count_tower_ipdr_events",
        lambda case_id: 10,
    )

    def fake_summary(
        case_id,
        start_time,
        end_time,
        **kwargs,
    ):
        observed["summaries"].append(
            {
                "case_id": case_id,
                "start_time": start_time,
                "end_time": end_time,
                **kwargs,
            }
        )
        return {
            "ok": True,
        }

    monkeypatch.setattr(
        tower_ipdr_controller,
        "tower_ipdr_range_investigation_summary",
        fake_summary,
    )
    monkeypatch.setattr(
        tower_ipdr_controller,
        "print_tower_ipdr_investigation_summary",
        lambda result, max_leads=10: None,
    )

    manifest = {
        "output_dir": "reports",
        "saved_files": {
            "excel_workbook": "parts.xlsx",
            "manifest": "manifest.json",
        },
    }

    monkeypatch.setattr(
        tower_ipdr_controller,
        "export_tower_ipdr_partwise_range_report",
        lambda *args, **kwargs: manifest,
    )

    result = (
        tower_ipdr_controller
        .run_tower_ipdr_saved_parts(
            {
                "case_id": "CASE-001",
            }
        )
    )

    assert result is not None
    assert result["manifest"] == manifest
    assert result["saved_files"] == (
        manifest["saved_files"]
    )
    assert len(
        result["results_by_part"]
    ) == 2
    assert len(
        observed["summaries"]
    ) == 2
    assert observed["summaries"][0][
        "spot_id"
    ] == "SPOT-01"
    assert observed["summaries"][1][
        "spot_id"
    ] == "SPOT-02"
