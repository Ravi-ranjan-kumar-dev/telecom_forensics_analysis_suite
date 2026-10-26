"""Shared privacy-preserving preflight for all four EthicalArmor evidence modules.

Preflight is not a replacement for case-specific analysis or investigation reports.
Unapproved/invalid evidence cannot be passed to descriptive summaries.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.loader.universal_evidence import load_universal_evidence
from modules.loader.universal_bridge import module_preview, require_analysis_ready, descriptive_module_summary
from modules.loader.universal_schema import MODULES

DEFAULT_PROFILES_DIR = Path(__file__).resolve().parents[2] / "data" / "format_profiles"


def run_universal_preflight(path: str | Path, *, module: str | None = None,
                             profiles_dir: str | Path | None = None,
                             selected_operator: str | None = None) -> dict[str, Any]:
    """Return *metadata-only* summary. Never return raw evidence, IDs or subscriber rows."""
    if module is not None and module not in MODULES:
        raise ValueError("Unrecognized module")
    result = load_universal_evidence(
        path, profiles_dir=profiles_dir or DEFAULT_PROFILES_DIR,
        selected_module=module, selected_operator=selected_operator,
    )
    summary = {"ok": bool(result.get("ok")), "source_sha256": result.get("source_sha256"),
               "files": module_preview(result), "errors": list(result.get("errors", [])),
               "analysis": [], "needs_review": False}
    # Never consume unverified rows in even a descriptive analysis.
    if summary["ok"]:
        validated_modules = {entry["module"] for entry in summary["files"]}
        for selected in sorted(validated_modules):
            try:
                accepted = require_analysis_ready(result, selected)
                summary["analysis"].append(descriptive_module_summary(accepted, selected))
            except ValueError:
                summary["needs_review"] = True
    summary["needs_review"] |= any(
        entry.get("status") not in ("ready", "native_validated") for entry in summary["files"]
    )
    return summary
