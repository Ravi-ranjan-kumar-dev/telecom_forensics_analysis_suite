"""Conservative telecom aliases and module contracts.

No column name or MCC/MNC proves an operator or that a report is a tower dump.
Dedicated IMEI evidence is NOT inferred from the mere existence of an IMEI field.
"""
from __future__ import annotations

import hashlib
import json
import re

MODULES = ("CDR", "TOWER_DUMP", "IPDR", "IMEI")
TYPES = ("CDR", "TOWER_CDR", "TOWER_GPRS", "TOWER_IPDR", "IPDR", "IMEI_CDR", "IMEI_GPRS", "IMEI_IPDR", "IMEI_INVENTORY")
TYPE_MODULE = {"CDR":"CDR", "TOWER_CDR":"TOWER_DUMP", "TOWER_GPRS":"TOWER_DUMP",
               "TOWER_IPDR":"TOWER_DUMP", "IPDR":"IPDR", "IMEI_CDR":"IMEI",
               "IMEI_GPRS":"IMEI", "IMEI_IPDR":"IMEI", "IMEI_INVENTORY":"IMEI"}

def norm(name: object) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(name or "").lower())).strip()

ALIASES = {
 "a_party": ["a party", "a party number", "target a party number", "target no", "target a party", "calling party telephone number", "calling number", "calling no", "from number"],
 "b_party": ["b party", "b party no", "b party number", "other b party number", "other party", "other b party", "called party telephone number", "called number", "called no", "to number"],
 "subscriber_number": ["msisdn", "subscriber number", "subscriber msisdn", "mobile number", "mobile no", "user number", "landline msisdn mdn leased circuit id for internet access"],
 "imei": ["imei", "imei number", "device imei", "device identification number", "observed imei"],
 "imsi": ["imsi", "imsi number", "subscriber imsi"],
 "event_time": ["event time", "event timestamp", "timestamp", "date time", "datetime", "start datetime", "call datetime", "time1 dd mm yyyy hh mm ss"],
 "call_date": ["call date", "date", "start date"],
 "call_time": ["call time", "call initiation time", "time", "start time"],
 "call_type": ["call type", "type of call", "call direction", "direction"],
 "call_duration": ["call duration", "call duration sec", "call duration seconds", "dur s", "duration", "duration sec"],
 "first_cell_id": ["first cgi", "first cell id", "first cell global id", "first cell global identity", "cell id", "cellid", "cgi"],
 "last_cell_id": ["last cgi", "last cell id", "last cell global id"],
 "apn": ["apn", "access point name", "access point"],
 "session_start": ["session start", "session start time", "session start datetime", "start time of session"],
 "session_end": ["session end", "session end time", "session end datetime", "time2 dd mm yyyy hh mm ss"],
 "allocation_start": ["allocation start", "public ip allocation start", "start date of public ip address allocation dd mm yyyy"],
 "allocation_end": ["allocation end", "public ip allocation end", "end date of public ip address allocation dd mm yyyy"],
 "allocation_start_time": ["ist start time of public ip address allocation hh mm ss", "ist start time of public ip address allocation", "allocation start time"],
 "allocation_end_time": ["ist end time of public ip address allocation hh mm ss", "ist end time of public ip address allocation", "allocation end time"],
 "source_ip": ["source ip address ip address assigned translated", "source ip", "source ip address", "src ip", "private ip", "subscriber ip", "subscriber ip address"],
 "source_port": ["source port", "src port", "source port port assigned translated", "private port"],
 "translated_ip": ["translated ip", "translated ip address", "public ip", "public ip address", "source public ipv4", "translated ip public ipv4", "public ipv4"],
 "translated_port": ["translated port", "translated port public port", "nat port", "public port", "public ip port"],
 "destination_ip": ["destination ip", "destination ip address", "dst ip", "dest ip", "remote ip"],
 "destination_port": ["destination port", "dest port", "dst port", "remote port"],
 "uplink_volume": ["data uplink volume", "uplink vol", "uplink volume", "upload volume", "uplink bytes"],
 "downlink_volume": ["data downlink volume", "downlink vol", "downlink volume", "download volume", "downlink bytes"],
 "service_type": ["service type", "type of service"],
 "roaming_circle": ["roaming network circle", "roaming circle", "roaming circle name", "home roaming circle"],
 "queried_imei": ["searched imei", "query imei", "requested imei"],
 "query_identifier": ["search value", "query identifier", "requested identifier"],
}
ALIASES = {k: frozenset(map(norm, v + [k])) for k, v in ALIASES.items()}
# Keep module definitions explicit; analyst-approved type determines downstream schema.
REQUIRED_GROUPS = {
 "CDR": (("a_party", "subscriber_number"), ("b_party",), ("event_time", "call_date")),
 "TOWER_CDR": (("a_party", "subscriber_number"), ("event_time", "call_date"), ("first_cell_id",)),
 "TOWER_GPRS": (("subscriber_number", "a_party", "imsi"), ("event_time", "session_start", "call_date"), ("first_cell_id",)),
 "TOWER_IPDR": (("subscriber_number", "imsi"), ("event_time", "session_start", "allocation_start", "call_date"), ("source_ip", "translated_ip")),
 "IPDR": (("subscriber_number", "imsi", "source_ip"), ("event_time", "session_start", "allocation_start", "call_date"), ("source_ip", "translated_ip", "destination_ip")),
 "IMEI_CDR": (("imei",), ("event_time", "call_date")),
 "IMEI_GPRS": (("imei",), ("event_time", "session_start", "call_date")),
 "IMEI_IPDR": (("imei",), ("event_time", "session_start", "allocation_start")),
 "IMEI_INVENTORY": (("imei",),),
}
TIMED_TYPES = set(REQUIRED_GROUPS) - {"IMEI_INVENTORY"}

def header_fingerprint(headers: list[str]) -> str:
    # Order matters: protects against reuse of a mapping on a shifted/reordered input.
    payload = json.dumps([norm(h) for h in headers], separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def proposed_mapping(headers: list[str]) -> tuple[dict[str, str], list[dict]]:
    mapping, ambiguous = {}, []
    for canonical, synonyms in ALIASES.items():
        matches = [str(header) for header in headers if norm(header) in synonyms]
        if len(matches) == 1: mapping[canonical] = matches[0]
        elif len(matches) > 1: ambiguous.append({"field": canonical, "columns": matches})
    # One source must not carry two different meanings without analyst review.
    by_source: dict[str, list[str]] = {}
    for canonical, source in mapping.items(): by_source.setdefault(source, []).append(canonical)
    for source, targets in by_source.items():
        if len(targets) > 1:
            ambiguous.append({"source":source,"fields":targets})
            for target in targets: mapping.pop(target, None)
    return mapping, ambiguous

def missing_groups(evidence_type: str, mapping: dict[str, str]) -> list[list[str]]:
    return [list(group) for group in REQUIRED_GROUPS[evidence_type] if not any(x in mapping for x in group)]
