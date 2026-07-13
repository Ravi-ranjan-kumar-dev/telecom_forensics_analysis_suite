"""Conservative canonicalization for telecom identifiers.

Raw values should always be retained by callers. These helpers create derived
canonical values and never attempt to infer a missing identity.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Any

from .identity import normalize_msisdn


def clean_digits(value: Any) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return re.sub(r"\D", "", text)


def normalize_imei(value: Any) -> str:
    digits = clean_digits(value)
    # IMEI is normally 15 digits; IMEISV can be 16. Keep other values empty
    # rather than silently truncating evidence identifiers.
    return digits if len(digits) in {15, 16} else ""


def normalize_imsi(value: Any) -> str:
    digits = clean_digits(value)
    return digits if 14 <= len(digits) <= 16 else ""


def canonical_ip(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        if "/" in text:
            return str(ipaddress.ip_interface(text))
        return ipaddress.ip_address(text).compressed
    except ValueError:
        return ""


def normalize_subscriber(value: Any) -> tuple[str, str]:
    mobile = normalize_msisdn(value)
    if mobile:
        return mobile, "MSISDN"
    digits = clean_digits(value)
    if 12 <= len(digits) <= 16:
        return digits, "NUMERIC_SUBSCRIBER_ID"
    text = str(value or "").strip()
    return (text, "USER_ID") if text else ("", "MISSING")
