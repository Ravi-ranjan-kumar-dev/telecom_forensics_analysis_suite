"""Safe end-to-end preflight tests: known formats vs unknown, no raw PII output."""
from pathlib import Path

import pytest

from modules.loader.universal_workspace import run_universal_preflight


def test_invalid_module_rejected(tmp_path):
    file = tmp_path / "e.csv"
    file.write_text("junk,a,b\n1,2,3\n")
    with pytest.raises(ValueError, match="Unrecognized module"):
        run_universal_preflight(file, module="WRONG")


def test_unknown_schema_is_review_only(tmp_path):
    file = tmp_path / "vendor.csv"
    file.write_text("vendor_key,billing_region,routing_zone,alpha_value\na,b,c,d\n")
    result = run_universal_preflight(file)
    assert not result["ok"]
    assert result["needs_review"]
    assert not result["analysis"]
    assert result["files"][0]["status"] == "needs_review"
    assert "alpha_value" not in str(result)


def test_invalid_file_returns_error_without_raw_values(tmp_path):
    file = tmp_path / "s.csv"
    file.write_text("onlyonecolumn\nsensitive-data-value\n")
    result = run_universal_preflight(file)
    assert not result["ok"]
    assert not result["analysis"]
    assert "sensitive-data-value" not in str(result)


def test_native_cdr_is_classified_as_cdr(tmp_path):
    file = tmp_path / "cdr.csv"
    file.write_text("Calling Party Telephone Number,Called Party Telephone Number,Call Date,Call Time,Call Duration,IMEI\n"
                    "9876543210,9999999999,15/10/2026,08:00:00,35,123456789012345\n")
    result = run_universal_preflight(file)
    assert result["files"][0]["module"] == "CDR"
    assert result["files"][0]["evidence_type"] == "CDR"
    assert "9876543210" not in str(result)


def test_module_selection_conflict_never_routes_to_reports(tmp_path):
    file = tmp_path / "cdr.csv"
    file.write_text("Calling Party Telephone Number,Called Party Telephone Number,Call Date,Call Time,Call Duration\n"
                    "9876543210,9999999999,15/10/2026,08:00:00,35\n")
    result = run_universal_preflight(file, module="IPDR")
    assert not result["ok"]
    assert not result["analysis"]
    assert result["needs_review"]
