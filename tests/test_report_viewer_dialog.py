from __future__ import annotations

import os
from pathlib import Path
import pytest
import pandas as pd
from openpyxl import Workbook

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui.app import build_application
from gui.widgets.report_viewer_dialog import (
    ReportViewerDialog,
    canonical_phone_number,
    detect_identifier_columns,
    detect_number_columns,
    prepare_related_records,
)


def _write_report(path: Path) -> None:
    workbook = Workbook()

    summary = workbook.active
    summary.title = "Call Summary"
    summary.append(["Contact", "Call Type", "Duration"])
    summary.append(["919000000001", "Outgoing", 30])
    summary.append(["9000000001", "Incoming", 20])

    details = workbook.create_sheet("Common Contacts")
    details.append(["Common Number", "Source Target", "Count"])
    details.append(["9000000002", "9000000001", 3])

    workbook.save(path)


def test_number_column_detection_supports_report_labels():
    assert detect_number_columns(
        ["Contact", "Call Type", "Common Number", "Source Target"]
    ) == (0, 2, 3)


def test_phone_number_normalization_matches_common_indian_formats():
    assert canonical_phone_number("+91 90000-00001") == "9000000001"
    assert canonical_phone_number("09000000001") == "9000000001"


def test_identifier_detection_separates_phone_cell_imei_and_imsi():
    assert detect_identifier_columns(
        ["Other Party", "Cell ID", "Old IMEI", "New IMSI", "Total Calls"]
    ) == {
        0: "phone",
        1: "cell_id",
        2: "imei",
        3: "imsi",
    }

    assert detect_identifier_columns(
        ["CGI Lookup Status", "Tower Address", "IMEI Status", "Total Calls"]
    ) == {}


def test_viewer_lists_sheets_and_detects_number_columns(tmp_path: Path):
    build_application(["report-viewer-test"])

    report = tmp_path / "report.xlsx"
    _write_report(report)

    dialog = ReportViewerDialog(report)

    assert dialog._sheet_selector.count() == 2
    assert dialog._table.rowCount() == 2
    assert dialog.number_columns == (0,)

    dialog._sheet_selector.setCurrentText("Common Contacts")

    assert dialog._table.rowCount() == 1
    assert dialog.number_columns == (0, 1)

    dialog.close()


def test_number_double_click_opens_verified_source_records(
    tmp_path: Path,
    monkeypatch,
):
    build_application(["report-viewer-source-test"])

    report = tmp_path / "report.xlsx"
    _write_report(report)

    dialog = ReportViewerDialog(report)

    from gui.widgets import report_viewer_dialog
    from modules.reporting import cdr_report_source

    expected = pd.DataFrame(
        [
            {
                "b_party": "9000000001",
                "call_type": "Incoming",
            }
        ]
    )

    monkeypatch.setattr(
        cdr_report_source,
        "load_verified_source_link",
        lambda path: {"verified": True},
    )
    monkeypatch.setattr(
        cdr_report_source,
        "query_related_records",
        lambda link, number, identifier_type="phone": expected,
    )

    opened = {}

    class FakeRelatedDialog:
        def __init__(
            self,
            number,
            records,
            parent,
            identifier_label="Number",
        ):
            opened["number"] = number
            opened["records"] = records
            opened["identifier_label"] = identifier_label

        def exec(self):
            opened["executed"] = True

    monkeypatch.setattr(
        report_viewer_dialog,
        "RelatedRecordsDialog",
        FakeRelatedDialog,
    )

    dialog._show_number_summary(0, 0)

    assert opened["number"] == "919000000001"
    assert opened["records"].equals(expected)
    assert opened["executed"] is True

    dialog.close()


def test_cell_id_double_click_uses_typed_verified_query(
    tmp_path: Path,
    monkeypatch,
):
    build_application(["report-viewer-cell-test"])

    report = tmp_path / "cell-report.xlsx"

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Cell ID", "Total Calls"])
    sheet.append(["405-51-834-15492631", 12])
    workbook.save(report)

    dialog = ReportViewerDialog(report)

    from gui.widgets import report_viewer_dialog
    from modules.reporting import cdr_report_source

    monkeypatch.setattr(
        cdr_report_source,
        "load_verified_source_link",
        lambda path: {"verified": True},
    )

    queried = {}
    expected = pd.DataFrame(
        [{"first_cell_id": "405-51-834-15492631"}]
    )

    def fake_query(
        link,
        identifier,
        *,
        identifier_type="phone",
    ):
        queried.update(
            identifier=identifier,
            identifier_type=identifier_type,
        )
        return expected

    monkeypatch.setattr(
        cdr_report_source,
        "query_related_records",
        fake_query,
    )

    opened = {}

    class FakeRelatedDialog:
        def __init__(
            self,
            value,
            records,
            parent,
            identifier_label="Number",
        ):
            opened.update(
                value=value,
                records=records,
                label=identifier_label,
            )

        def exec(self):
            opened["executed"] = True

    monkeypatch.setattr(
        report_viewer_dialog,
        "RelatedRecordsDialog",
        FakeRelatedDialog,
    )

    dialog._show_identifier_records(0, 0)

    assert queried == {
        "identifier": "4055183415492631",
        "identifier_type": "cell_id",
    }
    assert opened["label"] == "Cell ID"
    assert opened["executed"] is True

    dialog.close()


def test_prepare_related_records_removes_only_exact_duplicates():
    records = pd.DataFrame(
        [
            {
                "a_party": "9000000001",
                "b_party": "9000000002",
                "call_date": "10-01-2026",
                "call_time": "10:00:00",
                "call_type": "Outgoing",
                "call_duration": 30,
                "_source_order": 1,
            },
            {
                "a_party": "9000000001",
                "b_party": "9000000002",
                "call_date": "10-01-2026",
                "call_time": "10:00:00",
                "call_type": "Outgoing",
                "call_duration": 30,
                "_source_order": 1,
            },
            {
                "a_party": "9000000001",
                "b_party": "9000000002",
                "call_date": "10-01-2026",
                "call_time": "10:05:00",
                "call_type": "Outgoing",
                "call_duration": 30,
                "_source_order": 2,
            },
        ]
    )
    original = records.copy(deep=True)

    display_records, duplicates_hidden = prepare_related_records(records)

    assert duplicates_hidden == 1
    assert len(display_records) == 2
    assert display_records["Time"].tolist() == [
        "10:00:00",
        "10:05:00",
    ]

    pd.testing.assert_frame_equal(records, original)


def test_prepare_related_records_uses_safe_columns_and_labels():
    records = pd.DataFrame(
        [
            {
                "a_party": "9000000001",
                "target_number": "919999999999",
                "b_party": "9000000002",
                "call_date": "10-01-2026",
                "call_time": "10:00:00",
                "call_type": "Incoming",
                "call_duration": 45,
                "first_cell_id": "404-55-113-12101",
                "imei": "868116066643170",
                "imsi": "405001111111111",
                "_source_order": 7,
                "_internal_match_key": "hidden-value",
            }
        ]
    )

    display_records, duplicates_hidden = prepare_related_records(records)

    assert duplicates_hidden == 0
    assert list(display_records.columns) == [
        "Target Number",
        "Other Party",
        "Date",
        "Time",
        "Event Type",
        "Duration (Seconds)",
        "First Cell ID",
        "IMEI",
        "IMSI",
    ]
    assert display_records.iloc[0]["Target Number"] == "9000000001"
    assert "_source_order" not in display_records.columns
    assert "_internal_match_key" not in display_records.columns






@pytest.mark.parametrize(
    (
        "column_name",
        "identifier_value",
        "expected_identifier_type",
        "expected_label",
    ),
    [
        (
            "IMEI",
            "868116066643170",
            "imei",
            "IMEI",
        ),
        (
            "IMSI",
            "405001111111111",
            "imsi",
            "IMSI",
        ),
    ],
)
def test_device_identifier_double_click_uses_typed_verified_query(
    tmp_path: Path,
    monkeypatch,
    column_name: str,
    identifier_value: str,
    expected_identifier_type: str,
    expected_label: str,
):
    build_application(
        [f"report-viewer-{expected_identifier_type}-test"]
    )

    report = tmp_path / f"{expected_identifier_type}-report.xlsx"

    workbook = Workbook()
    sheet = workbook.active
    sheet.append([column_name, "Total Calls"])
    sheet.append([identifier_value, 5])
    workbook.save(report)

    dialog = ReportViewerDialog(report)

    from gui.widgets import report_viewer_dialog
    from modules.reporting import cdr_report_source

    monkeypatch.setattr(
        cdr_report_source,
        "load_verified_source_link",
        lambda path: {"verified": True},
    )

    queried = {}
    expected_records = pd.DataFrame(
        [{expected_identifier_type: identifier_value}]
    )

    def fake_query(
        link,
        identifier,
        *,
        identifier_type="phone",
    ):
        queried.update(
            identifier=identifier,
            identifier_type=identifier_type,
        )
        return expected_records

    monkeypatch.setattr(
        cdr_report_source,
        "query_related_records",
        fake_query,
    )

    opened = {}

    class FakeRelatedDialog:
        def __init__(
            self,
            value,
            records,
            parent,
            identifier_label="Number",
        ):
            opened.update(
                value=value,
                records=records,
                label=identifier_label,
            )

        def exec(self):
            opened["executed"] = True

    monkeypatch.setattr(
        report_viewer_dialog,
        "RelatedRecordsDialog",
        FakeRelatedDialog,
    )

    dialog._show_identifier_records(0, 0)

    assert queried == {
        "identifier": identifier_value,
        "identifier_type": expected_identifier_type,
    }
    assert opened["value"] == identifier_value
    assert opened["records"].equals(expected_records)
    assert opened["label"] == expected_label
    assert opened["executed"] is True

    dialog.close()