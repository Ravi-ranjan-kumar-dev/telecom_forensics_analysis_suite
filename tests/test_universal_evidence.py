"""Security + end-to-end synthetic regression for all EthicalArmor evidence modules."""
import gzip
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from modules.loader.universal_evidence import (inspect_universal_evidence,
    approve_format_profile,load_universal_evidence,group_ready_by_module)
from modules.loader.universal_bridge import (EvidenceReviewRequired,require_analysis_ready,module_preview)


def make_csv(tmp_path, name, header, rows):
    p=tmp_path/name
    p.write_text(header+"\n"+"\n".join(rows)+"\n",encoding="utf-8")
    return p

@pytest.mark.parametrize("evidence_type,header,rows,mapping,time_format",[
 ("CDR","Agent,Peer,DateX,TimeX,DurationX,Device",["9111100000,9222200000,15/10/2026,10:11:12,60,012345678901234"],
  {"a_party":"Agent","b_party":"Peer","call_date":"DateX","call_time":"TimeX","call_duration":"DurationX","imei":"Device"},"%d/%m/%Y %H:%M:%S"),
 ("TOWER_CDR","Agent,DateX,TimeX,Tower,Device",["9111100000,15/10/2026,10:11:12,405-52-1,012345678901234"],
  {"a_party":"Agent","call_date":"DateX","call_time":"TimeX","first_cell_id":"Tower","imei":"Device"},"%d/%m/%Y %H:%M:%S"),
 ("TOWER_GPRS","Phone,Event,Tower,Upload",["9111100000,2026-10-15 10:11:12,405-52-1,123"],
  {"subscriber_number":"Phone","event_time":"Event","first_cell_id":"Tower","uplink_volume":"Upload"},"%Y-%m-%d %H:%M:%S"),
 ("TOWER_IPDR","Phone,Event,LocalIP,Port",["9111100000,2026-10-15 10:11:12,10.0.0.1,1234"],
  {"subscriber_number":"Phone","event_time":"Event","source_ip":"LocalIP","source_port":"Port"},"%Y-%m-%d %H:%M:%S"),
 ("IPDR","Phone,Event,LocalIP,Port",["9111100000,2026-10-15 10:11:12,10.0.0.1,1234"],
  {"subscriber_number":"Phone","event_time":"Event","source_ip":"LocalIP","source_port":"Port"},"%Y-%m-%d %H:%M:%S"),
 ("IMEI_CDR","Device,DateX,Peer",["012345678901234,2026-10-15 10:11:12,9111100000"],
  {"imei":"Device","event_time":"DateX","b_party":"Peer"},"%Y-%m-%d %H:%M:%S"),
 ("IMEI_GPRS","Device,DateX,Phone",["012345678901234,2026-10-15 10:11:12,9111100000"],
  {"imei":"Device","event_time":"DateX","subscriber_number":"Phone"},"%Y-%m-%d %H:%M:%S"),
 ("IMEI_IPDR","Device,DateX,LocalIP",["012345678901234,2026-10-15 10:11:12,10.0.0.1"],
  {"imei":"Device","event_time":"DateX","source_ip":"LocalIP"},"%Y-%m-%d %H:%M:%S"),
 ("IMEI_INVENTORY","Device,Phone,SomeCode",["012345678901234,9111100000,ABCDE"],
  {"imei":"Device","subscriber_number":"Phone"},None),
])
def test_review_then_approved_profile_in_all_modules(tmp_path,evidence_type,header,rows,mapping,time_format):
    p=make_csv(tmp_path,"vendor.csv",header,rows)
    result=load_universal_evidence(p,allow_native=False)
    item=result["file_results"][0]
    assert item["status"]=="needs_review"
    with pytest.raises(EvidenceReviewRequired):require_analysis_ready(result,{"TOWER_CDR":"TOWER_DUMP","TOWER_IPDR":"TOWER_DUMP","TOWER_GPRS":"TOWER_DUMP"}.get(evidence_type,"IMEI" if evidence_type.startswith("IMEI") else evidence_type))
    profile=approve_format_profile(p,evidence_type=evidence_type,field_mapping=mapping,approved_by="test-analyst",
                  time_format=time_format, timezone_name="Asia/Kolkata" if time_format else None,profile_dir=tmp_path/"profiles")
    assert profile["evidence_type"]==evidence_type
    imported=load_universal_evidence(p,profiles_dir=tmp_path/"profiles",allow_native=False)
    item=imported["file_results"][0]
    assert item["status"]=="ready",item.get("errors")
    assert item["ok"] and len(item["df"])==1
    assert item["df"].iloc[0]["source_record_index"]==1
    assert len(require_analysis_ready(imported, profile["module"]))==1
    assert len(group_ready_by_module(imported)[profile["module"]])==1
    assert len(module_preview(imported))==1
    assert "Agent" not in str(profile) or "9111100000" not in str(profile)  # never store raw numbers


def test_unapproved_unknown_headers_are_review_only(tmp_path):
    p=make_csv(tmp_path,"any.csv","Alpha,Beta,Gamma",["a,b,c"])
    r=inspect_universal_evidence(p)
    assert r["ok"] and r["status"]=="needs_review"
    assert r["suggested_module"]=="UNKNOWN"
    loaded=load_universal_evidence(p)
    assert loaded["file_results"][0]["status"]=="needs_review"


def test_invalid_ip_ports_and_date_quarantined(tmp_path):
    p=make_csv(tmp_path,"bad.csv","Phone,DateX,LocalIP,Port",[
        "9111100000,2026-10-15 10:11:12,10.0.0.1,443",
        "9111100000,2026-10-15 10:11:12,300.1.1.1,70000",
        "9111100000,not-a-date,10.0.0.1,11"])
    approve_format_profile(p,evidence_type="IPDR",field_mapping={"subscriber_number":"Phone","event_time":"DateX",
        "source_ip":"LocalIP","source_port":"Port"},approved_by="operator",time_format="%Y-%m-%d %H:%M:%S",
        timezone_name="Asia/Kolkata",profile_dir=tmp_path/"profiles")
    r=load_universal_evidence(p,profiles_dir=tmp_path/"profiles",allow_native=False)
    item=r["file_results"][0]
    assert item["status"]=="ready" and len(item["df"])==1
    assert len(item["rejected_rows"])==2
    assert "INVALID_SOURCE_IP" in item["rejected_rows"].iloc[0]["reject_reason"]
    assert "BAD_OR_AMBIGUOUS_TIMESTAMP" in item["rejected_rows"].iloc[1]["reject_reason"]


def test_mapping_does_not_auto_approve(tmp_path):
    p=make_csv(tmp_path,"cdr.csv","A Party,B Party,Call Date,Call Time",["91,92,15/10/2026,13:00:00"])
    info=inspect_universal_evidence(p)
    assert info["suggested_module"]=="CDR"
    with pytest.raises(ValueError,match="requires explicit time_format"):
        approve_format_profile(p,evidence_type="CDR",approved_by="A",profile_dir=tmp_path/"profiles")
    assert info["status"]=="needs_review"


def test_source_columns_do_not_become_guessed_imei_type(tmp_path):
    p=make_csv(tmp_path,"cdr.csv","A Party,B Party,Call Date,IMEI",["91,92,15/10/2026,123456789012345"])
    info=inspect_universal_evidence(p)
    assert info["suggested_module"]=="CDR"


def test_gzip_and_zip_metadata_and_security(tmp_path):
    raw=b"Agent,Peer,DateX\n91,92,15/10/2026\n"
    z=tmp_path/"report.csv.gz"
    with gzip.open(z,"wb") as fh:fh.write(raw)
    gz=load_universal_evidence(z,allow_native=False)
    assert gz["file_results"][0]["status"]=="needs_review"
    assert gz["file_results"][0]["archive_member"]=="report.csv"
    assert gz["file_results"][0]["source_sha256"]==gz["source_sha256"]
    arch=tmp_path/"archive.zip"
    with zipfile.ZipFile(arch,"w") as fh:fh.writestr("../escape.csv",raw)
    bad=load_universal_evidence(arch)
    assert not bad["ok"] and "Unsafe ZIP member path" in " ".join(bad["errors"])
    assert not (tmp_path/"escape.csv").exists()


def test_header_profile_not_applied_to_reordered_columns(tmp_path):
    p=make_csv(tmp_path,"report.csv","Agent,Peer,DateX",["911,922,2026-10-15 10:11:12"])
    approve_format_profile(p,evidence_type="CDR",field_mapping={"a_party":"Agent","b_party":"Peer","event_time":"DateX"},
       approved_by="operator",time_format="%Y-%m-%d %H:%M:%S",timezone_name="Asia/Kolkata",profile_dir=tmp_path/"profiles")
    p.write_text("Peer,Agent,DateX\n922,911,2026-10-15 10:11:12\n")
    r=load_universal_evidence(p,profiles_dir=tmp_path/"profiles",allow_native=False)
    assert r["file_results"][0]["status"]=="needs_review"

def test_same_header_multiple_types_needs_explicit_choice(tmp_path):
    p=make_csv(tmp_path,"generic.csv","Phone,Event,LocalIP",["9111100000,2026-10-15 10:11:12,10.0.0.1"])
    fields={"subscriber_number":"Phone","event_time":"Event","source_ip":"LocalIP"}
    for kind in ("IPDR","TOWER_IPDR"):
        approve_format_profile(p,evidence_type=kind,field_mapping=fields,approved_by="tester",
           time_format="%Y-%m-%d %H:%M:%S",timezone_name="Asia/Kolkata",profile_dir=tmp_path/"profiles")
    result=load_universal_evidence(p,profiles_dir=tmp_path/"profiles",allow_native=False)
    assert result["file_results"][0]["status"]=="rejected"
    assert "Multiple approved profiles" in result["errors"][0]
    result=load_universal_evidence(p,profiles_dir=tmp_path/"profiles",selected_module="IPDR",
       selected_type="IPDR", allow_native=False)
    assert result["file_results"][0]["status"]=="ready"


def test_profile_manual_edit_does_not_gain_trust(tmp_path):
    p=make_csv(tmp_path,"report.csv","Agent,Peer,DateX",["91,92,2026-10-15 10:11:12"])
    approved=approve_format_profile(p,evidence_type="CDR",field_mapping={"a_party":"Agent","b_party":"Peer","event_time":"DateX"},
       approved_by="tester",time_format="%Y-%m-%d %H:%M:%S",timezone_name="Asia/Kolkata",profile_dir=tmp_path/"profiles")
    path=list((tmp_path/"profiles").glob("format_*.json"))[0]
    data=json.loads(path.read_text())
    data["field_mapping"]["source_ip"]="NONEXISTENT"
    path.write_text(json.dumps(data))
    imported=load_universal_evidence(p,profiles_dir=tmp_path/"profiles",allow_native=False)
    assert imported["file_results"][0]["status"]=="rejected"


def test_descriptive_summary_rejects_unapproved(tmp_path):
    from modules.loader.universal_bridge import descriptive_module_summary
    p=make_csv(tmp_path,"report.csv","A Party,B Party,Call Date",["91,92,15/10/2026"])
    r=load_universal_evidence(p,allow_native=False)
    with pytest.raises(EvidenceReviewRequired):
        descriptive_module_summary(r["file_results"],"CDR")


def test_forensic_descriptive_count_approved_only(tmp_path):
    from modules.loader.universal_bridge import descriptive_module_summary
    p=make_csv(tmp_path,"report.csv","Device,Phone,Extra",["012345678901234,9111100000,a","012345678901234,9222200000,b"])
    approve_format_profile(p,evidence_type="IMEI_INVENTORY",field_mapping={"imei":"Device","subscriber_number":"Phone"},
        approved_by="test",profile_dir=tmp_path/"profiles")
    result=load_universal_evidence(p,profiles_dir=tmp_path/"profiles",allow_native=False)
    items=require_analysis_ready(result,"IMEI")
    summary=descriptive_module_summary(items,"IMEI")
    assert summary["rows"]==2
    assert summary["unique_counts"]["imei"]==1
    assert summary["unique_counts"]["subscriber_number"]==2
    assert summary["analysis_level"]=="DESCRIPTIVE_ONLY"

def test_all_rows_invalid_never_analysis_ready(tmp_path):
    p=make_csv(tmp_path,"bad.csv","Phone,Time,LocalIP",["9111100000,not-a-date,10.0.0.1"])
    approve_format_profile(p,evidence_type="IPDR",field_mapping={"subscriber_number":"Phone","event_time":"Time","source_ip":"LocalIP"},
        approved_by="tester",time_format="%Y-%m-%d %H:%M:%S",timezone_name="Asia/Kolkata",profile_dir=tmp_path/"profiles")
    result=load_universal_evidence(p,profiles_dir=tmp_path/"profiles",allow_native=False)
    assert result["file_results"][0]["status"]=="rejected"
    with pytest.raises(EvidenceReviewRequired):require_analysis_ready(result,"IPDR")
