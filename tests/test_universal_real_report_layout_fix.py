"""Forensic-safe routing regressions; synthetic data only (no subscriber PII)."""

from __future__ import annotations

import pytest

from modules.loader.universal_evidence import inspect_universal_evidence, load_universal_evidence
from modules.loader.universal_bridge import EvidenceReviewRequired, require_analysis_ready
from modules.loader.tower_evidence_router import classify_tower_evidence


AIRTEL_TOWER = (
    "BHARTI AIRTEL LIMITED\n\nBIHAR JHARKHAND\n\n"
    "Call Details of CELL ID '405-52-340-46345' from '15-Jul-2026 00:00:00' to '21-Jul-2026 23:59:59'\n\n"
    "Target No,Call Type,TOC,B Party No,Date,Time,Dur(s),First CGI,Last CGI,IMEI,IMSI,Service Type\n"
    "'911100000000',OUT,Pre,'922200000000','15/07/2026',00:01:55,251,405-52-340-46345,405-52-340-46345,'123456789012345','405856123456789',Voice\n"
)


def test_airtel_tower_cdr_preamble_takes_precedence(tmp_path):
    p = tmp_path / "unrelated_name.csv"
    p.write_text(AIRTEL_TOWER, encoding="utf-8")
    info = inspect_universal_evidence(p)
    assert (info["suggested_module"],info["suggested_type"]) == ("TOWER_DUMP","TOWER_CDR")
    assert info["operator"] == "Airtel"
    assert classify_tower_evidence(p) == ("TOWER_CDR", "Airtel")


def test_plain_cdr_with_cell_fields_stays_cdr(tmp_path):
    p=tmp_path/"cdr.csv"
    p.write_text("Target No,B Party No,Date,Time,First CGI,IMEI\n91,92,15/07/2026,12:00:01,405,123456789012345\n")
    info=inspect_universal_evidence(p)
    assert info["suggested_type"]=="CDR"


@pytest.mark.parametrize("preamble,header,mod,typ,operator", [
    ("BHARTI AIRTEL LTD\nDynamic IPDR OF IMEI : 123456789012345 from 05-Oct-2025 00:00:00 to 11-Oct-2025 23:59:59",
     "MSISDN_userID,IMEI,IMSI,Session_Start_Time,Source_Public_IPv6,Destination_Port",
     "IMEI","IMEI_IPDR","Airtel"),
    ("VIL Call Data Records\nIMEI:-123456789012345\nReport Type:-DOT Report",
     "IMEI,MSISDN,Source IP,Source Port,Destination IP,Destination Port",
     "IMEI","IMEI_IPDR","Vi"),
    ("IMEI : - 123456789012345\nReport Type :- GPRS Report",
     "Target /A PARTY NUMBER,IMEI,IMSI,Call date,Call Initiation Time,First Cell Global Id",
     "IMEI","IMEI_GPRS","Unknown"),
])
def test_explicit_imei_scope_prioritized(tmp_path,preamble,header,mod,typ,operator):
    path=tmp_path/"request.csv"
    path.write_text(preamble+"\n"+header+"\n"+"a,b,c,d,e,f\n",encoding="utf-8")
    info=inspect_universal_evidence(path)
    assert (info["suggested_module"], info["suggested_type"]) == (mod,typ)
    assert info["operator"] == operator


@pytest.mark.parametrize("text, expected_reason",[
    ("Ticket Number :,LEA00001\nTotal Records :,0\n\nCalling Party Telephone Number,Called Party Telephone Number,Call Date,Call Time,Call Duration,First Cell ID,IMEI\nDisclaimer: System generated\n", "explicit_no_records"),
    ("VIL Call Data Records\nIMEI:-123456789012345\nReport Type:-DOT Report\n\nIMEI,IMSI,MSISDN,Source IP,Source Port,Destination IP,Destination Port\nNote :- This is a system generated report\n", "header_only_unconfirmed"),
    ("IMEI : - 123456789012345\nReport Type :- GPRS Report\nNote : No records found for the request\n\nTarget /A PARTY NUMBER,IMEI,IMSI,Call date,Call Initiation Time,First Cell Global Id\n----\n", "explicit_no_records"),
])
def test_no_records_are_never_analysis_ready(tmp_path,text,expected_reason):
    p=tmp_path/"data.csv"
    p.write_text(text,encoding="utf-8")
    result=load_universal_evidence(p,allow_native=False)
    item=result["file_results"][0]
    assert item["status"] == "no_data", item["errors"]
    assert item["no_data_reason"] == expected_reason
    assert not item["ok"]
    assert item["df"].empty
    assert not item["errors"]
    with pytest.raises(EvidenceReviewRequired):
        require_analysis_ready(result,item["module"] if item["module"]!="UNKNOWN" else "CDR")


def test_no_record_marker_with_real_rows_is_not_no_data(tmp_path):
    p=tmp_path/"real.csv"
    p.write_text("No records found in last query\n"+AIRTEL_TOWER)
    r=load_universal_evidence(p,allow_native=False)
    assert r["file_results"][0]["status"]!="no_data"


def test_unknown_header_only_is_not_magically_approved(tmp_path):
    p=tmp_path/"unknown.csv"
    p.write_text("Alpha,Beta,Gamma\n",encoding="utf-8")
    r=load_universal_evidence(p,allow_native=False)
    assert r["file_results"][0]["status"] != "native_validated"
    assert not r["ok"]
