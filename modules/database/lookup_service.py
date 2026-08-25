"""Canonical SDR and CGI lookup service."""

from functools import lru_cache
import re
from typing import Any

import pandas as pd

from modules.enrichment.sdr_subscriber_enrichment import lookup_sdr_subscribers, normalize_mobile_number
from .cgi_repository import create_cgi_table, lookup_cgi, normalize_cgi, normalize_cgi_key
from .sdr_repository import create_sdr_table, lookup_mobile


MATCHED = "MATCHED"
NOT_FOUND = "NOT_FOUND"
INVALID_INPUT = "INVALID_INPUT"
DATABASE_ERROR = "DATABASE_ERROR"


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text.casefold() in {"", "nan", "none", "<na>", "null"}:
        return ""
    return text


def clean_display_address(value: object) -> str:
    """Create a readable display copy."""
    text = _clean_text(value)
    if not text:
        return ""
    text = re.sub(r"[!|^]+", ", ", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"(?:,\s*){2,}", ", ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,")


_VERIFIED_SDR_OPERATOR_NAMES = {
    "AIRTEL", "BHARTI AIRTEL", "JIO", "RELIANCE JIO",
    "VODAFONE", "VODAFONE IDEA", "IDEA", "VI",
    "BSNL", "MTNL", "AIRCEL", "TATA DOCOMO",
    "TATA TELESERVICES", "RELIANCE COMMUNICATIONS",
    "UNINOR", "TELENOR",
}


def _verified_sdr_operator(value: object) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    cleaned = text.replace(" - Copy", "").strip()
    normalized = " ".join(cleaned.upper().replace("_", " ").replace("-", " ").split())
    if normalized in _VERIFIED_SDR_OPERATOR_NAMES:
        return cleaned
    strong_tokens = ("AIRTEL", "JIO", "VODAFONE", "BSNL", "MTNL", "AIRCEL", "DOCOMO", "TELENOR", "UNINOR")
    if any(token in normalized for token in strong_tokens):
        return cleaned
    return ""


@lru_cache(maxsize=128)
def _lookup_sdr_profile_cached(normalized_number: str) -> dict[str, Any]:
    try:
        dataframe = lookup_sdr_subscribers([normalized_number])
    except Exception as error:
        return {
            "status": DATABASE_ERROR, "found": False,
            "entered_number": "", "normalized_number": normalized_number,
            "record": {}, "records": [],
            "error_type": type(error).__name__, "error": str(error),
            "message": "SDR database query failed.",
        }
    if dataframe is None or dataframe.empty:
        return {
            "status": NOT_FOUND, "found": False,
            "entered_number": "", "normalized_number": normalized_number,
            "record": {}, "records": [],
            "message": "SDR profile database mein nahi mila.",
        }
    records = []
    for _, row in dataframe.iterrows():
        raw_address = row.get("subscriber_address", row.get("address", ""))
        records.append({
            "mobile_number": row.get("lookup_mobile", normalized_number),
            "subscriber_name": row.get("subscriber_name", ""),
            "father_name": row.get("father_name", ""),
            "raw_address": raw_address,
            "clean_address": clean_display_address(raw_address),
            "id_type": row.get("id_type", ""),
            "id_number": row.get("id_number", ""),
            "operator": _verified_sdr_operator(row.get("operator", "")),
            "operator_or_source_category": row.get("operator", ""),
            "circle": row.get("circle", ""),
            "activation_date": row.get("activation_date", ""),
            "caf_number": row.get("caf_number", ""),
            "source_file": row.get("source_file", ""),
        })
    return {
        "status": MATCHED, "found": True,
        "entered_number": "", "normalized_number": normalized_number,
        "record": records[0], "records": records,
        "match_count": len(records), "message": "SDR profile matched.",
    }


def lookup_sdr_profile(number: object) -> dict[str, Any]:
    entered_number = _clean_text(number)
    normalized_number = normalize_mobile_number(entered_number)
    if not normalized_number:
        return {
            "status": INVALID_INPUT, "found": False,
            "entered_number": entered_number, "normalized_number": "",
            "record": {}, "records": [],
            "message": "Valid 10-digit Indian mobile number required hai.",
        }
    result = _lookup_sdr_profile_cached(normalized_number)
    result["entered_number"] = entered_number
    return result


@lru_cache(maxsize=128)
def _lookup_cgi_profile_cached(normalized_cgi: str) -> dict[str, Any]:
    try:
        result = lookup_cgi(normalized_cgi)
    except Exception as error:
        return {
            "status": DATABASE_ERROR, "found": False,
            "entered_cgi": "", "normalized_cgi": normalized_cgi,
            "record": {}, "error_type": type(error).__name__,
            "error": str(error), "message": "CGI database query failed.",
        }
    if not isinstance(result, dict) or not result:
        return {
            "status": NOT_FOUND, "found": False,
            "entered_cgi": "", "normalized_cgi": normalized_cgi,
            "record": {}, "message": "CGI / Cell database mein nahi mila.",
        }
    record = {
        "cgi": result.get("cgi", normalized_cgi),
        "operator": result.get("operator", ""),
        "circle": result.get("circle", ""),
        "state": result.get("state", ""),
        "district": result.get("district", ""),
        "police_station": result.get("police_station", ""),
        "address": result.get("address", ""),
        "town": result.get("town", ""),
        "landmark": result.get("landmark", ""),
        "site_name": result.get("site_name", ""),
        "latitude": result.get("latitude", ""),
        "longitude": result.get("longitude", ""),
        "azimuth": result.get("azimuth", ""),
        "technology": result.get("technology", ""),
        "status": result.get("status", ""),
        "status_change_date": result.get("status_change_date", ""),
        "mcc_mnc": result.get("mcc_mnc", ""),
        "lac": result.get("lac", ""),
        "cid": result.get("cid", ""),
        "tac_id": result.get("tac_id", ""),
        "site_id": result.get("site_id", ""),
        "gnb_id": result.get("gnb_id", ""),
        "cell_id": result.get("cell_id", ""),
        "source_file": result.get("source_file", ""),
    }
    return {
        "status": MATCHED, "found": True,
        "entered_cgi": "", "normalized_cgi": normalized_cgi,
        "record": record, "message": "CGI / Cell record matched.",
    }


def lookup_cgi_profile(cgi_value: object) -> dict[str, Any]:
    entered_cgi = _clean_text(cgi_value)
    normalized_cgi = normalize_cgi(entered_cgi)
    if not normalized_cgi:
        return {
            "status": INVALID_INPUT, "found": False,
            "entered_cgi": entered_cgi, "normalized_cgi": "",
            "record": {}, "message": "Valid CGI / Cell ID required hai.",
        }
    result = _lookup_cgi_profile_cached(normalized_cgi)
    result["entered_cgi"] = entered_cgi
    return result


# ------------------------------------------------------------------
# Compatibility API
# ------------------------------------------------------------------

def initialize_master_lookup_database() -> None:
    create_cgi_table()
    create_sdr_table()


def lookup_number_identity(number: str):
    return lookup_mobile(number)


def lookup_tower_address(cgi: str):
    return lookup_cgi(cgi)


def clear_all_lookup_caches():
    """Clear all lookup caches."""
    try:
        from modules.database.sdr_repository import lookup_mobile_dataframe_cached, _normalize_mobile_cached
        lookup_mobile_dataframe_cached.cache_clear()
        _normalize_mobile_cached.cache_clear()
    except ImportError:
        pass
    try:
        from modules.database.cgi_repository import lookup_cgi_dataframe_cached, normalize_cgi_key
        lookup_cgi_dataframe_cached.cache_clear()
        normalize_cgi_key.cache_clear()
    except ImportError:
        pass
    try:
        from modules.enrichment.sdr_subscriber_enrichment import lookup_sdr_subscribers_cached, _normalize_mobile_cached
        lookup_sdr_subscribers_cached.cache_clear()
        _normalize_mobile_cached.cache_clear()
    except ImportError:
        pass
    try:
        from modules.enrichment.cgi_address_enrichment import _lookup_cgi_addresses_cached
        _lookup_cgi_addresses_cached.cache_clear()
    except ImportError:
        pass
    try:
        _lookup_sdr_profile_cached.cache_clear()
        _lookup_cgi_profile_cached.cache_clear()
    except AttributeError:
        pass