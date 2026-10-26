"""Evidence-grounded telecom operator hints for Universal Evidence Engine.

Never derive operator ownership from subscriber numbers, IMEI, IMSI, cell prefixes,
MCC/MNC or report filename. India has MNP, roaming and shared/reused schemas.

An issuer banner/explicit source field is evidence of the *reported* operator,
not independent verification of the subscriber's current network affiliation.
A Jio-style report template is PROVISIONAL unless independently corroborated.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any

KNOWN_OPERATORS = ("Jio", "Airtel", "Vi", "BSNL", "MTNL")
_OPERATOR_COLUMN_NAMES = frozenset({
    "operator", "operator name", "telecom operator", "telecom service provider",
    "service provider", "network operator", "tsp", "service provider name",
})
_EXPLICIT_LABEL = re.compile(
    r"^\s*(?:operator(?:\s+name)?|telecom(?:\s+service)?\s+provider|"
    r"service\s+provider(?:\s+name)?|network\s+operator|tsp)\s*[:=,-]\s*(.*?)\s*$",
    re.IGNORECASE,
)


def canonical_operator(value: object) -> str:
    """Canonicalize named operators; contradictory names stay Unknown."""
    value = re.sub(r"\s+", " ", str(value or "").strip().strip("'\" ")).strip()
    if not value or value.casefold() in {"unknown", "null", "none", "nan", "n/a"}:
        return "Unknown"
    key = value.casefold()
    patterns = {
        "Jio": r"\b(?:reliance\s+jio(?:\s+infocomm)?|jio(?:\s+infocomm)?|rjil)\b",
        "Airtel": r"\b(?:bharti\s+airtel|airtel)\b",
        "Vi": r"\b(?:vodafone\s+idea|idea\s+cellular|vodafone|vil)\b",
        "BSNL": r"\b(?:bsnl|bharat\s+sanchar\s+nigam)\b",
        "MTNL": r"\b(?:mtnl|mahanagar\s+telephone\s+nigam)\b",
    }
    found = {name for name,pattern in patterns.items() if re.search(pattern,key)}
    if key == "vi": found.add("Vi")
    return next(iter(found)) if len(found)==1 else "Unknown"


def _out(operator="Unknown", source="none", confidence="unknown", warning="") -> dict[str, str]:
    return {"operator":operator, "operator_source":source,
            "operator_confidence":confidence, "operator_warning":warning}


def _distinct_operators(values: list[str]) -> set[str]:
    return {canonical_operator(v) for v in values} - {"Unknown"}


def _read_preview(path: Path, encoding: str | None) -> str:
    if not encoding: return ""
    with path.open("rb") as stream: data = stream.read(128 * 1024)
    return data.decode(encoding, errors="replace")


def _operator_record_column(preview: str, headers: list[str], header_index: int,
                            delimiter: str | None) -> dict[str,str] | None:
    if not delimiter: return None
    columns = [re.sub(r"\s+", " ", str(c).lower().replace("_", " ")).strip() for c in headers]
    indices = [i for i, name in enumerate(columns) if name in _OPERATOR_COLUMN_NAMES]
    if len(indices) != 1: return None
    try:
        reader = csv.reader(io.StringIO(preview), delimiter=delimiter)
        for _ in range(header_index + 1): next(reader)
        values=[]
        for row in reader:
            if len(values)>=100:break
            if len(row)>indices[0] and str(row[indices[0]]).strip():
                values.append(row[indices[0]])
    except (csv.Error, StopIteration):
        return None
    distinct = _distinct_operators(values)
    if len(distinct)>1:
        return _out("Unknown", "conflicting_record_operator_values", "unknown",
                    "Operator column has multiple providers; resolve per-row before treating source as one operator.")
    if len(distinct)==1:
        return _out(next(iter(distinct)), "record_operator_column", "reported",
                    "Operator is taken from source records and is not independently verified.")
    return None


def detect_operator(path: str | Path, header: dict[str,Any]) -> dict[str,str]:
    """Read only bounded source preview and header metadata to identify operator.

    Source priority: explicit pre-header metadata > issuer banner > operator column >
    provisional known report template. Unknown is a valid result (fail closed).
    """
    source = Path(path)
    if header.get("kind") != "text":
        return _out(warning="Excel operator requires source metadata/manual review; no guess from IDs.")
    preview=_read_preview(source, header.get("encoding"))
    lines=preview.splitlines()
    preamble=lines[:min(int(header.get("header_row", 0)), 100)]
    candidates=[]
    for line in preamble:
        hit=_EXPLICIT_LABEL.match(line.strip())
        if hit:
            found=canonical_operator(hit.group(1))
            if found!="Unknown": candidates.append(found)
    if candidates:
        if len(set(candidates))==1:
            return _out(candidates[0],"declared_operator_metadata","reported",
                        "Operator is declared in report metadata, not independently verified.")
        return _out("Unknown","conflicting_operator_metadata","unknown",
                    "Conflicting operator metadata; analyst must confirm the issuing provider.")

    preamble_text="\n".join(preamble).lower()
    # Look for issuer banner ONLY in preamble: values in records might mention
    # roaming networks or unrelated operators and are not proof of issuer.
    banner=[]
    for branded in ("bharti airtel", "vodafone idea call data records", "vil call data records", "reliance jio",
                    "jio infocomm", "bharat sanchar nigam", "mahanagar telephone nigam"):
        if branded in preamble_text: banner.append(canonical_operator(branded))
    banner = [value for value in banner if value!="Unknown"]
    if banner:
        if len(set(banner))==1:
            return _out(banner[0],"source_issuer_banner","reported",
                        "Operator is inferred from source report branding; verify authenticity.")
        return _out("Unknown","conflicting_issuer_banners","unknown",
                    "Multiple provider brands in report header; analyst verification required.")

    recorded = _operator_record_column(preview, list(header.get("headers", [])),
                                       int(header.get("header_row",0)), header.get("delimiter"))
    if recorded:
        return recorded

    normalized = {re.sub(r"\s+", " ",re.sub(r"[^a-z0-9]+", " ",h.lower())).strip()
                  for h in header.get("headers",[])}
    # This particular report family is characteristic of Jio, but it also
    # contains subscriber CDRs. It MUST NOT affect module/evidence-type routing.
    if ("ticket number" in preamble_text
            and "input value (msisdn/b party/imei/imsi/cell id)" in preamble_text
            and "calling party telephone number" in normalized
            and "called party telephone number" in normalized):
        return _out("Jio","jio_report_template","provisional",
                    "Jio is a provisional report-template match; verify the issuing operator. "
                    "This does not classify a subscriber CDR as a tower dump.")

    return _out(warning="No reliable operator declaration in the source; verify with the provider/report owner. "
                        "Phone prefixes, IMEI/IMSI and MCC/MNC alone are not sufficient.")
