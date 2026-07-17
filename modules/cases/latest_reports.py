"""
Common latest-report registry.

Purpose:
- Keep one clean latest-report pointer per report category.
- Help View Case Reports show latest user-facing reports only.
- Hide backend/internal files from normal investigator-facing output.

Registry file:
cases/active/<case_id>/configuration/latest_reports.json
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.cases.repository import read_json, safe_descendant, write_json
from modules.cases.service import case_directory


LATEST_REPORTS_FILE = "latest_reports.json"


def _latest_reports_path(case_id: str) -> Path:
    """Return latest reports registry path for a case."""

    return safe_descendant(
        case_directory(case_id),
        "configuration",
        LATEST_REPORTS_FILE,
    )


def _normalise_report_type(value: str) -> str:
    """Normalize report type key."""

    return str(value).strip().lower().replace(" ", "_")


def load_latest_reports(case_id: str) -> dict[str, Any]:
    """Load latest report registry."""

    value = read_json(_latest_reports_path(case_id), default={})

    if isinstance(value, dict):
        return value

    return {}


def save_latest_report(
    case_id: str,
    report_type: str,
    *,
    title: str,
    report_path: str | Path,
    summary_path: str | Path | None = None,
    report_folder: str | Path | None = None,
    generated_at: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Save latest user-facing report pointer for a report type."""

    from datetime import datetime

    key = _normalise_report_type(report_type)
    registry = load_latest_reports(case_id)

    payload: dict[str, Any] = {
        "report_type": key,
        "title": str(title),
        "report_path": str(report_path),
        "summary_path": str(summary_path or ""),
        "report_folder": str(report_folder or ""),
        "generated_at": generated_at or datetime.now().isoformat(timespec="seconds"),
        "metadata": metadata or {},
    }

    registry[key] = payload
    write_json(_latest_reports_path(case_id), registry)

    return payload


def get_latest_report(case_id: str, report_type: str) -> dict[str, Any] | None:
    """Return one latest report entry."""

    return load_latest_reports(case_id).get(_normalise_report_type(report_type))


def list_latest_reports(case_id: str) -> list[dict[str, Any]]:
    """Return latest reports sorted by generated time descending."""

    registry = load_latest_reports(case_id)

    values = [
        value
        for value in registry.values()
        if isinstance(value, dict)
    ]

    return sorted(
        values,
        key=lambda item: str(item.get("generated_at", "")),
        reverse=True,
    )
