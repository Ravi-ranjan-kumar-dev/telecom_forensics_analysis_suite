"""Universal, opt-in telecom evidence import for EthicalArmor.

Public API:
  inspect_universal_evidence(path)
  approve_format_profile(path, evidence_type=..., field_mapping=..., ...)
  load_universal_evidence(path, profiles_dir=..., allow_native=True)

Safety: unidentified input is *review-only*, never analysis-ready. No operator is
inferred from phone numbers, IMEI prefixes, filenames or MCC/MNC alone.
This is deliberately not a magical 'any format' forensic parser.
"""
from __future__ import annotations

import contextlib
import csv
import gzip
import hashlib
import ipaddress
import json
import os
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from modules.loader.universal_operator import detect_operator, canonical_operator, KNOWN_OPERATORS
from modules.loader.universal_schema import (ALIASES, MODULES, TYPES, TIMED_TYPES, TYPE_MODULE,
    header_fingerprint, missing_groups, norm, proposed_mapping)

MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 200
MAX_ROWS = 1_000_000
TEXT_EXTENSIONS = {".csv", ".txt", ".tsv"}
TABLE_EXTENSIONS = TEXT_EXTENSIONS | {".xlsx", ".xls"}
PROFILE_VERSION = 1


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""): h.update(chunk)
    return h.hexdigest()


def _inspect_encoding(data: bytes) -> tuple[str, str]:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16", data.decode("utf-16", errors="strict")
    if b"\x00" in data:
        raise ValueError("NUL/binary data rejected (UTF-16 requires BOM)")
    for enc in ("utf-8-sig", "cp1252"):
        try: return enc, data.decode(enc, errors="strict")
        except UnicodeDecodeError: continue
    raise ValueError("Unsupported text encoding")


def _read_header(path: Path) -> dict[str, Any]:
    if not path.is_file(): raise FileNotFoundError(path)
    if path.stat().st_size > MAX_FILE_BYTES: raise ValueError("Input file exceeds 256 MiB limit")
    if path.suffix.lower() not in TABLE_EXTENSIONS: raise ValueError("Unsupported table format")
    if path.suffix.lower() in {".xlsx", ".xls"}:
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Excel file exceeds 32 MiB inspection limit")
        # Excel header rows are inspected, never execute formulas or macros.
        preview = pd.read_excel(path, header=None, nrows=100, dtype=str).fillna("")
        best = None
        for row_idx, row in preview.iterrows():
            cells = [str(x).strip() for x in row.tolist()]
            while cells and not cells[-1]: cells.pop()
            mapping, ambiguous = proposed_mapping(cells)
            score = len(mapping) + len(ambiguous)
            if 1 <= score and len(cells) >= 2 and (best is None or score > best[0]):
                best = (score, int(row_idx), cells)
        if best is None:
            for row_idx, row in preview.iterrows():
                cells = [str(x).strip() for x in row.tolist()]
                while cells and not cells[-1]: cells.pop()
                if len(cells) < 3 or len(set(map(norm,cells))) != len(cells): continue
                if sum(bool(re.search(r"[a-zA-Z]",c)) for c in cells) < len(cells)*0.65: continue
                best=(0,int(row_idx),cells); break
        if best is None: raise ValueError("No tabular Excel header candidate; manual preprocessing required")
        _, row, headers = best
        return {"headers":headers, "header_row":row, "delimiter":None, "encoding":None, "kind":"excel",
                "header_recognition":"aliases" if best[0] else "provisional_unknown_schema"}
    with path.open("rb") as fh: sample = fh.read(256 * 1024)
    encoding, decoded = _inspect_encoding(sample)
    lines = decoded.splitlines()[:100]
    if not lines: raise ValueError("Empty input")
    best = None
    separators = ("\t", ",", "|", ";")
    # Works even when operator adds multiline metadata before the real header.
    for idx, line in enumerate(lines):
        if len(line) > 65536: continue
        for sep in separators:
            try: headers = next(csv.reader([line], delimiter=sep, strict=True))
            except (csv.Error, StopIteration): continue
            headers = [h.strip().lstrip("\ufeff") for h in headers]
            if not 2 <= len(headers) <= 250: continue
            mapping, ambiguous = proposed_mapping(headers)
            score = len(mapping) + len(ambiguous)
            if score and (best is None or score > best[0]):
                best = (score, idx, headers, sep)
    if best is None:
        # Unknown vendor schema: choose a *provisional* tabular header; reviewer must
        # map it, and no record is ever analysis-ready on this guess alone.
        for idx, line in enumerate(lines):
            for sep in separators:
                try: cells = [c.strip() for c in next(csv.reader([line],delimiter=sep))]
                except (csv.Error, StopIteration): continue
                if not 3 <= len(cells) <= 250: continue
                if len(set(map(norm,cells))) < len(cells): continue
                if sum(bool(re.search(r"[a-zA-Z]",c)) for c in cells) < len(cells)*0.65: continue
                best=(0,idx,cells,sep)
                break
            if best: break
        if best is None: raise ValueError("No tabular header candidate found; manual preprocessing required")
    _, header_idx, headers, sep = best
    return {"headers":headers, "header_row":header_idx, "delimiter":sep,"encoding":encoding,"kind":"text",
            "header_recognition":"aliases" if best[0] else "provisional_unknown_schema"}


def _signature(path: Path, header: dict[str, Any], mapping: dict[str, str]) -> dict[str, str]:
    with path.open("rb") as fh: prefix = fh.read(32768)
    if header["kind"] == "text":
        text = prefix.decode(header["encoding"], errors="replace").lower()
    else:
        text = ""
    fields = set(mapping)
    tower = any(s in text for s in (
        "ipdr of cell id", "gprs of cell id", "cell id_ipdrnat", "cell id ipdrnat",
        "report type :- gprs report", "search criteria : first_cell_id", "search criteria : cell_id",
        "input value (msisdn/b party/imei/imsi/cell id)"))
    operator = "Unknown"
    if "bharti airtel" in text: operator = "Airtel"
    elif "vodafone idea call data records" in text: operator = "Vi"
    elif "reliance jio" in text or "jio infocomm" in text: operator = "Jio"
    # Jio report signatures used by already-verified source-specific parsers.
    elif "ticket number" in text and "calling party telephone number" in text:
        # Ticket Number is also present in subscriber CDR requests.  Only
        # treat it as a Jio tower signature after the queried cell is observed
        # in the source file's first/last cell columns.
        from modules.loader.tower_evidence_router import is_jio_cell_target_report
        if is_jio_cell_target_report(path, text):
            operator = "Jio (cell-target report signature)"
    elif "landline/msisdn/mdn/leased circuit id for internet access" in text and "translated ip address" in text:
        operator = "Jio (report signature)" if "static/dynamic ip address allocation" in text else "Unknown"
    elif "bsnl" in text: operator = "BSNL"
    elif "mtnl" in text: operator = "MTNL"

    # Explicit requested report scope takes precedence over generic IPDR/GPRS columns.
    # An IMEI field appearing in an ordinary CDR does NOT make it an IMEI report.
    preamble = "\n".join(text.splitlines()[:int(header.get("header_row", 0))])
    imei_request = bool(re.search(r"(?im)^\s*(?:imei\s*[:=-]|dynamic\s+ipdr\s+of\s+imei\s*[:=-])", preamble))
    if imei_request and "dynamic ipdr of imei" in preamble and {"imei", "session_start"} <= fields:
        return {"module":"IMEI", "type":"IMEI_IPDR", "operator":operator, "confidence":"scope_metadata"}
    if imei_request and "report type" in preamble and "gprs report" in preamble and "imei" in fields:
        return {"module":"IMEI", "type":"IMEI_GPRS", "operator":operator, "confidence":"scope_metadata"}
    if imei_request and "dot report" in preamble and "imei" in fields and (
            "source_ip" in fields or "translated_ip" in fields):
        return {"module":"IMEI", "type":"IMEI_IPDR", "operator":operator, "confidence":"scope_metadata"}
    if ("call details of cell id" in preamble and "first_cell_id" in fields
            and "a_party" in fields and "call_date" in fields):
        return {"module":"TOWER_DUMP", "type":"TOWER_CDR", "operator":operator, "confidence":"scope_metadata"}

    if "ipdr of cell id" in text or "cell id_ipdrnat" in path.name.lower() or "cell id_ipdrnat" in text:
        # File name alone is not enough to certify tower format.
        if "ipdr of cell id" in text or "static/dynamic ip address allocation" in text:
            return {"module":"TOWER_DUMP","type":"TOWER_IPDR","operator":operator,"confidence":"signature"}
    if "gprs of cell id" in text or "report type :- gprs report" in text:
        return {"module":"TOWER_DUMP","type":"TOWER_GPRS","operator":operator,"confidence":"signature"}
    from modules.loader.tower_evidence_router import is_jio_cell_target_report
    if ("search criteria : first_cell_id" in text
            or "report type :- main cdr report" in text
            and re.search(r"(?m)^\s*cellid\s*:\s*-?\s*\S+", text)
            or is_jio_cell_target_report(path, text)):
        return {"module":"TOWER_DUMP","type":"TOWER_CDR","operator":operator,"confidence":"signature"}
    if "search criteria : imei" in text or "search criteria: imei" in text:
        sub = "IMEI_IPDR" if ("source_ip" in fields or "destination_ip" in fields) else "IMEI_CDR"
        return {"module":"IMEI","type":sub,"operator":operator,"confidence":"signature"}
    if {"imei", "imsi"} <= fields and not fields.intersection({"a_party", "b_party", "source_ip", "destination_ip", "call_date", "event_time", "session_start"}):
        return {"module":"IMEI", "type":"IMEI_INVENTORY","operator":operator,"confidence":"structure"}
    if ("source_ip" in fields or "translated_ip" in fields) and ("destination_ip" in fields or "session_start" in fields):
        return {"module":"IPDR","type":"IPDR","operator":operator,"confidence":"structure"}
    if {"a_party", "b_party"} <= fields or "b_party" in fields and "call_date" in fields:
        return {"module":"CDR","type":"CDR","operator":operator,"confidence":"structure"}
    if tower and "first_cell_id" in fields:
        return {"module":"TOWER_DUMP","type":"TOWER_CDR","operator":operator,"confidence":"structure"}
    return {"module":"UNKNOWN","type":"UNKNOWN","operator":operator,"confidence":"unknown"}


def inspect_universal_evidence(path: str | Path) -> dict[str, Any]:
    """Read header and source fingerprint, without claiming the rows are forensic-valid."""
    p = Path(path).expanduser().resolve()
    base = {"ok":False, "status":"rejected", "file":str(p), "source_sha256":None,
        "suggested_module":"UNKNOWN", "suggested_type":"UNKNOWN", "operator":"Unknown",
        "operator_source":"none", "operator_confidence":"unknown",
        "column_mapping":{},"ambiguous":[],"warnings":[],"errors":[],"metadata":{}}
    try:
        head = _read_header(p)
        proposed, ambiguous = proposed_mapping(head["headers"])
        ident = _signature(p, head, proposed)
        operator_detail = detect_operator(p, head)
        if operator_detail["operator"] == "Unknown" and ident["operator"] != "Unknown":
            # A verified legacy report-format signature can supply a *provisional*
            # issuer hint. Do not confuse report provenance with subscriber network.
            legacy = canonical_operator(ident["operator"])
            if legacy != "Unknown" and operator_detail["operator_source"] == "none":
                operator_detail = {
                    "operator": legacy, "operator_source": "existing_report_signature",
                    "operator_confidence": "provisional",
                    "operator_warning": "Operator comes from a recognized report layout; issuing provider requires verification.",
                }
        if len(set(map(norm, head["headers"]))) != len(head["headers"]):
            ambiguous.append({"field":"headers", "warning":"Duplicate normalized column names; needs manual resolution"})
        base.update(ok=True,status="needs_review", source_sha256=_sha256(p),
            suggested_module=ident["module"],suggested_type=ident["type"],operator=operator_detail["operator"],
            operator_source=operator_detail["operator_source"],
            operator_confidence=operator_detail["operator_confidence"],
            column_mapping=proposed,ambiguous=ambiguous,
            metadata={**head,"header_fingerprint":header_fingerprint(head["headers"]),
                      "detector_confidence":ident["confidence"],
                      "operator_source":operator_detail["operator_source"],
                      "operator_confidence":operator_detail["operator_confidence"],
                      "size_bytes":p.stat().st_size})
        base["warnings"].append("Auto-detection is provisional. Unknown formats need analyst approval before downstream investigation.")
        if operator_detail["operator_warning"]:
            base["warnings"].append(operator_detail["operator_warning"])
    except Exception as exc:
        base["errors"].append(f"{type(exc).__name__}: {exc}")
    return base


def _profile_path(profile_dir: str | Path, fingerprint: str, evidence_type: str) -> Path:
    if evidence_type not in TYPES: raise ValueError("Invalid profile type")
    return Path(profile_dir).expanduser().resolve() / ("format_" + fingerprint + "_" + evidence_type + ".json")


def approve_format_profile(path: str | Path, *, evidence_type: str,
    field_mapping: dict[str,str] | None = None, approved_by: str,
    time_format: str | None = None, timezone_name: str | None = None,
    operator: str = "Unknown", profile_dir: str | Path) -> dict[str,Any]:
    """Explicit approval. Save header mapping only (no subscriber rows).

    Approval does NOT provide real authentication or verify operator provenance.
    Supply an explicit datetime format and timezone for time-based evidence.
    """
    inspected = inspect_universal_evidence(path)
    if not inspected["ok"]: raise ValueError("Cannot approve unreadable file: " + "; ".join(inspected["errors"]))
    if evidence_type not in TYPES: raise ValueError("Invalid evidence type")
    if not str(approved_by).strip(): raise ValueError("approved_by is required")
    mapping = dict(field_mapping) if field_mapping is not None else dict(inspected["column_mapping"])
    unknown_fields = set(mapping) - set(ALIASES)
    if unknown_fields: raise ValueError("Unknown canonical fields: " + ", ".join(sorted(unknown_fields)))
    headers = inspected["metadata"]["headers"]
    if any(src not in headers for src in mapping.values()): raise ValueError("Mapped source column does not exist")
    if len(set(mapping.values())) != len(mapping): raise ValueError("Duplicate source field mapping requires resolution")
    if len(set(map(norm, headers))) != len(headers): raise ValueError("Duplicate headers require a corrected source file")
    missing = missing_groups(evidence_type, mapping)
    if missing: raise ValueError(f"Missing required field groups for {evidence_type}: {missing}")
    if evidence_type in TIMED_TYPES:
        if not time_format or not timezone_name:
            raise ValueError("Timed evidence requires explicit time_format and timezone_name")
        if len(time_format)>80 or not re.fullmatch(r"[a-zA-Z0-9_+./:-]{1,64}", timezone_name):
            raise ValueError("Invalid time format or timezone name")
    profile = {"version":PROFILE_VERSION,"header_fingerprint":inspected["metadata"]["header_fingerprint"],
        "headers":headers,"module":TYPE_MODULE[evidence_type],"evidence_type":evidence_type,
        "field_mapping":mapping,"approved_by":str(approved_by).strip(),
        "approved_at_utc":datetime.now(timezone.utc).isoformat(),
        "time_format":time_format,"timezone_name":timezone_name,"operator":str(operator).strip() or "Unknown",
        "note":"Operator label and field meanings manually approved; no independent verification."}
    output = _profile_path(profile_dir, profile["header_fingerprint"], evidence_type)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Protect the local mapping from partial writes; directory is investigator-managed.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent, delete=False) as tmp:
        json.dump(profile,tmp,indent=2,ensure_ascii=False)
        tempname=tmp.name
    os.replace(tempname, output)
    return profile


def _load_profile(path: Path, fingerprint: str, module: str | None, evidence_type: str | None) -> dict | None:
    candidates = ([evidence_type] if evidence_type is not None else
                  [item for item in TYPES if module is None or TYPE_MODULE[item] == module])
    found = [_profile_path(path,fingerprint,t) for t in candidates if _profile_path(path,fingerprint,t).is_file()]
    if not found: return None
    if len(found) != 1:
        raise ValueError("Multiple approved profiles match these columns; choose selected_type explicitly")
    profile = json.loads(found[0].read_text(encoding="utf-8"))
    if profile.get("version") != PROFILE_VERSION or profile.get("header_fingerprint") != fingerprint:
        raise ValueError("Invalid/stale format profile")
    if header_fingerprint(profile.get("headers",[])) != fingerprint:
        raise ValueError("Approved profile header mismatch")
    mapping = profile.get("field_mapping")
    if not isinstance(mapping,dict) or set(mapping)-set(ALIASES):
        raise ValueError("Approved profile contains unrecognized canonical fields")
    if any(v not in profile["headers"] for v in mapping.values()) or len(set(mapping.values())) != len(mapping):
        raise ValueError("Approved profile contains invalid/duplicated source columns")
    if missing_groups(profile.get("evidence_type"),mapping) if profile.get("evidence_type") in TYPES else True:
        raise ValueError("Approved profile lacks required evidence fields")
    if profile.get("evidence_type") in TIMED_TYPES and (not profile.get("time_format") or not profile.get("timezone_name")):
        raise ValueError("Approved timed profile lacks explicit timestamp semantics")
    if profile.get("evidence_type") not in TYPES or profile.get("module")!=TYPE_MODULE[profile["evidence_type"]]:
        raise ValueError("Malformed format profile")
    if module and module != profile["module"]: raise ValueError("Approved profile conflicts with selected module")
    return profile


def _read_raw(path: Path, header: dict, max_rows: int) -> pd.DataFrame:
    if not 0 < max_rows <= MAX_ROWS: raise ValueError("max_rows must be 1..1,000,000")
    if header["kind"] == "excel":
        result = pd.read_excel(path,header=header["header_row"], nrows=max_rows+1,dtype=str,keep_default_na=False)
    else:
        result = pd.read_csv(path,sep=header["delimiter"],header=header["header_row"],
            encoding=header["encoding"],dtype=str,keep_default_na=False,
            on_bad_lines="error",nrows=max_rows+1,low_memory=False)
    if len(result)>max_rows: raise ValueError("Record count exceeds configured maximum")
    if result.empty: raise ValueError("No evidence data rows")
    # Empty trailing vendor columns are preserved for audit, not silently discarded.
    if len(result.columns)!=len(header["headers"]):
        raise ValueError("Header schema changed while reading")
    # Zero-based index + 1: logical data row, not necessarily a physical CSV line.
    result["source_record_index"] = pd.RangeIndex(1,len(result)+1)
    return result


def _parse_time(raw: pd.DataFrame, mapping: dict[str,str], fmt: str, zone: str) -> pd.Series:
    """Use only mapped source columns; fall back only when prior mapped time is blank.

    An IPDR TIME1 column can legitimately be empty for pure IP allocations.
    Allocation date and allocation clock time are separate in several Jio reports.
    """
    candidates=[]
    for field in ("event_time","session_start"):
        if field in mapping: candidates.append(raw[mapping[field]].astype(str).str.strip())
    if "allocation_start" in mapping:
        text=raw[mapping["allocation_start"]].astype(str).str.strip()
        if "allocation_start_time" in mapping:
            text=text + " " + raw[mapping["allocation_start_time"]].astype(str).str.strip()
        candidates.append(text)
    if "call_date" in mapping:
        text=raw[mapping["call_date"]].astype(str).str.strip()
        if "call_time" in mapping:
            text=text + " " + raw[mapping["call_time"]].astype(str).str.strip()
        candidates.append(text)
    parsed=pd.Series(pd.NaT,index=raw.index,dtype="datetime64[ns]")
    for series in candidates:
        candidate=pd.to_datetime(series,format=fmt,errors="coerce")
        parsed=parsed.combine_first(candidate)
    if getattr(parsed.dt, "tz", None) is None:
        parsed = parsed.dt.tz_localize(zone,ambiguous="NaT",nonexistent="NaT")
    else:
        parsed = parsed.dt.tz_convert(zone)
    return parsed


def _validate_and_normalize(raw: pd.DataFrame, profile: dict, provenance: dict[str,str]) -> tuple[pd.DataFrame,pd.DataFrame,dict]:
    mapping = profile["field_mapping"]
    missing = missing_groups(profile["evidence_type"],mapping)
    if missing: raise ValueError(f"Approved profile lacks required fields: {missing}")
    df = pd.DataFrame(index=raw.index)
    for field, column in mapping.items(): df[field]=raw[column].astype("string").fillna("").str.strip()
    for column in ("imei", "imsi", "a_party", "b_party", "subscriber_number", "first_cell_id", "last_cell_id"):
        if column in df.columns: df[column] = df[column].str.strip().str.strip("'\"")
    df["operator"] = profile["operator"]
    df["source_format"] = "UNIVERSAL_APPROVED_PROFILE_V1"
    df["evidence_type"] = profile["evidence_type"]
    df["source_file"] = provenance["source_file"]
    df["original_source_sha256"] = provenance["source_sha256"]
    df["archive_member"] = provenance.get("archive_member", "")
    df["source_record_index"] = raw["source_record_index"].astype("int64")
    df["source_row_number"] = df["source_record_index"] + provenance["header_row"] + 1
    # source_row_number is only an estimate when quoted embedded newlines occur.
    errors = pd.Series("",index=df.index,dtype="string")
    if profile["evidence_type"] in TIMED_TYPES:
        times = _parse_time(raw,mapping,profile["time_format"],profile["timezone_name"])
        df["event_time"] = times
        bad = times.isna()
        errors.loc[bad] = errors.loc[bad] + "BAD_OR_AMBIGUOUS_TIMESTAMP;"
    for field in ("source_ip", "translated_ip", "destination_ip"):
        if field not in df: continue
        def valid_ip(v):
            if not v: return True
            try: ipaddress.ip_address(v); return True
            except ValueError: return False
        invalid=~df[field].map(valid_ip)
        errors.loc[invalid]=errors.loc[invalid] + f"INVALID_{field.upper()};"
    for field in ("source_port","translated_port","destination_port"):
        if field not in df: continue
        numbers=pd.to_numeric(df[field],errors="coerce")
        bad=(df[field].ne("") & (numbers.isna() | numbers.lt(0) | numbers.gt(65535) | numbers.ne(numbers.round())))
        errors.loc[bad]=errors.loc[bad] + f"INVALID_{field.upper()};"
        df[field] = numbers.astype("Int64")
    for field in ("call_duration","uplink_volume","downlink_volume"):
        if field not in df:continue
        numbers = pd.to_numeric(df[field],errors="coerce")
        bad=df[field].ne("") & (numbers.isna() | numbers.lt(0))
        errors.loc[bad]=errors.loc[bad] + f"INVALID_{field.upper()};"
        df[field] = numbers
    # Keep rejected rows with reasons and provenance. Never silently discard.
    rejected=df.loc[errors.ne("")].copy()
    rejected["reject_reason"] = errors.loc[errors.ne("")]
    valid=df.loc[errors.eq("")].copy().reset_index(drop=True)
    rejected=rejected.reset_index(drop=True)
    typ = profile["evidence_type"]
    if typ in {"CDR","TOWER_CDR","IMEI_CDR"}:
        if "a_party" not in valid and "subscriber_number" in valid: valid["a_party"]=valid["subscriber_number"]
        if "subscriber_number" not in valid and "a_party" in valid: valid["subscriber_number"]=valid["a_party"]
        if "event_time" in valid:
            valid["call_datetime"] = valid["event_time"]
            valid["call_date"] = valid["event_time"].dt.strftime("%Y-%m-%d")
            valid["call_time"] = valid["event_time"].dt.strftime("%H:%M:%S")
        if "call_duration" in valid: valid["call_duration"] = pd.to_numeric(valid["call_duration"],errors="coerce")
    elif typ in {"IPDR","TOWER_IPDR","IMEI_IPDR"}:
        valid["record_type"] = "IPDR_UNCLASSIFIED_EVENT_APPROVED_MAPPING"
        # An allocation-start boundary is not proof of a subscriber session start.
        valid["report_scope"] = "UNSPECIFIED_APPROVED_MAPPING"
    elif typ in {"TOWER_GPRS","IMEI_GPRS"}:
        valid["record_type"] = "GPRS_EVENT_UNIVERSAL_APPROVED"
    # Return validated parsed fields only. Existing specialized loaders remain the authority
    # for derived case summaries; see universal_bridge for explicit handoff.
    summary={"records_read":len(raw),"records_accepted":len(valid),"records_rejected":len(rejected),
             "rejection_reasons":rejected["reject_reason"].value_counts().to_dict() if not rejected.empty else {},
             "module":profile["module"],"evidence_type":typ}
    return valid,rejected,summary


def _extract_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo, destination: Path) -> Path:
    name=info.filename.replace("\\","/")
    parts=Path(name).parts
    if name.startswith("/") or ".." in parts or re.match(r"^[a-zA-Z]:",name):
        raise ValueError("Unsafe ZIP member path")
    if (info.external_attr >> 16) & 0o170000 == 0o120000:
        raise ValueError("ZIP symlink rejected")
    if info.file_size>MAX_FILE_BYTES: raise ValueError("Archive member too large")
    with zf.open(info) as inp, destination.open("wb") as out:
        copied=0
        while True:
            block=inp.read(1024*1024)
            if not block: break
            copied+=len(block)
            if copied>MAX_FILE_BYTES: raise ValueError("Archive member exceeded limit")
            out.write(block)
    return destination


@contextlib.contextmanager
def _members(path: Path) -> Iterator[list[tuple[Path,str]]]:
    if not path.is_file(): raise FileNotFoundError(path)
    if path.stat().st_size>MAX_FILE_BYTES: raise ValueError("Source exceeds 256 MiB cap")
    with tempfile.TemporaryDirectory(prefix="ethicalarmor_universal_") as td:
        folder=Path(td)
        files=[]
        if path.suffix.lower()==".zip":
            with zipfile.ZipFile(path) as zf:
                members=[x for x in zf.infolist() if not x.is_dir()]
                if len(members)>MAX_ARCHIVE_MEMBERS: raise ValueError("Too many ZIP members")
                if sum(x.file_size for x in members)>MAX_ARCHIVE_TOTAL_BYTES:
                    raise ValueError("ZIP decompression quota exceeded")
                for idx,info in enumerate(members):
                    ext=Path(info.filename).suffix.lower()
                    if ext not in TABLE_EXTENSIONS: continue
                    target=folder/f"{idx:04d}{ext}"
                    files.append((_extract_member(zf,info,target), info.filename))
        elif path.suffix.lower()==".gz":
            name=path.stem
            ext=Path(name).suffix.lower()
            if ext not in TABLE_EXTENSIONS: raise ValueError("Unsupported gzip inner file")
            target=folder/("00"+ext)
            count=0
            with gzip.open(path,"rb") as inp, target.open("wb") as out:
                while True:
                    block=inp.read(1024*1024)
                    if not block: break
                    count+=len(block)
                    if count>MAX_FILE_BYTES: raise ValueError("GZIP decompression quota exceeded")
                    out.write(block)
            files.append((target,name))
        elif path.suffix.lower() in TABLE_EXTENSIONS:
            files.append((path,""))
        else: raise ValueError("Unsupported file extension")
        if not files: raise ValueError("No recognized tabular evidence members")
        yield files


def _empty_report_info(path: Path, header: dict[str, Any]) -> dict[str, Any] | None:
    """Detect a genuine header-only/no-records report, not a broken parser.

    Requires a coherent recognized header and *no* substantive data rows.
    Never makes an empty report analysis-ready or registers case evidence.
    Prevents metadata/footer disclaimers from being counted as telecom events.
    """
    headers = list(header.get("headers") or [])
    if header.get("kind") != "text" or len(headers) < 5:
        return None
    mapping, _ = proposed_mapping(headers)
    if len(mapping) < 3:
        return None
    raw = path.read_bytes()
    # Bound memory for this format probe, separate from MAX_FILE_BYTES.
    if len(raw) > 2 * 1024 * 1024:
        return None
    encoding = header.get("encoding") or "utf-8-sig"
    try:
        text = raw.decode(encoding)
        rows = list(csv.reader(text.splitlines(), delimiter=header["delimiter"]))
    except (UnicodeError, csv.Error, KeyError):
        return None
    index = int(header["header_row"])
    if index >= len(rows):
        return None
    # Data records generally contain at least three populated columns.  A
    # text-only footer, disclaimer, and repeated separator are not data.
    for row in rows[index + 1:]:
        nonempty = [str(c).strip() for c in row if str(c).strip()]
        if len(nonempty) >= 3:
            return None
        if len(nonempty) >= 2 and len(row) >= len(headers) // 2:
            return None
    prefix = "\n".join(text.splitlines()[:max(index + 1, 1)]).lower()
    all_lower = text.lower()
    explicit = bool(re.search(r"\bno\s+(?:data|records?)\s+(?:found|available)\b", all_lower)
                    or re.search(r"\btotal\s+records\s*:\s*,?\s*0\b", prefix))
    return {"explicit_no_records":explicit, "header_only":not explicit}


def _native_import(path: Path, info: dict) -> dict | None:
    """Opt-in bridge to verified legacy parsers; never use unknown-format heuristics."""
    from modules.loader.universal_native import try_native_import
    return try_native_import(path,info)


def load_universal_evidence(path: str | Path, *, profiles_dir: str | Path | None = None,
    selected_module: str | None = None, selected_type: str | None = None, allow_native: bool = True,
    max_rows: int = MAX_ROWS, include_raw: bool = False,
    selected_operator: str | None = None) -> dict[str,Any]:
    """Import any supported file; return per-member results with explicit trust state.

    status: native_validated | ready | needs_review | rejected
    - native_validated: known verified parser succeeded (still requires case-level checks)
    - ready: analyst-approved mapping passed validations (NOT identical to native)
    - needs_review: never feed into case correlations/reports
    - rejected: unreadable/invalid
    """
    source=Path(path).expanduser().resolve()
    result={"ok":False,"source_file":str(source),"source_sha256":None,
            "file_results":[],"warnings":[],"errors":[]}
    if selected_operator is not None and selected_operator not in KNOWN_OPERATORS:
        result["errors"].append("selected_operator must be Jio, Airtel, Vi, BSNL or MTNL")
        return result
    if selected_module is not None and selected_module not in MODULES:
        result["errors"].append("selected_module must be one of: "+", ".join(MODULES))
        return result
    if selected_type is not None and (selected_type not in TYPES or (selected_module and TYPE_MODULE[selected_type]!=selected_module)):
        result["errors"].append("selected_type must match selected_module and be a recognized evidence type")
        return result
    try:
        result["source_sha256"]=_sha256(source)
        with _members(source) as files:
            for member,member_name in files:
                source_ref=str(source) + ("::"+member_name if member_name else "")
                info=inspect_universal_evidence(member)
                item={"ok":False,"status":"rejected","module":"UNKNOWN","evidence_type":"UNKNOWN",
                      "file":source_ref,"source_sha256":result["source_sha256"],"archive_member":member_name,
                      "operator":"Unknown","operator_source":"none","operator_confidence":"unknown",
                      "df":pd.DataFrame(),"rejected_rows":pd.DataFrame(),
                      "metadata":{},"warnings":list(info["warnings"]),"errors":list(info["errors"])}
                if not info["ok"]:
                    result["file_results"].append(item);continue
                module=info["suggested_module"]
                item.update(status="needs_review",module=module,evidence_type=info["suggested_type"],
                    operator=info["operator"],operator_source=info["operator_source"],
                    operator_confidence=info["operator_confidence"],
                    column_mapping=info["column_mapping"],
                    ambiguous=info["ambiguous"],metadata={**info["metadata"],"source_file":source_ref,
                    "source_sha256":result["source_sha256"],"archive_member":member_name})
                empty_info = _empty_report_info(member, info["metadata"])
                if empty_info is not None:
                    item["status"] = "no_data"
                    item["no_data_reason"] = ("explicit_no_records" if empty_info["explicit_no_records"]
                                               else "header_only_unconfirmed")
                    item["warnings"].append(
                        "Report has no telecom data rows; no evidence imported. "
                        + ("Source explicitly states no records found."
                           if empty_info["explicit_no_records"]
                           else "Header-only export without explicit zero-record marker; verify completeness.")
                    )
                    result["file_results"].append(item)
                    continue
                profile=None
                profile_error=False
                profile=None
                profile_error=False
                if profiles_dir is not None:
                    try:
                        profile=_load_profile(Path(profiles_dir),info["metadata"]["header_fingerprint"],selected_module,selected_type)
                    except (ValueError, OSError, json.JSONDecodeError) as exc:
                        item["errors"].append(str(exc))
                        profile_error=True
                if profile_error:
                    item["status"]="rejected"
                    result["file_results"].append(item)
                    continue
                if profile is not None:
                    item.update(module=profile["module"],evidence_type=profile["evidence_type"],
                                operator=profile["operator"],operator_source="approved_profile",
                                operator_confidence="analyst_approved")
                    try:
                        raw=_read_raw(member,info["metadata"],max_rows)
                        provenance={"source_file":source_ref,"source_sha256":result["source_sha256"],
                            "archive_member":member_name,"header_row":info["metadata"]["header_row"]}
                        df,rejects,stats=_validate_and_normalize(raw,profile,provenance)
                        item.update(ok=not df.empty,status="ready" if not df.empty else "rejected",
                                    df=df,rejected_rows=rejects,stats=stats,approved_profile=profile)
                        if df.empty:
                            item["errors"].append("All records were quarantined: no analysis-ready rows")
                        if include_raw: item["raw"]=raw
                    except Exception as exc:
                        item["status"]="rejected";item["errors"].append(f"Approved mapping failed: {type(exc).__name__}: {exc}")
                elif allow_native and module!="UNKNOWN" and (selected_module is None or selected_module==module) and (selected_type is None or selected_type==info["suggested_type"]):
                    try:
                        native=_native_import(member,info)
                        if native is not None and native.get("ok"):
                            df=native.get("df",pd.DataFrame()).copy()
                            if "source_file" in df: df["source_file"]=source_ref
                            df["original_source_sha256"]=result["source_sha256"]
                            df["archive_member"]=member_name
                            native_meta = dict(native.get("metadata") or {})
                            native_meta["source_file"] = source_ref
                            native_meta["archive_member"] = member_name
                            native_meta["original_source_sha256"] = result["source_sha256"]
                            native_operator=canonical_operator(native.get("operator", "Unknown"))
                            # Legacy normal CDR loader has no operator metadata. Never
                            # overwrite a source-derived label with an empty/Unknown value.
                            # Reject a disagreement between issuer metadata and native loader.
                            source_operator=canonical_operator(item.get("operator"))
                            source_explicit=item.get("operator_source") in {
                                "declared_operator_metadata", "source_issuer_banner", "record_operator_column"
                            }
                            if (source_explicit and native_operator != "Unknown"
                                    and source_operator != native_operator):
                                item["status"]="needs_review"
                                item["warnings"].append("Source operator evidence conflicts with native parser; "
                                                        "do not import until provider is verified.")
                            else:
                                if native_operator != "Unknown" and not source_explicit:
                                    item["operator"] = native_operator
                                    item["operator_source"] = "native_parser"
                                    item["operator_confidence"] = "format_validated"
                                item.update(ok=True,status="native_validated",module=native["module"],
                                  evidence_type=native["evidence_type"],
                                  df=df,rejected_rows=native.get("rejected_rows",pd.DataFrame()),
                                  native_metadata=native_meta, warnings=item["warnings"]+native.get("warnings",[]))
                        else:
                            item["warnings"].append("No suitable verified native parser; manual review required")
                    except Exception as exc:
                        item["warnings"].append(f"Existing native parser failed; review required: {type(exc).__name__}: {exc}")
                if item["status"] == "needs_review":
                    try:
                        raw=_read_raw(member,info["metadata"],max_rows)
                        item["review_stats"]={"rows":len(raw),"columns":len(info["metadata"]["headers"]),
                            "suggested_type":info["suggested_type"],"mapped_fields":sorted(info["column_mapping"]),
                            "missing_required_groups":missing_groups(info["suggested_type"],info["column_mapping"]) if info["suggested_type"] in TYPES else []}
                        if include_raw: item["raw"]=raw
                    except Exception as exc:
                        item["status"]="rejected";item["errors"].append(f"Cannot read rows: {type(exc).__name__}: {exc}")
                if selected_operator and item["status"] not in {"rejected"}:
                    original_operator=canonical_operator(item["operator"])
                    strong_source=item.get("operator_source") in {
                        "declared_operator_metadata", "source_issuer_banner",
                        "record_operator_column", "approved_profile", "native_parser",
                    }
                    conflicting_source=item.get("operator_source") in {
                        "conflicting_operator_metadata", "conflicting_issuer_banners",
                        "conflicting_record_operator_values",
                    }
                    if conflicting_source or (strong_source and original_operator not in ("Unknown",selected_operator)):
                        item["ok"]=False
                        item["status"]="needs_review"
                        item["df"]=pd.DataFrame()
                        item["warnings"].append("Selected operator conflicts with source operator evidence; review required.")
                    else:
                        if original_operator != selected_operator:
                            item["warnings"].append("Analyst-selected operator overrides an unknown/provisional source hint; "
                                                    "independent verification is required.")
                        item["operator"]=selected_operator
                        item["operator_source"]="analyst_selected"
                        item["operator_confidence"]="manually_asserted"
                        if isinstance(item.get("native_metadata"),dict):
                            item["native_metadata"]["operator_source"]="analyst_selected"
                        if isinstance(item.get("df"),pd.DataFrame) and not item["df"].empty:
                            # Do not modify original content columns or existing per-row operator data.
                            item["df"].attrs["selected_operator"] = selected_operator
                if selected_module and item["module"] not in (selected_module,"UNKNOWN"):
                    # Do not route a subscriber IPDR as tower data, even when recognizable.
                    item["ok"]=False;item["status"]="needs_review"
                    item["warnings"].append("Detected module conflicts with selected module: explicit review required")
                    item["df"]=pd.DataFrame()
                result["file_results"].append(item)
        result["ok"]=bool(result["file_results"]) and all(item["ok"] for item in result["file_results"])
        for item in result["file_results"]:
            result["warnings"].extend(item["warnings"])
            result["errors"].extend(item["errors"])
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    return result


def group_ready_by_module(import_result: dict[str,Any]) -> dict[str,list[dict]]:
    """Only return rows approved or verified by a known parser.

    Caller MUST still apply its case-specific analysis and access controls.
    """
    grouped={m:[] for m in MODULES}
    for item in import_result.get("file_results",[]):
        if item.get("ok") and item.get("status") in {"ready","native_validated"}:
            if item.get("module") in grouped: grouped[item["module"]].append(item)
    return grouped
