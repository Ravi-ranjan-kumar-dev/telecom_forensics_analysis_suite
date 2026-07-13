from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from modules.analysis.towerdump import build_tower_dump_analysis_bundle
from modules.loader.tower_dump_loader import load_tower_dump_case


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOWER_DUMP_INPUT = PROJECT_ROOT / "data" / "tower_dump" / "input"


def run_tower_dump_analysis(
    input_folder: str | Path | None = None,
    *,
    enrich_cgi: bool = True,
    recursive: bool = True,
    remove_exact_duplicates: bool = False,
) -> dict[str, Any]:
    """
    Complete normal Tower Dump batch/case workflow.

    Ek folder ke sab Airtel/Jio/Vi/BSNL files load hote hain, combined DataFrame
    banta hai aur sab registered analyses exactly ek baar execute hote hain.
    """
    folder = Path(input_folder).expanduser() if input_folder else DEFAULT_TOWER_DUMP_INPUT

    load_result = load_tower_dump_case(
        folder,
        enrich_cgi=enrich_cgi,
        recursive=recursive,
        remove_exact_duplicates=remove_exact_duplicates,
    )

    df = load_result.get("df")
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {
            **load_result,
            "analysis": {
                "results": {},
                "status": pd.DataFrame(),
                "errors": pd.DataFrame(),
                "function_count": 0,
                "completed_count": 0,
                "failed_count": 0,
            },
        }

    analysis = build_tower_dump_analysis_bundle(df)

    return {
        **load_result,
        "analysis": analysis,
    }
