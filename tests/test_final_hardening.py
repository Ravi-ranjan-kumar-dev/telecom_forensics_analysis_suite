from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture()
def isolated_case_storage_final(tmp_path, monkeypatch):
    from modules.cases import repository

    active = tmp_path / "cases" / "active"
    archived = tmp_path / "cases" / "archived"
    monkeypatch.setattr(repository, "ACTIVE_CASES_DIR", active)
    monkeypatch.setattr(repository, "ARCHIVED_CASES_DIR", archived)
    monkeypatch.setattr(repository, "PROJECT_ROOT", tmp_path)
    return tmp_path


def test_audit_hash_chain_detects_tampering(isolated_case_storage_final):
    from modules.cases import create_case, register_target
    from modules.cases.service import case_directory, verify_case_audit

    case_id = create_case(case_name="Audit", case_id="FINAL-AUDIT-001")["case_id"]
    register_target(case_id, target_type="MSISDN", target_value="9876543210")
    assert verify_case_audit(case_id)["valid"] is True

    audit = case_directory(case_id) / "logs" / "audit.jsonl"
    lines = audit.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
    record["details"]["target_value"] = "9999999999"
    lines[-1] = json.dumps(record, sort_keys=True)
    audit.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = verify_case_audit(case_id)
    assert result["valid"] is False
    assert any("record_hash mismatch" in item for item in result["errors"])


def test_concurrent_target_updates_are_not_lost(isolated_case_storage_final):
    from modules.cases import create_case, register_target
    from modules.cases.service import case_directory

    case_id = create_case(case_name="Locking", case_id="FINAL-LOCK-001")["case_id"]

    def save(index: int):
        return register_target(
            case_id,
            target_type="MSISDN",
            target_value=f"9{index:09d}",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(save, range(30)))

    targets = json.loads(
        (case_directory(case_id) / "configuration" / "targets.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(targets) == 30


def test_manifest_contains_evidence_and_configuration_snapshot(isolated_case_storage_final):
    from modules.cases import case_evidence_dir, create_case, register_evidence, register_target
    from modules.cases.gprs_store import save_gprs_run

    case_id = create_case(case_name="Provenance", case_id="FINAL-PROV-001")["case_id"]
    source = case_evidence_dir(case_id, "tower_dump", "gprs") / "source.csv"
    source.write_text("header\nrow\n", encoding="utf-8")
    evidence = register_evidence(case_id, evidence_type="GPRS", source_file=source)
    register_target(case_id, target_type="MSISDN", target_value="9876543210")

    saved = save_gprs_run(
        case_id,
        analysis={"record_count": 1, "summary": pd.DataFrame([{"records": 1}])},
        input_folder=source.parent,
        source_files=[source],
    )
    manifest = json.loads(Path(saved["manifest"]).read_text(encoding="utf-8"))
    assert evidence["evidence_id"] in manifest["evidence_ids"]
    assert manifest["source_provenance"][0]["sha256"] == evidence["sha256"]
    assert manifest["configuration_snapshot"]["sha256"]


def test_report_attachment_requires_existing_case_local_file(isolated_case_storage_final, tmp_path):
    from modules.cases import InvalidCaseError, case_report_dir, create_case
    from modules.cases.gprs_store import attach_gprs_report, save_gprs_run

    case_id = create_case(case_name="Report", case_id="FINAL-REPORT-001")["case_id"]
    saved = save_gprs_run(
        case_id,
        analysis={"record_count": 0, "summary": pd.DataFrame()},
        input_folder="",
        source_files=[],
    )
    with pytest.raises(FileNotFoundError):
        attach_gprs_report(case_id, run_id=saved["run_id"], report_path=tmp_path / "missing.xlsx")

    outside = tmp_path / "outside.xlsx"
    outside.write_bytes(b"x")
    with pytest.raises(InvalidCaseError):
        attach_gprs_report(case_id, run_id=saved["run_id"], report_path=outside)

    inside = case_report_dir(case_id, "gprs_dump") / "report.xlsx"
    inside.write_bytes(b"xlsx")
    manifest = attach_gprs_report(case_id, run_id=saved["run_id"], report_path=inside)
    assert manifest["report_fingerprint"]["sha256"]


def test_read_only_missing_database_does_not_create_directories(tmp_path, monkeypatch):
    from modules.database import connection

    database = tmp_path / "nested" / "missing.db"
    monkeypatch.setattr(connection, "DEFAULT_DB_PATH", database)
    monkeypatch.delenv("TELECOM_FORENSICS_DB", raising=False)
    with pytest.raises(FileNotFoundError):
        connection.open_connection(read_only=True)
    assert not database.exists()
    assert not database.parent.exists()


def test_conservative_target_detection_rejects_ambiguous_contacts():
    from modules.loader.identity import detect_target_from_dataframe

    frame = pd.DataFrame(
        {
            "a_party": ["9000000001", "9000000002", "9000000003", "9000000004"],
            "b_party": ["8000000001", "8000000001", "8000000002", "8000000002"],
        }
    )
    result = detect_target_from_dataframe(frame)
    assert result.target is None
    assert result.method == "ambiguous-party-frequency"


def test_single_loader_rejects_multiple_files(tmp_path):
    from modules.loader.single_loader import get_single_file

    (tmp_path / "one.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / "two.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    assert get_single_file(tmp_path) is None


def test_header_detection_has_no_widest_row_fallback(tmp_path):
    from modules.loader.single_loader import find_header_row

    source = tmp_path / "not_cdr.csv"
    source.write_text("one,two,three,four\na,b,c,d\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Recognized CDR header not found"):
        find_header_row(source)


def test_coordinates_are_range_checked_and_swapped_only_when_unambiguous():
    from modules.loader.tower_dump_loader import _parse_lat_lon

    assert _parse_lat_lon("85.1376,25.5941") == (85.1376, 25.5941)  # both valid: preserve order
    assert _parse_lat_lon("120.5,25.5") == (25.5, 120.5)
    lat, lon = _parse_lat_lon("200,95")
    assert pd.isna(lat) and pd.isna(lon)


def test_run_ids_are_collision_resistant():
    from modules.core.time_utils import new_run_id

    values = {new_run_id("test") for _ in range(1000)}
    assert len(values) == 1000


def test_cgi_schema_and_provenance_ledger(tmp_path, monkeypatch):
    from modules.database import connection, schema
    from modules.database.cgi_importer import DB_COLUMNS, _flush_batch

    database = tmp_path / "database" / "cgi.db"
    monkeypatch.setattr(connection, "DEFAULT_DB_PATH", database)
    monkeypatch.setattr(connection, "CGI_DATA_DIR", tmp_path / "cgi_data")
    monkeypatch.delenv("TELECOM_FORENSICS_DB", raising=False)

    schema.initialize_database(create_migration_backup=False)
    with connection.database_connection() as conn:
        run = conn.execute(
            "INSERT INTO cgi_import_runs(started_at, source, status) VALUES(?,?,?)",
            ("2026-07-12T00:00:00Z", "fixture.csv", "RUNNING"),
        )
        record = {column: "" for column in DB_COLUMNS}
        record.update(
            {
                "cgi": "405-01-100-200",
                "cgi_key": "40501100200",
                "mcc": "405",
                "mnc": "01",
                "lac": "100",
                "cell_id": "200",
                "operator": "TEST",
                "source_file": "fixture.csv",
                "source_sheet": "Sheet1",
                "source_row": 2,
                "aliases": [("100200", "lac_cell")],
            }
        )
        _flush_batch(conn, [record], int(run.lastrowid))

    with connection.database_connection(read_only=True) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        provenance = conn.execute(
            "SELECT source_record_sha256, normalized_record_json "
            "FROM cgi_source_records"
        ).fetchone()
    assert version == schema.SCHEMA_VERSION
    assert provenance is not None
    assert len(provenance["source_record_sha256"]) == 64
    assert '"cgi_key":"40501100200"' in provenance["normalized_record_json"]


def test_controlled_case_reopen_requires_reason(isolated_case_storage_final):
    from modules.cases import CaseError, archive_case, create_case, open_case, reopen_case

    case_id = create_case(case_name="Reopen", case_id="FINAL-REOPEN-001")["case_id"]
    archive_case(case_id)
    with pytest.raises(CaseError):
        reopen_case(case_id, reason="")
    reopened = reopen_case(case_id, reason="Additional verified evidence received")
    assert reopened["status"] == "active"
    assert open_case(case_id)["status"] == "active"


def test_report_paths_are_unique(tmp_path):
    from modules.reporting.report_paths import get_multi_report_path, get_single_report_path

    assert get_single_report_path("9876543210", tmp_path) != get_single_report_path("9876543210", tmp_path)
    assert get_multi_report_path("Case", tmp_path) != get_multi_report_path("Case", tmp_path)


def test_gprs_normalization_preserves_raw_identifiers_and_tolerance(sample_path):
    from modules.loader.gprs_dump_loader import load_gprs_dump_file

    result = load_gprs_dump_file(sample_path)
    row = result["df"].iloc[0]
    assert row["imei_raw"] == "123456789012345"
    assert row["imei"] == "123456789012345"
    assert row["imsi_raw"] == "405010123456789"
    assert row["ipv4_address_raw"] == "10.0.0.1"
    assert row["ipv4_address"] == "10.0.0.1"
    assert bool(row["volume_consistent"]) is True
    assert row["volume_difference"] == 0


def test_cdr_scores_disclose_version_and_formula():
    from modules.analysis.cdr.contacts import contact_ranking
    from modules.analysis.cdr.social_network import social_network
    from modules.analysis.cdr.rules import RULESET_VERSION

    frame = pd.DataFrame(
        {
            "b_party": ["9000000001", "9000000001"],
            "call_type": ["incoming", "outgoing"],
            "call_duration": [60, 120],
            "first_cell_id": ["A", "B"],
        }
    )
    ranking = contact_ranking(frame)
    network = social_network(frame)
    assert ranking.iloc[0]["Score_Ruleset"] == RULESET_VERSION
    assert "Total_Events" in ranking.iloc[0]["Score_Formula"]
    assert network.iloc[0]["Strength_Ruleset"] == RULESET_VERSION
    assert "Total_Events" in network.iloc[0]["Strength_Formula"]


def test_legacy_database_gets_pre_migration_backup(tmp_path, monkeypatch):
    import sqlite3
    from modules.database import connection, schema

    database = tmp_path / "database" / "legacy.db"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE legacy_marker(value TEXT)")
        conn.execute("INSERT INTO legacy_marker(value) VALUES('preserve-me')")

    monkeypatch.setattr(connection, "DEFAULT_DB_PATH", database)
    monkeypatch.setattr(connection, "CGI_DATA_DIR", tmp_path / "cgi_data")
    monkeypatch.delenv("TELECOM_FORENSICS_DB", raising=False)
    schema.initialize_database(create_migration_backup=True)

    backups = list((database.parent / "backups").glob("*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute("SELECT value FROM legacy_marker").fetchone()[0] == "preserve-me"


def test_excel_safe_value_preserves_aware_datetime_as_iso_text():
    from datetime import datetime, timezone
    from modules.reporting.excel_security import excel_safe_value

    value = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
    assert excel_safe_value(value) == "2026-07-12T12:00:00+00:00"
