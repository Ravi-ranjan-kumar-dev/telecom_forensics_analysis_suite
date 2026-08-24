from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui.app import build_application
from gui.main_window import MainWindow
from gui.pages.case_details_page import CaseDetailsPage
from modules.cases import service


def test_case_overview_returns_current_evidence_and_counts(
    tmp_path,
    monkeypatch,
):
    records = {
        "targets.json": [{"target_type": "MSISDN", "target_value": "9876543210"}],
        "evidence.json": [
            {
                "evidence_id": "EVD-000001",
                "source_path_id": "same-source",
                "file_name": "old.csv",
                "registered_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "evidence_id": "EVD-000002",
                "source_path_id": "same-source",
                "file_name": "current.csv",
                "registered_at": "2026-01-02T00:00:00+00:00",
            },
        ],
        "reports.json": [{"report_id": "REPORT-1"}],
        "analysis_runs.json": [{"analysis_run_id": "RUN-1", "status": "COMPLETED"}],
    }

    monkeypatch.setattr(
        service,
        "open_case",
        lambda case_id, include_archived=True: {
            "case_id": case_id,
            "case_name": "Overview Test",
        },
    )
    monkeypatch.setattr(
        service,
        "_config_file",
        lambda case_id, name: tmp_path / name,
    )
    monkeypatch.setattr(
        service,
        "read_json",
        lambda path, default=None: records.get(Path(path).name, default),
    )
    monkeypatch.setattr(
        service,
        "verify_case_audit",
        lambda case_id: {"valid": True, "event_count": 7},
    )

    overview = service.get_case_overview("CASE-001")

    assert overview["summary"] == {
        "target_count": 1,
        "evidence_file_count": 1,
        "evidence_registration_count": 2,
        "report_count": 1,
        "analysis_run_count": 1,
        "completed_run_count": 1,
    }
    assert overview["evidence"][0]["file_name"] == "current.csv"
    assert overview["audit"]["valid"] is True


def test_case_details_page_populates_read_only_tables():
    build_application(["case-details-test"])

    page = CaseDetailsPage(
        loader=lambda: {
            "case": {
                "case_id": "CASE-001",
                "case_name": "GUI Case",
                "status": "active",
                "source_timezone": "Asia/Kolkata",
            },
            "summary": {
                "target_count": 1,
                "evidence_file_count": 1,
                "report_count": 2,
                "analysis_run_count": 3,
            },
            "targets": [{"target_type": "IMEI", "target_value": "354079831251890"}],
            "evidence": [
                {
                    "file_name": "imei.csv",
                    "evidence_type": "IMEI_CDR",
                    "change_status": "NEW",
                    "file_size_bytes": 2048,
                }
            ],
            "analysis_runs": [
                {
                    "analysis_type": "IMEI_CDR_ANALYSIS",
                    "status": "COMPLETED",
                    "input_records": 10,
                    "output_records": 5,
                }
            ],
            "audit": {"valid": True, "event_count": 12},
        }
    )

    assert page.overview["case"]["case_id"] == "CASE-001"
    assert page._metric_values["report_count"].text() == "2"
    assert page._targets_table.rowCount() == 1
    assert page._evidence_table.rowCount() == 1
    assert page._runs_table.rowCount() == 1
    assert page._audit_badge.text() == "AUDIT VERIFIED"
    page.close()


def test_main_window_uses_real_case_details_page():
    build_application(["case-details-main-window-test"])
    window = MainWindow()
    window.select_page_by_key("case_details")

    assert window.active_page_key == "case_details"
    assert isinstance(window._page_stack.currentWidget(), CaseDetailsPage)
    window.close()
