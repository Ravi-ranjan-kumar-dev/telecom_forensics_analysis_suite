
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from modules.database import (
    master_import_service,
)
from modules.database.master_import_service import (
    detect_master_data_type,
    import_master_data_file,
)
from modules.enrichment import (
    sdr_subscriber_enrichment,
)


def _use_temporary_database(
    monkeypatch,
    tmp_path: Path,
) -> Path:
    database_path = (
        tmp_path
        / "telecom_forensics.duckdb"
    )

    monkeypatch.setattr(
        master_import_service,
        "master_duckdb_path",
        lambda: database_path,
    )

    return database_path


def test_detects_sdr_csv(
    tmp_path: Path,
):
    path = (
        tmp_path
        / "sdr.csv"
    )

    path.write_text(
        "mobile_number,subscriber_name,address\n"
        "9000000001,Person One,Address One\n",
        encoding="utf-8",
    )

    result = detect_master_data_type(
        path
    )

    assert result[
        "import_type"
    ] == "SDR"


def test_detects_cgi_csv(
    tmp_path: Path,
):
    path = (
        tmp_path
        / "cgi.csv"
    )

    path.write_text(
        "cgi,address,latitude,longitude\n"
        "405-52-100-200,Tower Address,25.1,85.1\n",
        encoding="utf-8",
    )

    result = detect_master_data_type(
        path
    )

    assert result[
        "import_type"
    ] == "CGI"


def test_small_sdr_import_and_duplicate_guard(
    monkeypatch,
    tmp_path: Path,
):
    database_path = _use_temporary_database(
        monkeypatch,
        tmp_path,
    )

    source_path = (
        tmp_path
        / "sdr_update.csv"
    )

    source_path.write_text(
        "mobile_number,subscriber_name,address,operator\n"
        "9000000001,Person One,Address One,Airtel\n"
        "9000000002,Person Two,Address Two,Jio\n"
        "9000000002,Person Two Updated,Address Two,Jio\n"
        "12345,Invalid Person,Invalid Address,Unknown\n",
        encoding="utf-8",
    )

    first = import_master_data_file(
        source_path,
        create_backup=False,
    )

    assert first[
        "status"
    ] == "SUCCESS"
    assert first[
        "rows_read"
    ] == 4
    assert first[
        "valid_rows"
    ] == 2
    assert first[
        "invalid_rows"
    ] == 1
    assert first[
        "duplicate_rows"
    ] == 1
    assert first[
        "inserted_rows"
    ] == 2
    assert first[
        "updated_rows"
    ] == 0

    with duckdb.connect(
        str(
            database_path
        ),
        read_only=True,
    ) as connection:
        rows = connection.execute(
            """
            SELECT
                mobile_number,
                subscriber_name
            FROM sdr_subscribers
            ORDER BY mobile_number
            """
        ).fetchall()

    assert rows == [
        (
            "9000000001",
            "Person One",
        ),
        (
            "9000000002",
            "Person Two Updated",
        ),
    ]

    assert Path(
        first[
            "log_path"
        ]
    ).is_file()

    second = import_master_data_file(
        source_path,
        create_backup=False,
    )

    assert second[
        "status"
    ] == "SKIPPED_DUPLICATE"


def test_new_sdr_delta_has_lookup_priority(
    monkeypatch,
):
    primary = pd.DataFrame(
        [
            {
                "lookup_mobile": (
                    "9000000001"
                ),
                "subscriber_name": (
                    "Updated Person"
                ),
                "sdr_found": "Yes",
            }
        ]
    )

    large = pd.DataFrame(
        [
            {
                "lookup_mobile": (
                    "9000000002"
                ),
                "subscriber_name": (
                    "Historical Person"
                ),
                "sdr_found": "Yes",
            }
        ]
    )

    monkeypatch.setattr(
        sdr_subscriber_enrichment,
        "_lookup_from_primary_table",
        lambda numbers: primary,
    )

    captured = {}

    def fake_large_lookup(
        numbers,
    ):
        captured[
            "numbers"
        ] = list(
            numbers
        )
        return large

    monkeypatch.setattr(
        sdr_subscriber_enrichment,
        "_lookup_from_large_table",
        fake_large_lookup,
    )

    result = (
        sdr_subscriber_enrichment
        .lookup_sdr_subscribers(
            [
                "9000000001",
                "9000000002",
            ]
        )
    )

    assert captured[
        "numbers"
    ] == [
        "9000000002",
    ]

    assert result[
        "lookup_mobile"
    ].tolist() == [
        "9000000001",
        "9000000002",
    ]


def test_missing_sdr_numbers_return_not_found(
    monkeypatch,
):
    empty = pd.DataFrame()

    monkeypatch.setattr(
        sdr_subscriber_enrichment,
        "_lookup_from_primary_table",
        lambda numbers: empty,
    )

    monkeypatch.setattr(
        sdr_subscriber_enrichment,
        "_lookup_from_large_table",
        lambda numbers: empty,
    )

    result = (
        sdr_subscriber_enrichment
        .lookup_sdr_subscribers(
            [
                "9000000003",
            ]
        )
    )

    assert result.to_dict(
        orient="records"
    ) == [
        {
            "lookup_mobile": (
                "9000000003"
            ),
            "sdr_found": "No",
        }
    ]

def test_embedded_header_ignores_generic_companion(
    monkeypatch,
    tmp_path: Path,
):
    database_path = _use_temporary_database(
        monkeypatch,
        tmp_path,
    )

    generic_header = (
        tmp_path
        / "sdr_master_export_header.txt"
    )

    generic_header.write_text(
        "mobile_number,subscriber_name,address\n",
        encoding="utf-8",
    )

    headered_file = (
        tmp_path
        / "sdr_test.csv"
    )

    headered_file.write_text(
        "mobile_number,subscriber_name,address\n"
        "9000000001,Person One,Address One\n"
        "9000000002,Person Two,Address Two\n",
        encoding="utf-8",
    )

    result = import_master_data_file(
        headered_file,
        create_backup=False,
    )

    assert result["status"] == "SUCCESS"
    assert result["rows_read"] == 2
    assert result["valid_rows"] == 2
    assert result["invalid_rows"] == 0
    assert result["inserted_rows"] == 2

    with duckdb.connect(
        str(database_path),
        read_only=True,
    ) as connection:
        count = connection.execute(
            """
            SELECT COUNT(*)
            FROM sdr_subscribers
            """
        ).fetchone()[0]

    assert count == 2


def test_data_export_uses_generic_companion(
    monkeypatch,
    tmp_path: Path,
):
    _use_temporary_database(
        monkeypatch,
        tmp_path,
    )

    generic_header = (
        tmp_path
        / "sdr_master_export_header.txt"
    )

    generic_header.write_text(
        "mobile_number,subscriber_name,address\n",
        encoding="utf-8",
    )

    data_file = (
        tmp_path
        / "sdr_test_data.csv"
    )

    data_file.write_text(
        "9000000001,Person One,Address One\n"
        "9000000002,Person Two,Address Two\n",
        encoding="utf-8",
    )

    detected = detect_master_data_type(
        data_file
    )

    assert detected["import_type"] == "SDR"
    assert detected["header_columns"] == [
        "mobile_number",
        "subscriber_name",
        "address",
    ]

    result = import_master_data_file(
        data_file,
        create_backup=False,
    )

    assert result["status"] == "SUCCESS"
    assert result["rows_read"] == 2
    assert result["valid_rows"] == 2
    assert result["invalid_rows"] == 0
