"""CDR controller with safe single and multiple result normalisation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from modules.loader.path_manager import get_data_path
from modules.loader.identity import detect_target, normalize_msisdn
from modules.loader.duplicate_flags import flag_potential_duplicates
from modules.loader.single_loader import get_single_file, realign_target_and_b_party
from modules.loader.multi_loader import load_multiple_cdr
from modules.database.cgi import safe_enrich_cdr


def _normalise_mobile(value: Any) -> str | None:
    return normalize_msisdn(value)


def auto_detect_single_target(folder: str | Path, df: pd.DataFrame) -> str | None:
    folder_path = Path(folder)
    files = sorted(folder_path.glob("*.csv"))
    if len(files) != 1:
        return None
    result = detect_target(
        file_path=files[0],
        file_name=files[0].name,
        dataframe=df,
    )
    if result.warning:
        print(f"[!] Target detection: {result.warning}")
    return result.target


def run_single(
    folder: str | Path | None = None,
):
    input_folder = (
        Path(folder).expanduser().resolve()
        if folder is not None
        else Path(get_data_path("cdr", "single"))
    )
    print(f"\n[+] Loading Single CDR from: {input_folder}")
    df = get_single_file(input_folder)

    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        print("[-] Controller received Empty or None DataFrame.")
        return None, None

    target = auto_detect_single_target(
        input_folder,
        df,
    )
    if not target:
        print("[-] Target number could not be auto-detected.")
        return df, None

    print(f"[+] Automatically Detected Target Number: {target}")
    aligned = realign_target_and_b_party(df, target)
    return aligned, target


def _normalise_loaded_items(raw_result: Any) -> list[dict[str, Any]]:
    if isinstance(raw_result, list):
        return [item for item in raw_result if isinstance(item, dict)]

    if isinstance(raw_result, dict):
        items: list[dict[str, Any]] = []
        for target, info in raw_result.items():
            if isinstance(info, dict):
                item = dict(info)
                item.setdefault("target", target)
                items.append(item)
        return items

    return []


def run_multiple(
    folder: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    input_folder = (
        Path(folder).expanduser().resolve()
        if folder is not None
        else Path(get_data_path("cdr", "multiple"))
    )
    print(f"\n[+] Loading Multiple CDRs from: {input_folder}")
    raw_result = load_multiple_cdr(input_folder)
    items = _normalise_loaded_items(raw_result)

    grouped: dict[str, dict[str, Any]] = {}
    for item in items:
        target = _normalise_mobile(item.get("target"))
        df = item.get("df")
        if not target or not isinstance(df, pd.DataFrame) or df.empty:
            continue

        source_file = str(item.get("file") or item.get("source_file") or "Unknown")
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}

        if target not in grouped:
            grouped[target] = {
                "target": target,
                "file": source_file,
                "files": [source_file],
                "df": df.copy(),
                "metadata": dict(metadata),
                "rejected_rows": [
                    item.get("rejected_rows")
                ] if isinstance(item.get("rejected_rows"), pd.DataFrame) else [],
                "ingestion_metadata": [item.get("ingestion_metadata", {})],
            }
            continue

        existing = grouped[target]
        existing["df"] = pd.concat([existing["df"], df], ignore_index=True, sort=False)
        existing["files"].append(source_file)
        existing["file"] = ", ".join(dict.fromkeys(existing["files"]))
        existing["metadata"].update({k: v for k, v in metadata.items() if v not in (None, "")})
        rejected = item.get("rejected_rows")
        if isinstance(rejected, pd.DataFrame):
            existing["rejected_rows"].append(rejected)
        existing["ingestion_metadata"].append(item.get("ingestion_metadata", {}))

    for info in grouped.values():
        info["df"] = flag_potential_duplicates(info["df"]).reset_index(drop=True)
        info["files"] = list(dict.fromkeys(info["files"]))
        rejected_frames = [
            frame for frame in info.get("rejected_rows", [])
            if isinstance(frame, pd.DataFrame) and not frame.empty
        ]
        rejected_rows = (
            pd.concat(rejected_frames, ignore_index=True, sort=False)
            if rejected_frames else pd.DataFrame()
        )
        info["rejected_rows"] = rejected_rows
        info["df"].attrs["rejected_rows"] = rejected_rows
        info["df"].attrs["ingestion_metadata"] = info.get(
            "ingestion_metadata", []
        )

    return grouped
