"""Canonical telecom identity normalization and conservative target detection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

METADATA_KEYWORDS = (
    "msisdn",
    "target",
    "input value",
    "mobile number",
    "phone number",
    "subscriber number",
    "requested number",
)


@dataclass(frozen=True, slots=True)
class TargetDetection:
    target: str | None
    method: str
    confidence: str
    warning: str = ""


def digits_only(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return re.sub(r"\D", "", text)


def normalize_msisdn(value: Any, *, require_indian_mobile: bool = True) -> str | None:
    """Normalize common Indian prefixes without suffix-matching arbitrary IDs."""

    digits = digits_only(value)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if require_indian_mobile:
        return digits if len(digits) == 10 and digits[0] in "6789" else None
    return digits or None


def normalized_party_key(value: Any) -> str:
    mobile = normalize_msisdn(value)
    return mobile or digits_only(value)


def target_match_mask(series: pd.Series, target: Any) -> pd.Series:
    target_key = normalized_party_key(target)
    if not target_key:
        return pd.Series(False, index=series.index, dtype=bool)
    return series.map(normalized_party_key).eq(target_key)


def detect_target_from_metadata(path: str | Path, *, max_lines: int = 100) -> str | None:
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8-sig", errors="replace") as handle:
            for index, line in enumerate(handle):
                if index >= max_lines:
                    break
                if not any(keyword in line.lower() for keyword in METADATA_KEYWORDS):
                    continue
                for match in re.findall(r"(?<!\d)(?:91|0)?[6-9]\d{9}(?!\d)", line):
                    number = normalize_msisdn(match)
                    if number:
                        return number
    except OSError:
        return None
    return None


def detect_target_from_filename(file_name: str) -> str | None:
    for match in re.findall(r"(?<!\d)(?:91|0)?[6-9]\d{9}(?!\d)", str(file_name)):
        number = normalize_msisdn(match)
        if number:
            return number
    return None


def detect_target_from_dataframe(
    df: pd.DataFrame,
    *,
    minimum_row_share: float = 0.80,
    minimum_rows: int = 3,
) -> TargetDetection:
    """Use a frequency fallback only when one party appears in most events.

    A contact merely being the most frequent is insufficient. The candidate
    must appear in at least ``minimum_row_share`` of rows across A/B sides.
    """

    if not isinstance(df, pd.DataFrame) or df.empty:
        return TargetDetection(None, "not-detected", "NONE")
    columns = [name for name in ("a_party", "b_party") if name in df.columns]
    if not columns or len(df) < minimum_rows:
        return TargetDetection(
            None,
            "not-detected",
            "NONE",
            "Insufficient rows for conservative target fallback.",
        )

    row_candidates: list[set[str]] = []
    counts: dict[str, int] = {}
    for _, row in df[columns].iterrows():
        values = {
            number
            for number in (normalize_msisdn(row.get(column)) for column in columns)
            if number
        }
        row_candidates.append(values)
        for number in values:
            counts[number] = counts.get(number, 0) + 1
    if not counts:
        return TargetDetection(None, "not-detected", "NONE")
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    candidate, appearances = ordered[0]
    share = appearances / max(1, len(df))
    second_share = ordered[1][1] / len(df) if len(ordered) > 1 else 0.0
    if share < minimum_row_share or share - second_share < 0.20:
        return TargetDetection(
            None,
            "ambiguous-party-frequency",
            "LOW",
            (
                f"Top party share {share:.1%}; target metadata/filename required. "
                "No contact was auto-selected."
            ),
        )
    return TargetDetection(candidate, "row-presence-fallback", "MEDIUM")


def detect_target(
    *,
    file_path: str | Path,
    file_name: str,
    dataframe: pd.DataFrame,
) -> TargetDetection:
    target = detect_target_from_metadata(file_path)
    if target:
        return TargetDetection(target, "metadata", "HIGH")
    target = detect_target_from_filename(file_name)
    if target:
        return TargetDetection(target, "filename", "HIGH")
    return detect_target_from_dataframe(dataframe)
