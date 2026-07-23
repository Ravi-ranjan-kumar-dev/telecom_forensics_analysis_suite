from __future__ import annotations

import inspect
import re

import pandas as pd

from modules.controllers import (
    tower_ipdr_controller,
)
from modules.staging import (
    tower_ipdr_staging,
)


def test_partwise_menu_has_management_actions():
    source = inspect.getsource(
        tower_ipdr_controller
        ._run_partwise_analysis
    )

    assert (
        "Delete One Saved Part"
        in source
    )
    assert (
        "Clear All Saved Parts"
        in source
    )
    assert (
        "save_date_time_parts"
        in source
    )


def test_partwise_controller_exports_report():
    source = inspect.getsource(
        tower_ipdr_controller
        ._run_partwise_analysis
    )

    assert (
        "export_tower_ipdr_partwise_range_report"
        in source
    )
    assert (
        "precomputed_results="
        in source
    )
    assert (
        "Excel Report"
        in source
    )
    assert (
        "Latest Report"
        in source
    )


def test_console_report_uses_simple_english():
    source = inspect.getsource(
        tower_ipdr_staging
        .print_tower_ipdr_investigation_summary
    )

    assert not re.search(
        r"[\u0900-\u097F]",
        source,
    )

    assert (
        "Global-Uncommon"
        in source
    )
    assert (
        "independent verification"
        in source
    )


def test_export_reuses_results_and_creates_excel(
    tmp_path,
    monkeypatch,
):
    report_root = (
        tmp_path
        / "partwise_reports"
    )

    latest_path = (
        tmp_path
        / "latest_report.json"
    )

    monkeypatch.setattr(
        tower_ipdr_staging,
        "tower_ipdr_partwise_range_report_root",
        lambda _case_id: report_root,
    )

    monkeypatch.setattr(
        tower_ipdr_staging,
        "tower_ipdr_partwise_latest_report_path",
        lambda _case_id: latest_path,
    )

    summary = pd.DataFrame(
        [
            {
                "partition_time": (
                    "2026-06-11 20:00:00 to "
                    "2026-06-11 20:20:00"
                ),
                "spot_id": "SPOT-01",
                "spot_name": "spot_1",
                "spot_scope_mode": (
                    "SELECTED_SPOT_ONLY"
                ),
                "analysis_mode": (
                    "Date-Time Range + Spot"
                ),
                "records_found": 10,
                "numbers_found": 2,
                "cells_involved": 1,
                "first_activity": (
                    "2026-06-11 20:00:00"
                ),
                "last_activity": (
                    "2026-06-11 20:19:59"
                ),
            }
        ]
    )

    lead_summary = pd.DataFrame(
        [
            {
                "finding": (
                    "Global-Uncommon"
                ),
                "records": 1,
                "displayed_records": 1,
                "meaning": "Old text",
            }
        ]
    )

    lead = pd.DataFrame(
        [
            {
                "mobile_number": "9000000001",
                "priority": "High",
                "confidence_level": "High",
                "simple_reason": (
                    "PART_ONLY | NEW_IN_SPOT | "
                    "GLOBAL_UNCOMMON"
                ),
                "suggested_action": "Verify.",
            }
        ]
    )

    result = {
        "summary": summary,
        "lead_summary": lead_summary,
        "priority_leads": lead,
        "part_uncommon_numbers": lead,
        "spot_uncommon_numbers": lead,
        "global_uncommon_numbers": lead,
        "uncommon_numbers": lead.assign(
            meaning="Old report text",
        ),
        "common_numbers": pd.DataFrame(),
        "multi_cell_presence": pd.DataFrame(),
        "repeat_presence": pd.DataFrame(),
        "device_consistency": pd.DataFrame(),
        "suspicious_timing": pd.DataFrame(),
        "uncommon_classification": lead,
    }

    parts = [
        {
            "part_no": 1,
            "part_name": "Part 1",
            "spot_id": "SPOT-01",
            "spot_name": "spot_1",
            "start_time": (
                "2026-06-11 20:00:00"
            ),
            "end_time": (
                "2026-06-11 20:20:00"
            ),
        }
    ]

    manifest = (
        tower_ipdr_staging
        .export_tower_ipdr_partwise_range_report(
            "TEST-CASE",
            parts,
            comparison_parts=parts,
            precomputed_results={
                1: result,
            },
        )
    )

    saved_files = manifest[
        "saved_files"
    ]

    assert (
        "excel_workbook"
        in saved_files
    )
    assert (
        "investigation_summary_all_parts"
        in saved_files
    )
    assert (
        "manifest"
        in saved_files
    )
    assert (
        "latest_report"
        in saved_files
    )

    uncommon_csv = pd.read_csv(
        saved_files[
            "part_01_uncommon_numbers"
        ]
    )

    assert set(
        uncommon_csv["meaning"]
    ) == {
        (
            "Combined uncommon list across Part, "
            "Spot and global scope."
        )
    }

    assert (
        report_root.exists()
    )
    assert (
        latest_path.exists()
    )
