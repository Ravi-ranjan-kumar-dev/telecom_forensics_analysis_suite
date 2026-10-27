"""IMEI GUI-first viewing and explicitly requested full report export.

Only in-memory analyzed results are used for the viewer.
No report files are written until export_imei_full_reports is invoked.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any
import pandas as pd

PREVIEW_ROWS = 600


def build_imei_viewer_sheets(result: dict[str, Any]) -> dict[str, pd.DataFrame]:
    """Curated per-IMEI DataFrames, explicitly capped to avoid a huge GUI RAM load."""
    sheets: dict[str, pd.DataFrame] = {}
    singles = result.get("single_results") or []
    summaries = []
    for i, item in enumerate(singles, 1):
        if not isinstance(item, dict):
            continue
        analysis = item.get("analysis")
        identifier = str(item.get("identifier") or f"ID {i}")
        if not isinstance(analysis, dict):
            continue
        summaries.append({
            "IMEI": identifier,
            "Status": str(analysis.get("overall_status", "")),
            "Input Records": item.get("input_records", ""),
            "Output Records": item.get("output_records", ""),
        })
        for key, frame in analysis.items():
            if not isinstance(frame, pd.DataFrame) or frame.empty:
                continue
            label = f"{i}. {identifier[-6:]} {str(key).replace('_', ' ').title()}"
            if len(sheets) >= 55:
                break
            label += f" (preview {min(len(frame), PREVIEW_ROWS):,}/{len(frame):,})" if len(frame) > PREVIEW_ROWS else ""
            sheets[label] = frame.head(PREVIEW_ROWS).copy()
    common = result.get("common_result")
    if isinstance(common, dict) and isinstance(common.get("analysis"), dict):
        for key, frame in common["analysis"].items():
            if isinstance(frame, pd.DataFrame) and not frame.empty and len(sheets) < 65:
                label = f"Common {str(key).replace('_',' ').title()}"
                if len(frame) > PREVIEW_ROWS:
                    label += f" (preview {PREVIEW_ROWS:,}/{len(frame):,})"
                sheets[label] = frame.head(PREVIEW_ROWS).copy()
    if summaries:
        return {"IMEI Analysis Summary": pd.DataFrame(summaries), **sheets}
    return sheets


def export_imei_full_reports(result: dict[str, Any], destination: str | Path) -> list[str]:
    """Generate from analysis results only, never reload/reanalyze case evidence.

    Generates all workbooks in a private temporary folder first; moves them
    into the requested destination after successful rendering. Existing
    destination files are NOT overwritten, preventing evidence loss.
    """
    if not isinstance(result, dict) or not result.get("single_results"):
        return []
    mode = str(result.get("_ea_imei_export_mode") or result.get("mode", "")).lower()
    if mode not in {"cdr", "ipdr", "gprs", "unified"}:
        raise ValueError("Invalid IMEI analysis export mode")
    case = result.get("_ea_imei_export_case")
    if not isinstance(case, dict):
        raise ValueError("Missing current-case metadata for IMEI Export")
    dest = Path(destination).expanduser().resolve()
    if not dest.is_dir():
        raise FileNotFoundError(f"Export directory does not exist: {dest}")

    from modules.reporting import (
        generate_imei_device_report, generate_imei_common_report,
        generate_imei_ipdr_common_report,
    )
    pending: list[tuple[Path, str]] = []
    with tempfile.TemporaryDirectory(prefix="ea-imei-export-", dir=str(dest)) as temp:
        tmp = Path(temp)
        for item in result.get("single_results") or []:
            if not isinstance(item, dict) or not isinstance(item.get("analysis"), dict):
                continue
            analysis = item["analysis"]
            generated = generate_imei_device_report(case=case, analysis=analysis, output_dir=tmp)
            if generated:
                path = Path(generated).resolve()
                if not path.is_file() or path.parent != tmp.resolve():
                    raise RuntimeError("IMEI report generator returned an unexpected output path")
                pending.append((path, "UNIFIED_IMEI_ANALYSIS" if mode == "unified" else f"IMEI_{mode.upper()}_ANALYSIS"))
        common = result.get("common_result")
        if isinstance(common, dict) and isinstance(common.get("analysis"), dict):
            if mode == "cdr":
                generated = generate_imei_common_report(case=case, analysis=common["analysis"], output_dir=tmp)
                kind = "IMEI_CDR_COMMON_ANALYSIS"
            elif mode == "ipdr":
                generated = generate_imei_ipdr_common_report(case=case, analysis=common["analysis"], output_dir=tmp)
                kind = "IMEI_IPDR_COMMON_ANALYSIS"
            else:
                generated = None
                kind = ""
            if generated:
                path = Path(generated).resolve()
                if not path.is_file() or path.parent != tmp.resolve():
                    raise RuntimeError("IMEI common report returned an unexpected output path")
                pending.append((path, kind))
        filenames = [path.name for path, _ in pending]
        if len(filenames) != len(set(filenames)):
            raise FileExistsError("Two IMEI reports resolve to the same output filename")
        for path, _ in pending:
            if (dest / path.name).exists():
                raise FileExistsError(f"Report already exists: {dest / path.name}. Choose another folder.")
        exported = []
        created: list[Path] = []
        try:
            for path, kind in pending:
                target = dest / path.name
                # Exclusive create prevents overwriting existing files, even under a race.
                with open(target, "xb") as fout:
                    created.append(target)
                    with path.open("rb") as fin:
                        import shutil
                        shutil.copyfileobj(fin, fout)
                exported.append((str(target), kind))
        except Exception:
            # Remove only our newly created files; never touch pre-existing reports.
            for target in created:
                target.unlink(missing_ok=True)
            raise
    # Case report registry only updates after the user initiates a real export.
    if exported:
        from modules.cases import register_report
        case_id = str(case.get("case_id", "")).strip()
        if case_id:
            for path, kind in exported:
                register_report(case_id, report_type=kind, report_path=path)
    return [path for path, _ in exported]
