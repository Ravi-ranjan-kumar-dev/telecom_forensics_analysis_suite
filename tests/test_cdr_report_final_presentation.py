from __future__ import annotations

import pandas as pd
from openpyxl import Workbook

from modules.analysis.cdr import contact_report
from modules.reporting import cdr_compact_excel


def test_full_contact_presentation_adds_sdr_and_cgi_fields(
    monkeypatch,
):
    monkeypatch.setattr(
        contact_report,
        "_build_full_contact_summary_base_final",
        lambda data, summary: summary.copy(),
    )

    import modules.enrichment.sdr_subscriber_enrichment as sdr_module

    monkeypatch.setattr(
        sdr_module,
        "lookup_sdr_subscribers",
        lambda values: pd.DataFrame(
            [
                {
                    "lookup_mobile": "8000000001",
                    "subscriber_name": "Test Person",
                    "father_name": "Test Father",
                    "subscriber_address": "Test SDR Address",
                    "operator": "AIRTEL",
                    "circle": "Bihar",
                    "sdr_found": "Yes",
                }
            ]
        ),
    )

    monkeypatch.setattr(
        contact_report,
        "lookup_cgi_addresses",
        lambda values: pd.DataFrame(
            [
                {
                    "cgi": "404-55-113-12101",
                    "site_name": "Test Site",
                    "address": "Test Tower Address",
                    "latitude": 25.61,
                    "longitude": 85.14,
                }
            ]
        ),
    )

    summary = pd.DataFrame(
        [
            {
                "Other Party": "8000000001",
                "Total Calls": 1,
                "Most Used Target CGI": "404-55-113-12101",
                "Last Interaction CGI": "404-55-113-12101",
            }
        ]
    )

    result = contact_report.build_full_contact_summary(
        pd.DataFrame(),
        summary,
    )
    row = result.iloc[0]

    assert row["Name"] == "Test Person"
    assert row["Father Name"] == "Test Father"
    assert row["SDR Address"] == "Test SDR Address"
    assert row["SDR Lookup Status"] == "FOUND"
    assert row["Most Used Site Name"] == "Test Site"
    assert row["Most Used Tower Address"] == (
        "Test Tower Address"
    )
    assert float(row["Most Used Latitude"]) == 25.61
    assert float(row["Most Used Longitude"]) == 85.14
    assert row["Most Used CGI Lookup Status"] == "FOUND"


def test_full_contact_profile_keeps_requested_fields():
    columns = (
        cdr_compact_excel
        .SECTION_COLUMN_PROFILES[
            "FULL CONTACT SUMMARY (CC SUMMARY)"
        ]
    )

    required = {
        "Name",
        "Father Name",
        "SDR Address",
        "SDR Operator",
        "SDR Circle",
        "SDR Lookup Status",
        "Most Used CGI Lookup Status",
        "Most Used Tower Address",
        "Most Used Latitude",
        "Most Used Longitude",
        "Last Interaction CGI Lookup Status",
        "Last Interaction Tower Address",
    }

    assert required.issubset(
        set(columns)
    )


def test_finish_sheet_preserves_identifiers_as_text():
    workbook = Workbook()
    worksheet = workbook.active

    worksheet.append(
        [
            "Device Key",
            "IMEI",
            "Total Events",
        ]
    )
    worksheet.append(
        [
            35338312681475,
            353383126814750,
            1775,
        ]
    )
    worksheet.append(
        [
            None,
            None,
            None,
        ]
    )

    cdr_compact_excel._finish_sheet(
        worksheet
    )

    assert worksheet["A2"].value == "35338312681475"
    assert worksheet["B2"].value == "353383126814750"
    assert worksheet["A2"].number_format == "@"
    assert worksheet["B2"].number_format == "@"
    assert worksheet["C2"].value == 1775

# BEGIN FULL CONTACT COLUMN PRESERVATION TEST
def test_full_contact_blank_profile_columns_are_preserved():
    frame = pd.DataFrame(
        {
            "Other Party": [
                "8000000001",
            ],
        }
    )
    selected_columns = (
        cdr_compact_excel
        .SECTION_COLUMN_PROFILES[
            "FULL CONTACT SUMMARY (CC SUMMARY)"
        ]
    )

    result = (
        cdr_compact_excel
        ._ensure_full_contact_profile_columns(
            frame,
            "FULL CONTACT SUMMARY (CC SUMMARY)",
            selected_columns,
        )
    )

    required = {
        "SDR Circle",
        "Most Used Site Name",
        "Last Interaction Site Name",
    }

    assert required.issubset(
        result.columns
    )
    assert pd.isna(
        result.iloc[
            0
        ][
            "SDR Circle"
        ]
    )
# END FULL CONTACT COLUMN PRESERVATION TEST
