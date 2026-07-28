
from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from modules.controllers import (
    imei_device_controller,
)
from modules.loader.gprs_dump_loader import (
    STATUS_EMPTY_NO_DATA as GPRS_EMPTY_NO_DATA,
    load_gprs_dump_file,
)
from modules.loader.imei_evidence_loader import (
    STATUS_EMPTY_NO_DATA,
    STATUS_HAS_DATA,
    STATUS_UNSUPPORTED,
    normalize_imei_gprs_file,
)


AIRTEL_IMEI = "862261072892730"
VIL_IMEI = "862286069717074"
VIL_IMEISV = "8622610728927300"


def _write(
    path: Path,
    content: str,
) -> Path:
    path.write_text(
        content.strip(
            "\n"
        )
        + "\n",
        encoding="utf-8",
    )

    return path


def _airtel_empty(
    path: Path,
    imei: str = AIRTEL_IMEI,
) -> Path:
    return _write(
        path,
        f"""
BHARTI AIRTEL LTD

Pan India

GPRS OF IMEI : {imei} from 01-Feb-2025 00:00:00 to 09-Oct-2025 23:59:59

 Mobile No.,IP Address,IMEI,IMSI,Downlink Vol,Uplink Vol,Total Vol,Session Start Time,Session End Time, Pre/Post,Roaming Circle,2g/4g/5g,ICR Operator Name,Home Circle,IP, CGI Latitude, CGI Longitude, CGI
No Records Found
 This is System generated report, and needs no signature.
""",
    )


def _vil_empty(
    path: Path,
    imei: str = VIL_IMEI,
) -> Path:
    return _write(
        path,
        f"""
Vodafone Idea Call Data Records
IMEI : - {imei}
Report Type :- GPRS Report
Note : No records found for the request
Target /A PARTY NUMBER,Type of Connection,Call date,Call Initiation Time,Call Duration,First BTS Location,First Cell Global Id,Service Type,IMEI,IMSI,MAC ID,IP Address,APN,Data Uplink Volume,Data Downlink Volume,Data Volume,Roaming Network/Circle,PGW IP
Note :- This is a System generated Report.
""",
    )


def _ipdr_empty(
    path: Path,
) -> Path:
    return _write(
        path,
        """
BHARTI AIRTEL LTD

Pan India

Dynamic IPDR OF IMEI : 862286069717070 from 01-Oct-2025 00:00:00 to 12-Oct-2025 23:59:59

MSISDN_userID,IMEI,IMSI,Downlink_Vol,Uplink_Vol,Event_Start_Time,Session_Start_Time,Session_End_Time,Pre_Post,Roaming_Circle,ICR_Operator_Name,Home_Circle,Source_Public_IPv4,Source_Public_IPv6,Source_Public_Port,Destination_IP4,Destination_IP6,Destination_Port,Source_Private_IPV4,Source_Handset_Port,Duration,Charging_ID,Access_Point_Name,PACO_GW_IP,2g/4g/5g,CGI Latitude,CGI Longitude,CGI
No Records Found
""",
    )


def test_resolve_imei_gprs_folder_is_canonical():
    folder = (
        imei_device_controller
        .resolve_imei_gprs_input_folder(
            "CASE-001"
        )
    )

    assert folder.parts[
        -3:
    ] == (
        "device",
        "imei",
        "gprs",
    )


def test_missing_gprs_folder_returns_stable_inventory(
    monkeypatch,
    tmp_path: Path,
):
    missing = (
        tmp_path
        / "missing"
    )

    monkeypatch.setattr(
        imei_device_controller,
        "resolve_imei_gprs_input_folder",
        lambda case_id: missing,
    )

    inventory = (
        imei_device_controller
        ._load_dedicated_imei_gprs_inventory(
            "CASE-001"
        )
    )

    assert inventory[
        "files_found"
    ] == 0

    assert inventory[
        "identifiers"
    ] == []

    assert inventory[
        "device_frames"
    ] == {}

    assert inventory[
        "supported_gprs_content_groups"
    ] == 0

    assert inventory[
        "non_gprs_acquisitions"
    ] == 0


def test_inventory_separates_gprs_and_ipdr(
    monkeypatch,
    tmp_path: Path,
):
    _airtel_empty(
        tmp_path
        / "airtel.csv"
    )

    _vil_empty(
        tmp_path
        / "vil.csv"
    )

    _ipdr_empty(
        tmp_path
        / "ipdr.csv"
    )

    monkeypatch.setattr(
        imei_device_controller,
        "resolve_imei_gprs_input_folder",
        lambda case_id: tmp_path,
    )

    inventory = (
        imei_device_controller
        ._load_dedicated_imei_gprs_inventory(
            "CASE-001"
        )
    )

    assert inventory[
        "files_found"
    ] == 3

    assert inventory[
        "all_content_groups"
    ] == 3

    assert inventory[
        "supported_gprs_content_groups"
    ] == 2

    assert inventory[
        "non_gprs_acquisitions"
    ] == 1

    assert inventory[
        "duplicate_gprs_acquisitions"
    ] == 0

    assert inventory[
        "analytical_records"
    ] == 0

    assert set(
        inventory[
            "identifiers"
        ]
    ) == {
        AIRTEL_IMEI,
        VIL_IMEI,
    }

    assert all(
        frame.empty
        for frame in inventory[
            "device_frames"
        ].values()
    )

    manifest = inventory[
        "acquisition_manifest"
    ]

    assert len(
        manifest
    ) == 3

    assert (
        manifest[
            "Source Type"
        ]
        .value_counts()
        .to_dict()
        == {
            "GPRS": 2,
            "IPDR": 1,
        }
    )


def test_duplicate_gprs_acquisition_is_preserved_once(
    monkeypatch,
    tmp_path: Path,
):
    first = _airtel_empty(
        tmp_path
        / "first.csv"
    )

    shutil.copy2(
        first,
        tmp_path
        / "copy.csv",
    )

    monkeypatch.setattr(
        imei_device_controller,
        "resolve_imei_gprs_input_folder",
        lambda case_id: tmp_path,
    )

    inventory = (
        imei_device_controller
        ._load_dedicated_imei_gprs_inventory(
            "CASE-001"
        )
    )

    assert inventory[
        "files_found"
    ] == 2

    assert inventory[
        "all_content_groups"
    ] == 1

    assert inventory[
        "supported_gprs_content_groups"
    ] == 1

    assert inventory[
        "duplicate_gprs_acquisitions"
    ] == 1

    assert len(
        inventory[
            "acquisition_manifest"
        ]
    ) == 2


def test_airtel_imei_empty_report_uses_canonical_loader(
    tmp_path: Path,
):
    path = _airtel_empty(
        tmp_path
        / "airtel_empty.csv"
    )

    result = load_gprs_dump_file(
        path
    )

    assert result[
        "ok"
    ] is True

    assert result[
        "has_records"
    ] is False

    assert result[
        "data_status"
    ] == GPRS_EMPTY_NO_DATA

    assert result[
        "df"
    ].empty


def test_normalize_empty_vil_imei_gprs(
    tmp_path: Path,
):
    result = normalize_imei_gprs_file(
        _vil_empty(
            tmp_path
            / "vil_empty.csv"
        )
    )

    assert result[
        "ok"
    ] is True

    assert result[
        "status"
    ] == STATUS_EMPTY_NO_DATA

    assert result[
        "records_normalized"
    ] == 0

    assert result[
        "data"
    ].empty


def test_normalize_airtel_data_row_preserves_query_and_observed(
    tmp_path: Path,
):
    path = _write(
        tmp_path
        / "airtel_data.csv",
        f"""
BHARTI AIRTEL LTD

Pan India

GPRS OF IMEI : {AIRTEL_IMEI} from 01-Feb-2025 00:00:00 to 09-Oct-2025 23:59:59

 Mobile No.,IP Address,IMEI,IMSI,Downlink Vol,Uplink Vol,Total Vol,Session Start Time,Session End Time, Pre/Post,Roaming Circle,2g/4g/5g,ICR Operator Name,Home Circle,IP, CGI Latitude, CGI Longitude, CGI
919876543210,10.0.0.5,{AIRTEL_IMEI}0,405523214527244,100,50,150,01-Feb-2025 01:02:03,01-Feb-2025 01:03:03,PREPAID,Bihar,4G,,Bihar,2401:4900::1,25.1,85.1,405-52-2325-12554386743
""",
    )

    result = normalize_imei_gprs_file(
        path
    )

    assert result[
        "ok"
    ] is True

    assert result[
        "status"
    ] == STATUS_HAS_DATA

    assert result[
        "records_normalized"
    ] == 1

    row = result[
        "data"
    ].iloc[
        0
    ]

    assert row[
        "query_identifier_normalized"
    ] == AIRTEL_IMEI

    assert row[
        "observed_imei_normalized"
    ] == (
        AIRTEL_IMEI
        + "0"
    )

    assert row[
        "match_relation"
    ] == "SAME_BASE14"


def test_normalize_vil_data_row(
    tmp_path: Path,
):
    path = _write(
        tmp_path
        / "vil_data.csv",
        f"""
Vodafone Idea Call Data Records
IMEI : - {AIRTEL_IMEI}
Report Type :- GPRS Report
Target /A PARTY NUMBER,Type of Connection,Call date,Call Initiation Time,Call Duration,First BTS Location,First Cell Global Id,Service Type,IMEI,IMSI,MAC ID,IP Address,APN,Data Uplink Volume,Data Downlink Volume,Data Volume,Roaming Network/Circle,PGW IP
09876543210,PREPAID,01-06-2026,08:01:13,60,Tower A,4057040552421,4G,{VIL_IMEISV},405752741941459,-,10.0.0.7,airtelgprs.com,50,100,150,Bihar,10.1.1.1
""",
    )

    result = normalize_imei_gprs_file(
        path
    )

    assert result[
        "ok"
    ] is True

    assert result[
        "status"
    ] == STATUS_HAS_DATA

    assert result[
        "records_normalized"
    ] == 1

    row = result[
        "data"
    ].iloc[
        0
    ]

    assert row[
        "query_identifier_normalized"
    ] == AIRTEL_IMEI

    assert row[
        "observed_imei_normalized"
    ] == VIL_IMEISV

    assert row[
        "match_relation"
    ] == "SAME_BASE14"

    assert int(
        row[
            "session_duration_seconds"
        ]
    ) == 60


def test_non_gprs_report_is_rejected(
    tmp_path: Path,
):
    result = normalize_imei_gprs_file(
        _ipdr_empty(
            tmp_path
            / "ipdr.csv"
        )
    )

    assert result[
        "ok"
    ] is False

    assert result[
        "status"
    ] == STATUS_UNSUPPORTED

    assert result[
        "data"
    ].empty
