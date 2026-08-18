from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from modules.loader.tower_ipdr_loader import (
    NORMALIZED_COLUMNS,
)
from modules.staging import tower_ipdr_staging as staging


def _fake_ipdr_result(
    path: Path,
) -> dict:
    dataframe = pd.DataFrame(
        {
            column: [pd.NA]
            for column in NORMALIZED_COLUMNS
        }
    )

    dataframe["record_type"] = (
        "IPDR_NAT_EVENT"
    )
    dataframe["source_format"] = (
        "JIO_TOWER_IPDR_NAT"
    )
    dataframe["operator"] = "Jio"
    dataframe["subscriber_number"] = (
        "9000000001"
    )
    dataframe["searched_cell_id"] = (
        "4058560000001"
    )
    dataframe["imei"] = "111111111111111"
    dataframe["imsi"] = "405111111111111"
    dataframe["event_time"] = pd.to_datetime(
        [
            "2026-06-11 20:00:00",
        ]
    )
    dataframe["source_file"] = str(
        path.resolve()
    )
    dataframe["source_row_number"] = (
        pd.Series(
            [2],
            dtype="Int64",
        )
    )

    return {
        "ok": True,
        "df": dataframe,
        "file": str(
            path.resolve()
        ),
        "source_format": (
            "JIO_TOWER_IPDR_NAT"
        ),
        "metadata": {
            "operator": "Jio",
            "searched_cell_id": (
                "4058560000001"
            ),
            "event_time_min": (
                "2026-06-11 20:00:00"
            ),
            "event_time_max": (
                "2026-06-11 20:00:00"
            ),
            "unique_subscribers": 1,
        },
        "warnings": [],
        "errors": [],
    }


def test_staging_preserves_spot_provenance(
    tmp_path,
    monkeypatch,
):
    input_root = (
        tmp_path
        / "input"
    )

    spot_1 = input_root / "spot_1"
    spot_2 = input_root / "spot_2"

    spot_1.mkdir(
        parents=True
    )
    spot_2.mkdir(
        parents=True
    )

    file_1 = spot_1 / "a.csv"
    file_2 = spot_2 / "b.csv"

    file_1.write_text(
        "sample-a",
        encoding="utf-8",
    )
    file_2.write_text(
        "sample-b",
        encoding="utf-8",
    )

    staging_root = (
        tmp_path
        / "staging"
    )
    database_path = (
        staging_root
        / "tower_ipdr.duckdb"
    )
    manifest_path = (
        staging_root
        / "manifest.json"
    )

    monkeypatch.setattr(
        staging,
        "tower_ipdr_staging_root",
        lambda _case_id: staging_root,
    )
    monkeypatch.setattr(
        staging,
        "tower_ipdr_database_path",
        lambda _case_id: database_path,
    )
    monkeypatch.setattr(
        staging,
        "tower_ipdr_manifest_path",
        lambda _case_id: manifest_path,
    )
    monkeypatch.setattr(
        staging,
        "load_tower_ipdr_file",
        _fake_ipdr_result,
    )

    result = (
        staging
        .import_tower_ipdr_folder_to_duckdb(
            "TEST-CASE",
            input_root,
            recursive=True,
            force_rebuild=True,
        )
    )

    assert (
        result["loaded_files"]
        == 2
    )
    assert (
        result["failed_files"]
        == 0
    )
    assert (
        result["total_rows_in_database"]
        == 2
    )

    connection = duckdb.connect(
        str(database_path),
        read_only=True,
    )

    try:
        event_rows = connection.execute(
            """
            SELECT
                source_relative_path,
                spot_id,
                spot_name,
                spot_folder
            FROM tower_ipdr_events
            ORDER BY source_relative_path
            """
        ).fetchall()

        event_schema = {
            row[1]: row[2]
            for row in connection.execute(
                """
                PRAGMA table_info(
                    'tower_ipdr_events'
                )
                """
            ).fetchall()
        }

        file_rows = connection.execute(
            """
            SELECT
                source_relative_path,
                spot_id,
                spot_name,
                spot_folder
            FROM tower_ipdr_file_summary
            ORDER BY source_relative_path
            """
        ).fetchall()

    finally:
        connection.close()

    assert event_rows == [
        (
            "spot_1/a.csv",
            "SPOT-01",
            "spot_1",
            "spot_1",
        ),
        (
            "spot_2/b.csv",
            "SPOT-02",
            "spot_2",
            "spot_2",
        ),
    ]

    assert file_rows == event_rows

    for column in (
        "source_relative_path",
        "spot_id",
        "spot_name",
        "spot_folder",
    ):
        assert (
            event_schema[column]
            == "VARCHAR"
        )

    selected_result = (
        staging
        .import_tower_ipdr_folder_to_duckdb(
            "TEST-CASE",
            input_root,
            recursive=True,
            force_rebuild=True,
            selected_spot_folders=[
                "spot_2",
            ],
            include_root_files=False,
        )
    )

    assert selected_result[
        "loaded_files"
    ] == 1

    connection = duckdb.connect(
        str(database_path),
        read_only=True,
    )

    try:
        selected_rows = connection.execute(
            """
            SELECT
                source_relative_path,
                spot_id,
                spot_name
            FROM tower_ipdr_events
            ORDER BY source_relative_path
            """
        ).fetchall()
    finally:
        connection.close()

    assert selected_rows == [
        (
            "spot_2/b.csv",
            "SPOT-02",
            "spot_2",
        ),
    ]
