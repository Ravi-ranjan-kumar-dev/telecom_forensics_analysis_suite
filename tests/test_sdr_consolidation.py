from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from tools.merge_sdr_tables import build, activate, rollback, FIELDS


def fixture_database(path):
    con = duckdb.connect(str(path))
    columns = ",".join('"'+c+'" VARCHAR' for c in FIELDS[:-1])
    con.execute(f"CREATE TABLE sdr_subscribers ({columns}, imported_at TIMESTAMP, PRIMARY KEY(mobile_number))")
    con.execute(f"CREATE TABLE sdr_subscribers_large ({columns}, imported_at TIMESTAMPTZ)")
    def insert(table, number, name, date="2026-01-01", imported="2026-02-01 00:00:00+00"):
        values = [number,name,"Father", "Address", "ID", "123", "Operator", "Circle", date,"1","fixture.csv",imported]
        con.execute(f"INSERT INTO {table} VALUES ({','.join(['?']*12)})",values)
    insert("sdr_subscribers", "9000000001", "Primary authoritative", "2025-01-01")
    insert("sdr_subscribers", "0919000000002", "Invalid prefix")
    insert("sdr_subscribers_large", "919000000001", "Alternate newer", "2026-03-01")
    insert("sdr_subscribers_large", "09000000003", "Older", "2025-01-01")
    insert("sdr_subscribers_large", "9000000003.0", "Latest", "2026-01-01")
    insert("sdr_subscribers_large", "12345", "Invalid short")
    insert("sdr_subscribers_large", None, "Missing")
    insert("sdr_subscribers_large", "9000000004", "Standalone")
    con.execute("CREATE TABLE cgi_addresses(cgi VARCHAR PRIMARY KEY, latitude DOUBLE, longitude DOUBLE)")
    con.execute("INSERT INTO cgi_addresses VALUES ('405-01-1',25.5,85.1)")
    con.execute("CREATE TABLE postgres_sdr_migration_progress(offset_value BIGINT)")
    con.execute("INSERT INTO postgres_sdr_migration_progress VALUES (12)")
    con.close()
    return path


def test_merges_whole_rows_reconciles_audit_and_leaves_input_unchanged(tmp_path):
    source=fixture_database(tmp_path/"original.duckdb")
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    report=build(source,tmp_path/"unified",memory_limit="256MB",threads=1)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    assert report["canonical_records"]==3
    assert report["review_records"]==5
    assert report["invalid_mobile_records"]==3
    assert report["alternate_or_duplicate_records"]==2
    con=duckdb.connect(report["database_path"],read_only=True)
    assert "sdr_subscribers_large" not in {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    assert con.execute("SELECT subscriber_name FROM sdr_subscribers WHERE mobile_number='9000000001'").fetchone()[0]=="Primary authoritative"
    assert con.execute("SELECT subscriber_name FROM sdr_subscribers WHERE mobile_number='9000000003'").fetchone()[0]=="Latest"
    assert con.execute("SELECT * FROM cgi_addresses").fetchone()==('405-01-1',25.5,85.1)
    assert con.execute("SELECT * FROM postgres_sdr_migration_progress").fetchone()==(12,)
    assert con.execute("SELECT count(*) FROM read_parquet(?)",[report["review_path"]]).fetchone()[0]==5
    constraints=con.execute("SELECT constraint_type FROM duckdb_constraints() WHERE table_name='sdr_subscribers'").fetchall()
    assert ('PRIMARY KEY',) in constraints
    con.close()


def test_activation_and_rollback_are_reversible_without_renaming_input(tmp_path,monkeypatch):
    monkeypatch.delenv("ETHICALARMOR_MASTER_DB",raising=False)
    source=fixture_database(tmp_path/"source.duckdb")
    output=tmp_path/"output"
    report=build(source,output,memory_limit="256MB",threads=1)
    pointer=tmp_path/"config"/"master_database.json"
    result=activate(output,pointer)
    assert json.loads(pointer.read_text())["database_path"]==report["database_path"]
    rollback(output)
    assert not pointer.exists()
    assert source.exists() and Path(report["database_path"]).exists()


def test_restore_existing_pointer_and_refuse_overwrite_of_new_selection(tmp_path,monkeypatch):
    monkeypatch.delenv("ETHICALARMOR_MASTER_DB",raising=False)
    source=fixture_database(tmp_path/"source.duckdb")
    output=tmp_path/"output"
    build(source,output,memory_limit="256MB",threads=1)
    pointer=tmp_path/"master_database.json"
    old={"format":"ethicalarmor/master-database-pointer/v1","database_path":str(source)}
    pointer.write_text(json.dumps(old))
    activate(output,pointer)
    rollback(output)
    assert json.loads(pointer.read_text())==old


def test_refuses_existing_output_and_unknown_source_columns(tmp_path):
    source=fixture_database(tmp_path/"source.duckdb")
    output=tmp_path/"existing";output.mkdir()
    with pytest.raises(FileExistsError):build(source,output)
    con=duckdb.connect(str(source));con.execute("ALTER TABLE sdr_subscribers_large ADD COLUMN extra VARCHAR");con.close()
    with pytest.raises(ValueError,match="Unsupported columns"):build(source,tmp_path/"no-copy")
    assert not (tmp_path/"no-copy").exists()


def test_missing_database_pointer_fails_instead_of_creating_empty_db(tmp_path,monkeypatch):
    from modules.database import db_paths
    monkeypatch.setattr(db_paths,"DATABASE_DIR",tmp_path)
    monkeypatch.delenv("ETHICALARMOR_MASTER_DB",raising=False)
    (tmp_path/"master_database.json").write_text(json.dumps({"format":"ethicalarmor/master-database-pointer/v1","database_path":str(tmp_path/"missing.duckdb")}))
    with pytest.raises(FileNotFoundError):db_paths.master_duckdb_path()
    assert not (tmp_path/"missing.duckdb").exists()


def test_old_large_lookup_matches_real_address_schema_and_all_batches(tmp_path,monkeypatch):
    from modules.enrichment import sdr_subscriber_enrichment as enrichment
    con=duckdb.connect(":memory:")
    columns=",".join('"'+c+'" VARCHAR' for c in FIELDS)
    con.execute(f"CREATE TABLE sdr_subscribers_large ({columns})")
    numbers=[str(9000000000+i) for i in range(1200)]
    rows=[(n,"Name","Father","Correct address","ID","id","AIRTEL","Bihar","2026-01-01","1","fixture.csv","2026-01-02") for n in numbers]
    con.executemany("INSERT INTO sdr_subscribers_large VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",rows)
    monkeypatch.setattr(enrichment,"query_dataframe",lambda sql,parameters=None:con.execute(sql,parameters or []).df())
    result=enrichment._lookup_from_large_table(numbers)
    assert len(result)==1200
    assert set(result["subscriber_address"])=={"Correct address"}
    con.close()


def test_import_cache_clear_removes_old_negative_results():
    from modules.enrichment import sdr_subscriber_enrichment as enrichment
    from modules.database.lookup_service import clear_all_lookup_caches
    enrichment._SDR_MEM_POS['9000000001']={"sdr_found":"No"}
    clear_all_lookup_caches()
    assert '9000000001' not in enrichment._SDR_MEM_POS


def test_activation_refuses_changed_original_and_explicit_override(tmp_path,monkeypatch):
    source=fixture_database(tmp_path/"source.duckdb")
    output=tmp_path/"output"
    result=build(source,output,memory_limit="256MB",threads=1)
    pointer=tmp_path/"master_database.json"
    monkeypatch.setenv("ETHICALARMOR_MASTER_DB",result["database_path"])
    with pytest.raises(ValueError,match="overrides"):activate(output,pointer)
    monkeypatch.delenv("ETHICALARMOR_MASTER_DB")
    con=duckdb.connect(str(source));con.execute("INSERT INTO cgi_addresses VALUES ('405-01-2',1,2)");con.close()
    with pytest.raises(ValueError,match="Original database changed"):activate(output,pointer)
    assert not pointer.exists()


def test_existing_pointer_resolution_and_environment_priority(tmp_path,monkeypatch):
    from modules.database import db_paths
    source=fixture_database(tmp_path/"source.duckdb")
    output=tmp_path/"output"
    report=build(source,output,memory_limit="256MB",threads=1)
    pointer=tmp_path/"master_database.json"
    monkeypatch.setattr(db_paths,"DATABASE_DIR",tmp_path)
    monkeypatch.delenv("ETHICALARMOR_MASTER_DB",raising=False)
    activate(output,pointer)
    assert db_paths.master_duckdb_path()==Path(report["database_path"])
    monkeypatch.setenv("ETHICALARMOR_MASTER_DB",str(source))
    assert db_paths.master_duckdb_path()==source


def test_wal_refusal_does_not_create_output(tmp_path):
    source=fixture_database(tmp_path/"source.duckdb")
    Path(str(source)+".wal").write_bytes(b"fixture pending wal")
    with pytest.raises(ValueError,match="WAL"):build(source,tmp_path/"output")
    assert not (tmp_path/"output").exists()


def test_pointer_lock_refuses_concurrent_activation(tmp_path,monkeypatch):
    monkeypatch.delenv("ETHICALARMOR_MASTER_DB",raising=False)
    source=fixture_database(tmp_path/"source.duckdb")
    output=tmp_path/"output"
    build(source,output,memory_limit="256MB",threads=1)
    pointer=tmp_path/"master_database.json"
    pointer.with_name(pointer.name+".lock").write_text("other process")
    with pytest.raises(FileExistsError):activate(output,pointer)
    assert not pointer.exists()


def test_existing_master_importer_updates_unified_table_without_recreating_large(tmp_path,monkeypatch):
    from modules.database import master_import_service as service
    source=fixture_database(tmp_path/"source.duckdb")
    report=build(source,tmp_path/"output",memory_limit="256MB",threads=1)
    destination=Path(report["database_path"])
    monkeypatch.setattr(service,"master_duckdb_path",lambda:destination)
    monkeypatch.setattr(service,"_write_json_log",lambda *args,**kwargs:None)
    incoming=tmp_path/"sdr_addition.csv"
    incoming.write_text("mobile_number,subscriber_name,address,operator,circle,activation_date\n9000000005,Imported,Test Address,AIRTEL,Bihar,2026-05-01\n")
    result=service.import_master_data_file(incoming,create_backup=False)
    assert result["status"]=="SUCCESS",result
    con=duckdb.connect(str(destination),read_only=True)
    assert con.execute("SELECT subscriber_name FROM sdr_subscribers WHERE mobile_number='9000000005'").fetchone()[0]=="Imported"
    assert "sdr_subscribers_large" not in {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    con.close()
