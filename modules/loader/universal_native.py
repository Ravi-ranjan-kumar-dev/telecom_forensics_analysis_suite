"""Read-only adapter to EthicalArmor's existing operator-specific parsers.

New/unverified formats must go through universal_evidence profile approval.
Legacy module APIs are not modified and remain independently callable.
"""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Any
import pandas as pd


def _as_result(raw: dict[str, Any], *, module: str, typ: str, frame_key: str = "df") -> dict | None:
    if not raw or not raw.get("ok"): return None
    frame = raw.get(frame_key)
    if not isinstance(frame,pd.DataFrame) or frame.empty: return None
    return {"ok":True,"module":module,"evidence_type":typ,
        "operator":raw.get("operator",raw.get("metadata",{}).get("operator","Unknown")),
        "df":frame, "metadata":raw.get("metadata",{}),
        "rejected_rows":raw.get("rejected_rows",pd.DataFrame()),
        "warnings":raw.get("warnings",[])}


def try_native_import(path: str | Path, inspection: dict[str,Any]) -> dict | None:
    """Try source-specific loaders only for recognized report families.

    Returns None on unknown/unsupported evidence; caller keeps needs_review status.
    Does NOT assume a native parser supports all operators and variants.
    """
    p=Path(path)
    module=inspection.get("suggested_module")
    typ=inspection.get("suggested_type")
    if module == "TOWER_DUMP":
        from modules.loader.tower_evidence_router import classify_tower_evidence
        recognized, _ = classify_tower_evidence(p)
        if recognized not in {"TOWER_IPDR","TOWER_CDR","TOWER_GPRS"}: return None
        if typ!=recognized: return None
        if recognized=="TOWER_IPDR":
            from modules.loader.tower_ipdr_loader import load_tower_ipdr_file
            raw=load_tower_ipdr_file(p)
        elif recognized=="TOWER_GPRS":
            from modules.loader.gprs_dump_loader import load_gprs_dump_file
            from modules.loader.tower_dump_loader import load_tower_dump
            raw=load_gprs_dump_file(p) if inspection.get("operator")=="Airtel" else load_tower_dump(p,enrich_cgi=False)
        else:
            from modules.loader.tower_dump_loader import load_tower_dump
            raw=load_tower_dump(p,enrich_cgi=False)
        return _as_result(raw,module=module,typ=recognized)
    if module == "IPDR" and typ=="IPDR":
        from modules.loader.ipdr_loader import load_ipdr_file
        raw=load_ipdr_file(p)
        # Explicitly reject search-request workbooks without actual session data.
        return _as_result(raw,module="IPDR",typ="IPDR",frame_key="data")
    if module == "CDR" and typ=="CDR":
        from modules.loader.multi_loader import load_one_cdr_file
        # Existing loader prints processing details; do not echo PII in universal UI.
        with contextlib.redirect_stdout(io.StringIO()):
            raw=load_one_cdr_file(str(p),p.name)
        # The legacy single-CDR loader returns a populated dict WITHOUT an
        # 'ok' key on success.  _as_result requires an explicit success flag.
        # Mark success only for a real dict; _as_result still verifies the df.
        if not isinstance(raw, dict):
            return None
        return _as_result({**raw, "ok": True},module="CDR",typ="CDR")
    if module == "IMEI":
        from modules.loader.imei_evidence_loader import (inspect_imei_evidence_file,
            normalize_imei_cdr_file,normalize_imei_ipdr_file,normalize_imei_gprs_file)
        inspection_result=inspect_imei_evidence_file(p)
        if not inspection_result.get("ok") or inspection_result.get("format_id")=="UNKNOWN":return None
        detected=str(inspection_result.get("source_type","")).upper()
        if detected=="CDR": normalized=normalize_imei_cdr_file(p,inspection_result);type_name="IMEI_CDR"
        elif detected=="IPDR": normalized=normalize_imei_ipdr_file(p,inspection_result);type_name="IMEI_IPDR"
        elif detected=="GPRS": normalized=normalize_imei_gprs_file(p,inspection=inspection_result);type_name="IMEI_GPRS"
        else:return None
        if not normalized.get("ok"):return None
        out=_as_result(normalized,module="IMEI",typ=type_name,frame_key="data")
        if out is not None:out["operator"]=inspection_result.get("operator","Unknown")
        return out
    return None
