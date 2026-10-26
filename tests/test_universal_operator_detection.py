"""Regression for CDR operator provenance and non-misrouting of subscriber records."""
from pathlib import Path

import pandas as pd
import pytest

from modules.loader.universal_evidence import inspect_universal_evidence, load_universal_evidence
from modules.loader.universal_bridge import module_preview
from modules.loader.universal_operator import canonical_operator


NORMAL_CDR_HEADER = ("Calling Party Telephone Number,Called Party Telephone Number,Call Date,Call Time,"
                     "Call Duration,First Cell ID,Last Cell ID,IMEI,IMSI")
NORMAL_CDR_RECORD = ("919999999999,918888888888,15/10/2026,06:00:05,13,"
                     "4058560CC360010,4058560CC360010,123456789012345,405856123456789")


def cdr(tmp_path, *preamble, include_operator_column=False):
    p=tmp_path/"cdr1.csv"
    header=NORMAL_CDR_HEADER + (",Operator" if include_operator_column else "")
    record=NORMAL_CDR_RECORD + (",Jio" if include_operator_column else "")
    p.write_text("\n".join([*preamble, header,record,record]) + "\n", encoding="utf-8")
    return p


def test_normal_cdr_jio_template_keeps_cdr_module(tmp_path):
    path=cdr(tmp_path,"Ticket Number :,LEA00001",
             "Input Value (MSISDN/B PARTY/IMEI/IMSI/CELL ID) :,'919999999999'")
    item=inspect_universal_evidence(path)
    assert item["suggested_module"]=="CDR"
    assert item["suggested_type"]=="CDR"
    assert item["operator"]=="Jio"
    assert item["operator_source"]=="jio_report_template"
    assert item["operator_confidence"]=="provisional"
    assert any("provisional" in w.lower() for w in item["warnings"])


def test_unknown_operator_cdr_not_guessed_from_imsi_and_cell_id(tmp_path):
    item=inspect_universal_evidence(cdr(tmp_path))
    assert item["suggested_module"]=="CDR"
    assert item["operator"]=="Unknown"
    assert item["operator_source"]=="none"


@pytest.mark.parametrize("label, expected",[
    ("Jio Infocomm Limited","Jio"),
    ("Bharti Airtel Limited","Airtel"),
    ("Vodafone Idea","Vi"),
    ("BSNL","BSNL"),
    ("MTNL","MTNL"),
])
def test_explicit_operator_metadata(tmp_path,label,expected):
    item=inspect_universal_evidence(cdr(tmp_path,f"Operator : {label}"))
    assert item["operator"]==expected
    assert item["operator_source"]=="declared_operator_metadata"
    assert item["operator_confidence"]=="reported"


def test_operator_column_detected(tmp_path):
    item=inspect_universal_evidence(cdr(tmp_path,include_operator_column=True))
    assert item["operator"]=="Jio"
    assert item["operator_source"]=="record_operator_column"


def test_multiple_operator_column_values_need_review(tmp_path):
    p=cdr(tmp_path, include_operator_column=True)
    p.write_text(p.read_text().replace(',Jio\n', ',Airtel\n', 1))
    item=inspect_universal_evidence(p)
    assert item["operator"]=="Unknown"
    assert item["operator_source"]=="conflicting_record_operator_values"


def test_issuer_branding_detected_in_preamble_not_roaming_cell(tmp_path):
    item=inspect_universal_evidence(cdr(tmp_path,"Bharti Airtel Limited - Call Detail Records"))
    assert item["operator"]=="Airtel"
    assert item["operator_source"]=="source_issuer_banner"


def test_native_unknown_does_not_clobber_detected_operator(monkeypatch,tmp_path):
    p=cdr(tmp_path,"Operator : Vi")
    def fake(path,info):
        return {"ok":True,"module":"CDR","evidence_type":"CDR", "operator":"Unknown",
                "df":pd.DataFrame({"a_party":["919999999999"]}), "metadata":{}}
    import modules.loader.universal_native as native
    monkeypatch.setattr(native,"try_native_import",fake)
    loaded=load_universal_evidence(p)
    item=loaded["file_results"][0]
    assert item["status"]=="native_validated"
    assert item["operator"]=="Vi"
    assert item["operator_source"]=="declared_operator_metadata"
    assert module_preview(loaded)[0]["operator_confidence"]=="reported"


def test_analyst_selected_operator_with_unknown_source(monkeypatch,tmp_path):
    p=cdr(tmp_path)
    def fake(path,info):
        return {"ok":True,"module":"CDR","evidence_type":"CDR", "operator":"Unknown",
                "df":pd.DataFrame({"a_party":["919999999999"]}), "metadata":{}}
    import modules.loader.universal_native as native
    monkeypatch.setattr(native,"try_native_import",fake)
    loaded=load_universal_evidence(p,selected_module="CDR",selected_operator="Airtel")
    assert loaded["ok"]
    item=loaded["file_results"][0]
    assert item["operator"]=="Airtel"
    assert item["operator_source"]=="analyst_selected"
    assert item["operator_confidence"]=="manually_asserted"


def test_wrong_override_conflicts_with_report_metadata(monkeypatch,tmp_path):
    p=cdr(tmp_path,"Operator : Vi")
    def fake(path,info):
        return {"ok":True,"module":"CDR","evidence_type":"CDR", "operator":"Unknown",
                "df":pd.DataFrame({"a_party":["919999999999"]}), "metadata":{}}
    import modules.loader.universal_native as native
    monkeypatch.setattr(native,"try_native_import",fake)
    loaded=load_universal_evidence(p,selected_operator="Jio")
    assert not loaded["ok"]
    assert loaded["file_results"][0]["status"]=="needs_review"
    assert loaded["file_results"][0]["df"].empty


def test_canonical_operator_does_not_guess_mobile_number():
    assert canonical_operator("919999999999")=="Unknown"
    assert canonical_operator("405856") == "Unknown"
    assert canonical_operator("vodafone idea") == "Vi"


def test_conflicting_native_and_declared_operators_are_blocked(monkeypatch,tmp_path):
    p=cdr(tmp_path,"Operator : Vi")
    def fake(path,info):
        return {"ok":True,"module":"CDR","evidence_type":"CDR", "operator":"Jio",
                "df":pd.DataFrame({"a_party":["919999999999"]}), "metadata":{}}
    import modules.loader.universal_native as native
    monkeypatch.setattr(native,"try_native_import",fake)
    result=load_universal_evidence(p)
    item=result["file_results"][0]
    assert not result["ok"]
    assert item["status"]=="needs_review"
    assert item["operator"]=="Vi"
    assert any("conflicts" in w for w in item["warnings"])


def test_multiple_operator_names_not_silently_assigned():
    assert canonical_operator("Airtel / Jio") == "Unknown"
    assert canonical_operator("BSNL/MTNL") == "Unknown"
