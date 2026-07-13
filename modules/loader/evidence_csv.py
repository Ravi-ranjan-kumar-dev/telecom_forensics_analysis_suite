"""CSV ingestion helpers with explicit malformed-row quarantine.

The helper preserves physical source-line provenance for accepted rows and
returns a reject ledger instead of silently skipping malformed records.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pandas as pd


REJECT_COLUMNS = [
    "source_file",
    "source_row_number",
    "source_row_end_number",
    "rejection_reason",
    "raw_row_digest_sha256",
    "raw_fields_json",
]


def empty_reject_ledger() -> pd.DataFrame:
    return pd.DataFrame(columns=REJECT_COLUMNS)


def _decode(path: Path, preferred: str | None = None) -> tuple[str, str]:
    raw = path.read_bytes()
    encodings = []
    if preferred:
        encodings.append(str(preferred))
    encodings.extend(["utf-8-sig", "utf-8", "cp1252", "latin1"])

    seen: set[str] = set()
    for encoding in encodings:
        if encoding.lower() in seen:
            continue
        seen.add(encoding.lower())
        try:
            return raw.decode(encoding, errors="strict"), encoding
        except (UnicodeError, LookupError):
            continue

    raise UnicodeError(f"Supported encoding se file decode nahi hui: {path}")


def _dedupe_headers(values: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    output: list[str] = []
    for index, value in enumerate(values):
        base = str(value).replace("\ufeff", "").strip() or f"Unnamed: {index}"
        count = counts.get(base, 0)
        output.append(base if count == 0 else f"{base}.{count}")
        counts[base] = count + 1
    return output


def _reject_record(
    *,
    path: Path,
    row_start: int,
    row_end: int,
    reason: str,
    fields: list[str],
) -> dict[str, Any]:
    raw_json = json.dumps(fields, ensure_ascii=False, separators=(",", ":"))
    return {
        "source_file": str(path),
        "source_row_number": int(row_start),
        "source_row_end_number": int(row_end),
        "rejection_reason": reason,
        "raw_row_digest_sha256": hashlib.sha256(raw_json.encode("utf-8")).hexdigest(),
        "raw_fields_json": raw_json,
    }


def read_csv_with_quarantine(
    path: str | Path,
    *,
    skiprows: int = 0,
    sep: str = ",",
    encoding: str | None = None,
    keep_blank_rows: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Read one delimited file and return accepted rows plus reject ledger.

    Short rows are padded and rows with only trailing extra empty fields are
    trimmed, matching common operator-export behaviour. Rows containing extra
    non-empty fields are quarantined rather than silently truncated.
    """

    file_path = Path(path).expanduser().resolve()
    text, used_encoding = _decode(file_path, preferred=encoding)
    physical_lines = text.splitlines(keepends=True)
    body = "".join(physical_lines[int(skiprows):])
    reader = csv.reader(io.StringIO(body, newline=""), delimiter=sep)

    try:
        header = next(reader)
    except StopIteration:
        return pd.DataFrame(), empty_reject_ledger(), {
            "encoding": used_encoding,
            "delimiter": sep,
            "header_row": int(skiprows) + 1,
            "accepted_rows": 0,
            "rejected_rows": 0,
            "adjusted_rows": 0,
        }

    headers = _dedupe_headers(header)
    expected = len(headers)
    accepted: list[list[str]] = []
    source_starts: list[int] = []
    source_ends: list[int] = []
    statuses: list[str] = []
    notes: list[str] = []
    rejects: list[dict[str, Any]] = []
    adjusted_rows = 0
    previous_line = reader.line_num

    try:
        for fields in reader:
            row_end = int(skiprows) + reader.line_num
            row_start = int(skiprows) + previous_line + 1
            previous_line = reader.line_num

            if not fields or all(str(value).strip() == "" for value in fields):
                if keep_blank_rows:
                    rejects.append(
                        _reject_record(
                            path=file_path,
                            row_start=row_start,
                            row_end=row_end,
                            reason="BLANK_ROW",
                            fields=fields,
                        )
                    )
                continue

            status = "ACCEPTED"
            note = ""
            values = list(fields)

            if len(values) < expected:
                missing = expected - len(values)
                values.extend([""] * missing)
                status = "ACCEPTED_NORMALIZED"
                note = f"PADDED_{missing}_MISSING_TRAILING_FIELDS"
                adjusted_rows += 1
            elif len(values) > expected:
                extras = values[expected:]
                if all(str(value).strip() == "" for value in extras):
                    values = values[:expected]
                    status = "ACCEPTED_NORMALIZED"
                    note = f"TRIMMED_{len(extras)}_EMPTY_TRAILING_FIELDS"
                    adjusted_rows += 1
                else:
                    rejects.append(
                        _reject_record(
                            path=file_path,
                            row_start=row_start,
                            row_end=row_end,
                            reason=(
                                f"FIELD_COUNT_MISMATCH expected={expected} actual={len(values)}"
                            ),
                            fields=values,
                        )
                    )
                    continue

            accepted.append(values)
            source_starts.append(row_start)
            source_ends.append(row_end)
            statuses.append(status)
            notes.append(note)
    except csv.Error as error:
        row_number = int(skiprows) + max(reader.line_num, previous_line) + 1
        rejects.append(
            _reject_record(
                path=file_path,
                row_start=row_number,
                row_end=row_number,
                reason=f"CSV_PARSE_ERROR: {error}",
                fields=[],
            )
        )

    dataframe = pd.DataFrame(accepted, columns=headers, dtype="string")
    dataframe["_source_row_number"] = pd.Series(source_starts, dtype="Int64")
    dataframe["_source_row_end_number"] = pd.Series(source_ends, dtype="Int64")
    dataframe["_parse_status"] = pd.Series(statuses, dtype="string")
    dataframe["_parse_note"] = pd.Series(notes, dtype="string")
    rejected = pd.DataFrame(rejects, columns=REJECT_COLUMNS)

    metadata = {
        "encoding": used_encoding,
        "delimiter": sep,
        "header_row": int(skiprows) + 1,
        "accepted_rows": int(len(dataframe)),
        "rejected_rows": int(len(rejected)),
        "adjusted_rows": int(adjusted_rows),
    }
    return dataframe, rejected, metadata


def quarantine_dataframe_rows(
    dataframe: pd.DataFrame,
    mask: pd.Series,
    *,
    source_file: str | Path,
    reason: str,
) -> pd.DataFrame:
    """Build reject-ledger rows for already parsed records failing validation."""

    if dataframe.empty or not mask.any():
        return empty_reject_ledger()

    records: list[dict[str, Any]] = []
    for index, row in dataframe.loc[mask].iterrows():
        fields = [
            "" if pd.isna(value) else str(value)
            for key, value in row.items()
            if not str(key).startswith("_parse_")
        ]
        start = row.get(
            "source_row_number",
            row.get("_source_row_number", index + 1),
        )
        end = row.get(
            "source_row_end_number",
            row.get("_source_row_end_number", start),
        )
        try:
            start_int = int(start)
        except (TypeError, ValueError):
            start_int = int(index) + 1
        try:
            end_int = int(end)
        except (TypeError, ValueError):
            end_int = start_int
        records.append(
            _reject_record(
                path=Path(source_file),
                row_start=start_int,
                row_end=end_int,
                reason=reason,
                fields=fields,
            )
        )
    return pd.DataFrame(records, columns=REJECT_COLUMNS)
