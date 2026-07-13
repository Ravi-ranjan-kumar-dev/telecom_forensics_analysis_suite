from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.controllers.tower_controller import run_tower_dump_analysis
from modules.reporting.tower_dump_excel import generate_tower_dump_excel_report


def run_tower_dump_analysis_with_excel(
    input_folder: str | Path | None = None,
    *,
    enrich_cgi: bool = True,
    recursive: bool = True,
    case_name: str | None = None,
) -> dict[str, Any]:
    result = run_tower_dump_analysis(
        input_folder=input_folder,
        enrich_cgi=enrich_cgi,
        recursive=recursive,
    )

    if result.get("ok"):
        excel_path = generate_tower_dump_excel_report(
            result,
            case_name=case_name,
        )
        result["excel_report"] = str(excel_path)
    else:
        result["excel_report"] = ""

    return result
