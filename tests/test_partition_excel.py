from __future__ import annotations

from pathlib import Path

import pandas as pd

from modules.reporting.tower_partition_excel import (
    generate_tower_partition_excel_report,
)


def test_consolidated_partition_workbook(tmp_path: Path):
    partitions = ["P1", "P2", "P3", "P4", "P5"]

    subscriber_presence = pd.DataFrame(
        [
            {
                "subscriber_number": "9000000001",
                "match_count": 5,
                "total_sightings": 5,
                "match_ratio": "5/5",
                "matched_sightings": ", ".join(partitions),
                "matched_locations": "",
                "total_events": 9,
                "operators": "Airtel, Jio",
                "first_seen": pd.Timestamp("2026-07-10 12:55:00"),
                "last_seen": pd.Timestamp("2026-07-10 16:02:00"),
                **{partition: 1 for partition in partitions},
            },
            {
                "subscriber_number": "9000000002",
                "match_count": 3,
                "total_sightings": 5,
                "match_ratio": "3/5",
                "matched_sightings": "P1, P2, P4",
                "matched_locations": "",
                "total_events": 4,
                "operators": "Vi",
                "first_seen": pd.Timestamp("2026-07-10 12:58:00"),
                "last_seen": pd.Timestamp("2026-07-10 15:58:00"),
                "P1": 1,
                "P2": 1,
                "P3": 0,
                "P4": 1,
                "P5": 0,
            },
        ]
    )

    result = {
        "partition_summary": pd.DataFrame(
            [
                {
                    "sighting_id": partition,
                    "cctv_timestamp": f"2026-07-10 {12 + index}:00:00",
                    "window_start": f"2026-07-10 {11 + index}:50:00",
                    "window_end": f"2026-07-10 {12 + index}:10:00",
                    "filtered_records": 100 + index,
                    "unique_subscribers": 50 + index,
                    "unique_imei": 40 + index,
                    "unique_imsi": 45 + index,
                    "unique_searched_cells": 4,
                }
                for index, partition in enumerate(partitions, start=1)
            ]
        ),
        "subscriber_presence": subscriber_presence,
        "n_of_m_candidates": subscriber_presence.copy(),
        "strict_common_candidates": subscriber_presence.iloc[[0]].copy(),
        "imei_presence": pd.DataFrame(
            [{"imei": "123456789012345", "match_ratio": "5/5", **{p: 1 for p in partitions}}]
        ),
        "imsi_presence": pd.DataFrame(
            [{"imsi": "404000000000001", "match_ratio": "5/5", **{p: 1 for p in partitions}}]
        ),
        "total_sightings": 5,
        "total_input_records": 5000,
        "warnings": [],
        "errors": [],
        "operators": ["Airtel", "Jio", "Vi"],
        "cell_ids": ["A", "B", "C", "D"],
        "load_metadata": {
            "files_found": 4,
            "files_loaded": 4,
            "files_failed": 0,
        },
    }

    sightings = [
        {
            "sighting_id": partition,
            "cctv_timestamp": f"2026-07-10 {12 + index}:00:00",
            "window_start": f"2026-07-10 {11 + index}:50:00",
            "window_end": f"2026-07-10 {12 + index}:10:00",
            "minutes_before": 10,
            "minutes_after": 10,
            "cgi_group_id": "AUTO_ALL",
        }
        for index, partition in enumerate(partitions, start=1)
    ]

    report = generate_tower_partition_excel_report(
        result,
        case={
            "case_id": "CASE-20260710-001",
            "case_name": "Test Case",
        },
        sightings=sightings,
        output_dir=tmp_path,
        input_folder=tmp_path / "input",
        saved={
            "run_id": "partition_test",
            "run_directory": str(tmp_path / "backend"),
        },
    )

    assert report.is_file()

    from openpyxl import load_workbook

    workbook = load_workbook(report, read_only=True)
    names = workbook.sheetnames

    assert "1. Executive Summary" in names
    assert "3. Partition Summary" in names
    assert "5. N-of-M Candidates" in names
    assert "6. Strict Common" in names
    assert "9. Candidate Matrix" in names
    assert "10. Analysis Status" in names
    assert "11. Warnings" in names
    assert "12. Partition Status" in names
    assert "13. Rejected Rows" in names
    assert "Methodology & Limits" in names
