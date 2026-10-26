"""Case/UI bridge: block review-only data from entering final reports.

Use with existing CDR / Tower Dump / IPDR / IMEI analysis controllers:
  result = load_universal_evidence(...)
  validated = require_analysis_ready(result, 'IPDR')
  for item in validated: use item['df'] with downstream controller contract.

This does NOT silently insert evidence into case store or reroute existing GUI.
"""
from __future__ import annotations

from typing import Any
import pandas as pd

from modules.loader.universal_schema import MODULES

class EvidenceReviewRequired(ValueError):
    pass


def require_analysis_ready(result: dict[str,Any], module: str, *, allow_partial: bool = False) -> list[dict[str,Any]]:
    """Fail closed on unknown/rejected/member-mismatch evidence by default."""
    if module not in MODULES: raise ValueError("Unknown module")
    files=result.get("file_results",[])
    if not files: raise EvidenceReviewRequired("No evidence files")
    blocked=[item for item in files if item.get("status") not in ("native_validated","ready")
             or item.get("module") != module or not item.get("ok")]
    if blocked and not allow_partial:
        raise EvidenceReviewRequired("Review or correct every member before module analysis: " +
             ", ".join(item.get("file", "unknown") for item in blocked[:5]))
    accepted=[item for item in files if item.get("module")==module and item.get("ok")
              and item.get("status") in {"native_validated","ready"}]
    if not accepted: raise EvidenceReviewRequired("No accepted evidence for " + module)
    return accepted


def module_preview(result: dict[str,Any]) -> list[dict[str,Any]]:
    """Safe metadata summary for GUI; never include raw subscriber values."""
    items=[]
    for file in result.get("file_results",[]):
        df=file.get("df")
        item={"file":file.get("file"),"module":file.get("module"),
              "evidence_type":file.get("evidence_type"),"status":file.get("status"),
              "operator":file.get("operator"),
              "operator_source":file.get("operator_source","none"),
              "operator_confidence":file.get("operator_confidence","unknown"),
              "accepted_rows":len(df) if isinstance(df,pd.DataFrame) else 0,
              "rejected_rows":len(file.get("rejected_rows",[])),
              "warnings":file.get("warnings",[]),"errors":file.get("errors",[])}
        item["review_stats"]=file.get("review_stats",{})
        items.append(item)
    return items


def descriptive_module_summary(items: list[dict[str,Any]], module: str) -> dict[str,Any]:
    """Preliminary descriptive analysis, NOT automated investigative conclusions.

    Accept only 'native_validated' / 'ready' rows. Counts are derived solely from
    recorded values; no guessing of locations, ownership, identities or suspects.
    """
    if module not in MODULES:raise ValueError("Unknown module")
    if not items: raise EvidenceReviewRequired("No analysis-ready rows")
    relevant=[]
    for it in items:
        if it.get("status") not in {"ready","native_validated"} or not it.get("ok") or it.get("module")!=module:
            raise EvidenceReviewRequired("Unapproved evidence in descriptive analysis")
        if not isinstance(it.get("df"),pd.DataFrame):
            raise EvidenceReviewRequired("Missing normalized dataframe")
        relevant.append(it)
    total=sum(len(it["df"]) for it in relevant)
    output={"module":module,"analysis_level":"DESCRIPTIVE_ONLY", "files":len(relevant),
        "rows":total,"by_type":{},"unique_counts":{},"warnings":[]}
    for it in relevant:
        typ=it.get("evidence_type","UNKNOWN")
        output["by_type"][typ]=output["by_type"].get(typ,0)+len(it["df"])
    # No invented conclusions from co-occurrence; counts only.
    for key in ("imei","imsi","subscriber_number","a_party","source_ip","translated_ip","destination_ip","first_cell_id"):
        seen=set()
        for it in relevant:
            df=it["df"]
            if key not in df:continue
            vals=df[key].dropna().astype(str).str.strip()
            seen.update(v for v in vals if v and v.lower() not in {"nan","none","<na>"})
        if seen:output["unique_counts"][key]=len(seen)
    output["warnings"].append("Descriptive counts only. Specialist module analysis and case evidence checks are still required.")
    return output
