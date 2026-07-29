from __future__ import annotations

import pandas as pd

from modules.database.master_importer import (
    _has_known_master_columns,
    _prepare_cgi_dataframe,
)


def _sample_jammu_cgi_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "S.no.": "1",
                "sitename": "17 Mile, Vijaypur_NBSNL",
                "cell name(SITENAME_SECTORNO)": (
                    "17 Mile, Vijaypur_NBSNL_1"
                ),
                "azimuth": "125",
                "CGI FORMAT": "404-62-3105-8471",
                "cid": "8471",
                "lac": "3105",
                "latitude": "32.57657",
                "longitude": "74.99191",
                "VENDOR": "ERICSSON",
                "Site ID(Additional)": "VIJ17M",
                "SSA(Additional)": "Jammu",
                "Address": (
                    "Bodh Raj Sharma R/o Near factory, "
                    "17 miles vijaypur"
                ),
            }
        ]
    )


def test_cgi_format_header_is_recognized():
    dataframe = pd.DataFrame(
        columns=[
            "CGI FORMAT",
            "sitename",
        ]
    )

    assert _has_known_master_columns(
        dataframe
    ) is True


def test_cgi_format_row_is_prepared():
    prepared = _prepare_cgi_dataframe(
        _sample_jammu_cgi_dataframe(),
        "Cell ID Chart JK Dec. 2024.xlsx",
    )

    selected = prepared.loc[
        prepared["cgi"].eq(
            "404-62-3105-8471"
        )
    ]

    assert len(selected) == 1

    row = selected.iloc[0]

    assert row["site_name"] == (
        "17 Mile, Vijaypur_NBSNL"
    )
    assert row["site_id"] == "VIJ17M"
    assert row["lac"] == "3105"
    assert row["cid"] == "8471"
    assert row["azimuth"] == "125"
    assert row["latitude"] == 32.57657
    assert row["longitude"] == 74.99191
    assert row["operator"] == ""

    assert row["address"] == (
        "Bodh Raj Sharma R/o Near factory, "
        "17 miles vijaypur"
    )



def test_normal_multisheet_cgi_workbook_is_read(
    tmp_path,
):
    from modules.database.master_importer import (
        read_cgi_master_file,
    )

    workbook_path = (
        tmp_path
        / "normal_multisheet_cgi.xlsx"
    )

    two_g = pd.DataFrame(
        [
            {
                "sitename": "Test 2G Site",
                "CGI FORMAT": "404-62-3105-8471",
                "cid": "8471",
                "lac": "3105",
                "latitude": "32.57657",
                "longitude": "74.99191",
                "Site ID(Additional)": "TEST2G",
                "Address": "Test 2G address",
            }
        ]
    )

    three_g = pd.DataFrame(
        [
            {
                "Site Name": "Test 3G Site",
                "CGI FORMAT": "404-62-3105-8472",
                "cid": "8472",
                "lac": "3105",
                "latitude": "32.57658",
                "longitude": "74.99192",
                "Site ID (Additional)": "TEST3G",
                "Site Address(Additional)": (
                    "Test 3G address"
                ),
            }
        ]
    )

    four_g = pd.DataFrame(
        [
            {
                "SiteName": "Test 4G Site",
                "IPDR FORMAT": "404-62-3106-8473",
                "ci": "8473",
                "TAC": "3106",
                "Latitude": "32.57659",
                "Longitude": "74.99193",
                "Site Address(Additional)": (
                    "Test 4G address"
                ),
            }
        ]
    )

    notes = pd.DataFrame(
        {
            "Notes": [
                "This sheet contains no CGI records.",
            ]
        }
    )

    with pd.ExcelWriter(
        workbook_path
    ) as writer:
        two_g.to_excel(
            writer,
            sheet_name="2G",
            index=False,
        )

        three_g.to_excel(
            writer,
            sheet_name="3G",
            index=False,
        )

        four_g.to_excel(
            writer,
            sheet_name="4G",
            index=False,
        )

        notes.to_excel(
            writer,
            sheet_name="Notes",
            index=False,
        )

    frames = read_cgi_master_file(
        workbook_path
    )

    assert len(frames) == 3

    combined = pd.concat(
        frames,
        ignore_index=True,
    )

    assert set(
        combined["cgi"].tolist()
    ) == {
        "404-62-3105-8471",
        "404-62-3105-8472",
        "404-62-3106-8473",
    }

    assert set(
        combined["source_file"].tolist()
    ) == {
        "normal_multisheet_cgi.xlsx:2G",
        "normal_multisheet_cgi.xlsx:3G",
        "normal_multisheet_cgi.xlsx:4G",
    }



def test_cgi_dec_normal_multisheet_workbook(
    tmp_path,
):
    from modules.database.master_importer import (
        read_cgi_master_file,
    )

    workbook_path = (
        tmp_path
        / "cgi_dec_workbook.xlsx"
    )

    dataframe = pd.DataFrame(
        [
            {
                "Circle Name": "UPE",
                "BTS Name": "Test BTS",
                "BTS id / Cell_id": "TEST-BTS-1",
                "MCC": "404",
                "MNC": "55",
                "LAC": "3105",
                "Cell id": "8471",
                "CGI_DEC": "404-55-3105-8471",
                "CGI_HEX": "04f4370C212117",
                "lat_pd": "26.84670",
                "long_pd": "80.94620",
                "Site Address": "Test site address",
                "Vendor": "ERICSSON",
                "Technology": "2G",
                "Enodeb id": "TEST-ENB",
                "CI": "8471",
            }
        ]
    )

    with pd.ExcelWriter(
        workbook_path
    ) as writer:
        dataframe.to_excel(
            writer,
            sheet_name="2G3G",
            index=False,
        )

    frames = read_cgi_master_file(
        workbook_path
    )

    assert len(frames) == 1

    prepared = pd.concat(
        frames,
        ignore_index=True,
    )

    assert prepared["cgi"].tolist() == [
        "404-55-3105-8471"
    ]

    row = prepared.iloc[0]

    assert row["cgi"] != "8471"
    assert row["site_name"] == "Test BTS"
    assert row["circle"] == "UPE"
    assert row["latitude"] == 26.84670
    assert row["longitude"] == 80.94620
    assert row["address"] == "Test site address"
    assert row["site_id"] == "TEST-ENB"
