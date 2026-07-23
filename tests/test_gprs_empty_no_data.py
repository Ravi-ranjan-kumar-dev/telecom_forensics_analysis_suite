from pathlib import Path

from modules.loader.gprs_dump_loader import (
    NORMALIZED_COLUMNS,
    STATUS_EMPTY_NO_DATA,
    load_gprs_dump_case,
    load_gprs_dump_file,
)


def _write_empty_airtel_gprs_report(
    path: Path,
) -> None:
    path.write_text(
        "\n".join(
            [
                "BHARTI AIRTEL LTD",
                "",
                "Pan India",
                "",
                (
                    "GPRS OF CELL ID : "
                    "405-52-2325-12554386743 "
                    "from 11-Jun-2026 19:40:00 "
                    "to 11-Jun-2026 21:00:00"
                ),
                "",
                (
                    " Mobile No.,IP Address,IMEI,IMSI,"
                    "Downlink Vol,Uplink Vol,Total Vol,"
                    "Session Start Time,Session End Time,"
                    " Pre/Post,Roaming Circle,2g/4g/5g,"
                    "ICR Operator Name,Home Circle,IP,"
                    " CGI Latitude, CGI Longitude, CGI"
                ),
                "No Records Found",
                (
                    " This is System generated report, "
                    "and needs no signature."
                ),
                "",
                " 23-Jun-2026 11:10:45",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_empty_airtel_gprs_report_is_not_failed(
    tmp_path: Path,
):
    report = (
        tmp_path
        / "empty_gprs.csv"
    )

    _write_empty_airtel_gprs_report(
        report
    )

    result = load_gprs_dump_file(
        report
    )

    assert result["ok"] is True
    assert result["has_records"] is False
    assert (
        result["data_status"]
        == STATUS_EMPTY_NO_DATA
    )
    assert result["errors"] == []
    assert result["df"].empty
    assert list(result["df"].columns) == (
        NORMALIZED_COLUMNS
    )
    assert (
        result["metadata"][
            "valid_empty_report"
        ]
        is True
    )
    assert (
        result["metadata"]["records"]
        == 0
    )


def test_case_counts_valid_empty_report_separately(
    tmp_path: Path,
):
    spot = (
        tmp_path
        / "spot_1"
    )

    spot.mkdir()

    report = (
        spot
        / "empty_gprs.csv"
    )

    _write_empty_airtel_gprs_report(
        report
    )

    result = load_gprs_dump_case(
        tmp_path
    )

    metadata = result["metadata"]

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["df"].empty

    assert metadata["files_found"] == 1
    assert metadata["files_loaded"] == 0
    assert (
        metadata["files_empty_no_data"]
        == 1
    )
    assert (
        metadata["files_processed_count"]
        == 1
    )
    assert metadata["files_failed"] == 0

    summary = result["file_summary"]

    assert len(summary) == 1
    assert (
        summary.iloc[0]["status"]
        == STATUS_EMPTY_NO_DATA
    )
    assert (
        int(summary.iloc[0]["records"])
        == 0
    )
    assert (
        int(
            summary.iloc[0][
                "error_count"
            ]
        )
        == 0
    )
