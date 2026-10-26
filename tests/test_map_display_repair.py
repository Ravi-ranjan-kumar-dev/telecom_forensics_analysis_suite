from __future__ import annotations

import hashlib
import json
import re

import pandas as pd
import pytest


def payload(path):
    return json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',path.read_text(),re.S)[1])


@pytest.fixture
def lookup(monkeypatch):
    from modules.enrichment import cgi_address_enrichment as cgi
    calls=[]
    def find(keys):
        calls.append(list(keys))
        return pd.DataFrame([{'cgi':k,'latitude':25.5+i*.0001,'longitude':85.1+i*.0001} for i,k in enumerate(keys)])
    monkeypatch.setattr(cgi,'lookup_cgi_addresses',find)
    return calls


@pytest.mark.parametrize('prefix',['first_cell','last_cell','first_cgi','cell_id_cgi','searched_cell','First Tower'])
def test_tower_export_accepts_actual_coordinate_aliases(tmp_path,lookup,prefix):
    from modules.reporting.forensic_intelligence_suite import export_interactive_map_html
    frame=pd.DataFrame({prefix+'_latitude':[25.5],prefix+'_longitude':[85.1]})
    path,count=export_interactive_map_html({'Events':frame},tmp_path/'map.html')
    assert count==1 and payload(path)['points'][0]['lat']==25.5 and not lookup


def test_tower_export_hydrates_missing_coordinates_in_bounded_batches(tmp_path,lookup):
    from modules.reporting.forensic_intelligence_suite import export_interactive_map_html
    frame=pd.DataFrame({'first_cgi':['405-01-'+str(10000+i) for i in range(1001)]})
    path,count=export_interactive_map_html({'Full CDR Data':frame},tmp_path/'map.html')
    assert count==1001 and list(map(len,lookup))==[1000,1]
    assert payload(path)['diagnostics']['lookup_matches']==1001


def test_failed_master_lookup_produces_visible_reason(tmp_path,monkeypatch):
    from modules.enrichment import cgi_address_enrichment as cgi
    from modules.reporting.forensic_intelligence_suite import export_interactive_map_html
    def fail(*a):raise OSError('synthetic locked master')
    monkeypatch.setattr(cgi,'lookup_cgi_addresses',fail)
    path,count=export_interactive_map_html({'Events':pd.DataFrame({'first_cgi':['405-01-11111']})},tmp_path/'map.html')
    assert count==0 and payload(path)['diagnostics']['lookup_errors']==['OSError']
    assert 'CGI lookup failed' in payload(path)['diagnostics']['message']


def test_contact_map_resolves_cgi_when_summary_has_no_coordinates(tmp_path,lookup):
    from modules.reporting.cdr_contact_map import generate_cdr_contact_map
    path=generate_cdr_contact_map(pd.DataFrame({'Most Used Target CGI':['405-01-11111'],'Target':['9876543210']}),target='9876543210',report_path=tmp_path/'report.xlsx')
    assert len(payload(path)['points'])==1 and lookup


def test_movement_supports_normalized_aliases_and_chronological_metadata(tmp_path):
    from modules.reporting.cdr_movement_route import generate_cdr_movement_route
    frame=pd.DataFrame({'date':['30-07-2026']*2,'time':['12:20:00','12:00:00'],
                        'first_cgi':['405-01-22222','405-01-11111'],
                        'cell_id_cgi_latitude':[25.6,25.5],'cell_id_cgi_longitude':[85.2,85.1]})
    path=generate_cdr_movement_route(frame,target='9876543210',report_path=tmp_path/'report.xlsx')
    points=payload(path)['points']
    assert points[0]['label'].endswith('11111')
    assert [p['sequence'] for p in points]==[1,2]
    assert all(p['route'] and p['subscriber']=='9876543210' for p in points)


def test_movement_hydrates_missing_coordinates_and_emits_empty_diagnostic(tmp_path,lookup):
    from modules.reporting.cdr_movement_route import generate_cdr_movement_route
    frame=pd.DataFrame({'date':['30-07-2026'],'time':['12:00:00'],'first_cgi':['405-01-11111']})
    path=generate_cdr_movement_route(frame,target='9876543210',report_path=tmp_path/'report.xlsx')
    assert len(payload(path)['points'])==1 and lookup
    empty=generate_cdr_movement_route(pd.DataFrame(),target='9876543210',report_path=tmp_path/'empty.xlsx')
    assert empty.is_file() and payload(empty)['points']==[]
    assert 'No usable tower coordinates' in empty.read_text()


def test_multi_route_keeps_targets_and_sequences_separate():
    from modules.reporting.cdr_movement_route import render_multi_movement_route_html
    points=[{'latitude':25.5,'longitude':85.1,'cgi':'A','target':t,'sequence':i,'timestamp':'30-07-2026 12:00:00'} for t in ['TARGET-A','TARGET-B'] for i in [1,2]]
    doc=render_multi_movement_route_html(points)
    data=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',doc,re.S)[1])
    assert [p['subscriber'] for p in data['points']]==['TARGET-A']*2+['TARGET-B']*2
    assert [p['sequence'] for p in data['points']]==[1,2,1,2]


def test_missing_event_time_does_not_create_chronological_links(tmp_path):
    from modules.reporting.cdr_movement_route import generate_cdr_movement_route
    frame=pd.DataFrame({'date':['30-07-2026'],'first_cgi':['405-01-11111'],
                        'latitude':[25.5],'longitude':[85.1]})
    path=generate_cdr_movement_route(frame,target='9876543210',report_path=tmp_path/'report.xlsx')
    assert payload(path)['points'][0]['route'] is False


def test_multi_generator_hydrates_normalized_targets(tmp_path,lookup):
    from modules.reporting.cdr_movement_route import generate_multi_cdr_movement_route
    frame=pd.DataFrame({'target_number':['9876543210','9876543211'],'first_cgi':['405-01-11111']*2,
                        'date':['30-07-2026']*2,'time':['12:00:00']*2})
    path=generate_multi_cdr_movement_route(frame,report_path=tmp_path/'multi.xlsx')
    assert {p['subscriber'] for p in payload(path)['points']}=={'9876543210','9876543211'}


def test_repair_creates_separate_copy_and_preserves_original(tmp_path):
    from tools.repair_map_previews import repair
    from modules.reporting.offline_views import render_offline_view
    path=tmp_path/'old_map.html'
    path.write_text(render_offline_view('map',{'points':[{'lat':25.5,'lon':85.1,'label':'SYNTHETIC'}]}))
    original=hashlib.sha256(path.read_bytes()).hexdigest()
    result=repair(path)
    assert result[0]=='REPAIRED' and result[2]==1
    assert hashlib.sha256(path.read_bytes()).hexdigest()==original
    assert repair(path)[0]=='EXISTS'


def test_html_data_stays_escaped_and_styles_do_not_resize_leaflet_svg():
    from modules.reporting.offline_views import render_offline_view
    doc=render_offline_view('map',{'points':[{'lat':25.5,'lon':85.1,'label':'</script><script>alert(1)</script>'}]})
    assert '</script><script>alert(1)</script>' not in doc
    assert '#scene{width:100%' in doc and '\nsvg{width:100%' not in doc
    assert 'Bundled map engine unavailable' in doc and 'function fallback' in doc
