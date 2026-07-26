"""Regression tests for Airtel IPDR footer classification."""

from modules.loader.ipdr_loader import load_ipdr_file


def test_airtel_footer_metadata_is_not_rejected(
    tmp_path,
):
    """Keep a valid event and ignore known Airtel footer metadata."""

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

    result = load_ipdr_file(
        path
    )

    assert result[
        "ok"
    ] is True

    data = result[
        "data"
    ]

    rejected = result[
        "rejected_rows"
    ]

    metadata = result[
        "metadata"
    ]

    assert len(
        data
    ) == 1

    assert rejected.empty

    assert metadata[
        "rejected_rows"
    ] == 0

    record = data.iloc[
        0
    ]

    assert record[
        "imei"
    ] == "8622610728927300"

    assert record[
        "subscriber_number"
    ] == "5754021077243"

    assert str(
        record[
            "source_ip"
        ]
    ) == "2401:4900:8339:2dbc::2"

    assert str(
        record[
            "destination_ip"
        ]
    ) == "2a03:2880:f288:ca:face:b00c:0:7260"

    assert int(
        record[
            "source_row_number"
        ]
    ) == 8
