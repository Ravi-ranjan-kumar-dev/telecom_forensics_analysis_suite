"""CLI user-facing preflight. Existing case workflows remain unchanged."""
from __future__ import annotations
from pathlib import Path

from modules.loader.universal_workspace import run_universal_preflight


def handle_universal_evidence() -> None:
    print("\n=== UNIVERSAL EVIDENCE PREFLIGHT (CDR / TOWER / IPDR / IMEI) ===")
    path = input("Evidence file path (CSV/TXT/TSV/Excel/ZIP/GZ): ").strip().strip('"')
    if not path:
        print("No file selected.")
        return
    module_text = input("Module [AUTO/CDR/TOWER_DUMP/IPDR/IMEI] (default AUTO): ").strip().upper()
    module = None if module_text in ("", "AUTO") else module_text
    if module not in (None, "CDR", "TOWER_DUMP", "IPDR", "IMEI"):
        print("Invalid module; nothing loaded.")
        return
    try:
        result = run_universal_preflight(Path(path), module=module)
    except Exception as exc:
        print(f"Preflight failed: {type(exc).__name__}: {exc}")
        return
    print("Source SHA-256:", result.get("source_sha256") or "unavailable")
    for row in result["files"]:
        print(f"{Path(row['file']).name}: {row['module']} / {row['evidence_type']} "
              f"| {row['status']} | operator={row['operator']} "
              f"({row['operator_confidence']}) "
              f"| accepted={row['accepted_rows']} rejected={row['rejected_rows']}")
        for message in row.get("warnings", []):
            print("  WARNING:", message)
        for message in row.get("errors", []):
            print("  ERROR:", message)
    for report in result["analysis"]:
        print(f"Verified descriptive totals: {report['module']} "
              f"{report['rows']} rows in {report['files']} file(s)")
    if result["needs_review"]:
        print("REVIEW REQUIRED: do not use these rows in investigative reports yet.")
    if result["errors"]:
        print("Import errors:", "; ".join(result["errors"]))
    print("Note: preflight does not register case evidence or execute case-specific analysis.")
