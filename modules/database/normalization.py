"""CGI header and value normalization."""

from __future__ import annotations

import math
import re
from typing import Any, Iterable


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if value.is_integer():
            return str(int(value))
        return format(value, ".15g")
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "na", "n/a", "-"}:
        return ""
    return text


def digits_only(value: Any) -> str:
    return re.sub(r"\D", "", clean_text(value))


def normalize_header(value: Any) -> str:
    text = clean_text(value).lower()
    text = text.replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def safe_float(value: Any) -> float | None:
    text = clean_text(value).replace(",", "")
    if not text:
        return None
    try:
        number = float(text)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


COLUMN_ALIASES: dict[str, set[str]] = {
    "cgi": {"cgi", "cgi_dec", "cell_global_identity_cgi", "cell_global_identity", "cgi_decimal"},
    "mcc": {"mcc"},
    "mnc": {"mnc"},
    "mcc_mnc": {"mcc_mnc"},
    "lac": {"lac", "location_area_code"},
    "tac": {"tac", "tracking_area_code"},
    "cell_id": {"cell_id", "cellid", "cell_id_decimal", "ci"},
    "legacy_cell_ref": {"bts_id_cell_id", "bts_id_or_cell_id"},
    "enodeb_local": {"enodeb_local_cell_id", "e_nodeb_local_cell_id"},
    "enodeb_id": {"enodeb_id", "e_nodeb_id"},
    "local_cell_id": {"local_cell_id", "sector_id"},
    "mcc_mnc_enodeb_cid": {"mcc_mnc_enodeb_cid"},
    "technology": {"tech", "technology", "network_type"},
    "site_id": {"siteid", "site_id", "site_location_id", "bts_site_id"},
    "site_name": {"site_name", "bts_name", "cell_location"},
    "cell_name": {"cell_name", "cellname"},
    "latitude": {"lat", "latitude", "lat_pd"},
    "longitude": {"long", "longitude", "lng", "lon", "long_pd"},
    "azimuth": {"azimuth", "orientation"},
    "address": {"address", "site_address"},
    "town": {"town", "city"},
    "block": {"block"},
    "district": {"district"},
    "state": {"state", "state_name"},
    "circle": {"circle", "circle_name"},
    "ssa": {"ssa", "ssaname", "ssa_name"},
    "pin_code": {"pin_code", "pincode", "pin"},
    "operator": {"tsp_name", "operator", "operator_name", "service_provider"},
    "vendor": {"oem", "vendor"},
}

ALIAS_TO_CANONICAL = {
    alias: canonical
    for canonical, aliases in COLUMN_ALIASES.items()
    for alias in aliases
}


def header_score(values: Iterable[Any]) -> int:
    normalized = [normalize_header(value) for value in values]
    recognized = [ALIAS_TO_CANONICAL.get(item) for item in normalized]
    score = sum(4 for item in recognized if item)
    if "cgi" in recognized:
        score += 10
    if "latitude" in recognized and "longitude" in recognized:
        score += 6
    if "cell_id" in recognized:
        score += 4
    return score


def detect_header_row(rows: list[tuple[Any, ...]]) -> int | None:
    best_index = None
    best_score = 0
    for index, row in enumerate(rows):
        score = header_score(row)
        if score > best_score:
            best_score = score
            best_index = index
    return best_index if best_score >= 12 else None


def build_column_map(headers: Iterable[Any]) -> dict[str, list[int]]:
    mapping: dict[str, list[int]] = {}
    for index, header in enumerate(headers):
        canonical = ALIAS_TO_CANONICAL.get(normalize_header(header))
        if canonical:
            mapping.setdefault(canonical, []).append(index)
    return mapping


def first_value(row: tuple[Any, ...], indexes: list[int] | None) -> str:
    for index in indexes or []:
        if index < len(row):
            value = clean_text(row[index])
            if value:
                return value
    return ""


def split_mcc_mnc(value: str) -> tuple[str, str]:
    parts = [part for part in re.split(r"\D+", value) if part]
    if len(parts) >= 2:
        return parts[0], parts[1]
    digits = digits_only(value)
    if len(digits) >= 5:
        return digits[:3], digits[3:]
    return "", ""


def _infer_components_from_cgi(
    cgi_raw: str,
    *,
    mcc: str,
    mnc: str,
    lac: str,
    tac: str,
    cell_id: str,
) -> tuple[str, str, str, str, str]:
    parts = [part for part in re.split(r"\D+", cgi_raw) if part]
    if len(parts) >= 4:
        mcc = mcc or parts[0]
        mnc = mnc or parts[1]
        area = parts[2]
        cell_id = cell_id or parts[3]
        if tac:
            tac = tac or area
        elif lac:
            lac = lac or area
        else:
            lac = area
        return mcc, mnc, lac, tac, cell_id

    key = digits_only(cgi_raw)
    area = tac or lac
    if key and area and cell_id and key.endswith(digits_only(area) + digits_only(cell_id)):
        prefix = key[: -len(digits_only(area) + digits_only(cell_id))]
        if len(prefix) >= 5:
            mcc = mcc or prefix[:3]
            mnc = mnc or prefix[3:]
    return mcc, mnc, lac, tac, cell_id


def normalize_record(
    row: tuple[Any, ...],
    column_map: dict[str, list[int]],
    *,
    source_file: str,
    source_sheet: str,
    source_row: int,
) -> tuple[dict[str, Any] | None, str | None]:
    get = lambda name: first_value(row, column_map.get(name))

    cgi_raw = get("cgi")
    mcc = digits_only(get("mcc"))
    mnc = digits_only(get("mnc"))
    mcc_mnc = get("mcc_mnc")
    if mcc_mnc and (not mcc or not mnc):
        parsed_mcc, parsed_mnc = split_mcc_mnc(mcc_mnc)
        mcc = mcc or parsed_mcc
        mnc = mnc or parsed_mnc

    lac = digits_only(get("lac"))
    tac = digits_only(get("tac"))
    cell_id = digits_only(get("cell_id")) or digits_only(get("legacy_cell_ref"))

    enodeb_id = digits_only(get("enodeb_id"))
    local_cell_id = digits_only(get("local_cell_id"))
    enodeb_local = get("enodeb_local")
    if enodeb_local:
        enodeb_parts = [part for part in re.split(r"\D+", enodeb_local) if part]
        if len(enodeb_parts) >= 2:
            enodeb_id = enodeb_id or enodeb_parts[0]
            local_cell_id = local_cell_id or enodeb_parts[-1]

    mcc, mnc, lac, tac, cell_id = _infer_components_from_cgi(
        cgi_raw, mcc=mcc, mnc=mnc, lac=lac, tac=tac, cell_id=cell_id
    )

    cgi_key = digits_only(cgi_raw)
    area_code = tac or lac
    if not cgi_key and mcc and mnc and area_code and cell_id:
        cgi_key = f"{mcc}{mnc}{area_code}{cell_id}"

    if not cgi_key or len(cgi_key) < 8:
        return None, "Valid CGI could not be created"

    technology = clean_text(get("technology"))
    if technology and "4g" in technology.lower() and not tac and lac:
        tac, lac = lac, ""

    if cgi_raw:
        cgi_display = cgi_raw
    elif mcc and mnc and area_code and cell_id:
        cgi_display = f"{mcc}-{mnc}-{area_code}-{cell_id}"
    else:
        cgi_display = cgi_key

    latitude = safe_float(get("latitude"))
    longitude = safe_float(get("longitude"))
    if latitude is not None and not (-90 <= latitude <= 90):
        return None, f"Invalid latitude: {latitude}"
    if longitude is not None and not (-180 <= longitude <= 180):
        return None, f"Invalid longitude: {longitude}"

    address = get("address") or get("site_name")
    site_name = get("site_name")

    record = {
        "cgi": cgi_display,
        "cgi_key": cgi_key,
        "mcc": mcc,
        "mnc": mnc,
        "lac": lac,
        "tac": tac,
        "cell_id": cell_id,
        "enodeb_id": enodeb_id,
        "local_cell_id": local_cell_id,
        "technology": technology,
        "site_id": get("site_id"),
        "site_name": site_name,
        "cell_name": get("cell_name"),
        "latitude": latitude,
        "longitude": longitude,
        "azimuth": safe_float(get("azimuth")),
        "address": address,
        "town": get("town"),
        "block": get("block"),
        "district": get("district"),
        "state": get("state"),
        "circle": get("circle"),
        "ssa": get("ssa"),
        "pin_code": digits_only(get("pin_code")),
        "operator": get("operator"),
        "vendor": get("vendor"),
        "source_file": source_file,
        "source_sheet": source_sheet,
        "source_row": source_row,
    }

    aliases: list[tuple[str, str]] = []
    alternate = digits_only(get("mcc_mnc_enodeb_cid"))
    if alternate and alternate != cgi_key:
        aliases.append((alternate, "mcc_mnc_enodeb_cid"))
    if enodeb_id and local_cell_id and mcc and mnc:
        aliases.append((f"{mcc}{mnc}{enodeb_id}{local_cell_id}", "enodeb_local"))
    record["aliases"] = aliases
    return record, None
