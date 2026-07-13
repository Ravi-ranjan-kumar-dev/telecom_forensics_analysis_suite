from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture()
def isolated_case_storage(tmp_path, monkeypatch):
    from modules.cases import repository

    active = tmp_path / "cases" / "active"
    archived = tmp_path / "cases" / "archived"
    project_root = tmp_path

    monkeypatch.setattr(repository, "ACTIVE_CASES_DIR", active)
    monkeypatch.setattr(repository, "ARCHIVED_CASES_DIR", archived)
    monkeypatch.setattr(repository, "PROJECT_ROOT", project_root)

    return active, archived


def test_case_evidence_dir_rejects_path_escape(isolated_case_storage):
    from modules.cases import InvalidCaseError, case_evidence_dir, create_case

    case = create_case(case_name="Path Safety", case_id="TEST-PATH-001")
    case_id = case["case_id"]

    with pytest.raises(InvalidCaseError):
        case_evidence_dir(case_id, "..")

    with pytest.raises(InvalidCaseError):
        case_evidence_dir(case_id, "/tmp")

    with pytest.raises(InvalidCaseError):
        case_evidence_dir(case_id, "tower_dump/ipdr")

    valid = case_evidence_dir(case_id, "tower_dump", "ipdr")
    assert valid.is_dir()
    assert valid.parts[-3:] == ("evidence", "tower_dump", "ipdr")


def test_evidence_registration_is_append_only(isolated_case_storage):
    from modules.cases import case_evidence_dir, create_case, register_evidence
    from modules.cases.repository import read_json
    from modules.cases.service import case_directory

    case = create_case(case_name="Evidence History", case_id="TEST-EVD-001")
    case_id = case["case_id"]
    source = case_evidence_dir(case_id, "cdr", "single") / "sample.csv"
    source.write_text("alpha\n", encoding="utf-8")

    first = register_evidence(
        case_id,
        evidence_type="CDR",
        source_file=source,
    )
    second = register_evidence(
        case_id,
        evidence_type="CDR",
        source_file=source,
    )

    source.write_text("beta\n", encoding="utf-8")
    third = register_evidence(
        case_id,
        evidence_type="CDR",
        source_file=source,
    )

    records = read_json(
        case_directory(case_id) / "configuration" / "evidence.json",
        default=[],
    )

    assert len(records) == 3
    assert first["change_status"] == "NEW"
    assert second["change_status"] == "UNCHANGED"
    assert third["change_status"] == "MODIFIED"
    assert second["previous_evidence_id"] == first["evidence_id"]
    assert third["previous_evidence_id"] == second["evidence_id"]
    assert records[0]["sha256"] == first["sha256"]
    assert records[0]["sha256"] != third["sha256"]
    assert not Path(first["source_file"]).is_absolute()


def test_archived_case_is_read_only(isolated_case_storage):
    from modules.cases import (
        ArchivedCaseReadOnlyError,
        archive_case,
        case_evidence_dir,
        create_case,
        open_case,
        register_analysis_run,
        register_target,
    )

    case = create_case(case_name="Archive Guard", case_id="TEST-ARC-001")
    case_id = case["case_id"]
    archive_case(case_id)

    assert open_case(case_id, include_archived=True)["status"] == "archived"

    with pytest.raises(ArchivedCaseReadOnlyError):
        register_target(
            case_id,
            target_type="MSISDN",
            target_value="9999999999",
        )

    with pytest.raises(ArchivedCaseReadOnlyError):
        case_evidence_dir(case_id, "cdr", "single")

    with pytest.raises(ArchivedCaseReadOnlyError):
        register_analysis_run(
            case_id,
            analysis_type="TEST",
            status="COMPLETED",
        )


def test_relative_manifest_survives_archival(isolated_case_storage):
    from modules.cases import archive_case, case_evidence_dir, create_case
    from modules.cases.gprs_store import (
        load_latest_gprs_manifest,
        save_gprs_run,
    )
    from modules.cases.repository import read_json
    from modules.cases.service import case_directory

    case = create_case(case_name="Portable Manifest", case_id="TEST-MAN-001")
    case_id = case["case_id"]
    input_folder = case_evidence_dir(case_id, "tower_dump", "gprs")
    source = input_folder / "sample.csv"
    source.write_text("x\n1\n", encoding="utf-8")

    saved = save_gprs_run(
        case_id,
        analysis={
            "record_count": 1,
            "summary": pd.DataFrame([{"records": 1}]),
        },
        input_folder=input_folder,
        source_files=[str(source)],
    )

    latest_path = (
        case_directory(case_id)
        / "results"
        / "gprs_dump"
        / "latest.json"
    )
    latest = read_json(latest_path, default={})

    assert not Path(latest["run_directory"]).is_absolute()
    assert not Path(latest["manifest"]).is_absolute()

    manifest = read_json(Path(saved["manifest"]), default={})
    assert not Path(manifest["input_folder"]).is_absolute()
    assert all(not Path(value).is_absolute() for value in manifest["saved_files"].values())

    archive_case(case_id)
    loaded = load_latest_gprs_manifest(case_id)

    assert loaded is not None
    assert loaded["run_id"] == saved["run_id"]
    assert loaded["record_count"] == 1


def test_atomic_json_write_leaves_no_temp_file(isolated_case_storage, tmp_path):
    from modules.cases.repository import read_json, write_json

    path = tmp_path / "atomic" / "manifest.json"
    write_json(path, {"ok": True, "count": 1})

    assert read_json(path) == {"ok": True, "count": 1}
    assert list(path.parent.glob(f".{path.name}.*.tmp")) == []
    json.loads(path.read_text(encoding="utf-8"))


def test_all_case_run_stores_write_portable_manifests(isolated_case_storage, tmp_path):
    from modules.cases import case_report_dir, create_case
    from modules.cases.ipdr_store import attach_ipdr_report, save_ipdr_run
    from modules.cases.partition_store import save_partition_run
    from modules.cases.repository import read_json
    from modules.cases.service import case_directory
    from modules.cases.tower_ipdr_store import save_tower_ipdr_run

    case = create_case(case_name="Run Stores", case_id="TEST-RUN-001")
    case_id = case["case_id"]
    project_input = tmp_path / "data" / "ipdr" / "single"
    project_input.mkdir(parents=True)
    source = project_input / "sample.csv"
    source.write_text("x\n1\n", encoding="utf-8")
    table = pd.DataFrame([{"records": 1}])

    ipdr_saved = save_ipdr_run(
        case_id,
        mode="single",
        analysis={"record_count": 1, "summary": table},
        input_folder=project_input,
        source_files=[str(source)],
    )
    ipdr_manifest = read_json(Path(ipdr_saved["manifest"]), default={})
    assert ipdr_manifest["input_folder"].startswith("project://")
    assert all(not Path(value).is_absolute() for value in ipdr_manifest["saved_files"].values())

    report = case_report_dir(case_id, "ipdr_single") / "result.xlsx"
    report.write_bytes(b"xlsx-placeholder")
    attached = attach_ipdr_report(
        case_id,
        mode="single",
        run_id=ipdr_saved["run_id"],
        report_path=report,
    )
    assert not Path(attached["user_facing_report"]).is_absolute()

    tower_saved = save_tower_ipdr_run(
        case_id,
        analysis={
            "record_count": 1,
            "total_cells": 1,
            "summary": table,
        },
        input_folder=project_input,
        source_files=[str(source)],
    )
    tower_manifest = read_json(Path(tower_saved["manifest"]), default={})
    assert tower_manifest["input_folder"].startswith("project://")
    assert all(not Path(value).is_absolute() for value in tower_manifest["saved_files"].values())

    partition_saved = save_partition_run(
        case_id,
        {
            "total_input_records": 1,
            "total_sightings": 1,
            "partition_summary": table,
            "subscriber_presence": table,
        },
    )
    partition_manifest = read_json(
        Path(partition_saved["manifest"]),
        default={},
    )
    assert all(
        not Path(value).is_absolute()
        for value in partition_manifest["saved_files"].values()
    )

    case_root = case_directory(case_id)
    for latest_path in case_root.rglob("latest.json"):
        latest = read_json(latest_path, default={})
        for key in ("run_directory", "manifest", "user_facing_report"):
            value = str(latest.get(key, ""))
            if value:
                assert not Path(value).is_absolute()


def test_attach_run_id_rejects_path_traversal(isolated_case_storage):
    from modules.cases import InvalidCaseError, create_case
    from modules.cases.gprs_store import attach_gprs_report

    case = create_case(case_name="Attach Safety", case_id="TEST-ATT-001")

    with pytest.raises(InvalidCaseError):
        attach_gprs_report(
            case["case_id"],
            run_id="../../outside",
            report_path="outside.xlsx",
        )
