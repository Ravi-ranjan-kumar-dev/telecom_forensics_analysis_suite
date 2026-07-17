"""Canonical multi-operator target/reverse IPDR loader.

Supported sample families:
- Bharti Airtel dynamic IPDR (target mobile and destination-IP reports)
- Vodafone Idea/VIL destination-IP IPDR
- Jio target IPDR/NAT event export
- Jio broadband IPv6 allocation export
- Airtel IPv4 reverse-search request workbook

Tower/cell-requested ``CELL ID_IPDRNAT`` exports are deliberately rejected
from this top-level IPDR loader and belong to Tower Dump Analysis.
"""

from __future__ import annotations

import csv
import hashlib
import ipaddress
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from modules.loader.evidence_csv import (
    empty_reject_ledger,
    quarantine_dataframe_rows,
    read_csv_with_quarantine,
)


SUPPORTED_SUFFIXES = {".csv", ".txt", ".xlsx", ".xls"}

FORMAT_AIRTEL = "AIRTEL_DYNAMIC_IPDR"
FORMAT_VI = "VI_DYNAMIC_IPDR"
FORMAT_JIO = "JIO_IPDR"
FORMAT_SEARCH = "AIRTEL_IPV4_SEARCH_REQUEST"
FORMAT_TOWER = "TOWER_IPDR_NAT"
FORMAT_UNKNOWN = "UNKNOWN_IPDR_FORMAT"

SCOPE_TARGET = "TARGET_SUBSCRIBER"
SCOPE_REVERSE = "REVERSE_DESTINATION_IP"
SCOPE_PUBLIC = "REVERSE_PUBLIC_IP_PORT"
SCOPE_BROADBAND = "BROADBAND_IPV6_ALLOCATION"
SCOPE_SEARCH = "SEARCH_REQUEST_INPUT"
SCOPE_UNKNOWN = "UNKNOWN_SCOPE"

NORMALIZED_COLUMNS = [
    "record_type",
    "operator",
    "source_format",
    "report_scope",
    "query_value",
    "query_port",
    "subscriber_number_raw",
    "subscriber_number",
    "subscriber_identifier_type",
    "imei",
    "imsi",
    "event_time",
    "session_start",
    "session_end",
    "allocation_start",
    "allocation_end",
    "session_duration_seconds",
    "source_ip",
    "source_ip_version",
    "source_public_ipv4",
    "source_public_ipv6",
    "source_private_ipv4",
    "source_port",
    "translated_ip",
    "translated_port",
    "destination_ip",
    "destination_ip_version",
    "destination_ipv4",
    "destination_ipv6",
    "destination_port",
    "charging_id",
    "apn",
    "gateway_ip",
    "first_cell_id",
    "last_cell_id",
    "cgi",
    "latitude",
    "longitude",
    "technology",
    "pre_post",
    "home_circle",
    "roaming_circle",
    "roaming_status",
    "uplink_volume",
    "downlink_volume",
    "volume_scope",
    "allocation_key",
    "source_file",
    "source_row_number",
]


def _text(value: Any) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


def _clean_header(value: Any) -> str:
    text = _text(value).replace("\ufeff", "").lower()
    text = re.sub(r"[_\r\n\t]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalise_subscriber(value: Any) -> tuple[str, str]:
    raw = _text(value)
    digits = re.sub(r"\D+", "", raw)

    if re.fullmatch(r"91[6-9]\d{9}", digits):
        return digits[-10:], "MSISDN"

    if re.fullmatch(r"[6-9]\d{9}", digits):
        return digits, "MSISDN"

    if re.fullmatch(r"\d{12,16}", digits):
        return digits, "NUMERIC_SUBSCRIBER_ID"

    if raw:
        return raw, "USER_ID"

    return "", "MISSING"


def _canonical_ip(value: Any) -> str:
    text = _text(value)

    if not text:
        return ""

    prefix = ""

    if "/" in text:
        text, prefix = text.split("/", 1)
        prefix = "/" + prefix

    try:
        return ipaddress.ip_address(text).compressed + prefix
    except ValueError:
        return _text(value)


def _ip_version(value: Any) -> str:
    text = _text(value)

    if not text:
        return ""

    try:
        address = text.split("/", 1)[0]
        return f"IPv{ipaddress.ip_address(address).version}"
    except ValueError:
        return "INVALID"


def _number(series: Any) -> pd.Series:
    index = (
        series.index
        if isinstance(series, (pd.Series, pd.DataFrame))
        else pd.RangeIndex(0)
    )
    safe = _as_series(series, index=index)
    return pd.to_numeric(safe, errors="coerce")


def _datetime(
    series: Any,
    *,
    dayfirst: bool = False,
) -> pd.Series:
    """Parse mixed operator date formats without dropping source rows."""

    index = (
        series.index
        if isinstance(series, (pd.Series, pd.DataFrame))
        else pd.RangeIndex(0)
    )
    safe = _as_series(series, index=index)
    text = (
        safe.where(safe.notna(), "")
        .astype(str)
        .str.strip()
        .replace(
            {
                "nan": "",
                "None": "",
                "NULL": "",
                "<NA>": "",
            }
        )
    )

    try:
        parsed = pd.to_datetime(
            text,
            errors="coerce",
            dayfirst=dayfirst,
            format="mixed",
        )
    except (TypeError, ValueError):
        parsed = pd.to_datetime(
            text,
            errors="coerce",
            dayfirst=dayfirst,
        )

    unresolved = parsed.isna() & text.ne("")

    if unresolved.any():
        try:
            retry = pd.to_datetime(
                text.loc[unresolved],
                errors="coerce",
                dayfirst=not dayfirst,
                format="mixed",
            )
        except (TypeError, ValueError):
            retry = pd.to_datetime(
                text.loc[unresolved],
                errors="coerce",
                dayfirst=not dayfirst,
            )

        parsed.loc[unresolved] = retry

    # Excel serial-date fallback for operator exports.
    unresolved = parsed.isna() & text.ne("")

    if unresolved.any():
        numeric = pd.to_numeric(
            text.loc[unresolved],
            errors="coerce",
        )
        excel_dates = numeric.between(
            20_000,
            80_000,
            inclusive="both",
        )

        if excel_dates.any():
            parsed.loc[numeric.index[excel_dates]] = pd.to_datetime(
                numeric.loc[excel_dates],
                unit="D",
                origin="1899-12-30",
                errors="coerce",
            )

    return parsed.reindex(index)


def _parse_jio_datetime(series: Any) -> pd.Series:
    """Parse Jio dd/MM/yyyy timestamps without month-first ambiguity."""

    index = series.index if isinstance(series, pd.Series) else pd.RangeIndex(0)
    text = _as_series(series, index=index).fillna("").astype(str).str.strip()
    parsed = pd.Series(pd.NaT, index=index, dtype="datetime64[ns]")

    formats = (
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    )
    unresolved = text.ne("")
    for format_string in formats:
        if not unresolved.any():
            break
        values = pd.to_datetime(
            text.loc[unresolved],
            format=format_string,
            errors="coerce",
        )
        accepted = values.notna()
        parsed.loc[values.index[accepted]] = values.loc[accepted]
        unresolved = parsed.isna() & text.ne("")

    return parsed


def _combine_datetime(date_series: pd.Series, time_series: pd.Series) -> pd.Series:
    combined = (
        date_series.fillna("").astype(str).str.strip()
        + " "
        + time_series.fillna("").astype(str).str.strip()
    ).str.strip()
    return _parse_jio_datetime(combined)


def _read_prefix(path: Path, size: int = 20000) -> str:
    raw = path.read_bytes()[:size]

    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            return raw.decode(encoding)
        except UnicodeError:
            continue

    return raw.decode("latin1", errors="replace")


def _csv_rows(path: Path, limit: int = 40) -> list[list[str]]:
    prefix = _read_prefix(path)
    lines = prefix.splitlines()[:limit]
    sample = "\n".join(lines[:20])

    try:
        delimiter = csv.Sniffer().sniff(
            sample,
            delimiters=",\t;|",
        ).delimiter
    except csv.Error:
        delimiter = ","

    return list(csv.reader(lines, delimiter=delimiter))


def _find_header_row(path: Path, required: set[str]) -> int:
    for index, row in enumerate(_csv_rows(path, limit=120)):
        cleaned = {_clean_header(value) for value in row}

        if required.issubset(cleaned):
            return index

    raise ValueError(
        f"Header row not found in {path.name}; required={sorted(required)}"
    )


def _find_airtel_header_row(path: Path) -> int:
    """Detect Airtel IPDR header without requiring optional Charging_ID."""

    for index, row in enumerate(_csv_rows(path, limit=160)):
        cleaned = {_clean_header(value) for value in row}

        has_subscriber = any(
            value in cleaned
            for value in (
                "msisdn userid",
                "msisdn user id",
                "msisdn",
            )
        )
        has_event = any(
            value in cleaned
            for value in (
                "event start time",
                "event time",
            )
        )
        has_source = any(
            value in cleaned
            for value in (
                "source public ipv4",
                "source public ipv6",
                "source private ipv4",
            )
        )
        has_destination = any(
            value in cleaned
            for value in (
                "destination ip4",
                "destination ip6",
                "destination ip",
            )
        )

        if has_subscriber and has_event and (has_source or has_destination):
            return index

    raise ValueError(
        f"Airtel IPDR header row not found in {path.name}. "
        "Required identity/event/IP columns were not detected."
    )


def _filename_public_query(
    path: Path,
) -> tuple[str, int | None]:
    """Extract public IP and port from common Airtel result filenames."""

    match = re.search(
        r"public[_\s-]*ip([46])[_\s-]+(.+?)"
        r"[_\s-]*public[_\s-]*port[_\s-]*(\d+)",
        path.stem,
        flags=re.I,
    )

    if not match:
        return "", None

    version = match.group(1)
    raw_ip = match.group(2).strip(" _-")
    port = int(match.group(3))

    if version == "6":
        raw_ip = raw_ip.replace(".", ":")
    else:
        raw_ip = raw_ip.replace("_", ".")

    return _canonical_ip(raw_ip), port


def _parse_airtel_query(
    path: Path,
    prefix: str,
) -> dict[str, Any]:
    """Parse Airtel query type, IP/MSISDN and optional public port."""

    query_type = ""
    query_value = ""
    query_port: int | None = None

    match = re.search(
        r"Dynamic\s+IPDR\s+OF\s+(.+?)\s*:\s*"
        r"(.+?)\s+from\s+(.+?)\s+to\s+([^\r\n]+)",
        prefix,
        flags=re.I,
    )

    if match:
        query_type = _text(match.group(1))
        payload = _text(match.group(2))

        port_match = re.search(
            r"(?:\bAND\s+)?PUBLIC\s+PORT\s*:\s*(\d+)",
            payload,
            flags=re.I,
        )

        if port_match:
            query_port = int(port_match.group(1))
            payload = re.sub(
                r"\s*(?:\bAND\s+)?PUBLIC\s+PORT\s*:\s*\d+\s*$",
                "",
                payload,
                flags=re.I,
            ).strip()

        query_value = _canonical_ip(payload)

    filename_ip, filename_port = _filename_public_query(path)

    if not query_value and filename_ip:
        query_value = filename_ip

    if query_port is None and filename_port is not None:
        query_port = filename_port

    type_text = _clean_header(query_type)
    name_text = _clean_header(path.name)

    if re.search(r"mobile|msisdn|subscriber", type_text, flags=re.I):
        scope = SCOPE_TARGET
    elif (
        re.search(r"public\s*ip|source\s*ip", type_text, flags=re.I)
        or "public ip" in name_text
        or query_port is not None
    ):
        scope = SCOPE_PUBLIC
    elif re.search(r"destination|dest", type_text, flags=re.I):
        scope = SCOPE_REVERSE
    elif re.search(r"\bip\b", type_text, flags=re.I):
        scope = SCOPE_REVERSE
    else:
        scope = SCOPE_UNKNOWN

    return {
        "query_type": query_type,
        "query_value": query_value,
        "query_port": query_port,
        "report_scope": scope,
    }


def _detect_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    name = path.name.lower()

    if re.search(r"cell\s*id[_\s-]*ipdrnat", name, flags=re.I):
        return {
            "source_format": FORMAT_TOWER,
            "operator": "Jio",
            "report_scope": "TOWER_IPDR_NAT",
            "query_value": "",
            "query_port": None,
            "header_row": 0,
        }

    if suffix in {".xlsx", ".xls"}:
        preview = pd.read_excel(path, sheet_name=0, nrows=5, dtype=str)
        cleaned = {_clean_header(column) for column in preview.columns}

        if {"search value", "from date", "to date", "port"}.issubset(cleaned):
            return {
                "source_format": FORMAT_SEARCH,
                "operator": "Airtel",
                "report_scope": SCOPE_SEARCH,
                "query_value": "",
                "header_row": 0,
            }

        return {
            "source_format": FORMAT_UNKNOWN,
            "operator": "",
            "report_scope": SCOPE_UNKNOWN,
            "query_value": "",
            "query_port": None,
            "header_row": 0,
        }

    prefix = _read_prefix(path)

    cleaned_prefix = _clean_header(prefix)

    if (
        "msisdn userid" in cleaned_prefix
        and "event start time" in cleaned_prefix
    ):
        header_row = _find_airtel_header_row(path)
        query = _parse_airtel_query(path, prefix)
        return {
            "source_format": FORMAT_AIRTEL,
            "operator": "Airtel",
            "report_scope": query["report_scope"],
            "query_value": query["query_value"],
            "query_port": query["query_port"],
            "query_type": query["query_type"],
            "header_row": header_row,
        }

    if "VIL Call Data Records" in prefix and "Destination IP" in prefix:
        header_row = _find_header_row(
            path,
            {"sr.no.", "msisdn", "destination ip"},
        )
        match = re.search(r"DESTIP\s*:-\s*([^\r\n]+)", prefix, flags=re.I)
        return {
            "source_format": FORMAT_VI,
            "operator": "Vi",
            "report_scope": SCOPE_REVERSE,
            "query_value": _canonical_ip(_text(match.group(1))) if match else "",
            "query_port": None,
            "header_row": header_row,
        }

    first_row = {_clean_header(value) for value in (_csv_rows(path, limit=2)[0] or [])}

    if {
        "source ip address",
        "destination ip address",
        "landline/msisdn/mdn/leased circuit id for internet access",
    }.issubset(first_row):
        return {
            "source_format": FORMAT_JIO,
            "operator": "Jio",
            "report_scope": SCOPE_UNKNOWN,
            "query_value": "",
            "query_port": None,
            "header_row": 0,
        }

    return {
        "source_format": FORMAT_UNKNOWN,
        "operator": "",
        "report_scope": SCOPE_UNKNOWN,
        "query_value": "",
        "header_row": 0,
    }


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=NORMALIZED_COLUMNS)


def _column_key(value: Any) -> str:
    """Create a duplicate-safe key for operator column matching."""

    key = _clean_header(value)
    key = re.sub(r"\.\d+$", "", key)
    key = re.sub(r"\s+", " ", key).strip()
    return key


def _as_series(
    value: Any,
    *,
    index: pd.Index,
) -> pd.Series:
    """Always return one Series, even when pandas returns duplicate columns."""

    if isinstance(value, pd.Series):
        return value.reindex(index)

    if isinstance(value, pd.DataFrame):
        if value.empty:
            return pd.Series("", index=index, dtype="object")

        candidates = value.reindex(index=index).copy()

        for name in candidates.columns:
            candidates[name] = (
                candidates[name]
                .where(candidates[name].notna(), "")
                .astype(str)
                .str.strip()
                .replace(
                    {
                        "nan": "",
                        "None": "",
                        "NULL": "",
                        "<NA>": "",
                    }
                )
            )

        # First non-blank value across duplicate/variant source columns.
        coalesced = candidates.replace("", pd.NA).bfill(axis=1).iloc[:, 0]
        return coalesced.fillna("").reindex(index)

    if value is None:
        return pd.Series("", index=index, dtype="object")

    if isinstance(value, (list, tuple)):
        return pd.Series(value, index=index)

    return pd.Series(value, index=index)


def _series(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return a single duplicate-safe source column.

    Operator exports can contain duplicate headers, pandas-generated `.1/.2`
    suffixes, leading spaces and minor underscore/space variations. Matching
    columns are coalesced left-to-right without dropping any raw rows.
    """

    target = _column_key(column)
    positions = [
        position
        for position, source_column in enumerate(frame.columns)
        if _column_key(source_column) == target
    ]

    if not positions:
        return pd.Series("", index=frame.index, dtype="object")

    if len(positions) == 1:
        return _as_series(
            frame.iloc[:, positions[0]],
            index=frame.index,
        )

    return _as_series(
        frame.iloc[:, positions],
        index=frame.index,
    )



AIRTEL_NON_DATA_PATTERNS = (
    r"\bno\s+records?\s+found\b",
    r"\bno\s+data\s+found\b",
    r"\bthis\s+is\s+(?:a\s+)?system\s+generated\s+report\b",
    r"\bsystem\s+generated\s+report\b",
    r"\breport\s+generated\s+(?:on|at|by)\b",
    r"\bend\s+of\s+report\b",
    r"\bpage\s+\d+\s+of\s+\d+\b",
    r"\btotal\s+(?:records?|rows?)\b",
)


def _clean_data_text(value: Any) -> str:
    text = _text(value)
    if text.lower() in {"nan", "none", "null", "<na>"}:
        return ""
    return text


def _row_text(frame: pd.DataFrame) -> pd.Series:
    """Build normalized text for footer/banner detection."""

    if frame.empty:
        return pd.Series("", index=frame.index, dtype="object")

    safe = frame.copy()

    for column in safe.columns:
        safe[column] = safe[column].map(_clean_data_text)

    return (
        safe.astype(str)
        .agg(" ".join, axis=1)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .str.lower()
    )


def _airtel_non_data_mask(frame: pd.DataFrame) -> pd.Series:
    """Identify Airtel report banners, footer rows and no-result markers."""

    text = _row_text(frame)
    mask = pd.Series(False, index=frame.index)

    for pattern in AIRTEL_NON_DATA_PATTERNS:
        mask = mask | text.str.contains(
            pattern,
            case=False,
            regex=True,
            na=False,
        )

    return mask


def _airtel_data_mask(
    frame: pd.DataFrame,
    event_time: pd.Series,
) -> tuple[pd.Series, dict[str, int | bool]]:
    """Return a conservative mask for genuine Airtel IPDR event rows.

    Airtel exports may append footer rows inside the CSV table, including
    ``No Records Found``, ``This is System generated report`` and report
    generation timestamps. Those rows must never become subscriber records.
    """

    if frame.empty:
        empty = pd.Series(False, index=frame.index)
        return empty, {
            "raw_rows_after_header": 0,
            "valid_data_rows": 0,
            "filtered_non_data_rows": 0,
            "footer_marker_rows": 0,
            "no_records_marker": False,
        }

    footer_mask = _airtel_non_data_mask(frame)

    subscriber_raw = (
        _series(frame, "MSISDN_userID")
        .map(_clean_data_text)
    )
    normalized_subscriber = subscriber_raw.map(
        lambda value: _normalise_subscriber(value)[0]
    )
    plausible_subscriber = normalized_subscriber.str.fullmatch(
        r"(?:[6-9]\d{9}|91[6-9]\d{9}|\d{12,16})",
        na=False,
    )

    imei = _series(frame, "IMEI").map(_clean_data_text)
    imsi = _series(frame, "IMSI").map(_clean_data_text)

    source_ipv4 = _series(
        frame,
        "Source_Public_IPv4",
    ).map(_clean_data_text)
    source_ipv6 = _series(
        frame,
        "Source_Public_IPv6",
    ).map(_clean_data_text)
    source_private = _series(
        frame,
        "Source_Private_IPV4",
    ).map(_clean_data_text)
    destination_ipv4 = _series(
        frame,
        "Destination_IP4",
    ).map(_clean_data_text)
    destination_ipv6 = _series(
        frame,
        "Destination_IP6",
    ).map(_clean_data_text)

    source_port = _series(
        frame,
        "Source_Public_Port",
    ).map(_clean_data_text)
    destination_port = _series(
        frame,
        "Destination_Port",
    ).map(_clean_data_text)
    charging_id = _series(
        frame,
        "Charging_ID",
    ).map(_clean_data_text)
    cgi = _series(frame, "CGI").map(_clean_data_text)

    session_start_raw = _series(
        frame,
        "Session_Start_Time",
    ).map(_clean_data_text)
    session_end_raw = _series(
        frame,
        "Session_End_Time",
    ).map(_clean_data_text)
    session_start = _datetime(session_start_raw)
    session_end = _datetime(session_end_raw)

    network_present = (
        source_ipv4.ne("")
        | source_ipv6.ne("")
        | source_private.ne("")
        | destination_ipv4.ne("")
        | destination_ipv6.ne("")
    )
    port_present = (
        source_port.ne("")
        | destination_port.ne("")
    )
    identity_present = (
        plausible_subscriber
        | imei.ne("")
        | imsi.ne("")
    )
    session_identifier_present = (
        charging_id.ne("")
        | cgi.ne("")
    )
    time_present = (
        event_time.notna()
        | session_start.notna()
        | session_end.notna()
    )

    # Strong IPDR evidence is required. A value in only the first source
    # column, such as a generated timestamp, is not treated as an event.
    genuine_row = (
        ~footer_mask
        & (
            (
                event_time.notna()
                & (
                    network_present
                    | port_present
                    | identity_present
                    | session_identifier_present
                )
            )
            | (
                network_present
                & identity_present
                & (
                    time_present
                    | port_present
                    | session_identifier_present
                )
            )
        )
    )

    row_text = _row_text(frame)
    no_records_marker = row_text.str.contains(
        r"\bno\s+(?:records?|data)\s+found\b",
        case=False,
        regex=True,
        na=False,
    )

    stats: dict[str, int | bool] = {
        "raw_rows_after_header": int(len(frame)),
        "valid_data_rows": int(genuine_row.sum()),
        "filtered_non_data_rows": int((~genuine_row).sum()),
        "footer_marker_rows": int(footer_mask.sum()),
        "no_records_marker": bool(no_records_marker.any()),
    }
    return genuine_row, stats


def _base_frame(length: int) -> pd.DataFrame:
    return pd.DataFrame(
        {column: pd.Series("", index=range(length), dtype="object")
         for column in NORMALIZED_COLUMNS}
    )


def _finalise(
    frame: pd.DataFrame,
    *,
    source_file: str,
    first_source_row: int,
    source_rows: pd.Series | None = None,
) -> pd.DataFrame:
    frame = frame.reindex(columns=NORMALIZED_COLUMNS)

    for column in (
        "subscriber_number_raw",
        "subscriber_number",
        "subscriber_identifier_type",
        "imei",
        "imsi",
        "source_ip",
        "source_public_ipv4",
        "source_public_ipv6",
        "source_private_ipv4",
        "translated_ip",
        "destination_ip",
        "destination_ipv4",
        "destination_ipv6",
        "charging_id",
        "apn",
        "gateway_ip",
        "first_cell_id",
        "last_cell_id",
        "cgi",
        "technology",
        "pre_post",
        "home_circle",
        "roaming_circle",
        "roaming_status",
    ):
        frame[column] = frame[column].fillna("").astype(str).str.strip()

    frame["source_ip"] = frame["source_ip"].map(_canonical_ip)
    frame["source_public_ipv4"] = frame["source_public_ipv4"].map(_canonical_ip)
    frame["source_public_ipv6"] = frame["source_public_ipv6"].map(_canonical_ip)
    frame["source_private_ipv4"] = frame["source_private_ipv4"].map(_canonical_ip)
    frame["translated_ip"] = frame["translated_ip"].map(_canonical_ip)
    frame["destination_ip"] = frame["destination_ip"].map(_canonical_ip)
    frame["destination_ipv4"] = frame["destination_ipv4"].map(_canonical_ip)
    frame["destination_ipv6"] = frame["destination_ipv6"].map(_canonical_ip)
    frame["source_ip_version"] = frame["source_ip"].map(_ip_version)
    frame["destination_ip_version"] = frame["destination_ip"].map(_ip_version)

    for column in (
        "source_port",
        "translated_port",
        "destination_port",
        "query_port",
        "session_duration_seconds",
        "uplink_volume",
        "downlink_volume",
        "latitude",
        "longitude",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    for column in (
        "event_time",
        "session_start",
        "session_end",
        "allocation_start",
        "allocation_end",
    ):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")

    frame["source_file"] = source_file
    if source_rows is not None and len(source_rows) == len(frame):
        frame["source_row_number"] = pd.to_numeric(
            source_rows.reset_index(drop=True), errors="coerce"
        ).astype("Int64")
    else:
        frame["source_row_number"] = range(
            first_source_row,
            first_source_row + len(frame),
        )

    key_columns = [
        "operator",
        "subscriber_number",
        "source_ip",
        "allocation_start",
        "allocation_end",
        "session_start",
        "session_end",
        "charging_id",
        "imei",
        "imsi",
    ]

    if frame.empty:
        # pandas DataFrame.agg(axis=1) returns another DataFrame for an
        # empty input. Assigning that object to one column causes the
        # misleading "Columns must be same length as key" error.
        frame["allocation_key"] = pd.Series(
            index=frame.index,
            dtype="object",
        )
    else:
        frame["allocation_key"] = (
            frame[key_columns]
            .fillna("")
            .astype(str)
            .agg("|".join, axis=1)
        )

    return frame


def _load_airtel(
    path: Path,
    metadata: dict[str, Any],
) -> pd.DataFrame:
    """Load Airtel IPDR with duplicate-column and stage diagnostics."""

    stage = "read CSV"

    try:
        header_row = int(metadata["header_row"])
        raw, parser_rejects, ingestion_metadata = read_csv_with_quarantine(
            path,
            skiprows=header_row,
            sep=",",
        )

        stage = "event-time extraction"
        event_source = _series(
            raw,
            "Event_Start_Time",
        )
        event_time = _datetime(event_source)

        stage = "Airtel data-row classification"
        data_row, row_stats = _airtel_data_mask(
            raw,
            event_time,
        )
        metadata.update(row_stats)

        validation_rejects = quarantine_dataframe_rows(
            raw,
            ~data_row,
            source_file=path,
            reason="NON_DATA_OR_INVALID_AIRTEL_IPDR_ROW",
        )
        source_rows = raw.loc[data_row, "_source_row_number"].reset_index(drop=True)
        raw = raw.loc[data_row].reset_index(drop=True)
        event_time = event_time.loc[data_row].reset_index(drop=True)

        stage = "normalized-frame creation"
        frame = _base_frame(len(raw))

        stage = "subscriber normalization"
        subscriber_source = _series(
            raw,
            "MSISDN_userID",
        )
        numbers = subscriber_source.map(
            _normalise_subscriber
        )

        frame["record_type"] = "IPDR_EVENT"
        frame["operator"] = "Airtel"
        frame["source_format"] = FORMAT_AIRTEL
        frame["report_scope"] = metadata["report_scope"]
        frame["query_value"] = metadata.get(
            "query_value",
            "",
        )
        frame["query_port"] = metadata.get(
            "query_port",
            None,
        )
        frame["subscriber_number_raw"] = subscriber_source
        frame["subscriber_number"] = numbers.map(
            lambda item: item[0]
        )
        frame["subscriber_identifier_type"] = numbers.map(
            lambda item: item[1]
        )

        stage = "identity fields"
        frame["imei"] = _series(raw, "IMEI")
        frame["imsi"] = _series(raw, "IMSI")

        stage = "session timestamps"
        frame["event_time"] = event_time
        frame["session_start"] = _datetime(
            _series(raw, "Session_Start_Time")
        )
        frame["session_end"] = _datetime(
            _series(raw, "Session_End_Time")
        )
        frame["allocation_start"] = frame[
            "session_start"
        ]
        frame["allocation_end"] = frame[
            "session_end"
        ]
        frame["session_duration_seconds"] = _number(
            _series(raw, "Duration")
        )

        stage = "source IP fields"
        frame["source_public_ipv4"] = _series(
            raw,
            "Source_Public_IPv4",
        )
        frame["source_public_ipv6"] = _series(
            raw,
            "Source_Public_IPv6",
        )
        frame["source_private_ipv4"] = _series(
            raw,
            "Source_Private_IPV4",
        )
        source_ipv4 = frame[
            "source_public_ipv4"
        ].fillna("").astype(str).str.strip()
        frame["source_ip"] = frame[
            "source_public_ipv4"
        ].where(
            source_ipv4.ne(""),
            frame["source_public_ipv6"],
        )
        frame["source_port"] = _number(
            _series(raw, "Source_Public_Port")
        )

        stage = "destination IP fields"
        frame["destination_ipv4"] = _series(
            raw,
            "Destination_IP4",
        )
        frame["destination_ipv6"] = _series(
            raw,
            "Destination_IP6",
        )
        destination_ipv4 = frame[
            "destination_ipv4"
        ].fillna("").astype(str).str.strip()
        frame["destination_ip"] = frame[
            "destination_ipv4"
        ].where(
            destination_ipv4.ne(""),
            frame["destination_ipv6"],
        )
        frame["destination_port"] = _number(
            _series(raw, "Destination_Port")
        )

        stage = "session metadata"
        frame["charging_id"] = _series(
            raw,
            "Charging_ID",
        )
        frame["apn"] = _series(
            raw,
            "Access_Point_Name",
        )
        frame["gateway_ip"] = _series(
            raw,
            "PACO_GW_IP",
        )

        stage = "cell and coordinate fields"
        frame["cgi"] = _series(raw, "CGI")
        frame["first_cell_id"] = frame["cgi"]
        frame["last_cell_id"] = frame["cgi"]
        frame["latitude"] = _number(
            _series(raw, "CGI Latitude")
        )
        frame["longitude"] = _number(
            _series(raw, "CGI Longitude")
        )

        stage = "subscriber attributes"
        frame["technology"] = _series(
            raw,
            "2g/4g/5g",
        )
        frame["pre_post"] = _series(
            raw,
            "Pre_Post",
        )
        frame["home_circle"] = _series(
            raw,
            "Home_Circle",
        )
        frame["roaming_circle"] = _series(
            raw,
            "Roaming_Circle",
        )

        stage = "volume fields"
        frame["uplink_volume"] = _number(
            _series(raw, "Uplink_Vol")
        )
        frame["downlink_volume"] = _number(
            _series(raw, "Downlink_Vol")
        )
        frame["volume_scope"] = "SESSION"

        stage = "final normalization"
        output = _finalise(
            frame,
            source_file=path.name,
            first_source_row=header_row + 2,
            source_rows=source_rows,
        )
        output.attrs["rejected_rows"] = pd.concat(
            [parser_rejects, validation_rejects],
            ignore_index=True,
        )
        output.attrs["ingestion_metadata"] = ingestion_metadata
        return output

    except Exception as error:
        duplicate_keys = sorted(
            {
                _column_key(column)
                for column in raw.columns
                if sum(
                    1
                    for candidate in raw.columns
                    if _column_key(candidate)
                    == _column_key(column)
                )
                > 1
            }
        ) if "raw" in locals() else []

        raise ValueError(
            f"Airtel IPDR load failed at stage '{stage}'. "
            f"Duplicate/variant column groups={duplicate_keys or 'None'}. "
            f"Original error: {type(error).__name__}: {error}"
        ) from error


def _load_vi(path: Path, metadata: dict[str, Any]) -> pd.DataFrame:
    header_row = int(metadata["header_row"])
    raw, parser_rejects, ingestion_metadata = read_csv_with_quarantine(
        path,
        skiprows=header_row,
        sep=",",
    )
    event_time = _datetime(
        _series(raw, "Session Start date & time"),
        dayfirst=True,
    )
    valid = event_time.notna()
    validation_rejects = quarantine_dataframe_rows(
        raw,
        ~valid,
        source_file=path,
        reason="NON_DATA_OR_INVALID_VI_IPDR_TIMESTAMP",
    )
    source_rows = raw.loc[valid, "_source_row_number"].reset_index(drop=True)
    raw = raw.loc[valid].reset_index(drop=True)
    event_time = event_time.loc[valid].reset_index(drop=True)
    frame = _base_frame(len(raw))
    numbers = _series(raw, "MSISDN").map(_normalise_subscriber)

    source = _series(raw, "Source IP")
    destination = _series(raw, "Destination IP")
    frame["record_type"] = "IPDR_EVENT"
    frame["operator"] = "Vi"
    frame["source_format"] = FORMAT_VI
    frame["report_scope"] = SCOPE_REVERSE
    frame["query_value"] = metadata.get("query_value", "")
    frame["subscriber_number_raw"] = _series(raw, "MSISDN")
    frame["subscriber_number"] = numbers.map(lambda item: item[0])
    frame["subscriber_identifier_type"] = numbers.map(lambda item: item[1])
    frame["imei"] = _series(raw, "IMEI")
    frame["imsi"] = _series(raw, "IMSI")
    frame["event_time"] = event_time
    frame["session_start"] = event_time
    frame["session_end"] = _datetime(
        _series(raw, "Session End date & time"),
        dayfirst=True,
    )
    frame["allocation_start"] = frame["session_start"]
    frame["allocation_end"] = frame["session_end"]
    frame["session_duration_seconds"] = _number(
        _series(raw, "Duration in sec")
    )
    frame["source_ip"] = source
    frame["source_public_ipv4"] = source.where(
        source.map(_ip_version).eq("IPv4"),
        "",
    )
    frame["source_public_ipv6"] = source.where(
        source.map(_ip_version).eq("IPv6"),
        "",
    )
    frame["source_port"] = _number(_series(raw, "Source Port"))
    frame["translated_ip"] = _series(raw, "Translated IP")
    frame["translated_port"] = _number(_series(raw, "Translated Port"))
    frame["destination_ip"] = destination
    frame["destination_ipv4"] = destination.where(
        destination.map(_ip_version).eq("IPv4"),
        "",
    )
    frame["destination_ipv6"] = destination.where(
        destination.map(_ip_version).eq("IPv6"),
        "",
    )
    frame["destination_port"] = _number(_series(raw, "Destination Port"))
    frame["charging_id"] = _series(raw, "Charging ID")
    frame["apn"] = _series(raw, "Access Point Name")
    frame["gateway_ip"] = _series(raw, "PGW IP address")
    frame["first_cell_id"] = _series(raw, "First Cell ID-Name/Location")
    frame["last_cell_id"] = frame["first_cell_id"]
    frame["cgi"] = _series(raw, "CGI-ld")
    frame["technology"] = _series(raw, "RAT")
    frame["uplink_volume"] = _number(_series(raw, "Data Volume Uplink"))
    frame["downlink_volume"] = _number(_series(raw, "Data Volume Downlink"))
    frame["volume_scope"] = "SESSION"
    output = _finalise(
        frame,
        source_file=path.name,
        first_source_row=header_row + 2,
        source_rows=source_rows,
    )
    output.attrs["rejected_rows"] = pd.concat(
        [parser_rejects, validation_rejects],
        ignore_index=True,
    )
    output.attrs["ingestion_metadata"] = ingestion_metadata
    return output


def _load_jio(path: Path, metadata: dict[str, Any]) -> pd.DataFrame:
    raw, parser_rejects, ingestion_metadata = read_csv_with_quarantine(
        path,
        skiprows=0,
        sep=",",
    )
    subscriber_column = (
        "Landline/MSISDN/MDN/Leased Circuit ID for Internet Access"
    )
    event_column = "TIME1 (dd/MM/yyyy HH:mm:ss)"
    duration_column = (
        "Session Duration (Seconds)"
        if "Session Duration (Seconds)" in raw.columns
        else "Session Duration"
    )
    uplink_column = (
        "Data Volume Up Link"
        if "Data Volume Up Link" in raw.columns
        else "Data Volume Up LinkData"
    )
    downlink_column = (
        "Data Volume Down Link"
        if "Data Volume Down Link" in raw.columns
        else "Volume Down Link"
    )

    event_time = _parse_jio_datetime(_series(raw, event_column))
    has_events = event_time.notna().any()
    identifiers = _series(raw, subscriber_column).dropna().astype(str).str.strip()
    numeric_identifiers = identifiers.str.fullmatch(r"\d{10,15}", na=False)
    scope = (
        SCOPE_TARGET
        if has_events and numeric_identifiers.any()
        else SCOPE_BROADBAND
        if not has_events
        else SCOPE_UNKNOWN
    )
    metadata["report_scope"] = scope
    metadata["query_value"] = (
        identifiers.iloc[0]
        if len(identifiers) and identifiers.nunique() == 1
        else ""
    )

    valid = (
        event_time.notna()
        if has_events
        else _combine_datetime(
            _series(raw, "Start Date of Public IP Address allocation (dd/mm/yyyy)"),
            _series(raw, "IST Start Time of Public IP address allocation (hh:mm:ss)"),
        ).notna()
    )
    validation_rejects = quarantine_dataframe_rows(
        raw,
        ~valid,
        source_file=path,
        reason="NON_DATA_OR_INVALID_JIO_IPDR_TIMESTAMP",
    )
    source_rows = raw.loc[valid, "_source_row_number"].reset_index(drop=True)
    raw = raw.loc[valid].reset_index(drop=True)
    event_time = event_time.loc[valid].reset_index(drop=True)
    frame = _base_frame(len(raw))
    numbers = _series(raw, subscriber_column).map(_normalise_subscriber)
    allocation_start = _combine_datetime(
        _series(raw, "Start Date of Public IP Address allocation (dd/mm/yyyy)"),
        _series(raw, "IST Start Time of Public IP address allocation (hh:mm:ss)"),
    )
    allocation_end = _combine_datetime(
        _series(raw, "End Date of Public IP address allocation (dd/mm/yyyy)"),
        _series(raw, "IST End Time of Public IP address allocation (hh:mm:ss)"),
    )
    source = _series(raw, "Source IP Address")
    destination = _series(raw, "Destination IP Address")

    frame["record_type"] = "IPDR_EVENT" if has_events else "IP_ALLOCATION"
    frame["operator"] = "Jio"
    frame["source_format"] = FORMAT_JIO
    frame["report_scope"] = scope
    frame["query_value"] = metadata.get("query_value", "")
    frame["subscriber_number_raw"] = _series(raw, subscriber_column)
    frame["subscriber_number"] = numbers.map(lambda item: item[0])
    frame["subscriber_identifier_type"] = numbers.map(lambda item: item[1])
    frame["imei"] = _series(
        raw,
        "Source MAC-ID Address/Other device Identification number",
    )
    frame["imsi"] = _series(raw, "IMSI")
    frame["event_time"] = event_time
    frame["session_start"] = allocation_start
    frame["session_end"] = allocation_end
    frame["allocation_start"] = allocation_start
    frame["allocation_end"] = allocation_end
    frame["session_duration_seconds"] = _number(
        _series(raw, duration_column)
    )
    frame["source_ip"] = source
    frame["source_public_ipv4"] = source.where(
        source.map(_ip_version).eq("IPv4"),
        "",
    )
    frame["source_public_ipv6"] = source.where(
        source.map(_ip_version).eq("IPv6"),
        "",
    )
    frame["source_port"] = _number(_series(raw, "Source Port"))
    frame["translated_ip"] = _series(raw, "Translated IP Address")
    frame["translated_port"] = _number(_series(raw, "Translated Port"))
    frame["destination_ip"] = destination
    frame["destination_ipv4"] = destination.where(
        destination.map(_ip_version).eq("IPv4"),
        "",
    )
    frame["destination_ipv6"] = destination.where(
        destination.map(_ip_version).eq("IPv6"),
        "",
    )
    frame["destination_port"] = _number(_series(raw, "Destination Port"))
    frame["apn"] = _series(raw, "Access Point Name")
    frame["gateway_ip"] = _series(raw, "PGW IP address")
    frame["first_cell_id"] = _series(raw, "First CELL ID")
    frame["last_cell_id"] = _series(raw, "Last CELL ID")
    frame["cgi"] = frame["first_cell_id"]
    frame["roaming_status"] = _series(raw, "Roaming Circle Indicator")
    frame["roaming_circle"] = _series(raw, "Roaming Circle")
    frame["uplink_volume"] = _number(_series(raw, uplink_column))
    frame["downlink_volume"] = _number(_series(raw, downlink_column))
    frame["volume_scope"] = "ALLOCATION"
    output = _finalise(
        frame,
        source_file=path.name,
        first_source_row=2,
        source_rows=source_rows,
    )
    output.attrs["rejected_rows"] = pd.concat(
        [parser_rejects, validation_rejects],
        ignore_index=True,
    )
    output.attrs["ingestion_metadata"] = ingestion_metadata
    return output


def _load_search_request(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=0, dtype=str)
    cleaned = {_clean_header(column): column for column in raw.columns}

    def column(name: str) -> pd.Series:
        source = cleaned.get(name)
        return _series(raw, source) if source else pd.Series("", index=raw.index)

    result = pd.DataFrame(
        {
            "search_value": column("search value").map(_canonical_ip),
            "from_datetime": _datetime(column("from date")),
            "to_datetime": _datetime(column("to date")),
            "port": _number(column("port")),
            "operator": "Airtel",
            "request_type": "REVERSE_IPV4_LOOKUP",
            "source_file": path.name,
            "source_row_number": range(2, len(raw) + 2),
        }
    )
    return result[result["search_value"].fillna("").astype(str).str.strip().ne("")]


def load_ipdr_file(path: str | Path) -> dict[str, Any]:
    file_path = Path(path).expanduser().resolve()

    if not file_path.is_file():
        raise FileNotFoundError(file_path)

    metadata = _detect_file(file_path)
    source_format = metadata["source_format"]

    if source_format == FORMAT_TOWER:
        return {
            "ok": False,
            "file": str(file_path),
            "file_name": file_path.name,
            "metadata": metadata,
            "data": _empty_frame(),
            "search_requests": pd.DataFrame(),
            "warning": (
                "Tower IPDR/NAT file detected. Use Tower Dump Analysis > "
                "Tower IPDR Dump Analysis."
            ),
            "error": "",
        }

    if source_format == FORMAT_SEARCH:
        requests = _load_search_request(file_path)
        return {
            "ok": True,
            "file": str(file_path),
            "file_name": file_path.name,
            "metadata": metadata,
            "data": _empty_frame(),
            "search_requests": requests,
            "warning": (
                "Search-request workbook detected; it contains lookup inputs, "
                "not IPDR result events."
            ),
            "error": "",
        }

    if source_format == FORMAT_AIRTEL:
        data = _load_airtel(file_path, metadata)
    elif source_format == FORMAT_VI:
        data = _load_vi(file_path, metadata)
    elif source_format == FORMAT_JIO:
        data = _load_jio(file_path, metadata)
    else:
        return {
            "ok": False,
            "file": str(file_path),
            "file_name": file_path.name,
            "metadata": metadata,
            "data": _empty_frame(),
            "search_requests": pd.DataFrame(),
            "warning": "",
            "error": "Unsupported or unverified IPDR format.",
        }

    rejected_rows = data.attrs.get("rejected_rows", empty_reject_ledger())
    ingestion_metadata = data.attrs.get("ingestion_metadata", {})
    metadata["rejected_rows"] = int(len(rejected_rows))
    metadata["adjusted_rows"] = int(ingestion_metadata.get("adjusted_rows", 0))

    return {
        "ok": True,
        "file": str(file_path),
        "file_name": file_path.name,
        "metadata": metadata,
        "data": data,
        "rejected_rows": rejected_rows.reset_index(drop=True),
        "search_requests": pd.DataFrame(),
        "warning": "",
        "error": "",
    }



def _concat_ipdr_frames_safely(
    frames: list[pd.DataFrame],
    *,
    ignore_index: bool = True,
    sort: bool = False,
) -> pd.DataFrame:
    """
    Safely concatenate IPDR DataFrames.

    Pandas compares DataFrame.attrs during concat. Some loader stages may carry
    non-scalar attrs, including DataFrame objects, which can raise:
    ValueError: The truth value of a DataFrame is ambiguous.

    Investigator data remains unchanged; only temporary internal attrs metadata
    is cleared before concat.
    """

    clean_frames: list[pd.DataFrame] = []

    if frames is None:
        return pd.DataFrame()

    for frame in frames:
        if not isinstance(frame, pd.DataFrame):
            continue

        try:
            frame.attrs = {}
        except Exception:
            pass

        clean_frames.append(frame)

    if not clean_frames:
        return pd.DataFrame()

    combined = pd.concat(
        clean_frames,
        ignore_index=ignore_index,
        sort=sort,
    )

    try:
        combined.attrs = {}
    except Exception:
        pass

    return combined

def load_ipdr_case(
    folder: str | Path,
    *,
    recursive: bool = True,
) -> dict[str, Any]:
    directory = Path(folder).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    iterator = directory.rglob("*") if recursive else directory.glob("*")
    files = sorted(
        (
            path
            for path in iterator
            if path.is_file()
            and path.suffix.lower() in SUPPORTED_SUFFIXES
        ),
        key=lambda path: (
            len(path.name),
            path.name.lower(),
        ),
    )

    frames: list[pd.DataFrame] = []
    requests: list[pd.DataFrame] = []
    summaries: list[dict[str, Any]] = []
    file_results: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []
    reject_frames: list[pd.DataFrame] = []
    seen_hashes: dict[str, Path] = {}

    for path in files:
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()

            if digest in seen_hashes:
                original = seen_hashes[digest]
                summaries.append(
                    {
                        "file_name": path.name,
                        "source_format": "DUPLICATE_FILE",
                        "operator": "",
                        "report_scope": "",
                        "query_value": "",
                        "query_port": None,
                        "records_loaded": 0,
                        "search_requests": 0,
                        "raw_rows_after_header": 0,
                        "filtered_non_data_rows": 0,
                        "footer_marker_rows": 0,
                        "no_records_marker": False,
                        "status": "DUPLICATE_SKIPPED",
                        "file_size_bytes": path.stat().st_size,
                        "source_path": str(path),
                        "sha256": digest,
                    }
                )
                warnings.append(
                    f"{path.name}: exact duplicate of {original.name}; skipped."
                )
                continue

            seen_hashes[digest] = path
            result = load_ipdr_file(path)
            result["sha256"] = digest
            file_results.append(result)
            metadata = result["metadata"]
            data = result["data"]
            request_data = result["search_requests"]
            rejected = result.get("rejected_rows")
            if isinstance(rejected, pd.DataFrame) and not rejected.empty:
                reject_frames.append(rejected)

            if isinstance(data, pd.DataFrame) and not data.empty:
                frames.append(data)

            if isinstance(request_data, pd.DataFrame) and not request_data.empty:
                requests.append(request_data)

            if result["ok"]:
                file_status = (
                    "LOADED"
                    if len(data) or len(request_data)
                    else "LOADED_EMPTY"
                )
            else:
                file_status = "ROUTED/REJECTED"

            summaries.append(
                {
                    "file_name": path.name,
                    "source_format": metadata.get("source_format", ""),
                    "operator": metadata.get("operator", ""),
                    "report_scope": metadata.get("report_scope", ""),
                    "query_value": metadata.get("query_value", ""),
                    "query_port": metadata.get("query_port", None),
                    "records_loaded": len(data),
                    "search_requests": len(request_data),
                    "raw_rows_after_header": metadata.get(
                        "raw_rows_after_header",
                        len(data),
                    ),
                    "filtered_non_data_rows": metadata.get(
                        "filtered_non_data_rows",
                        0,
                    ),
                    "footer_marker_rows": metadata.get(
                        "footer_marker_rows",
                        0,
                    ),
                    "no_records_marker": metadata.get(
                        "no_records_marker",
                        False,
                    ),
                    "status": file_status,
                    "file_size_bytes": path.stat().st_size,
                    "source_path": str(path),
                    "sha256": digest,
                }
            )

            filtered_rows = int(
                metadata.get(
                    "filtered_non_data_rows",
                    0,
                )
                or 0
            )

            if filtered_rows:
                warnings.append(
                    f"{path.name}: {filtered_rows} report/footer/non-data "
                    "row(s) excluded from IPDR events."
                )

            if file_status == "LOADED_EMPTY":
                warnings.append(
                    f"{path.name}: valid IPDR query report loaded with "
                    "zero genuine result rows."
                )

            if result.get("warning"):
                warnings.append(f"{path.name}: {result['warning']}")

            if result.get("error"):
                errors.append(f"{path.name}: {result['error']}")

        except Exception as error:
            errors.append(
                f"{path.name}: {type(error).__name__}: {error}"
            )
            summaries.append(
                {
                    "file_name": path.name,
                    "source_format": "",
                    "operator": "",
                    "report_scope": "",
                    "query_value": "",
                    "query_port": None,
                    "records_loaded": 0,
                    "search_requests": 0,
                    "raw_rows_after_header": 0,
                    "filtered_non_data_rows": 0,
                    "footer_marker_rows": 0,
                    "no_records_marker": False,
                    "status": "FAILED",
                    "file_size_bytes": path.stat().st_size,
                    "source_path": str(path),
                    "sha256": "",
                }
            )

    data = (
        _concat_ipdr_frames_safely(frames, ignore_index=True, sort=False)
        if frames
        else _empty_frame()
    )
    search_requests = (
        pd.concat(requests, ignore_index=True, sort=False)
        if requests
        else pd.DataFrame(
            columns=[
                "search_value",
                "from_datetime",
                "to_datetime",
                "port",
                "operator",
                "request_type",
                "source_file",
                "source_row_number",
            ]
        )
    )
    file_summary = pd.DataFrame(summaries)

    processed_statuses = {
        "LOADED",
        "LOADED_EMPTY",
    }
    processed_files = (
        int(
            file_summary["status"]
            .isin(processed_statuses)
            .sum()
        )
        if not file_summary.empty
        else 0
    )

    return {
        "ok": bool(processed_files),
        "folder": str(directory),
        "data": data,
        "search_requests": search_requests,
        "file_summary": file_summary,
        "file_results": file_results,
        "rejected_rows": (
            pd.concat(reject_frames, ignore_index=True)
            if reject_frames
            else empty_reject_ledger()
        ),
        "warnings": warnings,
        "errors": errors,
        "metadata": {
            "files_found": len(files),
            "files_loaded": processed_files,
            "empty_result_files": int(
                file_summary["status"].eq("LOADED_EMPTY").sum()
            ) if not file_summary.empty else 0,
            "files_failed": int((file_summary["status"] == "FAILED").sum())
            if not file_summary.empty else 0,
            "event_records": int((data["record_type"] == "IPDR_EVENT").sum())
            if not data.empty else 0,
            "allocation_records": int((data["record_type"] == "IP_ALLOCATION").sum())
            if not data.empty else 0,
            "total_records": len(data),
            "search_requests": len(search_requests),
            "rejected_rows": int(sum(len(item) for item in reject_frames)),
            "operators": sorted(
                value
                for value in data["operator"].dropna().astype(str).unique()
                if value
            ) if not data.empty else [],
            "scopes": sorted(
                value
                for value in data["report_scope"].dropna().astype(str).unique()
                if value
            ) if not data.empty else [],
        },
    }


# JIO_DYNAMIC_IPDR_FALLBACK_V1
def _looks_like_jio_dynamic_ipdr_csv(path: str | Path) -> bool:
    try:
        sample = Path(path).read_text(encoding="utf-8", errors="ignore")[:4000]
    except Exception:
        return False

    required_markers = [
        "Landline/MSISDN/MDN/Leased Circuit ID for Internet Access",
        "Source IP Address",
        "Destination IP Address",
        "TIME1 (dd/MM/yyyy HH:mm:ss)",
        "First CELL ID",
        "Last CELL ID",
    ]

    return all(marker in sample for marker in required_markers)


def _combine_jio_date_time(
    dataframe: pd.DataFrame,
    date_column: str,
    time_column: str,
) -> pd.Series:
    date_values = (
        dataframe.get(date_column, "")
        .astype(str)
        .str.strip()
    )
    time_values = (
        dataframe.get(time_column, "")
        .astype(str)
        .str.strip()
    )

    combined = date_values + " " + time_values

    return pd.to_datetime(
        combined,
        errors="coerce",
        yearfirst=True,
    )


def _load_jio_dynamic_ipdr_csv_fallback(path: str | Path) -> dict[str, Any]:
    source_path = Path(path)

    try:
        raw = pd.read_csv(
            source_path,
            dtype=str,
            keep_default_na=False,
        )
    except Exception as error:
        return {
            "ok": False,
            "file": str(source_path),
            "data": pd.DataFrame(),
            "search_requests": pd.DataFrame(),
            "rejected_rows": pd.DataFrame(),
            "warnings": [],
            "errors": [f"Jio dynamic IPDR fallback read failed: {error}"],
            "metadata": {
                "operator": "Jio",
                "source_format": "JIO_DYNAMIC_IPDR",
                "source_file": str(source_path),
            },
        }

    if raw.empty:
        return {
            "ok": True,
            "file": str(source_path),
            "data": pd.DataFrame(),
            "search_requests": pd.DataFrame(),
            "rejected_rows": pd.DataFrame(),
            "warnings": [
                f"{source_path.name}: valid Jio IPDR file loaded with zero rows."
            ],
            "errors": [],
            "metadata": {
                "operator": "Jio",
                "source_format": "JIO_DYNAMIC_IPDR",
                "report_scope": "JIO_DYNAMIC_IPDR",
                "total_records": 0,
                "source_file": str(source_path),
            },
        }

    raw.columns = [str(column).strip() for column in raw.columns]

    normalized = pd.DataFrame()

    normalized["subscriber_number"] = (
        raw.get("Landline/MSISDN/MDN/Leased Circuit ID for Internet Access", "")
        .astype(str)
        .str.strip()
    )
    normalized["subscriber_identifier_type"] = "MSISDN"

    normalized["user_id"] = (
        raw.get("User Id for internet Access based on authentication", "")
        .astype(str)
        .str.strip()
    )

    normalized["source_ip"] = (
        raw.get("Source IP Address", "")
        .astype(str)
        .str.strip()
    )
    normalized["source_port"] = (
        raw.get("Source Port", "")
        .astype(str)
        .str.strip()
    )

    normalized["translated_ip"] = (
        raw.get("Translated IP Address", "")
        .astype(str)
        .str.strip()
    )
    normalized["translated_port"] = (
        raw.get("Translated Port", "")
        .astype(str)
        .str.strip()
    )

    normalized["destination_ip"] = (
        raw.get("Destination IP Address", "")
        .astype(str)
        .str.strip()
    )
    normalized["destination_port"] = (
        raw.get("Destination Port", "")
        .astype(str)
        .str.strip()
    )

    normalized["allocation_type"] = (
        raw.get("Static/Dynamic IP Address Allocation", "")
        .astype(str)
        .str.strip()
    )

    normalized["allocation_start"] = _combine_jio_date_time(
        raw,
        "Start Date of Public IP Address allocation (dd/mm/yyyy)",
        "IST Start Time of Public IP address allocation (hh:mm:ss)",
    )
    normalized["allocation_end"] = _combine_jio_date_time(
        raw,
        "End Date of Public IP address allocation (dd/mm/yyyy)",
        "IST End Time of Public IP address allocation (hh:mm:ss)",
    )

    normalized["event_time"] = pd.to_datetime(
        raw.get("TIME1 (dd/MM/yyyy HH:mm:ss)", "")
        .astype(str)
        .str.strip(),
        errors="coerce",
        yearfirst=True,
    )

    normalized["imei"] = (
        raw.get("Source MAC-ID Address/Other device Identification number", "")
        .astype(str)
        .str.strip()
    )
    normalized["imsi"] = (
        raw.get("IMSI", "")
        .astype(str)
        .str.strip()
    )

    normalized["pgw_ip"] = (
        raw.get("PGW IP address", "")
        .astype(str)
        .str.strip()
    )
    normalized["apn"] = (
        raw.get("Access Point Name", "")
        .astype(str)
        .str.strip()
    )

    normalized["first_cell_id"] = (
        raw.get("First CELL ID", "")
        .astype(str)
        .str.strip()
    )
    normalized["last_cell_id"] = (
        raw.get("Last CELL ID", "")
        .astype(str)
        .str.strip()
    )
    normalized["cell_id"] = normalized["first_cell_id"]

    normalized["duration_seconds"] = pd.to_numeric(
        raw.get("Session Duration (Seconds)", ""),
        errors="coerce",
    )
    normalized["uplink_volume"] = pd.to_numeric(
        raw.get("Data Volume Up Link", ""),
        errors="coerce",
    )
    normalized["downlink_volume"] = pd.to_numeric(
        raw.get("Data Volume Down Link", ""),
        errors="coerce",
    )

    normalized["roaming_circle_indicator"] = (
        raw.get("Roaming Circle Indicator", "")
        .astype(str)
        .str.strip()
    )
    normalized["roaming_circle"] = (
        raw.get("Roaming Circle", "")
        .astype(str)
        .str.strip()
    )
    normalized["sim_type"] = (
        raw.get("SIM Type", "")
        .astype(str)
        .str.strip()
    )

    normalized["operator"] = "Jio"
    normalized["source_format"] = "JIO_DYNAMIC_IPDR"
    normalized["report_scope"] = "JIO_DYNAMIC_IPDR"
    normalized["source_file"] = str(source_path)
    normalized["source_file_name"] = source_path.name
    normalized["raw_row_number"] = range(1, len(normalized) + 1)

    # Jio dynamic IPDR rows are real internet activity rows, not empty
    # allocation-only rows. These aliases help the common IPDR analysis
    # engine count them as event records.
    normalized["is_allocation_only"] = False
    normalized["record_type"] = "EVENT"
    normalized["row_type"] = "EVENT"
    normalized["event_type"] = "IPDR_EVENT"
    normalized["ipdr_record_type"] = "EVENT"

    normalized["event_start_time"] = normalized["event_time"]
    normalized["session_start"] = normalized["event_time"]
    normalized["session_end"] = normalized["event_time"]
    normalized["start_time"] = normalized["event_time"]
    normalized["end_time"] = normalized["event_time"]

    normalized["cgi"] = normalized["first_cell_id"]
    normalized["cell_id"] = normalized["first_cell_id"]
    normalized["searched_cell_id"] = normalized["first_cell_id"]

    normalized["total_volume"] = (
        normalized["uplink_volume"].fillna(0)
        + normalized["downlink_volume"].fillna(0)
    )

    event_mask = (
        normalized["subscriber_number"].astype(str).str.strip().ne("")
        & normalized["source_ip"].astype(str).str.strip().ne("")
        & normalized["destination_ip"].astype(str).str.strip().ne("")
        & normalized["event_time"].notna()
    )

    rejected_rows = raw.loc[~event_mask].copy()
    normalized = normalized.loc[event_mask].reset_index(drop=True)

    try:
        normalized.attrs = {}
        rejected_rows.attrs = {}
    except Exception:
        pass

    warnings = []
    if not rejected_rows.empty:
        warnings.append(
            f"{source_path.name}: {len(rejected_rows)} non-event row(s) excluded."
        )

    return {
        "ok": True,
        "file": str(source_path),
        "data": normalized,
        "search_requests": pd.DataFrame(),
        "rejected_rows": rejected_rows,
        "warnings": warnings,
        "errors": [],
        "metadata": {
            "operator": "Jio",
            "source_format": "JIO_DYNAMIC_IPDR",
            "report_scope": "JIO_DYNAMIC_IPDR",
            "source_file": str(source_path),
            "file_name": source_path.name,
            "total_records": int(len(normalized)),
            "records_loaded": int(len(normalized)),
            "empty_result": bool(normalized.empty),
        },
    }


_original_load_ipdr_file_before_jio_dynamic_fallback = load_ipdr_file


def load_ipdr_file(path: str | Path) -> dict[str, Any]:
    result = _original_load_ipdr_file_before_jio_dynamic_fallback(path)

    data = result.get("data") if isinstance(result, dict) else None

    if isinstance(data, pd.DataFrame) and not data.empty:
        return result

    if _looks_like_jio_dynamic_ipdr_csv(path):
        fallback_result = _load_jio_dynamic_ipdr_csv_fallback(path)
        fallback_data = fallback_result.get("data")

        if isinstance(fallback_data, pd.DataFrame) and not fallback_data.empty:
            return fallback_result

    return result

