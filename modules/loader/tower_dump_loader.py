from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from modules.loader.evidence_csv import (
    empty_reject_ledger,
    quarantine_dataframe_rows,
    read_csv_with_quarantine,
)
from modules.loader.duplicate_flags import flag_potential_duplicates
from modules.loader.tower_spot_layout import (
    build_tower_spot_layout,
    select_tower_evidence_files,
)


SUPPORTED_SUFFIXES = {".csv", ".txt", ".tsv"}


# ---------------------------------------------------------------------------
# Normalized output columns
# ---------------------------------------------------------------------------
NORMALIZED_COLUMNS = [
    "subscriber_number",
    "other_party",
    "a_party",
    "b_party",
    "call_type",
    "raw_call_type",
    "service_type",
    "connection_type",
    "call_date",
    "call_time",
    "call_datetime",
    "call_duration",
    "imei",
    "imsi",
    "first_cell_id",
    "last_cell_id",
    "first_tower_address",
    "last_tower_address",
    "first_latitude",
    "first_longitude",
    "last_latitude",
    "last_longitude",
    "sms_center",
    "call_forwarding_number",
    "roaming_circle",
    "operator",
    "searched_cell_id",
    "first_cell_matches_search",
    "last_cell_matches_search",
    "present_at_searched_cell",
    "source_file",
    "source_relative_path",
    "spot_id",
    "spot_name",
    "spot_folder",
    "source_row",
]


COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "a_party": (
        "target no",
        "target a party number",
        "target a-party number",
        "calling party telephone number",
    ),
    "b_party": (
        "b party no",
        "b party number",
        "other b-party number",
        "called party telephone number",
    ),
    "raw_call_type": ("call type", "call_type"),
    "connection_type": ("toc", "type of connection"),
    "call_date": ("date", "call date"),
    "call_time": ("time", "call initiation time", "call time"),
    "call_duration": ("dur s", "call duration"),
    "first_cell_id": ("first cgi", "first cell global id", "first cell id"),
    "last_cell_id": ("last cgi", "last cell global id", "last cell id"),
    "first_tower_address": ("first bts location",),
    "last_tower_address": ("last bts location",),
    "first_lat_lon": ("first cgi lat long",),
    "last_lat_lon": ("last cgi lat long",),
    "sms_center": ("smsc no", "sms centre no", "sms centre number", "sms center number"),
    "service_type": ("service type",),
    "imei": ("imei",),
    "imsi": ("imsi",),
    "call_forwarding_number": (
        "call fow no",
        "call forwarding number",
        "call forwarding",
        "original calling party",
    ),
    "roaming_circle": ("roam nw", "roaming network circle", "roaming circle name"),
}


CALL_TYPE_MAP = {
    "out": "outgoing",
    "outgoing": "outgoing",
    "aout": "outgoing",
    "a_out": "outgoing",
    "voiceout": "outgoing",
    "in": "incoming",
    "incoming": "incoming",
    "ain": "incoming",
    "a_in": "incoming",
    "voicein": "incoming",
    "smo": "smsout",
    "smsout": "smsout",
    "sms_out": "smsout",
    "p2pout": "smsout",
    "p2p_out": "smsout",
    "a2psmsout": "smsout",
    "a2p_smsout": "smsout",
    "smt": "smsin",
    "smsin": "smsin",
    "sms_in": "smsin",
    "p2pin": "smsin",
    "p2p_in": "smsin",
    "a2psmsin": "smsin",
    "a2p_smsin": "smsin",
    "v_out": "outgoing",
    "v_in": "incoming",
    "p2aout": "smsout",
    "a_frw": "forwarded",
}


@dataclass
class TowerDumpLoadResult:
    file: str
    operator: str
    searched_cell_id: str
    dataframe: pd.DataFrame
    metadata: dict[str, Any] = field(default_factory=dict)
    rejected_rows: pd.DataFrame = field(default_factory=empty_reject_ledger)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.dataframe.empty and not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "operator": self.operator,
            "searched_cell_id": self.searched_cell_id,
            "df": self.dataframe,
            "metadata": self.metadata,
            "rejected_rows": self.rejected_rows,
            "warnings": self.warnings,
            "errors": self.errors,
            "ok": self.ok,
        }


# ---------------------------------------------------------------------------
# Basic text helpers
# ---------------------------------------------------------------------------
def _clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).replace("\ufeff", "").strip()
    if len(text) >= 2 and text[0] == text[-1] == "'":
        text = text[1:-1].strip()
    if text.lower() in {"nan", "none", "null", "-", "--", "---"}:
        return ""
    return text


def _normalize_header(value: Any) -> str:
    text = _clean_text(value).lower()
    text = text.replace("/", " ").replace("_", " ").replace("-", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_identifier(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return text.replace(" ", "")


def _normalize_phone(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""

    # Preserve alpha-numeric SMS sender IDs such as AX-FINOBK-S.
    if re.search(r"[A-Za-z]", text):
        return text.upper()

    digits = re.sub(r"\D", "", text)
    if not digits:
        return text

    # Normalize common Indian prefixes without truncating unusual service IDs.
    if len(digits) == 12 and digits.startswith("91"):
        return digits[-10:]
    if len(digits) == 11 and digits.startswith("0"):
        return digits[-10:]
    return digits


def _normalize_cell_id(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = re.sub(r"\s+", "", text).upper()
    return text




def _cell_aliases(value: Any) -> set[str]:
    """Cell ID ke common textual/operator variants banata hai."""
    text = _normalize_cell_id(value)
    if not text:
        return set()

    aliases = {text, re.sub(r"[^A-Z0-9]", "", text)}
    groups = [group for group in re.split(r"[^A-Z0-9]+", text) if group]

    if groups and all(group.isdigit() for group in groups):
        aliases.add("".join(groups))

        # Vi exports may show 40570-5123-15746 while row data carries
        # 405700512315746 (the middle group is zero padded to five digits).
        if len(groups) == 3 and len(groups[0]) == 5 and len(groups[1]) < 5:
            aliases.add(groups[0] + groups[1].zfill(5) + groups[2])

    return {alias for alias in aliases if alias}


def _cell_matches(value: Any, searched_cell_id: Any) -> bool:
    return bool(_cell_aliases(value) & _cell_aliases(searched_cell_id))


def _parse_lat_lon(value: Any) -> tuple[Any, Any]:
    text = _clean_text(value)
    if not text:
        return pd.NA, pd.NA

    match = re.search(
        r"(-?\d{1,3}(?:\.\d+)?)\s*[/,; ]\s*(-?\d{1,3}(?:\.\d+)?)",
        text,
    )
    if not match:
        return pd.NA, pd.NA

    try:
        first, second = float(match.group(1)), float(match.group(2))
    except ValueError:
        return pd.NA, pd.NA
    # Normal order is latitude, longitude. Swap only when the first value
    # cannot be latitude but the second can; otherwise reject invalid ranges.
    if not (-90 <= first <= 90) and -90 <= second <= 90 and -180 <= first <= 180:
        first, second = second, first
    if not (-90 <= first <= 90 and -180 <= second <= 180):
        return pd.NA, pd.NA
    return first, second


def _extract_lat_lon_from_address(value: Any) -> tuple[Any, Any]:
    text = _clean_text(value)
    if not text:
        return pd.NA, pd.NA

    lat = re.search(r"lat\s*[-:]?\s*(-?\d+(?:\.\d+)?)", text, re.I)
    lon = re.search(r"(?:long|lon)\s*[-:]?\s*(-?\d+(?:\.\d+)?)", text, re.I)

    try:
        latitude = float(lat.group(1)) if lat else pd.NA
        longitude = float(lon.group(1)) if lon else pd.NA
    except ValueError:
        return pd.NA, pd.NA
    if latitude is not pd.NA and not (-90 <= latitude <= 90):
        latitude = pd.NA
    if longitude is not pd.NA and not (-180 <= longitude <= 180):
        longitude = pd.NA
    return latitude, longitude


def _duration_to_seconds(value: Any) -> float:
    text = _clean_text(value)
    if not text:
        return 0.0

    try:
        if re.fullmatch(r"\d+(?:\.\d+)?", text):
            return float(text)
        parts = [float(part) for part in text.split(":")]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
    except (TypeError, ValueError):
        return 0.0
    return 0.0


def _canonical_call_type(raw_type: Any, service_type: Any) -> str:
    raw = _clean_text(raw_type).lower()
    compact = re.sub(r"[^a-z0-9_]", "", raw)
    service = _clean_text(service_type).lower()

    if compact in CALL_TYPE_MAP:
        result = CALL_TYPE_MAP[compact]
    elif "sms" in compact and ("in" in compact or compact.endswith("mt")):
        result = "smsin"
    elif "sms" in compact and ("out" in compact or compact.endswith("mo")):
        result = "smsout"
    elif compact.startswith(("a_in", "ain", "in")):
        result = "incoming"
    elif compact.startswith(("a_out", "aout", "out")):
        result = "outgoing"
    else:
        result = compact or "unknown"

    # BSNL/Vi may use IN/OUT together with Service Type=SMS.
    if "sms" in service:
        if result == "incoming":
            return "smsin"
        if result == "outgoing":
            return "smsout"

    return result


# ---------------------------------------------------------------------------
# File/header/operator/metadata detection
# ---------------------------------------------------------------------------
def _read_preview(path: Path, limit: int = 80) -> list[str]:
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        return [line.rstrip("\r\n") for _, line in zip(range(limit), handle)]


def _detect_delimiter(lines: Iterable[str]) -> str:
    candidates = [line for line in lines if line.strip()]
    sample = "\n".join(candidates[:20])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
    except csv.Error:
        counts = {d: sum(line.count(d) for line in candidates[:20]) for d in [",", "\t", ";", "|"]}
        return max(counts, key=counts.get)


def _header_score(row: list[str]) -> int:
    headers = {_normalize_header(value) for value in row}
    score = 0
    keywords = [
        "call type",
        "call date",
        "call time",
        "call initiation time",
        "calling party telephone number",
        "called party telephone number",
        "target no",
        "target a party number",
        "first cgi",
        "first cell id",
        "first cell global id",
        "imei",
        "imsi",
    ]
    for keyword in keywords:
        if keyword in headers:
            score += 2
    if len(row) >= 10:
        score += 2
    return score


def _find_header_row(lines: list[str], delimiter: str) -> int:
    best_index = -1
    best_score = -1

    for index, line in enumerate(lines):
        try:
            row = next(csv.reader([line], delimiter=delimiter))
        except csv.Error:
            continue
        score = _header_score(row)
        if score > best_score:
            best_index, best_score = index, score

    if best_index < 0 or best_score < 8:
        raise ValueError("Tower Dump header row detect nahi hua.")
    return best_index


def _detect_operator(lines: list[str], normalized_headers: set[str]) -> str:
    preview = "\n".join(lines[:20]).lower()
    if "bharti airtel" in preview or "first cgi lat long" in normalized_headers:
        return "airtel"
    if "vodafone idea" in preview or "report index" in preview:
        return "vi"
    if "search criteria" in preview and "first cell global id" in normalized_headers:
        return "bsnl"
    if "ticket number" in preview or "calling party telephone number" in normalized_headers:
        return "jio"
    return "unknown"


def _extract_metadata(lines: list[str], operator: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {"operator": operator}

    def put(key: str, value: str) -> None:
        value = _clean_text(value)
        if value:
            metadata[key] = value

    for line in lines[:25]:
        stripped = line.strip()
        lower = stripped.lower()

        if operator == "airtel":
            match = re.search(
                r"cell id\s+'([^']+)'.*?from\s+'([^']+)'.*?to\s+'([^']+)'",
                stripped,
                re.I,
            )
            if match:
                put("searched_cell_id", match.group(1))
                put("from_date", match.group(2))
                put("to_date", match.group(3))

        elif operator == "jio":
            if lower.startswith("ticket number"):
                put("ticket_number", stripped.split(",", 1)[-1])
            elif lower.startswith("input value"):
                put("searched_cell_id", stripped.split(",", 1)[-1])
            elif lower.startswith("date range"):
                value = stripped.split(",", 1)[-1]
                put("date_range", value)
                if " to " in value:
                    start, end = value.split(" to ", 1)
                    put("from_date", start)
                    put("to_date", end)
            elif lower.startswith("total records"):
                put("declared_total_records", stripped.split(",", 1)[-1])
            elif lower.startswith("report generated at"):
                put("report_generated_at", stripped.split(",", 1)[-1])

        elif operator == "bsnl":
            if lower.startswith("search criteria"):
                put("search_criteria", stripped.split(":", 1)[-1])
            elif lower.startswith("search value"):
                put("searched_cell_id", stripped.split(":", 1)[-1])
            elif lower.startswith("start date"):
                put("from_date", stripped.split(":", 1)[-1])
            elif lower.startswith("end date"):
                put("to_date", stripped.split(":", 1)[-1])

        elif operator == "vi":
            if lower.startswith("cellid"):
                put("searched_cell_id", stripped.split("-", 1)[-1])
            elif lower.startswith("from date"):
                put("from_date", stripped.split(":-", 1)[-1])
            elif lower.startswith("till date"):
                put("to_date", stripped.split(":-", 1)[-1])
            elif lower.startswith("report index"):
                put("report_index", stripped.split(":-", 1)[-1])
            elif lower.startswith("report date"):
                put("report_generated_at", stripped.split(":-", 1)[-1])

    metadata["searched_cell_id"] = _normalize_cell_id(metadata.get("searched_cell_id", ""))
    return metadata


# ---------------------------------------------------------------------------
# DataFrame normalization
# ---------------------------------------------------------------------------
def _build_column_lookup(columns: Iterable[Any]) -> dict[str, str]:
    normalized_to_original = {_normalize_header(column): str(column) for column in columns}
    lookup: dict[str, str] = {}

    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            normalized_alias = _normalize_header(alias)
            if normalized_alias in normalized_to_original:
                lookup[canonical] = normalized_to_original[normalized_alias]
                break
    return lookup


def _series(raw: pd.DataFrame, lookup: dict[str, str], name: str) -> pd.Series:
    source = lookup.get(name)
    if source is None:
        return pd.Series([""] * len(raw), index=raw.index, dtype="object")
    return raw[source].map(_clean_text)


def _derive_subscriber_and_other_party(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    subscriber: list[str] = []
    other: list[str] = []

    for a_party, b_party, call_type in zip(df["a_party"], df["b_party"], df["call_type"]):
        if call_type in {"incoming", "smsin"}:
            subscriber.append(_normalize_phone(b_party))
            other.append(_normalize_phone(a_party))
        else:
            subscriber.append(_normalize_phone(a_party))
            other.append(_normalize_phone(b_party))

    return (
        pd.Series(subscriber, index=df.index, dtype="object"),
        pd.Series(other, index=df.index, dtype="object"),
    )


def _normalize_dataframe(
    raw: pd.DataFrame,
    operator: str,
    searched_cell_id: str,
    source_file: str,
    header_row: int,
) -> pd.DataFrame:
    lookup = _build_column_lookup(raw.columns)
    df = pd.DataFrame(index=raw.index)

    df["a_party"] = _series(raw, lookup, "a_party").map(_normalize_phone)
    df["b_party"] = _series(raw, lookup, "b_party").map(_normalize_phone)
    df["raw_call_type"] = _series(raw, lookup, "raw_call_type")
    df["service_type"] = _series(raw, lookup, "service_type")
    df["connection_type"] = _series(raw, lookup, "connection_type")
    df["call_date"] = _series(raw, lookup, "call_date")
    df["call_time"] = _series(raw, lookup, "call_time")
    df["call_duration"] = _series(raw, lookup, "call_duration").map(_duration_to_seconds)
    df["imei"] = _series(raw, lookup, "imei").map(_normalize_identifier)
    df["imsi"] = _series(raw, lookup, "imsi").map(_normalize_identifier)
    df["first_cell_id"] = _series(raw, lookup, "first_cell_id").map(_normalize_cell_id)
    df["last_cell_id"] = _series(raw, lookup, "last_cell_id").map(_normalize_cell_id)
    df["first_tower_address"] = _series(raw, lookup, "first_tower_address")
    df["last_tower_address"] = _series(raw, lookup, "last_tower_address")
    df["sms_center"] = _series(raw, lookup, "sms_center").map(_normalize_phone)
    df["call_forwarding_number"] = _series(raw, lookup, "call_forwarding_number").map(_normalize_phone)
    df["roaming_circle"] = _series(raw, lookup, "roaming_circle")

    df["call_type"] = [
        _canonical_call_type(raw_type, service)
        for raw_type, service in zip(df["raw_call_type"], df["service_type"])
    ]

    # For Airtel/BSNL/Vi the first party is already the tower subscriber.
    if operator == "jio":
        df["subscriber_number"], df["other_party"] = _derive_subscriber_and_other_party(df)
    else:
        df["subscriber_number"] = df["a_party"].map(_normalize_phone)
        df["other_party"] = df["b_party"].map(_normalize_phone)

    date_text = df["call_date"].fillna("").astype(str).str.strip()
    time_text = df["call_time"].fillna("").astype(str).str.strip()
    combined = (date_text + " " + time_text).str.strip()
    df["call_datetime"] = pd.to_datetime(combined, dayfirst=True, errors="coerce")

    first_latlon = _series(raw, lookup, "first_lat_lon")
    last_latlon = _series(raw, lookup, "last_lat_lon")

    first_coords = [
        _parse_lat_lon(value) if _clean_text(value) else _extract_lat_lon_from_address(address)
        for value, address in zip(first_latlon, df["first_tower_address"])
    ]
    last_coords = [
        _parse_lat_lon(value) if _clean_text(value) else _extract_lat_lon_from_address(address)
        for value, address in zip(last_latlon, df["last_tower_address"])
    ]

    df["first_latitude"] = [item[0] for item in first_coords]
    df["first_longitude"] = [item[1] for item in first_coords]
    df["last_latitude"] = [item[0] for item in last_coords]
    df["last_longitude"] = [item[1] for item in last_coords]

    df["operator"] = operator
    df["searched_cell_id"] = searched_cell_id
    df["first_cell_matches_search"] = [
        _cell_matches(value, searched_cell_id) for value in df["first_cell_id"]
    ]
    df["last_cell_matches_search"] = [
        _cell_matches(value, searched_cell_id) for value in df["last_cell_id"]
    ]
    df["present_at_searched_cell"] = (
        df["first_cell_matches_search"] | df["last_cell_matches_search"]
    )
    df["source_file"] = source_file
    if "_source_row_number" in raw.columns:
        df["source_row"] = pd.to_numeric(
            raw["_source_row_number"], errors="coerce"
        ).astype("Int64")
    else:
        df["source_row"] = [header_row + 2 + index for index in range(len(df))]

    # A valid normal Tower Dump record must carry a parseable event timestamp.
    # This removes decorative separators, END OF REPORT and disclaimer rows.
    useful = df["call_datetime"].notna() & (
        df["subscriber_number"].ne("")
        | df["imei"].ne("")
        | df["imsi"].ne("")
        | df["first_cell_id"].ne("")
        | df["last_cell_id"].ne("")
    )
    validation_rejects = quarantine_dataframe_rows(
        df,
        ~useful,
        source_file=source_file,
        reason="INVALID_OR_NON_DATA_TOWER_DUMP_ROW",
    )
    df = df.loc[useful].copy()

    # Repeated embedded headers are quarantined, not silently discarded.
    repeated_header = df["raw_call_type"].map(_normalize_header).eq("call type")
    repeated_rejects = quarantine_dataframe_rows(
        df,
        repeated_header,
        source_file=source_file,
        reason="REPEATED_EMBEDDED_HEADER_ROW",
    )
    df = df.loc[~repeated_header].copy()

    # Prefer integer-like duration while retaining nullable safety.
    df["call_duration"] = pd.to_numeric(df["call_duration"], errors="coerce").fillna(0)
    df["call_duration"] = df["call_duration"].round().astype("Int64")

    for column in NORMALIZED_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA

    output = df[NORMALIZED_COLUMNS].reset_index(drop=True)
    output.attrs["rejected_rows"] = pd.concat(
        [validation_rejects, repeated_rejects],
        ignore_index=True,
    )
    return output


def _safe_cgi_enrichment(df: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    try:
        from modules.database.cgi import safe_enrich_cdr
    except Exception as exc:
        warnings.append(f"CGI enrichment unavailable: {type(exc).__name__}: {exc}")
        return df

    try:
        enriched = safe_enrich_cdr(df)
        return enriched if isinstance(enriched, pd.DataFrame) else df
    except Exception as exc:
        warnings.append(f"CGI enrichment failed; original data retained: {type(exc).__name__}: {exc}")
        return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def load_tower_dump(
    file_path: str | Path,
    *,
    enrich_cgi: bool = True,
) -> dict[str, Any]:
    """
    Airtel, Jio, BSNL aur Vi normal Tower Dump CSV ko common schema mein load karta hai.

    Return structure::

        {
            "file": "dump.csv",
            "operator": "airtel",
            "searched_cell_id": "405-52-792-2120",
            "df": pandas.DataFrame,
            "metadata": {...},
            "warnings": [...],
            "errors": [...],
            "ok": True,
        }

    File/row error par exception propagate karne ke bajay error result return hota hai.
    """
    path = Path(file_path).expanduser().resolve()
    empty = pd.DataFrame(columns=NORMALIZED_COLUMNS)

    if not path.exists() or not path.is_file():
        return TowerDumpLoadResult(
            file=path.name,
            operator="unknown",
            searched_cell_id="",
            dataframe=empty,
            errors=[f"File not found: {path}"],
        ).as_dict()

    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return TowerDumpLoadResult(
            file=path.name,
            operator="unknown",
            searched_cell_id="",
            dataframe=empty,
            errors=[f"Unsupported file type: {path.suffix}"],
        ).as_dict()

    warnings: list[str] = []
    errors: list[str] = []

    try:
        lines = _read_preview(path)
        delimiter = _detect_delimiter(lines)
        header_row = _find_header_row(lines, delimiter)

        header_values = next(csv.reader([lines[header_row]], delimiter=delimiter))
        normalized_headers = {_normalize_header(value) for value in header_values}
        operator = _detect_operator(lines, normalized_headers)
        metadata = _extract_metadata(lines, operator)
        searched_cell_id = _normalize_cell_id(metadata.get("searched_cell_id", ""))

        raw, parser_rejects, ingestion_metadata = read_csv_with_quarantine(
            path,
            sep=delimiter,
            skiprows=header_row,
            encoding="utf-8-sig",
        )

        if raw.empty:
            raise ValueError("Header detect hua, lekin koi data row nahi mili.")

        df = _normalize_dataframe(
            raw=raw,
            operator=operator,
            searched_cell_id=searched_cell_id,
            source_file=path.name,
            header_row=header_row,
        )
        rejected_rows = pd.concat(
            [
                parser_rejects,
                df.attrs.get("rejected_rows", empty_reject_ledger()),
            ],
            ignore_index=True,
        )

        if df.empty:
            raise ValueError("Normalization ke baad koi valid Tower Dump record nahi bacha.")

        if operator == "unknown":
            warnings.append("Operator auto-detect nahi hua; generic mapping use hui.")

        missing_core = [
            column
            for column in ("subscriber_number", "call_datetime", "first_cell_id")
            if column not in df.columns or df[column].isna().all() or df[column].astype(str).str.strip().eq("").all()
        ]
        if missing_core:
            warnings.append("Core data partially missing: " + ", ".join(missing_core))

        if enrich_cgi:
            df = _safe_cgi_enrichment(df, warnings)

        metadata.update(
            {
                "source_file": path.name,
                "header_row": header_row + 1,
                "delimiter": delimiter,
                "loaded_records": int(len(df)),
                "records_at_searched_cell": int(df["present_at_searched_cell"].sum()),
                "records_without_searched_cell_match": int((~df["present_at_searched_cell"]).sum()),
                "operator": operator,
                "searched_cell_id": searched_cell_id,
                "rejected_rows": int(len(rejected_rows)),
                "adjusted_rows": int(ingestion_metadata.get("adjusted_rows", 0)),
            }
        )
        df.attrs["metadata"] = metadata
        df.attrs["warnings"] = warnings

        return TowerDumpLoadResult(
            file=path.name,
            operator=operator,
            searched_cell_id=searched_cell_id,
            dataframe=df,
            metadata=metadata,
            rejected_rows=rejected_rows.reset_index(drop=True),
            warnings=warnings,
            errors=errors,
        ).as_dict()

    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"

        try:
            preview_lines = list(
                locals().get("lines")
                or _read_preview(
                    path,
                    limit=120,
                )
            )
        except Exception:
            preview_lines = []

        preview_text = "\n".join(
            preview_lines
        ).casefold()

        no_data_markers = (
            "no data found",
            "no records found",
            "no record found",
        )

        is_valid_empty_report = any(
            marker in preview_text
            for marker in no_data_markers
        )

        if is_valid_empty_report:
            detected_metadata = dict(
                locals().get("metadata")
                or {}
            )

            detected_operator = str(
                locals().get("operator")
                or "unknown"
            ).strip()

            detected_cell_id = _normalize_cell_id(
                locals().get("searched_cell_id")
                or detected_metadata.get(
                    "searched_cell_id",
                    "",
                )
            )

            detected_metadata.update(
                {
                    "source_file": path.name,
                    "empty_report": True,
                    "data_status": "EMPTY_NO_DATA",
                }
            )

            empty_warnings = [
                *warnings,
                (
                    "Valid operator report loaded, lekin "
                    "requested Cell ID/date range ke liye "
                    "koi CDR record available nahi tha."
                ),
            ]

            payload = TowerDumpLoadResult(
                file=path.name,
                operator=detected_operator,
                searched_cell_id=detected_cell_id,
                dataframe=empty,
                metadata=detected_metadata,
                warnings=empty_warnings,
                errors=[],
            ).as_dict()

            # File successfully processed hui, lekin records zero hain.
            payload["ok"] = True
            payload["has_records"] = False
            payload["data_status"] = "EMPTY_NO_DATA"

            return payload

        errors.append(error_message)

        payload = TowerDumpLoadResult(
            file=path.name,
            operator="unknown",
            searched_cell_id="",
            dataframe=empty,
            metadata={"source_file": path.name},
            warnings=warnings,
            errors=errors,
        ).as_dict()

        payload["has_records"] = False
        payload["data_status"] = "FAILED"

        return payload


def load_tower_dump_folder(
    folder_path: str | Path,
    *,
    enrich_cgi: bool = True,
) -> dict[str, Any]:
    """Folder ke sab supported normal Tower Dump files ko safely load karta hai."""
    folder = Path(folder_path).expanduser().resolve()
    results: list[dict[str, Any]] = []

    if not folder.exists() or not folder.is_dir():
        return {
            "files_found": 0,
            "files_loaded": 0,
            "files_failed": 0,
            "results": [],
            "errors": [f"Folder not found: {folder}"],
        }

    files = sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )

    for path in files:
        results.append(load_tower_dump(path, enrich_cgi=enrich_cgi))

    return {
        "files_found": len(files),
        "files_loaded": sum(bool(item.get("ok")) for item in results),
        "files_failed": sum(not bool(item.get("ok")) for item in results),
        "results": results,
        "errors": [
            f"{item.get('file')}: {'; '.join(item.get('errors', []))}"
            for item in results
            if item.get("errors")
        ],
    }


def load_tower_dump_case(
    folder_path: str | Path,
    *,
    enrich_cgi: bool = True,
    recursive: bool = True,
    remove_exact_duplicates: bool = False,
    selected_spot_folders: Iterable[str] | None = None,
    include_root_files: bool = True,
) -> dict[str, Any]:
    """
    Ek Tower Dump case folder ke sab supported files ko load, normalize aur combine karta hai.

    Tower Dump target-centric nahi hota. Isliye return mein ek combined DataFrame milta hai,
    jisme sab operators aur searched CGI/Cell IDs ke records hote hain.
    """
    folder = Path(folder_path).expanduser().resolve()
    empty = pd.DataFrame(columns=NORMALIZED_COLUMNS)

    if not folder.exists() or not folder.is_dir():
        return {
            "df": empty,
            "files": [],
            "file_results": [],
            "file_summary": pd.DataFrame(),
            "spot_summary": pd.DataFrame(),
            "operators": [],
            "cell_ids": [],
            "metadata": {},
            "warnings": [],
            "errors": [f"Tower Dump input folder not found: {folder}"],
            "ok": False,
        }

    iterator = folder.rglob("*") if recursive else folder.iterdir()
    candidate_files = sorted(
        path
        for path in iterator
        if (
            path.is_file()
            and path.suffix.lower() in SUPPORTED_SUFFIXES
            and not path.name.startswith(("~$", "."))
        )
    )
    files = select_tower_evidence_files(
        folder,
        candidate_files,
        selected_spot_folders=selected_spot_folders,
        include_root_files=include_root_files,
    )

    if not files:
        return {
            "df": empty,
            "files": [],
            "file_results": [],
            "file_summary": pd.DataFrame(),
            "spot_summary": pd.DataFrame(),
            "operators": [],
            "cell_ids": [],
            "metadata": {"input_folder": str(folder)},
            "warnings": [],
            "errors": [f"No supported Tower Dump files found in: {folder}"],
            "ok": False,
        }

    file_results: list[dict[str, Any]] = []
    frames: list[pd.DataFrame] = []
    warnings: list[str] = []
    errors: list[str] = []
    summary_rows: list[dict[str, Any]] = []
    reject_frames: list[pd.DataFrame] = []

    spot_layout = build_tower_spot_layout(
        folder,
        files,
        identity_files=candidate_files,
    )
    spot_assignments = spot_layout.get(
        "assignments",
        {},
    )
    warnings.extend(
        spot_layout.get(
            "warnings",
            [],
        )
    )

    for path in files:
        relative_path = str(
            path.relative_to(folder)
        )

        assignment = dict(
            spot_assignments.get(
                str(path.resolve()),
                {
                    "spot_id": "UNASSIGNED-ROOT",
                    "spot_name": "ROOT_LEVEL_FILES",
                    "spot_folder": ".",
                    "source_relative_path": relative_path,
                    "is_root_file": True,
                },
            )
        )

        result = load_tower_dump(
            path,
            # Batch enrichment runs once after all selected files are merged.
            enrich_cgi=False,
        )

        result["spot_id"] = assignment["spot_id"]
        result["spot_name"] = assignment["spot_name"]
        result["spot_folder"] = assignment["spot_folder"]
        result["source_relative_path"] = assignment[
            "source_relative_path"
        ]

        result_metadata = result.setdefault(
            "metadata",
            {},
        )
        result_metadata.update(
            {
                "spot_id": assignment["spot_id"],
                "spot_name": assignment["spot_name"],
                "spot_folder": assignment["spot_folder"],
                "source_relative_path": assignment[
                    "source_relative_path"
                ],
            }
        )

        file_results.append(result)

        result_warnings = result.get("warnings") or []
        result_errors = result.get("errors") or []

        for warning in result_warnings:
            warnings.append(f"{path.name}: {warning}")
        for error in result_errors:
            errors.append(f"{path.name}: {error}")

        rejected = result.get("rejected_rows")
        if isinstance(rejected, pd.DataFrame) and not rejected.empty:
            reject_frames.append(rejected)

        df = result.get("df")
        record_count = (
            len(df)
            if isinstance(df, pd.DataFrame)
            else 0
        )

        data_status = str(
            result.get(
                "data_status",
                "",
            )
        ).strip().upper()

        if not data_status:
            if result.get("ok") and record_count > 0:
                data_status = "LOADED"
            elif result.get("ok") and record_count == 0:
                data_status = "EMPTY_NO_DATA"
            else:
                data_status = "FAILED"

        result["data_status"] = data_status
        result["has_records"] = record_count > 0

        summary_rows.append(
            {
                "spot_id": assignment["spot_id"],
                "spot_name": assignment["spot_name"],
                "spot_folder": assignment["spot_folder"],
                "file": path.name,
                "relative_path": assignment[
                    "source_relative_path"
                ],
                "operator": result.get("operator", "unknown"),
                "searched_cell_id": result.get("searched_cell_id", ""),
                "records": record_count,
                "status": data_status,
                "warnings": " | ".join(result_warnings),
                "errors": " | ".join(result_errors),
            }
        )

        if isinstance(df, pd.DataFrame) and not df.empty:
            frame = df.copy()
            frame.attrs = {}
            frame["source_relative_path"] = assignment[
                "source_relative_path"
            ]
            frame["spot_id"] = assignment["spot_id"]
            frame["spot_name"] = assignment["spot_name"]
            frame["spot_folder"] = assignment["spot_folder"]
            frames.append(frame)

    files_loaded_count = sum(
        row.get("status") == "LOADED"
        for row in summary_rows
    )
    files_empty_no_data_count = sum(
        row.get("status") == "EMPTY_NO_DATA"
        for row in summary_rows
    )
    files_failed_count = sum(
        row.get("status") == "FAILED"
        for row in summary_rows
    )
    files_processed_count = (
        files_loaded_count
        + files_empty_no_data_count
    )

    if not frames:
        return {
            "df": empty,
            "files": [str(path) for path in files],
            "file_results": file_results,
            "file_summary": pd.DataFrame(summary_rows),
            "spot_summary": pd.DataFrame(
                spot_layout.get(
                    "spot_summary",
                    [],
                )
            ),
            "operators": [],
            "cell_ids": [],
            "metadata": {
                "input_folder": str(folder),
                "input_mode": spot_layout.get(
                    "input_mode",
                    "LEGACY_ROOT_FILES",
                ),
                "spot_count": int(
                    spot_layout.get(
                        "spot_count",
                        0,
                    )
                    or 0
                ),
                "spot_names": list(
                    spot_layout.get(
                        "spot_names",
                        [],
                    )
                    or []
                ),
                "root_level_file_count": int(
                    spot_layout.get(
                        "root_level_file_count",
                        0,
                    )
                    or 0
                ),
                "files_found": len(files),
                "files_loaded": files_loaded_count,
                "files_empty_no_data": files_empty_no_data_count,
                "files_failed": files_failed_count,
                "files_processed": files_processed_count,
            },
            "warnings": warnings,
            "errors": errors or ["No valid Tower Dump records loaded."],
            "ok": False,
        }
    for frame in frames:
        frame.attrs = {}
    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined.attrs = {}
    records_before_dedup = len(combined)

    dedup_columns = [
        column
        for column in (
            "operator",
            "searched_cell_id",
            "subscriber_number",
            "other_party",
            "call_type",
            "call_datetime",
            "call_duration",
            "imei",
            "imsi",
            "first_cell_id",
            "last_cell_id",
        )
        if column in combined.columns
    ]

    potential_duplicate_records = (
        int(combined.duplicated(subset=dedup_columns, keep=False).sum())
        if dedup_columns
        else 0
    )

    if remove_exact_duplicates and dedup_columns:
        warnings.append(
            "remove_exact_duplicates request ignored: forensic source rows are "
            "retained and only flagged."
        )

    combined = flag_potential_duplicates(
        combined,
        signature_columns=dedup_columns,
    )

    combined = combined.sort_values(
        ["call_datetime", "operator", "subscriber_number"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)

    if enrich_cgi:
        combined = _safe_cgi_enrichment(
            combined,
            warnings,
        )

    operators = sorted(
        value
        for value in combined.get("operator", pd.Series(dtype="object"))
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        if value
    )
    cell_ids = sorted(
        value
        for value in combined.get("searched_cell_id", pd.Series(dtype="object"))
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        if value
    )

    datetimes = pd.to_datetime(
        combined.get("call_datetime", pd.Series(dtype="datetime64[ns]")),
        errors="coerce",
    )

    metadata = {
        "input_folder": str(folder),
        "input_mode": spot_layout.get(
            "input_mode",
            "LEGACY_ROOT_FILES",
        ),
        "spot_count": int(
            spot_layout.get(
                "spot_count",
                0,
            )
            or 0
        ),
        "spot_names": list(
            spot_layout.get(
                "spot_names",
                [],
            )
            or []
        ),
        "root_level_file_count": int(
            spot_layout.get(
                "root_level_file_count",
                0,
            )
            or 0
        ),
        "files_found": len(files),
        "files_loaded": files_loaded_count,
        "files_empty_no_data": files_empty_no_data_count,
        "files_failed": files_failed_count,
        "files_processed": files_processed_count,
        "records_before_deduplication": records_before_dedup,
        "records_after_deduplication": len(combined),
        "potential_exact_duplicate_records": potential_duplicate_records,
        "duplicates_removed": 0,
        "deduplication_applied": False,
        "rejected_rows": int(sum(len(item) for item in reject_frames)),
        "operators": operators,
        "searched_cell_ids": cell_ids,
        "date_from": datetimes.min() if datetimes.notna().any() else pd.NaT,
        "date_to": datetimes.max() if datetimes.notna().any() else pd.NaT,
    }

    combined.attrs["metadata"] = metadata
    combined.attrs["warnings"] = warnings
    combined.attrs["errors"] = errors

    return {
        "df": combined,
        "files": [str(path) for path in files],
        "file_results": file_results,
        "file_summary": pd.DataFrame(summary_rows),
        "spot_summary": pd.DataFrame(
            spot_layout.get(
                "spot_summary",
                [],
            )
        ),
        "operators": operators,
        "cell_ids": cell_ids,
        "metadata": metadata,
        "rejected_rows": (
            pd.concat(reject_frames, ignore_index=True)
            if reject_frames
            else empty_reject_ledger()
        ),
        "warnings": warnings,
        "errors": errors,
        "ok": not combined.empty,
    }
