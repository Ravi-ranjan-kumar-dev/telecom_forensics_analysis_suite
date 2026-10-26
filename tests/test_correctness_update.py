"""Behavioral regressions for desktop correctness phase 1 (synthetic data only)."""
from __future__ import annotations

import asyncio
import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import duckdb
import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def accounts(monkeypatch):
    from backend.app import auth, models
    from backend.app.security import hash_password
    monkeypatch.setenv('SECRET_KEY', 'synthetic-correctness-tests-only-secret-over-32-chars')
    engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    with Session(engine) as db:
        for username, role, active, expiry in [('admin','admin',True,''),('viewer','viewer',True,''),('disabled','admin',False,''),('expired','admin',True,'2000-01-01')]:
            db.add(models.User(username=username, role=role, is_active=active, expires_at=expiry,
                               password_hash=hash_password('Synthetic Long Password 2026')))
        db.commit()
        yield db, {name:auth.create_access_token({'sub':name}) for name in ['admin','viewer','disabled','expired','deleted']}
    engine.dispose()


@pytest.mark.parametrize('name', ['viewer','disabled','expired','deleted'])
def test_import_rejects_unauthorized_account_before_parsing(accounts, monkeypatch, name):
    from backend.app.routers import imports
    from backend.app.database import get_db
    db, tokens = accounts
    app = FastAPI(); app.include_router(imports.router)
    app.dependency_overrides[get_db] = lambda: db
    def forbidden(*a, **kw):
        raise AssertionError('Unauthorized upload reached parser')
    monkeypatch.setattr(imports, 'detect_master_data_type', forbidden)
    with TestClient(app) as client:
        response = client.post('/api/import/master', headers={'Authorization':'Bearer '+tokens[name]}, files={'file':('audit.csv',b'synthetic')})
    assert response.status_code == 403


@pytest.mark.parametrize('name', ['disabled','expired','deleted'])
def test_managed_account_policy_applies_to_existing_tokens(accounts, name):
    from backend.app.routers import admin, lookup, auth
    db, tokens = accounts
    for fn in [admin.get_current_user, lookup.get_current_user, auth.read_users_me]:
        with pytest.raises(HTTPException):
            fn(tokens[name], db)


def test_expired_account_cannot_login(accounts):
    from backend.app.routers.auth import login
    db, _ = accounts
    with pytest.raises(HTTPException) as error:
        login(SimpleNamespace(username='expired',password='Synthetic Long Password 2026'),db)
    assert error.value.status_code == 401


@pytest.mark.parametrize(('expiry','now','valid'), [
    ('2026-10-19','2026-10-19T23:59:59+00:00',True),
    ('2026-10-19','2026-10-20T00:00:00+00:00',False),
    ('2026-10-19T21:00:00+05:30','2026-10-19T15:30:00+00:00',False),
    ('bad-date','2026-10-19T00:00:00+00:00',False),
])
def test_expiry_boundary(expiry,now,valid):
    from backend.app.access_policy import account_is_usable
    assert account_is_usable(SimpleNamespace(is_active=True,expires_at=expiry),now=datetime.fromisoformat(now)) is valid


@pytest.mark.parametrize('local_failure', [False,True])
def test_import_reports_committed_primary_and_local_sync_state(accounts,monkeypatch,local_failure):
    from backend.app.routers import imports
    db,tokens=accounts
    monkeypatch.setattr(imports,'detect_master_data_type',lambda _: {'import_type':'SDR'})
    monkeypatch.setattr(imports,'_read_input_file',lambda _:pd.DataFrame({'mobile':['9876543210']}))
    monkeypatch.setattr(imports,'_prepare_sdr_dataframe',lambda raw,name:pd.DataFrame({'mobile_number':['9876543210']}))
    monkeypatch.setattr(imports,'_upsert_sdr_postgres',lambda *a:(1,0))
    clears=[]
    monkeypatch.setattr(imports,'clear_all_lookup_caches',lambda:clears.append(True))
    def local(*a,**kw):
        if local_failure: raise OSError('synthetic replica failure')
        return {'status':'SUCCESS'}
    monkeypatch.setattr(imports,'import_master_data_file',local)
    result=asyncio.run(imports.import_master_file(UploadFile(file=io.BytesIO(b'synthetic'),filename='audit.csv'),db,tokens['admin']))
    if local_failure:
        assert result.status_code==207
        payload=json.loads(result.body)
        assert payload['status']=='PARTIAL' and payload['primary_store']=='COMMITTED' and payload['local_store']=='FAILED'
    else:
        assert result['status']=='SUCCESS' and result['local_store']=='SYNCHRONIZED' and clears


def test_cgi_cache_invalidation_refreshes_missing_and_changed_records(tmp_path,monkeypatch):
    from modules.enrichment import cgi_address_enrichment as cgi
    from modules.database.lookup_service import clear_all_lookup_caches
    path=tmp_path/'master.duckdb'; monkeypatch.setenv('ETHICALARMOR_MASTER_DB',str(path))
    with duckdb.connect(str(path)) as con:
        con.execute('CREATE TABLE cgi_addresses(cgi VARCHAR,operator VARCHAR,circle VARCHAR,state VARCHAR,district VARCHAR,police_station VARCHAR,town VARCHAR,site_name VARCHAR,address VARCHAR,latitude DOUBLE,longitude DOUBLE,source_file VARCHAR)')
    clear_all_lookup_caches()
    assert cgi.lookup_cgi_addresses(['405-01-11111']).empty
    with duckdb.connect(str(path)) as con:
        con.execute("INSERT INTO cgi_addresses(cgi,address) VALUES ('405-01-11111','SYNTHETIC OLD')")
    clear_all_lookup_caches()
    assert cgi.lookup_cgi_addresses(['405-01-11111']).iloc[0]['address']=='SYNTHETIC OLD'
    with duckdb.connect(str(path)) as con:
        con.execute("UPDATE cgi_addresses SET address='SYNTHETIC NEW'")
    clear_all_lookup_caches()
    assert cgi.lookup_cgi_addresses(['405-01-11111']).iloc[0]['address']=='SYNTHETIC NEW'
    clear_all_lookup_caches()


def test_jio_fallback_handles_dates_missing_optional_columns_and_bad_times(tmp_path, monkeypatch):
    from modules.loader import ipdr_loader as loader
    source=tmp_path/'jio.csv'
    pd.DataFrame({
        'Landline/MSISDN/MDN/Leased Circuit ID for Internet Access':['9876543210']*2,
        'Source IP Address':['192.0.2.1']*2,
        'Destination IP Address':['198.51.100.1']*2,
        'TIME1 (dd/MM/yyyy HH:mm:ss)':['11/06/2026 12:00:01','invalid'],
        'First CELL ID':['405-01-11111']*2,'Last CELL ID':['405-01-11111']*2,
        'Start Date of Public IP Address allocation (dd/mm/yyyy)':['11/06/2026']*2,
        'IST Start Time of Public IP address allocation (hh:mm:ss)':['11:00:00']*2,
    }).to_csv(source,index=False)
    monkeypatch.setattr(loader,'_original_load_ipdr_file_before_jio_dynamic_fallback',lambda _: {'data':pd.DataFrame()})
    result=loader.load_ipdr_file(source)
    assert len(result['data'])==1 and len(result['rejected_rows'])==1
    assert result['data'].iloc[0]['allocation_start']==pd.Timestamp('2026-06-11 11:00:00')


@pytest.fixture
def staging(tmp_path,monkeypatch):
    from modules.cases import repository
    from modules.staging import tower_ipdr_staging as stage
    monkeypatch.setattr(repository,'ACTIVE_CASES_DIR',tmp_path/'cases/active')
    path=stage.tower_ipdr_database_path('AUDIT-001');path.parent.mkdir(parents=True)
    frame=pd.DataFrame({'event_time':['2026-06-11 12:00:01','2026-06-11 12:00:40','2026-06-11 13:00:00'],
                        'subscriber_number':['9876543210']*3,'searched_cell_id':['405-01-11111']*3,
                        'imei':['111111111111111']*3,'imsi':['405011111111111']*3})
    with duckdb.connect(str(path)) as con:
        con.register('synthetic',frame);con.execute('CREATE TABLE tower_ipdr_events AS SELECT * FROM synthetic')
    return stage


@pytest.mark.parametrize(('mode','expected'), [('same_minute',2),('exact_second',1)])
def test_real_tower_partition_query_and_export(staging,mode,expected):
    result=staging.tower_ipdr_investigation_summary('AUDIT-001','2026-06-11 12:00:01',mode=mode)
    assert int(result['summary'].iloc[0]['records_found'])==expected
    manifest=staging.export_tower_ipdr_investigation_summary('AUDIT-001','2026-06-11 12:00:01',mode=mode)
    from pathlib import Path
    assert json.loads((Path(manifest['output_dir'])/'manifest.json').read_text())['analysis_mode']==mode


def test_complete_controller_explicit_folder_reaches_loader(tmp_path,monkeypatch):
    from modules.controllers import tower_ipdr_controller as controller
    called=[]
    def ready(*a,**kw):called.append(kw['input_folder']);return False
    monkeypatch.setattr(controller,'_ensure_tower_ipdr_data_ready',ready)
    assert controller._run_complete_tower_ipdr_analysis({'case_id':'AUDIT-001'},input_folder=tmp_path) is None
    assert called==[tmp_path.resolve()]


def test_case_paths_ignore_cwd_and_reject_workflow_traversal(tmp_path,monkeypatch):
    from modules.cases import repository,date_time_partitions
    from modules.staging.tower_ipdr_staging import tower_ipdr_staging_root
    root=tmp_path/'runtime';monkeypatch.setattr(repository,'ACTIVE_CASES_DIR',root/'cases/active')
    monkeypatch.chdir(tmp_path)
    assert date_time_partitions.date_time_partition_path('AUDIT-001','ipdr').is_relative_to(root)
    assert tower_ipdr_staging_root('AUDIT-001').is_relative_to(root)
    with pytest.raises(ValueError):date_time_partitions.date_time_partition_path('AUDIT-001','../../escape')


def test_profile_rejects_summary_rows_and_discloses_scoring():
    from modules.reporting.forensic_intelligence_suite import generate_auto_suspect_profile
    frame=pd.DataFrame({'target_number':['9876543210']*3,'b_party':['9876543211']*3})
    assert generate_auto_suspect_profile({'Contact Summary':frame.assign(Total_Events=120)}).empty
    result=generate_auto_suspect_profile({'Full Loaded Data':frame})
    assert result.iloc[0]['Total Events']==3
    assert result.iloc[0]['Ruleset']=='AUTO-PROFILE-1.0'
    assert 'Risk Score' not in result.columns and result.iloc[0]['Score Formula']


def test_full_source_includes_links_beyond_old_preview_boundary():
    from modules.reporting.gui_bundle_extractor import append_full_loaded_data_tab
    from modules.reporting.forensic_intelligence_suite import build_call_links
    frame=pd.DataFrame({'target_number':['9876543210']*200001,'b_party':['9876543211']*200000+['9876543212']})
    sheets=append_full_loaded_data_tab({}, {'df':frame})
    assert len(sheets['Full Loaded Data (200,001 rows)'])==200001
    links=build_call_links(sheets)
    assert sum(e['events'] for e in links['edges'])==200001
    assert any(e['contact']=='9876543212' for e in links['edges'])
    preview=append_full_loaded_data_tab({}, {'df':frame},max_rows=2)
    assert len(preview['Preview Loaded Data (2 of 200,001 rows)'])==2
    assert not build_call_links(preview)['edges']


def test_api_import_without_token_does_not_trigger_local_service_fallback():
    from gui.api_client import ApiClient,AuthenticationError
    with pytest.raises(AuthenticationError):ApiClient().import_master_file('unused.csv')


def test_partial_import_keeps_actual_committed_primary_record(accounts,monkeypatch):
    from backend.app import models
    from backend.app.routers import imports
    db,tokens=accounts
    monkeypatch.setattr(imports,'detect_master_data_type',lambda _: {'import_type':'SDR'})
    frame=pd.DataFrame({'mobile_number':['9876543210'],'subscriber_name':['SYNTHETIC PERSON']})
    monkeypatch.setattr(imports,'_read_input_file',lambda _:frame)
    monkeypatch.setattr(imports,'_prepare_sdr_dataframe',lambda *a:frame)
    monkeypatch.setattr(imports,'import_master_data_file',lambda *a,**kw:{'status':'FAILED'})
    result=asyncio.run(imports.import_master_file(UploadFile(file=io.BytesIO(b'synthetic'),filename='audit.csv'),db,tokens['admin']))
    assert result.status_code==207
    assert db.query(models.SDRSubscriber).filter_by(mobile_number='9876543210').one().subscriber_name=='SYNTHETIC PERSON'
