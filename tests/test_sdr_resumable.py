from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from test_sdr_consolidation import fixture_database
from tools import merge_sdr_resumable as merge
from tools.merge_sdr_tables import activate, rollback


def test_v2_build_preserves_source_and_reconciles_all_rows(tmp_path):
    source=fixture_database(tmp_path/'source.duckdb')
    original=hashlib.sha256(source.read_bytes()).hexdigest()
    report=merge.build(source,tmp_path/'new',memory_limit='256MB',batch_rows=1)
    assert report['canonical_records']==3
    assert report['review_records']==5
    assert report['input_sdr_records']==8
    assert report['builder']=='resumable-v2'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original
    con=duckdb.connect(report['database_path'],read_only=True)
    assert con.execute("SELECT subscriber_name FROM sdr_subscribers WHERE mobile_number='9000000001'").fetchone()[0]=='Primary authoritative'
    assert con.execute("SELECT subscriber_name FROM sdr_subscribers WHERE mobile_number='9000000003'").fetchone()[0]=='Latest'
    assert con.execute('SELECT count(*) FROM cgi_addresses').fetchone()[0]==1
    assert 'sdr_subscribers_large' not in {r[0] for r in con.execute('SHOW TABLES').fetchall()}
    assert merge.CURSOR not in {r[0] for r in con.execute('SHOW TABLES').fetchall()}
    con.close()


def test_v2_resumes_after_committed_batch_without_reranking(tmp_path,monkeypatch):
    source=fixture_database(tmp_path/'source.duckdb')
    root=tmp_path/'new'
    with pytest.raises(InterruptedError):
        merge.build(source,root,memory_limit='256MB',batch_rows=1,stop_after_batches=1)
    state=json.loads((root/'resume.json').read_text())
    assert state['phase']=='LOADING'
    con=duckdb.connect(str(root/'telecom_forensics.duckdb'),read_only=True)
    assert con.execute(f'SELECT loaded_rows FROM {merge.CURSOR}').fetchone()[0]==1
    con.close()
    monkeypatch.setattr(merge,'create_keys',lambda *a:pytest.fail('ranking must not repeat'))
    report=merge.build(source,root,resume=True,memory_limit='256MB',batch_rows=2)
    assert report['canonical_records']==3


def test_v2_detects_changed_checkpoint_artifact(tmp_path):
    source=fixture_database(tmp_path/'source.duckdb')
    root=tmp_path/'new'
    with pytest.raises(InterruptedError):
        merge.build(source,root,memory_limit='256MB',batch_rows=1,stop_after_batches=1)
    state=json.loads((root/'resume.json').read_text())
    path=root/state['audit']['path']
    with path.open('ab') as f:f.write(b'changed')
    with pytest.raises(ValueError,match='changed or is corrupt'):
        merge.build(source,root,resume=True,memory_limit='256MB')
    assert not (root/'migration-report.json').exists()


def test_v2_refuses_changed_source_and_v1_resume(tmp_path):
    source=fixture_database(tmp_path/'source.duckdb')
    root=tmp_path/'new'
    with pytest.raises(InterruptedError):
        merge.build(source,root,memory_limit='256MB',batch_rows=1,stop_after_batches=1)
    source.touch()
    with pytest.raises(ValueError,match='Original database changed'):
        merge.build(source,root,resume=True,memory_limit='256MB')
    v1=tmp_path/'old';v1.mkdir();(v1/'INCOMPLETE.json').write_text('{}')
    with pytest.raises(ValueError,match='old v1 TEMP'):
        merge.build(source,v1,resume=True)


def test_v2_reversible_activation_uses_existing_pointer_protocol(tmp_path,monkeypatch):
    monkeypatch.delenv('ETHICALARMOR_MASTER_DB',raising=False)
    source=fixture_database(tmp_path/'source.duckdb')
    root=tmp_path/'new'
    report=merge.build(source,root,memory_limit='256MB',batch_rows=2)
    pointer=tmp_path/'pointer.json'
    activate(root,pointer)
    assert json.loads(pointer.read_text())['database_path']==report['database_path']
    rollback(root)
    assert not pointer.exists()


@pytest.mark.parametrize("failure",[RuntimeError,duckdb.OutOfMemoryException])
def test_v2_load_transaction_rolls_back_failed_batch(tmp_path,monkeypatch,failure):
    source=fixture_database(tmp_path/'source.duckdb')
    root=tmp_path/'new'
    with pytest.raises(InterruptedError):
        merge.build(source,root,memory_limit='256MB',batch_rows=1,stop_after_batches=1)
    state=json.loads((root/'resume.json').read_text())
    original_connect=merge.connection
    class FailingConnection:
        def __init__(self,con):self.con=con
        def execute(self,sql,parameters=None):
            if sql.startswith(f'UPDATE {merge.CURSOR}'):
                raise failure('Injected failure before cursor commit')
            return self.con.execute(sql,parameters) if parameters is not None else self.con.execute(sql)
        def register(self,*args):return self.con.register(*args)
        def close(self):return self.con.close()
    monkeypatch.setattr(merge,'connection',lambda *args:FailingConnection(original_connect(*args)))
    with pytest.raises(failure,match='Injected failure'):
        merge.load_batches(root,state,'256MB',1,1)
    monkeypatch.setattr(merge,'connection',original_connect)
    con=duckdb.connect(str(root/'telecom_forensics.duckdb'),read_only=True)
    assert con.execute('SELECT count(*) FROM sdr_subscribers').fetchone()[0]==1
    assert con.execute(f'SELECT loaded_rows FROM {merge.CURSOR}').fetchone()[0]==1
    con.close()
    assert merge.build(source,root,resume=True,memory_limit='256MB',batch_rows=1)['canonical_records']==3


def test_v2_recovers_when_json_save_fails_after_target_ddl_commit(tmp_path,monkeypatch):
    source=fixture_database(tmp_path/'source.duckdb')
    root=tmp_path/'new'
    original_save=merge.save
    def fail_once(root_arg,state):
        if state['phase']=='LOADING':
            raise IOError('Injected after target checkpoint')
        original_save(root_arg,state)
    monkeypatch.setattr(merge,'save',fail_once)
    with pytest.raises(IOError,match='Injected'):
        merge.build(source,root,memory_limit='256MB',batch_rows=1)
    assert json.loads((root/'resume.json').read_text())['phase']=='SORTED_READY'
    monkeypatch.setattr(merge,'save',original_save)
    assert merge.build(source,root,resume=True,memory_limit='256MB',batch_rows=1)['canonical_records']==3


def test_v2_reuses_sorted_partition_when_phase_update_was_interrupted(tmp_path,monkeypatch):
    source=fixture_database(tmp_path/'source.duckdb')
    root=tmp_path/'new'
    original_save=merge.save
    def fail_once(root_arg,state):
        if state['phase']=='SORTED_READY':
            raise IOError('Injected after sorted files checkpoint')
        original_save(root_arg,state)
    monkeypatch.setattr(merge,'save',fail_once)
    with pytest.raises(IOError,match='Injected'):
        merge.build(source,root,memory_limit='256MB',batch_rows=1)
    state=json.loads((root/'resume.json').read_text())
    assert state['phase']=='EXPORTS_READY' and state['sorted']
    assert all(not (root/e['path']).exists() for e in state['raw_partitions'])
    monkeypatch.setattr(merge,'save',original_save)
    monkeypatch.setattr(merge,'create_keys',lambda *a:pytest.fail('ranking must not repeat'))
    monkeypatch.setattr(merge,'export_data',lambda *a:pytest.fail('exports must not repeat'))
    assert merge.build(source,root,resume=True,memory_limit='256MB',batch_rows=1)['canonical_records']==3


def test_v2_resumes_when_checkpoint_fails_after_successful_commit(tmp_path,monkeypatch):
    source=fixture_database(tmp_path/'source.duckdb')
    root=tmp_path/'new'
    with pytest.raises(InterruptedError):
        merge.build(source,root,memory_limit='256MB',batch_rows=1,stop_after_batches=1)
    original_connection=merge.connection
    class FailCheckpoint:
        def __init__(self,con):self.con=con
        def execute(self,sql,parameters=None):
            if sql=='CHECKPOINT':raise duckdb.OutOfMemoryException('Injected post-commit checkpoint failure')
            return self.con.execute(sql,parameters) if parameters is not None else self.con.execute(sql)
        def register(self,*args):return self.con.register(*args)
        def close(self):return self.con.close()
    monkeypatch.setattr(merge,'connection',lambda *args:FailCheckpoint(original_connection(*args)))
    state=json.loads((root/'resume.json').read_text())
    with pytest.raises(duckdb.OutOfMemoryException,match='post-commit'):
        merge.load_batches(root,state,'256MB',1,1)
    monkeypatch.setattr(merge,'connection',original_connection)
    con=duckdb.connect(str(root/'telecom_forensics.duckdb'),read_only=True)
    assert con.execute('SELECT count(*) FROM sdr_subscribers').fetchone()[0]==2
    assert con.execute(f'SELECT loaded_rows FROM {merge.CURSOR}').fetchone()[0]==2
    con.close()
    assert merge.build(source,root,resume=True,memory_limit='256MB',batch_rows=1)['canonical_records']==3
