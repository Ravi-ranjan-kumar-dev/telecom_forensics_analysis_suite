from __future__ import annotations

import json
import multiprocessing as mp
import os
from pathlib import Path
from threading import Event, Thread

import duckdb
import pandas as pd
import pytest


@pytest.fixture
def store(tmp_path, monkeypatch):
    from modules.database import duckdb_core
    from modules.database.lookup_service import (
        initialize_master_lookup_database,
        clear_all_lookup_caches,
    )

    path = tmp_path / "project/database/unified_sdr_v2/telecom_forensics.duckdb"
    monkeypatch.setenv("ETHICALARMOR_MASTER_DB", str(path))
    monkeypatch.delenv("ETHICALARMOR_DATA_DIR", raising=False)
    initialize_master_lookup_database()
    duckdb_core.execute_sql(
        "INSERT INTO sdr_subscribers(mobile_number,subscriber_name) VALUES ('9876543210','SYNTHETIC OLD')"
    )
    duckdb_core.execute_sql(
        "INSERT INTO cgi_addresses(cgi,address,latitude,longitude) VALUES ('405-01-11111','SYNTHETIC OLD',25.5,85.1)"
    )
    clear_all_lookup_caches()
    yield path
    clear_all_lookup_caches()


def _attempt_lock(path, queue):
    from modules.database.master_access import master_access

    try:
        with master_access(path, timeout=0.15):
            queue.put("ACQUIRED")
    except TimeoutError:
        queue.put("BLOCKED")


def _update_store(path):
    from modules.database.duckdb_core import duckdb_connection

    with duckdb_connection(Path(path)) as con:
        con.execute("UPDATE cgi_addresses SET address='SYNTHETIC NEW'")
        con.execute("UPDATE sdr_subscribers SET subscriber_name='SYNTHETIC NEW'")


@pytest.mark.skipif(os.name != "posix", reason="Linux shared-container locking test")
def test_forked_process_obeys_same_lock_and_can_acquire_after_release(store):
    from modules.database.master_access import master_access

    ctx = mp.get_context("fork")
    queue = ctx.Queue()
    with master_access(store):
        with master_access(store):
            process = ctx.Process(target=_attempt_lock, args=(store, queue))
            process.start()
            process.join(4)
            assert process.exitcode == 0 and queue.get(timeout=1) == "BLOCKED"
    process = ctx.Process(target=_attempt_lock, args=(store, queue))
    process.start()
    process.join(4)
    assert process.exitcode == 0 and queue.get(timeout=1) == "ACQUIRED"


def test_thread_contention_timeout_preserves_store_and_releases_guard(store):
    from modules.database.master_access import master_access

    started = Event()
    release = Event()

    def owner():
        with master_access(store):
            started.set()
            release.wait(4)

    thread = Thread(target=owner)
    thread.start()
    assert started.wait(2)
    try:
        with pytest.raises(TimeoutError):
            with master_access(store, timeout=0.1):
                pass
    finally:
        release.set()
        thread.join(2)
    with master_access(store, timeout=0.1):
        pass


def test_read_queries_never_initialize_missing_master(tmp_path, monkeypatch):
    from modules.database.duckdb_core import query_dataframe

    path = tmp_path / "absent/database.duckdb"
    monkeypatch.setenv("ETHICALARMOR_MASTER_DB", str(path))
    with pytest.raises(FileNotFoundError):
        query_dataframe("SELECT 1")
    assert not path.exists() and not path.parent.exists()


def test_read_connection_is_query_only(store):
    from modules.database.duckdb_core import duckdb_connection

    with duckdb_connection(store, read_only=True) as con:
        with pytest.raises(duckdb.InvalidInputException):
            con.execute("CREATE TABLE forbidden(value INT)")


@pytest.mark.skipif(os.name != "posix", reason="Independent Linux writer process")
def test_other_process_commit_invalidates_cached_sdr_and_cgi(store):
    from modules.enrichment.cgi_address_enrichment import lookup_cgi_addresses
    from modules.database.lookup_service import lookup_sdr_profile

    assert lookup_cgi_addresses(["405-01-11111"]).iloc[0]["address"] == "SYNTHETIC OLD"
    assert lookup_sdr_profile("9876543210")["record"]["subscriber_name"] == "SYNTHETIC OLD"
    process = mp.get_context("fork").Process(target=_update_store, args=(store,))
    process.start()
    process.join(6)
    assert process.exitcode == 0
    assert lookup_cgi_addresses(["405-01-11111"]).iloc[0]["address"] == "SYNTHETIC NEW"
    assert lookup_sdr_profile("9876543210")["record"]["subscriber_name"] == "SYNTHETIC NEW"


def test_busy_profile_error_is_not_cached_permanently(store, monkeypatch):
    from modules.database import lookup_service

    original = lookup_service.lookup_sdr_subscribers

    def unavailable(*a):
        raise TimeoutError("synthetic busy master")

    monkeypatch.setattr(lookup_service, "lookup_sdr_subscribers", unavailable)
    assert lookup_service.lookup_sdr_profile("9876543210")["status"] == "DATABASE_ERROR"
    monkeypatch.setattr(lookup_service, "lookup_sdr_subscribers", original)
    assert lookup_service.lookup_sdr_profile("9876543210")["status"] == "MATCHED"


def test_compose_override_mounts_selected_master_without_copying_it(store, monkeypatch):
    from tools.configure_shared_master import configure

    project = store.parents[2]
    (project / "backend").mkdir()
    (project / "backend/docker-compose.yml").write_text("services: {}\n")
    before = store.read_bytes()
    output = configure(project)
    payload = json.loads(output.read_text())
    api = payload["services"]["api"]
    assert api["environment"]["ETHICALARMOR_MASTER_DB"] == "/master/telecom_forensics.duckdb"
    assert api["environment"]["ETHICALARMOR_MASTER_AUTHORITATIVE"] == "1"
    assert api["user"] == f"{os.getuid()}:{os.getgid()}"
    assert api["volumes"][0]["source"] == str(store.parent)
    assert api["volumes"][0]["bind"]["create_host_path"] is False
    assert "db" not in payload["services"] and store.read_bytes() == before
    assert configure(project) == output


def test_generator_refuses_missing_master_and_preserves_unknown_override(tmp_path, monkeypatch):
    from tools.configure_shared_master import configure

    project = tmp_path / "project"
    (project / "backend").mkdir(parents=True)
    (project / "backend/docker-compose.yml").write_text("services: {}\n")
    monkeypatch.setenv("ETHICALARMOR_MASTER_DB", str(project / "missing.duckdb"))
    with pytest.raises(FileNotFoundError):
        configure(project)
    assert not (project / "missing.duckdb").exists()


class NoSQLLookup:
    def query(self, *a, **kw):
        raise AssertionError("Authoritative master should not consult PostgreSQL lookup rows")


def test_authoritative_api_single_and_batch_use_master(store, monkeypatch):
    from backend.app.routers import lookup
    from backend.app import schemas

    monkeypatch.setenv("ETHICALARMOR_MASTER_AUTHORITATIVE", "1")
    db = NoSQLLookup()
    assert lookup.lookup_sdr("9876543210", None, db).subscriber_name == "SYNTHETIC OLD"
    assert lookup.lookup_cgi("405-01-11111", None, db).address == "SYNTHETIC OLD"
    assert (
        lookup.lookup_sdr_batch(
            schemas.SDRBatchLookupRequest(numbers=["9876543210"]), None, db
        ).count
        == 1
    )
    assert (
        lookup.lookup_cgi_batch(
            schemas.CGIBatchLookupRequest(cgis=["405-01-11111"]), None, db
        ).count
        == 1
    )


def test_authoritative_missing_master_returns_unavailable_not_not_found(tmp_path, monkeypatch):
    from backend.app.routers import lookup
    from fastapi import HTTPException

    monkeypatch.setenv("ETHICALARMOR_MASTER_AUTHORITATIVE", "1")
    monkeypatch.setenv("ETHICALARMOR_MASTER_DB", str(tmp_path / "missing.duckdb"))
    with pytest.raises(HTTPException) as error:
        lookup.lookup_sdr("9876543210", None, NoSQLLookup())
    assert error.value.status_code == 503
    with pytest.raises(HTTPException) as error:
        lookup.lookup_cgi("405-01-11111", None, NoSQLLookup())
    assert error.value.status_code == 503
    assert not (tmp_path / "missing.duckdb").exists()


def test_duplicate_local_sync_is_successful_after_primary_commit(monkeypatch):
    from backend.app.routers import imports

    monkeypatch.setattr(
        imports, "import_master_data_file", lambda *a, **kw: {"status": "SKIPPED_DUPLICATE"}
    )
    result = imports._sync_local_master("synthetic.csv", {"status": "SUCCESS"})
    assert result["status"] == "SUCCESS" and result["local_store"] == "SYNCHRONIZED"


def test_generator_preserves_unknown_override(store):
    from tools.configure_shared_master import configure

    project = store.parents[2]
    (project / "backend").mkdir()
    (project / "backend/docker-compose.yml").write_text("services: {}\n")
    output = project / "backend/docker-compose.shared-master.json"
    output.write_text('{"services": {"custom": {}}}')
    before = output.read_bytes()
    with pytest.raises((ValueError, RuntimeError)):
        configure(project)
    assert output.read_bytes() == before
