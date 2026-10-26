"""Ensure subscriber CDR cannot accidentally enter Tower Dump analysis."""
from pathlib import Path
import os

import pytest
import pandas as pd

from modules.loader.tower_evidence_router import classify_tower_evidence
from modules.loader.universal_evidence import inspect_universal_evidence, load_universal_evidence
from modules.loader.universal_native import try_native_import

HEADER = ("Calling Party Telephone Number,Called Party Telephone Number,Call Date,Call Time,"
          "Call Duration,First Cell ID,Last Cell ID,Call Type,IMEI,IMSI")


def _jio_report(tmp_path: Path, query: str, first_cells: list[str]) -> Path:
    path = tmp_path / "cdr1.csv"  # filename is not a classification signal
    data = ["Ticket Number :,LEA001",
            f"Input Value (MSISDN/B PARTY/IMEI/IMSI/CELL ID) :,'{query}'",
            "Total Records :,3", "", "", HEADER]
    for cell in first_cells:
        data.append(f"'919999999999','918888888888',15/10/2026,06:00:05,13,'{cell}','{cell}',a_out,123456789012345,405856123456789")
    path.write_text("\n".join(data) + "\n", encoding="utf-8")
    return path


def test_jio_subscriber_cdr_remains_normal_cdr(tmp_path):
    path = _jio_report(tmp_path, "919999999999", ["4058560CC360010"] * 3)
    assert classify_tower_evidence(path)[0] == "UNRECOGNIZED"
    info = inspect_universal_evidence(path)
    assert info["suggested_module"] == "CDR", info
    assert info["suggested_type"] == "CDR"


def test_jio_cell_target_report_stays_tower_dump(tmp_path):
    path = _jio_report(tmp_path, "4058560CC360010", ["4058560CC360010"] * 3)
    assert classify_tower_evidence(path)[0] == "TOWER_CDR"
    info = inspect_universal_evidence(path)
    assert info["suggested_module"] == "TOWER_DUMP", info
    assert info["suggested_type"] == "TOWER_CDR"


def test_jio_cdr_without_cell_match_is_not_tower_even_with_ticket(tmp_path):
    path = _jio_report(tmp_path, "999999999999", ["4058560CC360010"] * 3)
    assert classify_tower_evidence(path)[0] == "UNRECOGNIZED"
    assert inspect_universal_evidence(path)["suggested_module"] == "CDR"


def test_legacy_normal_cdr_without_ok_flag_is_accepted(monkeypatch, tmp_path):
    path = _jio_report(tmp_path, "919999999999", ["4058560CC360010"] * 3)
    import modules.loader.multi_loader as multi
    monkeypatch.setattr(multi, "load_one_cdr_file", lambda *_: {
        "file":path.name, "target":"919999999999", "df":pd.DataFrame({"a_party":["919999999999"],"b_party":["918888888888"]})})
    native = try_native_import(path, inspect_universal_evidence(path))
    assert native and native["ok"] and native["module"] == "CDR"
    result = load_universal_evidence(path)
    assert result["ok"]
    assert result["file_results"][0]["module"] == "CDR"
    assert result["file_results"][0]["status"] == "native_validated"


def test_real_jio_vvm_tower_sample():
    supplied = os.environ.get("ETHICALARMOR_JIO_VVM_SAMPLE", "")
    if not supplied:
        pytest.skip("Set ETHICALARMOR_JIO_VVM_SAMPLE to test a real Jio Tower CDR")
    path = Path(supplied)
    if not path.is_file():
        pytest.skip("Optional Jio VVM sample not present")
    assert classify_tower_evidence(path)[0] == "TOWER_CDR"
    assert inspect_universal_evidence(path)["suggested_module"] == "TOWER_DUMP"


def test_vi_cdr_report_requires_explicit_cell_query(tmp_path):
    p = tmp_path / "generic_vi.csv"
    p.write_text("Vodafone Idea Call Data Records\nReport Type :- Main CDR Report\n"
                 "Target /A PARTY NUMBER,Other /B PARTY NUMBER,Call date,First Cell Global Id\n"
                 "919999999999,918888888888,09-03-2024,4057014039435282\n")
    assert classify_tower_evidence(p)[0] == "UNRECOGNIZED"
    assert inspect_universal_evidence(p)["suggested_module"] == "CDR"
