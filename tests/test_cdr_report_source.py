from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from modules.reporting import cdr_report_source
from modules.reporting.cdr_report_source import (
    SourceLinkError,
    create_cdr_source_run,
    link_report_to_source,
    load_verified_source_link,
    query_related_records,
    report_source_link_path,
)


def _records() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "a_party": "9000000001",
                "b_party": "+91 90000 00002",
                "call_type": "Outgoing",
                "call_duration": 30,
                "first_cell_id": "405-51-834-15492631",
                "imei": "862518054878650",
                "imsi": "405523226150896",
            },
            {
                "a_party": "9000000001",
                "b_party": "9000000003",
                "call_type": "Incoming",
                "call_duration": 10,
                "first_cell_id": "405-51-834-15492711",
                "imei": "868115072474690",
                "imsi": "405523226150896",
            },
        ]
    )


def test_report_link_returns_only_verified_related_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(cdr_report_source, "PROJECT_ROOT", tmp_path)
    report = tmp_path / "cases" / "active" / "CASE-1" / "reports" / "report.xlsx"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"workbook-content")

    source_run = create_cdr_source_run(
        case_id="CASE-1",
        analysis_run_id="run-1",
        target_frames={"9000000001": _records()},
    )
    link_report_to_source(report, source_run, targets=["9000000001"])

    verified = load_verified_source_link(report)
    records = query_related_records(verified, "09000000002")

    assert report_source_link_path(report).is_file()
    assert len(records) == 1
    assert records.iloc[0]["b_party"] == "+91 90000 00002"
    assert records.iloc[0]["Source Target"] == "9000000001"


def test_report_change_blocks_source_record_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(cdr_report_source, "PROJECT_ROOT", tmp_path)
    report = tmp_path / "cases" / "active" / "CASE-1" / "reports" / "report.xlsx"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"original")
    source_run = create_cdr_source_run(
        case_id="CASE-1",
        analysis_run_id="run-2",
        target_frames={"9000000001": _records()},
    )
    link_report_to_source(report, source_run)

    report.write_bytes(b"changed")

    with pytest.raises(SourceLinkError, match="report changed"):
        load_verified_source_link(report)


@pytest.mark.parametrize(
    ("identifier_type", "identifier", "column", "expected"),
    [
        ("cell_id", "405-51-834-15492631", "first_cell_id", "405-51-834-15492631"),
        ("imei", "862518054878650", "imei", "862518054878650"),
        ("imsi", "405523226150896", "imsi", "405523226150896"),
    ],
)
def test_typed_identifier_query_returns_only_matching_records(
    tmp_path, monkeypatch, identifier_type, identifier, column, expected
):
    monkeypatch.setattr(cdr_report_source, "PROJECT_ROOT", tmp_path)
    report = tmp_path / "cases/active/CASE-1/reports/report.xlsx"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"workbook-content")
    source_run = create_cdr_source_run(
        case_id="CASE-1", analysis_run_id="typed", target_frames={"9000000001": _records()}
    )
    link_report_to_source(report, source_run)
    records = query_related_records(
        load_verified_source_link(report), identifier, identifier_type=identifier_type
    )
    assert len(records) == (2 if identifier_type == "imsi" else 1)
    assert records.iloc[0][column] == expected



def test_cell_id_query_handles_numeric_float_suffix(
    tmp_path: Path,
    monkeypatch,
):
    source_path = tmp_path / "source.parquet"

    records = pd.DataFrame(
        [
            {
                "a_party": "9000000001",
                "b_party": "9000000002",
                "first_cell_id": 4055183415492631.0,
                "call_type": "Outgoing",
            }
        ]
    )
    records.to_parquet(source_path, index=False)

    monkeypatch.setattr(
        cdr_report_source,
        "_resolve_portable_path",
        lambda value: source_path,
    )

    source_link = {
        "datasets": [
            {
                "target": "9000000001",
                "path": str(source_path),
                "columns": list(records.columns),
            }
        ]
    }

    result = cdr_report_source.query_related_records(
        source_link,
        "405-51-834-15492631",
        identifier_type="cell_id",
    )

    assert len(result) == 1
    assert result.iloc[0]["Source Target"] == "9000000001"


def _write_related_limit_probe_dataset(tmp_path, name, row_count):
    import pandas as pd

    frame = pd.DataFrame(
        {
            "a_party": ["9000000001"] * row_count,
            "b_party": ["9000000002"] * row_count,
            "call_date": ["01/08/2026"] * row_count,
            "call_time": [
                f"10:00:{index:02d}"
                for index in range(row_count)
            ],
        }
    )
    path = tmp_path / f"{name}.parquet"
    frame.to_parquet(path, index=False)
    return {
        "path": path.name,
        "columns": list(frame.columns),
        "target": name,
    }


def test_query_related_records_distinguishes_exact_limit_from_truncation(
    tmp_path,
    monkeypatch,
):
    from modules.reporting import cdr_report_source

    monkeypatch.setattr(
        cdr_report_source,
        "_resolve_portable_path",
        lambda value: tmp_path / str(value),
    )
    query_related_records = cdr_report_source.query_related_records

    first_dataset = _write_related_limit_probe_dataset(
        tmp_path,
        "first_target",
        2,
    )

    exact_result = query_related_records(
        {"datasets": [first_dataset]},
        "9000000002",
        limit=2,
    )

    assert len(exact_result) == 2
    assert exact_result.attrs["result_limit"] == 2
    assert exact_result.attrs["result_limited"] is False

    second_dataset = _write_related_limit_probe_dataset(
        tmp_path,
        "second_target",
        1,
    )
    limited_result = query_related_records(
        {"datasets": [first_dataset, second_dataset]},
        "9000000002",
        limit=2,
    )

    assert len(limited_result) == 2
    assert limited_result.attrs["result_limit"] == 2
    assert limited_result.attrs["result_limited"] is True


def test_query_related_records_attaches_metadata_to_empty_results(
    tmp_path,
    monkeypatch,
):
    from modules.reporting import cdr_report_source

    monkeypatch.setattr(
        cdr_report_source,
        "_resolve_portable_path",
        lambda value: tmp_path / str(value),
    )
    query_related_records = cdr_report_source.query_related_records

    dataset = _write_related_limit_probe_dataset(
        tmp_path,
        "empty_result_target",
        1,
    )
    source_link = {"datasets": [dataset]}

    for identifier in ("", "9888888888"):
        result = query_related_records(
            source_link,
            identifier,
            limit=2,
        )

        assert result.empty
        assert result.attrs["result_limit"] == 2
        assert result.attrs["result_limited"] is False
