from __future__ import annotations

from pathlib import Path

from modules.loader.imei_evidence_loader import (
    FORMAT_AIRTEL_DYNAMIC_IMEI_IPDR,
    FORMAT_AIRTEL_IMEI_GPRS,
    FORMAT_GENERIC_IMEI_IPDR,
    FORMAT_JIO_IMEI_CDR,
    FORMAT_SEARCH_CRITERIA_IMEI_CDR,
    FORMAT_VIL_IMEI_CDR,
    FORMAT_VIL_IMEI_DOT,
    FORMAT_VIL_IMEI_GPRS,
    STATUS_EMPTY_NO_DATA,
    STATUS_HAS_DATA,
    STATUS_UNSUPPORTED,
    classify_match_relation,
    inspect_imei_evidence_file,
    IMEI_CDR_CANONICAL_COLUMNS,
    normalize_imei_cdr_file,
    inspect_imei_evidence_folder,
)


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


def test_match_relation_contract():
    assert classify_match_relation(
        "123456789012345",
        "123456789012345",
    ) == "EXACT"

    assert classify_match_relation(
        "12345678901234",
        "123456789012345",
    ) == "BASE14_MATCH"

    assert classify_match_relation(
        "123456789012345",
        "1234567890123400",
    ) == "SAME_BASE14"

    assert classify_match_relation(
        "123456789012345",
        "999999999999999",
    ) == "REPORT_SCOPE"


def test_vil_imei_cdr_detection(
    tmp_path: Path,
):
    path = _write(
        tmp_path / "vil_voice.csv",
        """
Vodafone Idea Call Data Records
IMEI : - 866284043482077
Report Type :- Main CDR Report
Target /A PARTY NUMBER,CALL_TYPE,Type of Connection,B PARTY NUMBER,LRN- B Party Number,Translation of LRN,Call date,Call Initiation Time,Call Duration,First BTS Location,First Cell Global Id,Last BTS Location,Last Cell Global Id,SMS Centre Number,Service Type,IMEI,IMSI,Call Forwarding Number,Roaming Network/Circle,MSC ID,In TG ,Out TG
918600000001,Outgoing,PREPAID,919000000001,3087,Jio,01-06-2026,08:01:39,5,Tower A,405701,Tower A,405701,-,Voice,866284043482070,405752741941459,-,Bihar,MSC,IN,OUT,
""",
    )

    result = inspect_imei_evidence_file(
        path
    )

    assert result[
        "format_id"
    ] == FORMAT_VIL_IMEI_CDR

    assert result[
        "status"
    ] == STATUS_HAS_DATA

    assert result[
        "record_count"
    ] == 1

    assert result[
        "match_relation_counts"
    ] == {
        "SAME_BASE14": 1
    }


def test_search_criteria_cdr_detection(
    tmp_path: Path,
):
    path = _write(
        tmp_path / "search_imei.csv",
        """
Search Criteria : IMEI
Search Value : 866741058018575
Start Date : 202601010000
End Date : 202607170000
Target/A-Party Number,Call Type,Type of Connection,Other/B-party Number,LRN of B-Party Number,Translation of LRN,Call Date,Call Initiation Time,Call Duration,First BTS Location,First Cell Global ID,Last BTS Location,Last Cell Global ID,SMS Centre No.,Service Type,IMEI,IMSI,Original Calling Party,Roaming Network/Circle,Switch/MSC ID,In TG,Out TG
8986000001,IN,,BB-BSNLBH-P,,,28/03/2026,18:16:15,1,Tower A,404-75-1-1,,-,919475580002,SMS,866741058018570,404758180316980,,BSNL - Bihar,MSC,,
*** END OF REPORT ***
CDR COUNT : 1
""",
    )

    result = inspect_imei_evidence_file(
        path
    )

    assert result[
        "format_id"
    ] == FORMAT_SEARCH_CRITERIA_IMEI_CDR

    assert result[
        "operator"
    ] == "BSNL"

    assert result[
        "record_count"
    ] == 1


def test_jio_base14_imei_cdr_detection(
    tmp_path: Path,
):
    path = _write(
        tmp_path / "jio.csv",
        """
Ticket Number :,LEA00000000000000000001
Input Value (MSISDN/B PARTY/IMEI/IMSI/CELL ID) :,'35309885264836'
Total Records :,2
Calling Party Telephone Number,Called Party Telephone Number,Call Forwarding,LRN Called No,Call Date,Call Time,Call Termination Time,Call Duration,First Cell ID,Last Cell ID,Call Type,SMS Center Number,IMEI,IMSI,Roaming Circle Name
'919000000001','919000000002',,,02/06/2026,17:29:23,17:29:23,,'405856001',,A2P_SMSIN,'919475580002','353098852648366','405856140573551',BH
'919000000001','919000000003',,,02/06/2026,17:30:23,17:30:23,,'405856001',,a_out,,'353098852648360','405856140573551',BH
""",
    )

    result = inspect_imei_evidence_file(
        path
    )

    assert result[
        "format_id"
    ] == FORMAT_JIO_IMEI_CDR

    assert result[
        "query_identifier_type"
    ] == "BASE14"

    assert result[
        "record_count"
    ] == 2

    assert result[
        "match_relation_counts"
    ] == {
        "BASE14_MATCH": 2
    }


def test_airtel_dynamic_ipdr_detection(
    tmp_path: Path,
):
    path = _write(
        tmp_path / "imei_862261072892730_1.csv",
        """
BHARTI AIRTEL LTD
Pan India
Dynamic IPDR OF IMEI : 862261072892730 from 05-Oct-2025 00:00:00 to 11-Oct-2025 23:59:59
MSISDN_userID,IMEI,IMSI,Downlink_Vol,Uplink_Vol,Event_Start_Time,Session_Start_Time,Session_End_Time,Pre_Post,Roaming_Circle,ICR_Operator_Name,Home_Circle,Source_Public_IPv4,Source_Public_IPv6,Source_Public_Port,Destination_IP4,Destination_IP6,Destination_Port,Source_Private_IPV4,Source_Handset_Port,Duration,Charging_ID,Access_Point_Name,PACO_GW_IP,2g/4g/5g, CGI Latitude, CGI Longitude, CGI
5754021077243,8622610728927300,405523214527244,10,20,05-Oct-2025 08:14:24,05-Oct-2025 08:14:21,05-Oct-2025 08:15:56,Post,DELHI,,BIHAR-JHAR,,2401:4900::2,44784,,2404:6800::1,443,,44784,95,1019,airtelmeterv6,223.224.146.169,4G,28.65,77.10,404-10-2330-1
""",
    )

    result = inspect_imei_evidence_file(
        path
    )

    assert result[
        "format_id"
    ] == FORMAT_AIRTEL_DYNAMIC_IMEI_IPDR

    assert result[
        "query_identifier_type"
    ] == "IMEI15"

    assert result[
        "record_count"
    ] == 1

    assert result[
        "match_relation_counts"
    ] == {
        "SAME_BASE14": 1
    }


def test_vil_gprs_no_data_is_valid(
    tmp_path: Path,
):
    path = _write(
        tmp_path / "vil_gprs.csv",
        """
Vodafone Idea Call Data Records
IMEI : - 8622610728927300
Report Type :- GPRS Report
Note : No records found for the request
Target /A PARTY NUMBER,Type of Connection,Call date,Call Initiation Time,Call Duration,First BTS Location,First Cell Global Id,Service Type,IMEI,IMSI,MAC ID,IP Address,APN,Data Uplink Volume,Data Downlink Volume,Data Volume,Roaming Network/Circle,PGW IP
Note :- This is a System generated Report.
""",
    )

    result = inspect_imei_evidence_file(
        path
    )

    assert result[
        "format_id"
    ] == FORMAT_VIL_IMEI_GPRS

    assert result[
        "status"
    ] == STATUS_EMPTY_NO_DATA

    assert result[
        "ok"
    ] is True

    assert result[
        "record_count"
    ] == 0


def test_header_only_generic_ipdr_is_valid_no_data(
    tmp_path: Path,
):
    path = _write(
        tmp_path
        / (
            "sample_IMEI_IPDR_86130707817163_"
            "20250901000000_20251002205611.csv"
        ),
        """
Landline/MSISDN/MDN/Leased Circuit ID for Internet Access,Source IP Address,Source Port,Public IP Address,Public IP Port,Destination IP Address,Destination Port,Start Date,Start Time,End Date,End Time,Static/Dynamic IP Address Allocation,User Id,Source MAC-ID Address/Other device Identification number,IMSI,PGW IP address,Access Point Name,CGI ID,TIME1,Roaming Circle Indicator,Roaming Circle,Session Duration,Data Volume Up Link,Data Volume Down Link
""",
    )

    result = inspect_imei_evidence_file(
        path
    )

    assert result[
        "format_id"
    ] == FORMAT_GENERIC_IMEI_IPDR

    assert result[
        "query_identifier_type"
    ] == "BASE14"

    assert result[
        "status"
    ] == STATUS_EMPTY_NO_DATA


def test_vil_dot_no_data_detection(
    tmp_path: Path,
):
    path = _write(
        tmp_path / "vil_dot.csv",
        """
VIL Call Data Records
IMEI:-862261072892735
Report Type:-DOT Report
From Date:-2025-10-05
Till Date:-2025-10-12
SR.NO.,IMSI,IMEI,MSISDN,MAC ID,Source IP,Source Port,Destination IP,Destination Port,Translated IP,Translated Port,First Cell ID-Name/Location,Session Start date & time,Session End date & time,Duration in sec,Data Volume Uplink,Data Volume Downlink,PGW IP address,Charging ID,Access Point Name,PDP Address IPv4,PDP Address IPv6,CGI-ld,RAT,PDP-type,ESIM,IP_TYPE
Note :- This is a System generated Report.
""",
    )

    result = inspect_imei_evidence_file(
        path
    )

    assert result[
        "format_id"
    ] == FORMAT_VIL_IMEI_DOT

    assert result[
        "source_type"
    ] == "IPDR"

    assert result[
        "status"
    ] == STATUS_EMPTY_NO_DATA


def test_unsupported_file_is_not_treated_as_valid(
    tmp_path: Path,
):
    path = _write(
        tmp_path / "ordinary.csv",
        """
name,value
alpha,1
""",
    )

    result = inspect_imei_evidence_file(
        path
    )

    assert result[
        "ok"
    ] is False

    assert result[
        "status"
    ] == STATUS_UNSUPPORTED


def test_folder_inspection_keeps_file_results_separate(
    tmp_path: Path,
):
    _write(
        tmp_path / "vil.csv",
        """
Vodafone Idea Call Data Records
IMEI : - 866284043482077
Report Type :- Main CDR Report
Target /A PARTY NUMBER,CALL_TYPE,IMEI,IMSI,Call date
918600000001,Outgoing,866284043482070,405752741941459,01-06-2026
""",
    )

    _write(
        tmp_path / "unknown.csv",
        """
one,two
1,2
""",
    )

    result = inspect_imei_evidence_folder(
        tmp_path
    )

    assert result[
        "file_count"
    ] == 2

    assert len(
        result[
            "file_results"
        ]
    ) == 2

    assert result[
        "status_counts"
    ][
        STATUS_HAS_DATA
    ] == 1

    assert result[
        "status_counts"
    ][
        STATUS_UNSUPPORTED
    ] == 1

def test_airtel_imei_gprs_no_data_detection(
    tmp_path: Path,
):
    path = _write(
        tmp_path / "imei_862261072892730.csv",
        """
BHARTI AIRTEL LTD

Pan India

GPRS OF IMEI : 862261072892730 from 01-Feb-2025 00:00:00 to 09-Oct-2025 23:59:59

 Mobile No.,IP Address,IMEI,IMSI,Downlink Vol,Uplink Vol,Total Vol,Session Start Time,Session End Time, Pre/Post,Roaming Circle,2g/4g/5g,ICR Operator Name,Home Circle,IP,  CGI Latitude, CGI Longitude, CGI
No Records Found
 This is System generated report, and needs no signature.

 11-Oct-2025 19:18:29
""",
    )

    result = inspect_imei_evidence_file(
        path
    )

    assert result[
        "ok"
    ] is True

    assert result[
        "format_id"
    ] == FORMAT_AIRTEL_IMEI_GPRS

    assert result[
        "operator"
    ] == "Bharti Airtel"

    assert result[
        "source_type"
    ] == "GPRS"

    assert result[
        "query_identifier_normalized"
    ] == "862261072892730"

    assert result[
        "query_identifier_type"
    ] == "IMEI15"

    assert result[
        "status"
    ] == STATUS_EMPTY_NO_DATA

    assert result[
        "record_count"
    ] == 0

def test_normalize_vil_imei_cdr_contract(
    tmp_path: Path,
):
    path = _write(
        tmp_path / "vil_voice.csv",
        """
Vodafone Idea Call Data Records
IMEI : - 866284043482077
Report Type :- Main CDR Report
Target /A PARTY NUMBER,CALL_TYPE,Type of Connection,B PARTY NUMBER,LRN- B Party Number,Translation of LRN,Call date,Call Initiation Time,Call Duration,First BTS Location,First Cell Global Id,Last BTS Location,Last Cell Global Id,SMS Centre Number,Service Type,IMEI,IMSI,Call Forwarding Number,Roaming Network/Circle,MSC ID,In TG ,Out TG
08603111094,Incoming,PREPAID,VD-ViCARE-S,4126,Vodafone,01-06-2026,08:01:13,1,Tower A,4057040552421,Tower A,4057040552421,919830000182,SMS,866284043482070,405752741941459,-,Bihar,MSC,-,-
""",
    )

    result = normalize_imei_cdr_file(
        path
    )

    assert result[
        "ok"
    ] is True

    assert result[
        "records_normalized"
    ] == 1

    dataframe = result[
        "data"
    ]

    assert tuple(
        dataframe.columns
    ) == IMEI_CDR_CANONICAL_COLUMNS

    row = dataframe.iloc[
        0
    ]

    assert row[
        "target"
    ] == "08603111094"

    assert row[
        "b_party"
    ] == "VD-ViCARE-S"

    assert row[
        "call_type"
    ] == "incoming_sms"

    assert row[
        "raw_call_type"
    ] == "Incoming"

    assert row[
        "call_direction"
    ] == "incoming"

    assert row[
        "observed_imei_normalized"
    ] == "866284043482070"

    assert row[
        "match_relation"
    ] == "SAME_BASE14"

    assert row[
        "source_row_number"
    ] == 5


def test_normalize_search_criteria_imei_cdr(
    tmp_path: Path,
):
    path = _write(
        tmp_path / "bsnl.csv",
        """
Search Criteria : IMEI
Search Value : 866741058018575
Target/A-Party Number,Call Type,Type of Connection,Other/B-party Number,LRN of B-Party Number,Translation of LRN,Call Date,Call Initiation Time,Call Duration,First BTS Location,First Cell Global ID,Last BTS Location,Last Cell Global ID,SMS Centre No.,Service Type,IMEI,IMSI,Original Calling Party,Roaming Network/Circle,Switch/MSC ID,In TG,Out TG
8986052687,OUT,,9572464525,3087,Reliance Jio,24/03/2026,07:17:37,46,Tower A,404-75-4213-31023,Tower A,404-75-4213-31021,,Voice Call,866741058018570,404758180316980,,BSNL Bihar,MSC,IN,OUT
""",
    )

    result = normalize_imei_cdr_file(
        path
    )

    row = result[
        "data"
    ].iloc[
        0
    ]

    assert result[
        "ok"
    ] is True

    assert row[
        "call_type"
    ] == "outgoing"

    assert row[
        "call_duration"
    ] == 46

    assert row[
        "first_cell_id"
    ] == "404-75-4213-31023"

    assert row[
        "imsi"
    ] == "404758180316980"


def test_normalize_jio_direction_and_base14(
    tmp_path: Path,
):
    path = _write(
        tmp_path / "jio.csv",
        """
Ticket Number :,LEA00000000000000000001
Input Value (MSISDN/B PARTY/IMEI/IMSI/CELL ID) :,'35309885264836'
Total Records :,2
Calling Party Telephone Number,Called Party Telephone Number,Call Forwarding,LRN Called No,Call Date,Call Time,Call Termination Time,Call Duration,First Cell ID,Last Cell ID,Call Type,SMS Center Number,IMEI,IMSI,Roaming Circle Name
'JX-JIOSVC-S','919234228158',,,02/06/2026,17:29:23,17:29:23,,'405856005DC1A',,A2P_SMSIN,'916362784225','353098852648366','405856140573551',BH
'919234228158','919999999999',,,02/06/2026,17:30:23,17:31:23,60,'405856005DC1A','405856005DC2',a_out,,'353098852648360','405856140573551',BH
""",
    )

    result = normalize_imei_cdr_file(
        path
    )

    dataframe = result[
        "data"
    ]

    assert result[
        "records_normalized"
    ] == 2

    incoming = dataframe.iloc[
        0
    ]

    outgoing = dataframe.iloc[
        1
    ]

    assert incoming[
        "target"
    ] == "919234228158"

    assert incoming[
        "b_party"
    ] == "JX-JIOSVC-S"

    assert incoming[
        "call_type"
    ] == "incoming_sms"

    assert outgoing[
        "target"
    ] == "919234228158"

    assert outgoing[
        "b_party"
    ] == "919999999999"

    assert outgoing[
        "call_type"
    ] == "outgoing"

    assert set(
        dataframe[
            "match_relation"
        ]
    ) == {
        "BASE14_MATCH"
    }

    assert set(
        dataframe[
            "query_identifier_type"
        ]
    ) == {
        "BASE14"
    }


def test_normalize_valid_no_data_cdr(
    tmp_path: Path,
):
    path = _write(
        tmp_path / "jio_empty.csv",
        """
Ticket Number :,LEA00000000000000000001
Input Value (MSISDN/B PARTY/IMEI/IMSI/CELL ID) :,'35309885264837'
Total Records :,0
Calling Party Telephone Number,Called Party Telephone Number,Call Forwarding,LRN Called No,Call Date,Call Time,Call Termination Time,Call Duration,First Cell ID,Last Cell ID,Call Type,SMS Center Number,IMEI,IMSI,Roaming Circle Name
""",
    )

    result = normalize_imei_cdr_file(
        path
    )

    assert result[
        "ok"
    ] is True

    assert result[
        "status"
    ] == STATUS_EMPTY_NO_DATA

    assert result[
        "data"
    ].empty

    assert tuple(
        result[
            "data"
        ].columns
    ) == IMEI_CDR_CANONICAL_COLUMNS


def test_non_cdr_imei_report_is_not_normalized_as_cdr(
    tmp_path: Path,
):
    path = _write(
        tmp_path / "airtel_gprs.csv",
        """
BHARTI AIRTEL LTD
GPRS OF IMEI : 862261072892730 from 01-Feb-2025 00:00:00 to 09-Oct-2025 23:59:59
Mobile No.,IP Address,IMEI,IMSI,Downlink Vol,Uplink Vol,Total Vol,Session Start Time,Session End Time,Pre/Post,Roaming Circle,2g/4g/5g,ICR Operator Name,Home Circle,IP,CGI Latitude,CGI Longitude,CGI
No Records Found
""",
    )

    result = normalize_imei_cdr_file(
        path
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


def test_normalization_does_not_modify_inspection(
    tmp_path: Path,
):
    from copy import deepcopy

    path = _write(
        tmp_path / "vil.csv",
        """
Vodafone Idea Call Data Records
IMEI : - 866284043482077
Report Type :- Main CDR Report
Target /A PARTY NUMBER,CALL_TYPE,B PARTY NUMBER,Call date,Call Initiation Time,Call Duration,First Cell Global Id,Last Cell Global Id,Service Type,IMEI,IMSI
08603111094,Incoming,VD-ViCARE-S,01-06-2026,08:01:13,1,4057040552421,4057040552421,SMS,866284043482070,405752741941459
""",
    )

    inspection = inspect_imei_evidence_file(
        path
    )

    original = deepcopy(
        inspection
    )

    normalize_imei_cdr_file(
        path,
        inspection=inspection,
    )

    assert inspection == original

def test_normalize_jio_operator_specific_direction_codes(
    tmp_path: Path,
):
    path = _write(
        tmp_path / "jio_direction_codes.csv",
        """
Ticket Number :,LEA00000000000000000001
Input Value (MSISDN/B PARTY/IMEI/IMSI/CELL ID) :,'35309885264836'
Total Records :,4
Calling Party Telephone Number,Called Party Telephone Number,Call Forwarding,LRN Called No,Call Date,Call Time,Call Termination Time,Call Duration,First Cell ID,Last Cell ID,Call Type,SMS Center Number,IMEI,IMSI,Roaming Circle Name
'918111111111','919234228158',,,02/06/2026,10:00:00,10:00:16,16,'49.47.132.116:10630',,a_in_wifi,,'353098852648366','405856140573551',BH
'918222222222','919234228158',,,02/06/2026,10:01:00,10:01:11,11,'2409:4124:0058:86d4::',,a_in_wv,,'353098852648366','405856140573551',BH
'918333333333','919234228158',,,02/06/2026,10:02:00,10:02:19,19,'405856005DC17',,a_in_vw,,'353098852648366','405856140573551',BH
'919234228158','918444444444',,,02/06/2026,10:03:00,10:03:00,,'4058560C0098001',,P2POUT,,'353098852648360','405856140573551',BH
""",
    )

    result = normalize_imei_cdr_file(
        path
    )

    assert result[
        "ok"
    ] is True

    assert result[
        "records_normalized"
    ] == 4

    dataframe = result[
        "data"
    ]

    incoming = dataframe.iloc[
        :3
    ]

    outgoing = dataframe.iloc[
        3
    ]

    assert set(
        incoming[
            "call_direction"
        ]
    ) == {
        "incoming"
    }

    assert set(
        incoming[
            "call_type"
        ]
    ) == {
        "incoming"
    }

    assert set(
        incoming[
            "target"
        ]
    ) == {
        "919234228158"
    }

    assert set(
        incoming[
            "b_party"
        ]
    ) == {
        "918111111111",
        "918222222222",
        "918333333333",
    }

    assert outgoing[
        "raw_call_type"
    ] == "P2POUT"

    assert outgoing[
        "call_direction"
    ] == "outgoing"

    assert outgoing[
        "call_type"
    ] == "outgoing"

    assert outgoing[
        "target"
    ] == "919234228158"

    assert outgoing[
        "b_party"
    ] == "918444444444"

    assert set(
        dataframe[
            "match_relation"
        ]
    ) == {
        "BASE14_MATCH"
    }

def test_normalize_jio_additional_outgoing_direction_codes(
    tmp_path: Path,
):
    path = _write(
        tmp_path / "jio_outgoing_codes.csv",
        """
Ticket Number :,LEA00000000000000000002
Input Value (MSISDN/B PARTY/IMEI/IMSI/CELL ID) :,'35309885264836'
Total Records :,4
Calling Party Telephone Number,Called Party Telephone Number,Call Forwarding,LRN Called No,Call Date,Call Time,Call Termination Time,Call Duration,First Cell ID,Last Cell ID,Call Type,SMS Center Number,IMEI,IMSI,Roaming Circle Name
'919234228158','918111111111',,,02/06/2026,11:00:00,11:00:16,16,'49.47.132.116:10630',,a_out_wifi,,'353098852648366','405856140573551',BH
'919234228158','918222222222',,,02/06/2026,11:01:00,11:01:11,11,'2409:4124:0058:86d4::',,a_out_wv,,'353098852648366','405856140573551',BH
'919234228158','918333333333',,,02/06/2026,11:02:00,11:02:19,19,'405856005DC17',,a_out_vw,,'353098852648366','405856140573551',BH
'919234228158','918444444444',,,02/06/2026,11:03:00,11:03:00,,'4058560C0098001',,P2AOUT,,'353098852648360','405856140573551',BH
""",
    )

    result = normalize_imei_cdr_file(
        path
    )

    assert result[
        "ok"
    ] is True

    assert result[
        "records_normalized"
    ] == 4

    dataframe = result[
        "data"
    ]

    assert set(
        dataframe[
            "raw_call_type"
        ]
    ) == {
        "a_out_wifi",
        "a_out_wv",
        "a_out_vw",
        "P2AOUT",
    }

    assert set(
        dataframe[
            "call_direction"
        ]
    ) == {
        "outgoing"
    }

    assert set(
        dataframe[
            "call_type"
        ]
    ) == {
        "outgoing"
    }

    assert set(
        dataframe[
            "target"
        ]
    ) == {
        "919234228158"
    }

    assert set(
        dataframe[
            "b_party"
        ]
    ) == {
        "918111111111",
        "918222222222",
        "918333333333",
        "918444444444",
    }

    assert set(
        dataframe[
            "match_relation"
        ]
    ) == {
        "BASE14_MATCH"
    }

def test_airtel_dynamic_ipdr_footer_timestamp_is_non_data(
    tmp_path: Path,
):
    from modules.loader.imei_evidence_loader import (
        FORMAT_AIRTEL_DYNAMIC_IMEI_IPDR,
        STATUS_HAS_DATA,
        _extract_rows_with_line_numbers,
        _find_header,
        _read_text,
    )

    path = _write(
        tmp_path / "airtel_dynamic_ipdr.csv",
        """
BHARTI AIRTEL LTD

Dynamic IPDR OF IMEI : 862261072892730 from 01-Oct-2025 00:00:00 to 12-Oct-2025 23:59:59

MSISDN_userID,IMEI,IMSI,Downlink_Vol,Uplink_Vol,Event_Start_Time,Session_Start_Time,Session_End_Time,Pre_Post,Roaming_Circle,ICR_Operator_Name,Home_Circle,Source_Public_IPv4,Source_Public_IPv6,Source_Public_Port,Destination_IP4,Destination_IP6,Destination_Port,Source_Private_IPV4,Source_Handset_Port,Duration,Charging_ID,Access_Point_Name,PACO_GW_IP,2g/4g/5g,CGI Latitude,CGI Longitude,CGI
5754021077243,8622610728927300,405523214527244,1784731,632337,05-Oct-2025 08:14:24,05-Oct-2025 08:14:21,05-Oct-2025 08:15:56,Post,DELHI,,BIHAR-JHAR,,2401:4900:8339:2dbc:0:0:0:2,44784,,2a03:2880:f288:ca:face:b00c:0:7260,5222,,44784,95,1019420895,airtelmeterv6,223.224.146.169,4G,28.65557,77.10866,404-10-2330-158187265

 This is System generated report, and needs no signature.

 12-Oct-2025 18:16:55
""",
    )

    inspection = inspect_imei_evidence_file(
        path
    )

    assert inspection[
        "ok"
    ] is True

    assert inspection[
        "format_id"
    ] == FORMAT_AIRTEL_DYNAMIC_IMEI_IPDR

    assert inspection[
        "status"
    ] == STATUS_HAS_DATA

    assert inspection[
        "record_count"
    ] == 1

    assert inspection[
        "rejected_line_count"
    ] == 0

    text = _read_text(
        path
    )

    lines = text.splitlines()

    header_line, header = _find_header(
        lines
    )

    numbered_rows, rejected = (
        _extract_rows_with_line_numbers(
            lines=lines,
            header_line=header_line,
            header=header,
        )
    )

    assert len(
        numbered_rows
    ) == 1

    assert rejected == 0

    assert numbered_rows[
        0
    ][
        1
    ][
        0
    ] == "5754021077243"

def test_normalize_airtel_dynamic_imei_ipdr_contract(
    tmp_path,
):
    """Reuse canonical IPDR output and add dedicated IMEI context."""

    import copy

    from modules.loader.imei_evidence_loader import (
        FORMAT_AIRTEL_DYNAMIC_IMEI_IPDR,
        STATUS_HAS_DATA,
        inspect_imei_evidence_file,
        normalize_imei_ipdr_file,
    )

    path = (
        tmp_path
        / "airtel_dynamic_imei_ipdr.csv"
    )

    path.write_text(
        """
BHARTI AIRTEL LTD

Pan India

Dynamic IPDR OF IMEI : 862261072892730 from 01-Oct-2025 00:00:00 to 12-Oct-2025 23:59:59

MSISDN_userID,IMEI,IMSI,Downlink_Vol,Uplink_Vol,Event_Start_Time,Session_Start_Time,Session_End_Time,Pre_Post,Roaming_Circle,ICR_Operator_Name,Home_Circle,Source_Public_IPv4,Source_Public_IPv6,Source_Public_Port,Destination_IP4,Destination_IP6,Destination_Port,Source_Private_IPV4,Source_Handset_Port,Duration,Charging_ID,Access_Point_Name,PACO_GW_IP,2g/4g/5g,CGI Latitude,CGI Longitude,CGI
5754021077243,8622610728927300,405523214527244,1784731,632337,05-Oct-2025 08:14:24,05-Oct-2025 08:14:21,05-Oct-2025 08:15:56,Post,DELHI,,BIHAR-JHAR,,2401:4900:8339:2dbc:0:0:0:2,44784,,2a03:2880:f288:ca:face:b00c:0:7260,5222,,44784,95,1019420895,airtelmeterv6,223.224.146.169,4G,28.65557,77.10866,404-10-2330-158187265

 This is System generated report, and needs no signature.

 12-Oct-2025 18:16:55
""".lstrip(),
        encoding="utf-8",
    )

    inspection = inspect_imei_evidence_file(
        path
    )

    inspection_before = copy.deepcopy(
        inspection
    )

    result = normalize_imei_ipdr_file(
        path,
        inspection=inspection,
    )

    assert inspection == inspection_before

    assert result[
        "ok"
    ] is True

    assert result[
        "status"
    ] == STATUS_HAS_DATA

    assert result[
        "format_id"
    ] == FORMAT_AIRTEL_DYNAMIC_IMEI_IPDR

    assert result[
        "records_read"
    ] == 1

    assert result[
        "records_normalized"
    ] == 1

    assert result[
        "rejected_line_count"
    ] == 0

    assert result[
        "rejected_rows"
    ].empty

    dataframe = result[
        "data"
    ]

    assert len(
        dataframe
    ) == 1

    record = dataframe.iloc[
        0
    ]

    assert record[
        "report_scope"
    ] == "IMEI"

    assert record[
        "query_identifier_raw"
    ] == "862261072892730"

    assert record[
        "query_identifier_normalized"
    ] == "862261072892730"

    assert record[
        "query_identifier_type"
    ] == "IMEI15"

    assert record[
        "observed_imei_raw"
    ] == "8622610728927300"

    assert record[
        "observed_imei_normalized"
    ] == "8622610728927300"

    assert record[
        "match_relation"
    ] == "SAME_BASE14"

    assert record[
        "detected_operator"
    ] == "Bharti Airtel"

    assert record[
        "detected_format"
    ] == FORMAT_AIRTEL_DYNAMIC_IMEI_IPDR

    assert record[
        "subscriber_number"
    ] == "5754021077243"

    assert record[
        "source_ip"
    ] == "2401:4900:8339:2dbc::2"

    assert record[
        "destination_ip"
    ] == "2a03:2880:f288:ca:face:b00c:0:7260"

    assert int(
        record[
            "source_port"
        ]
    ) == 44784

    assert int(
        record[
            "destination_port"
        ]
    ) == 5222

    assert record[
        "apn"
    ] == "airtelmeterv6"

    assert record[
        "cgi"
    ] == "404-10-2330-158187265"

    assert int(
        record[
            "source_row_number"
        ]
    ) == 8

    assert record[
        "source_path"
    ] == str(
        path.resolve()
    )


def test_normalize_valid_no_data_imei_ipdr(
    tmp_path,
):
    """A valid no-data IMEI IPDR report remains successful evidence."""

    from modules.loader.imei_evidence_loader import (
        STATUS_EMPTY_NO_DATA,
        normalize_imei_ipdr_file,
    )

    path = (
        tmp_path
        / "airtel_empty_imei_ipdr.csv"
    )

    path.write_text(
        """
BHARTI AIRTEL LTD

Pan India

Dynamic IPDR OF IMEI : 862286069717070 from 01-Oct-2025 00:00:00 to 12-Oct-2025 23:59:59

MSISDN_userID,IMEI,IMSI,Downlink_Vol,Uplink_Vol,Event_Start_Time,Session_Start_Time,Session_End_Time,Pre_Post,Roaming_Circle,ICR_Operator_Name,Home_Circle,Source_Public_IPv4,Source_Public_IPv6,Source_Public_Port,Destination_IP4,Destination_IP6,Destination_Port,Source_Private_IPV4,Source_Handset_Port,Duration,Charging_ID,Access_Point_Name,PACO_GW_IP,2g/4g/5g,CGI Latitude,CGI Longitude,CGI

No Records Found

 This is System generated report, and needs no signature.

 12-Oct-2025 18:16:55
""".lstrip(),
        encoding="utf-8",
    )

    result = normalize_imei_ipdr_file(
        path
    )

    assert result[
        "ok"
    ] is True

    assert result[
        "status"
    ] == STATUS_EMPTY_NO_DATA

    assert result[
        "records_read"
    ] == 0

    assert result[
        "records_normalized"
    ] == 0

    assert result[
        "rejected_line_count"
    ] == 0

    assert result[
        "data"
    ].empty

    assert result[
        "rejected_rows"
    ].empty

    required_columns = {
        "record_type",
        "imei",
        "query_identifier_raw",
        "query_identifier_normalized",
        "query_identifier_type",
        "observed_imei_raw",
        "observed_imei_normalized",
        "match_relation",
        "detected_operator",
        "detected_format",
        "source_path",
    }

    assert required_columns.issubset(
        result[
            "data"
        ].columns
    )


def test_non_ipdr_report_is_not_normalized_as_ipdr(
    tmp_path,
):
    """A recognized GPRS report must not enter the IPDR wrapper."""

    from modules.loader.imei_evidence_loader import (
        STATUS_UNSUPPORTED,
        normalize_imei_ipdr_file,
    )

    path = (
        tmp_path
        / "airtel_imei_gprs.csv"
    )

    path.write_text(
        """
BHARTI AIRTEL LTD

GPRS OF IMEI : 862261072892730 from 01-Oct-2025 00:00:00 to 12-Oct-2025 23:59:59

No Records Found
""".lstrip(),
        encoding="utf-8",
    )

    result = normalize_imei_ipdr_file(
        path
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

    assert (
        "not a supported IPDR"
        in result[
            "message"
        ]
    )

