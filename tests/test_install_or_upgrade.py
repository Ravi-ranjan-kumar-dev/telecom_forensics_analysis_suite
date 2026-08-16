"""Regression tests for safe application upgrades."""

from __future__ import annotations

from pathlib import Path

from tools.install_or_upgrade import copy_runtime


def test_copy_runtime_preserves_master_duckdb_and_wal(
    tmp_path: Path,
) -> None:
    backup = tmp_path / "backup"
    staging = tmp_path / "staging"

    old_database = backup / "database"
    old_database.mkdir(parents=True)

    expected_files = {
        "telecom_forensics.duckdb": b"duckdb-main",
        "telecom_forensics.duckdb.wal": b"duckdb-wal",
        "telecom_forensics.db": b"sqlite-main",
        "telecom_forensics.db-wal": b"sqlite-wal",
        "telecom_forensics.db-shm": b"sqlite-shm",
    }

    for file_name, content in expected_files.items():
        (old_database / file_name).write_bytes(content)

    copy_runtime(
        backup,
        staging,
    )

    restored_database = staging / "database"

    for file_name, expected_content in expected_files.items():
        restored_file = restored_database / file_name

        assert restored_file.is_file()
        assert restored_file.read_bytes() == expected_content



def test_complete_upgrade_preserves_master_duckdb(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from tools import install_or_upgrade

    source = tmp_path / "release_source"
    destination = tmp_path / "installed_application"

    (source / "modules").mkdir(parents=True)
    (source / "main.py").write_text(
        'print("release source")\n',
        encoding="utf-8",
    )

    installed_database = destination / "database"
    installed_database.mkdir(parents=True)

    expected_database = b"existing-master-duckdb"
    expected_wal = b"existing-master-duckdb-wal"

    (installed_database / "telecom_forensics.duckdb").write_bytes(
        expected_database
    )
    (installed_database / "telecom_forensics.duckdb.wal").write_bytes(
        expected_wal
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "install_or_upgrade.py",
            "--source",
            str(source),
            "--destination",
            str(destination),
        ],
    )

    result = install_or_upgrade.main()

    assert result == 0
    assert (
        destination
        / "database"
        / "telecom_forensics.duckdb"
    ).read_bytes() == expected_database
    assert (
        destination
        / "database"
        / "telecom_forensics.duckdb.wal"
    ).read_bytes() == expected_wal
