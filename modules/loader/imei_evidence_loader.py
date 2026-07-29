"""Detect and inspect dedicated IMEI evidence report formats.

This module performs read-only format inspection. It preserves the distinction
between the requested report identifier and identifiers observed in data rows.
Source-specific normalization is added separately after format contracts are
stable.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
from modules.loader.telecom_identifiers import (
    normalize_imei,
)
SUPPORTED_SUFFIXES = {
    ".csv",
    ".txt",
}

STATUS_HAS_DATA = "HAS_DATA"
STATUS_EMPTY_NO_DATA = "EMPTY_NO_DATA"
STATUS_UNSUPPORTED = "UNSUPPORTED"
STATUS_ERROR = "ERROR"

FORMAT_VIL_IMEI_CDR = "VIL_IMEI_CDR"
FORMAT_SEARCH_CRITERIA_IMEI_CDR = (
    "SEARCH_CRITERIA_IMEI_CDR"
)
FORMAT_JIO_IMEI_CDR = "JIO_IMEI_CDR"
FORMAT_AIRTEL_DYNAMIC_IMEI_IPDR = (
    "AIRTEL_DYNAMIC_IMEI_IPDR"
)
FORMAT_AIRTEL_IMEI_GPRS = (
    "AIRTEL_IMEI_GPRS"
)
FORMAT_VIL_IMEI_GPRS = "VIL_IMEI_GPRS"
FORMAT_GENERIC_IMEI_IPDR = "GENERIC_IMEI_IPDR"
FORMAT_VIL_IMEI_DOT = "VIL_IMEI_DOT"
FORMAT_UNKNOWN = "UNKNOWN"


IMEI_CDR_SUPPORTED_FORMATS = {
    FORMAT_VIL_IMEI_CDR,
    FORMAT_SEARCH_CRITERIA_IMEI_CDR,
    FORMAT_JIO_IMEI_CDR,
}


IMEI_IPDR_SUPPORTED_FORMATS = {
    FORMAT_AIRTEL_DYNAMIC_IMEI_IPDR,
}


IMEI_CDR_CANONICAL_COLUMNS = (
    "target",
    "call_date",
    "call_time",
    "call_type",
    "raw_call_type",
    "call_direction",
    "b_party",
    "call_duration",
    "imei",
    "imsi",
    "first_cell_id",
    "last_cell_id",
    "service_type",
    "query_identifier_raw",
    "query_identifier_normalized",
    "query_identifier_type",
    "observed_imei_raw",
    "observed_imei_normalized",
    "match_relation",
    "detected_operator",
    "detected_format",
    "source_file",
    "source_path",
    "source_row_number",
)


def _parse_imei_gprs_session_start(
    date_value: pd.Series,
    time_value: pd.Series,
) -> pd.Series:
    """Parse mixed operator GPRS date-time values safely."""

    combined_time = (
        date_value.astype("string").fillna("")
        + " "
        + time_value.astype("string").fillna("")
    ).str.strip()

    return pd.to_datetime(
        combined_time,
        format="mixed",
        errors="coerce",
        dayfirst=True,
    )


def _read_text(
    path: Path,
) -> str:
    for encoding in (
        "utf-8-sig",
        "utf-8",
        "latin-1",
    ):
        try:
            return path.read_text(
                encoding=encoding
            )
        except UnicodeDecodeError:
            continue

    return path.read_text(
        encoding="utf-8",
        errors="replace",
    )


def _clean_value(
    value: Any,
) -> str:
    return (
        str(
            value or ""
        )
        .strip()
        .strip(
            "'\""
        )
        .strip()
    )


def _digits(
    value: Any,
) -> str:
    return "".join(
        re.findall(
            r"\d",
            _clean_value(
                value
            ),
        )
    )


def classify_device_identifier(
    value: Any,
) -> str:
    """Classify a device identifier by its exact digit length."""

    digits = _digits(
        value
    )

    return {
        14: "BASE14",
        15: "IMEI15",
        16: "IMEISV16",
    }.get(
        len(
            digits
        ),
        "UNKNOWN",
    )


def classify_match_relation(
    query_identifier: Any,
    observed_identifier: Any,
) -> str:
    """Describe the relationship without silently truncating identifiers."""

    query_digits = _digits(
        query_identifier
    )

    observed_digits = _digits(
        observed_identifier
    )

    if (
        not query_digits
        or not observed_digits
    ):
        return "UNAVAILABLE"

    if query_digits == observed_digits:
        return "EXACT"

    if (
        len(
            query_digits
        )
        == 14
        and observed_digits.startswith(
            query_digits
        )
    ):
        return "BASE14_MATCH"

    if (
        len(
            query_digits
        )
        in {
            15,
            16,
        }
        and len(
            observed_digits
        )
        in {
            15,
            16,
        }
        and query_digits[
            :14
        ]
        == observed_digits[
            :14
        ]
    ):
        return "SAME_BASE14"

    return "REPORT_SCOPE"


def _parse_csv_line(
    line: str,
) -> list[str]:
    try:
        return next(
            csv.reader(
                [
                    line
                ]
            )
        )

    except csv.Error:
        return [
            line
        ]


def _trim_header_trailing_empty(
    values: list[str],
) -> list[str]:
    result = list(
        values
    )

    while (
        result
        and not _clean_value(
            result[
                -1
            ]
        )
    ):
        result.pop()

    return result


def _canonical_header(
    value: Any,
) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        _clean_value(
            value
        ).lower(),
    ).strip()


def _find_imei_column(
    header: list[str],
) -> int | None:
    for index, value in enumerate(
        header
    ):
        if (
            _canonical_header(
                value
            )
            == "imei"
        ):
            return index

    for index, value in enumerate(
        header
    ):
        canonical = _canonical_header(
            value
        )

        if (
            "imei" in canonical
            or (
                "device identification number"
                in canonical
            )
        ):
            return index

    return None


def _detect_format(
    *,
    path: Path,
    text: str,
) -> dict[str, str]:
    lowered = text.lower()

    if (
        "vodafone idea call data records"
        in lowered
        and "report type :- main cdr report"
        in lowered
    ):
        return {
            "format_id": FORMAT_VIL_IMEI_CDR,
            "operator": "Vodafone Idea",
            "source_type": "CDR",
        }

    if (
        "search criteria : imei"
        in lowered
        and "target/a-party number"
        in lowered
    ):
        operator = (
            "BSNL"
            if "bsnl" in lowered
            else "Unknown"
        )

        return {
            "format_id": (
                FORMAT_SEARCH_CRITERIA_IMEI_CDR
            ),
            "operator": operator,
            "source_type": "CDR",
        }

    if (
        "ticket number :"
        in lowered
        and "input value "
        in lowered
        and (
            "calling party telephone number"
            in lowered
        )
    ):
        return {
            "format_id": FORMAT_JIO_IMEI_CDR,
            "operator": "Reliance Jio",
            "source_type": "CDR",
        }

    if (
        "gprs of imei"
        in lowered
        and "bharti airtel"
        in lowered
    ):
        return {
            "format_id": FORMAT_AIRTEL_IMEI_GPRS,
            "operator": "Bharti Airtel",
            "source_type": "GPRS",
        }

    if (
        "dynamic ipdr of imei"
        in lowered
        and "bharti airtel"
        in lowered
    ):
        return {
            "format_id": (
                FORMAT_AIRTEL_DYNAMIC_IMEI_IPDR
            ),
            "operator": "Bharti Airtel",
            "source_type": "IPDR",
        }

    if (
        "vodafone idea call data records"
        in lowered
        and "report type :- gprs report"
        in lowered
    ):
        return {
            "format_id": FORMAT_VIL_IMEI_GPRS,
            "operator": "Vodafone Idea",
            "source_type": "GPRS",
        }

    if (
        "report type:-dot report"
        in lowered
        and "source ip" in lowered
        and "destination ip" in lowered
    ):
        return {
            "format_id": FORMAT_VIL_IMEI_DOT,
            "operator": "Vodafone Idea",
            "source_type": "IPDR",
        }

    if (
        "imei_ipdr"
        in path.name.lower()
        and "destination ip address"
        in lowered
        and "source ip address"
        in lowered
    ):
        return {
            "format_id": FORMAT_GENERIC_IMEI_IPDR,
            "operator": "Unknown",
            "source_type": "IPDR",
        }

    return {
        "format_id": FORMAT_UNKNOWN,
        "operator": "Unknown",
        "source_type": "UNKNOWN",
    }


def _extract_query_identifier(
    *,
    path: Path,
    text: str,
) -> str:
    text_patterns = (
        (
            r"(?im)^\s*IMEI\s*:\s*-\s*"
            r"([0-9]{14,16})"
        ),
        (
            r"(?im)^\s*IMEI\s*:-\s*"
            r"([0-9]{14,16})"
        ),
        (
            r"(?im)^\s*Search\s+Value\s*:\s*"
            r"([0-9]{14,16})"
        ),
        (
            r"(?im)^\s*Input\s+Value.*?:\s*,?\s*"
            r"['\"]?([0-9]{14,16})"
        ),
        (
            r"(?im)Dynamic\s+IPDR\s+OF\s+IMEI\s*:\s*"
            r"([0-9]{14,16})"
        ),
        (
            r"(?im)GPRS\s+OF\s+IMEI\s*:\s*"
            r"([0-9]{14,16})"
        ),
    )

    for pattern in text_patterns:
        match = re.search(
            pattern,
            text,
        )

        if match:
            return _digits(
                match.group(
                    1
                )
            )

    filename_patterns = (
        r"(?i)IMEI_IPDR_([0-9]{14,16})",
        r"(?i)IMEI_([0-9]{14,16})",
        r"^([0-9]{14,16})_",
        r"(?i)imei_([0-9]{14,16})",
    )

    for pattern in filename_patterns:
        match = re.search(
            pattern,
            path.name,
        )

        if match:
            return _digits(
                match.group(
                    1
                )
            )

    return ""


def _extract_metadata(
    text: str,
) -> dict[str, str]:
    metadata: dict[str, str] = {}

    patterns = {
        "report_type": (
            r"(?im)^\s*Report\s+Type\s*:-?\s*(.+?)\s*$"
        ),
        "from_date": (
            r"(?im)^\s*From\s+Date\s*:-?\s*(.+?)\s*$"
        ),
        "from_time": (
            r"(?im)^\s*From\s+Time\s*:-?\s*(.+?)\s*$"
        ),
        "till_date": (
            r"(?im)^\s*Till\s+Date\s*:-?\s*(.+?)\s*$"
        ),
        "till_time": (
            r"(?im)^\s*Till\s+Time\s*:-?\s*(.+?)\s*$"
        ),
        "start_date": (
            r"(?im)^\s*Start\s+Date\s*:\s*(.+?)\s*$"
        ),
        "end_date": (
            r"(?im)^\s*End\s+Date\s*:\s*(.+?)\s*$"
        ),
        "report_index": (
            r"(?im)^\s*Report\s+Index\s*:-?\s*(.+?)\s*$"
        ),
        "report_date": (
            r"(?im)^\s*Report\s+Date\s*:-?\s*(.+?)\s*$"
        ),
        "ticket_number": (
            r"(?im)^\s*Ticket\s+Number\s*:\s*,?\s*"
            r"(.+?)\s*$"
        ),
        "total_records_declared": (
            r"(?im)^\s*Total\s+Records\s*:\s*,?\s*"
            r"(.+?)\s*$"
        ),
    }

    for key, pattern in patterns.items():
        match = re.search(
            pattern,
            text,
        )

        if match:
            metadata[
                key
            ] = _clean_value(
                match.group(
                    1
                )
            )

    return metadata


def _header_score(
    values: list[str],
) -> int:
    canonical = " | ".join(
        _canonical_header(
            value
        )
        for value in values
    )

    tokens = (
        "imei",
        "imsi",
        "call date",
        "call time",
        "session start",
        "source ip",
        "destination ip",
        "calling party",
        "target a party",
        "msisdn",
    )

    return sum(
        token in canonical
        for token in tokens
    )


def _find_header(
    lines: list[str],
) -> tuple[
    int | None,
    list[str],
]:
    best_line = None
    best_values: list[str] = []
    best_score = 0

    for line_number, line in enumerate(
        lines,
        start=1,
    ):
        values = _trim_header_trailing_empty(
            _parse_csv_line(
                line
            )
        )

        if len(
            values
        ) < 5:
            continue

        score = _header_score(
            values
        )

        if (
            score > best_score
            or (
                score == best_score
                and len(
                    values
                )
                > len(
                    best_values
                )
            )
        ):
            best_line = line_number
            best_values = values
            best_score = score

    if best_score < 2:
        return None, []

    return (
        best_line,
        best_values,
    )


def _is_non_data_line(
    line: str,
) -> bool:
    # Standalone report-generation timestamps are footer metadata.
    report_line = str(
        line or ""
    ).strip()

    if (
        report_line
        and "," not in report_line
        and re.fullmatch(
            r"\d{1,2}-[A-Za-z]{3}-\d{4}\s+"
            r"\d{2}:\d{2}:\d{2}",
            report_line,
        )
    ):
        return True

    stripped = line.strip()

    if not stripped:
        return True

    lowered = stripped.lower()

    if set(
        stripped
    ) <= {
        "-",
        "_",
        "=",
    }:
        return True

    return lowered.startswith(
        (
            "note ",
            "note:",
            "note :-",
            "generated on ",
            "disclaimer ",
            "call_forward ",
            "lrn ",
            "*** end of report",
            "cdr count ",
            "this is system generated",
        )
    )


def _extract_rows_with_line_numbers(
    *,
    lines: list[str],
    header_line: int | None,
    header: list[str],
) -> tuple[
    list[tuple[int, list[str]]],
    int,
]:
    """Extract valid rows with their original one-based line numbers."""

    if (
        header_line is None
        or not header
    ):
        return [], 0

    rows: list[
        tuple[
            int,
            list[str],
        ]
    ] = []

    rejected = 0
    width = len(
        header
    )

    for source_line_number, line in enumerate(
        lines[
            header_line:
        ],
        start=header_line + 1,
    ):
        if _is_non_data_line(
            line
        ):
            continue

        values = _parse_csv_line(
            line
        )

        if (
            len(
                values
            )
            == width + 1
            and not _clean_value(
                values[
                    -1
                ]
            )
        ):
            values = values[
                :-1
            ]

        if len(
            values
        ) != width:
            rejected += 1
            continue

        if _header_score(
            values
        ) >= 2:
            rejected += 1
            continue

        rows.append(
            (
                source_line_number,
                values,
            )
        )

    return rows, rejected


def _extract_rows(
    *,
    lines: list[str],
    header_line: int | None,
    header: list[str],
) -> tuple[
    list[list[str]],
    int,
]:
    """Extract valid rows while preserving the existing public contract."""

    numbered_rows, rejected = (
        _extract_rows_with_line_numbers(
            lines=lines,
            header_line=header_line,
            header=header,
        )
    )

    return (
        [
            row
            for _, row in numbered_rows
        ],
        rejected,
    )


def inspect_imei_evidence_file(
    path: str | Path,
) -> dict[str, Any]:
    """Inspect one dedicated IMEI report without altering evidence."""

    source_path = Path(
        path
    ).expanduser().resolve()

    result: dict[str, Any] = {
        "ok": False,
        "status": STATUS_ERROR,
        "source_path": str(
            source_path
        ),
        "source_file": source_path.name,
        "format_id": FORMAT_UNKNOWN,
        "operator": "Unknown",
        "source_type": "UNKNOWN",
        "query_identifier_raw": "",
        "query_identifier_normalized": "",
        "query_identifier_type": "UNKNOWN",
        "header_line": None,
        "column_count": 0,
        "columns": [],
        "record_count": 0,
        "rejected_line_count": 0,
        "observed_identifier_count": 0,
        "observed_identifiers_preview": [],
        "match_relation_counts": {},
        "metadata": {},
        "message": "",
    }

    try:
        if not source_path.is_file():
            raise FileNotFoundError(
                f"File not found: {source_path}"
            )

        if (
            source_path.suffix.lower()
            not in SUPPORTED_SUFFIXES
        ):
            result.update(
                {
                    "status": STATUS_UNSUPPORTED,
                    "message": (
                        "Unsupported IMEI evidence file type."
                    ),
                }
            )

            return result

        text = _read_text(
            source_path
        )

        lines = text.splitlines()

        detected = _detect_format(
            path=source_path,
            text=text,
        )

        result.update(
            detected
        )

        if (
            detected[
                "format_id"
            ]
            == FORMAT_UNKNOWN
        ):
            result.update(
                {
                    "status": STATUS_UNSUPPORTED,
                    "message": (
                        "Dedicated IMEI report format "
                        "was not recognized."
                    ),
                }
            )

            return result

        query_identifier = (
            _extract_query_identifier(
                path=source_path,
                text=text,
            )
        )

        header_line, header = _find_header(
            lines
        )

        data_rows, rejected = _extract_rows(
            lines=lines,
            header_line=header_line,
            header=header,
        )

        imei_column = _find_imei_column(
            header
        )

        observed_counter: Counter[str] = Counter()

        if imei_column is not None:
            for row in data_rows:
                if imei_column >= len(
                    row
                ):
                    continue

                observed = _digits(
                    row[
                        imei_column
                    ]
                )

                if len(
                    observed
                ) in {
                    14,
                    15,
                    16,
                }:
                    observed_counter[
                        observed
                    ] += 1

        relation_counter: Counter[str] = Counter()

        for observed, count in observed_counter.items():
            relation_counter[
                classify_match_relation(
                    query_identifier,
                    observed,
                )
            ] += count

        explicit_no_data = bool(
            re.search(
                r"(?i)\bno records found\b",
                text,
            )
        )

        record_count = len(
            data_rows
        )

        status = (
            STATUS_EMPTY_NO_DATA
            if (
                explicit_no_data
                or record_count == 0
            )
            else STATUS_HAS_DATA
        )

        message = (
            "Valid dedicated IMEI report loaded "
            "with no data rows."
            if status == STATUS_EMPTY_NO_DATA
            else (
                "Dedicated IMEI report format "
                "recognized with data rows."
            )
        )

        result.update(
            {
                "ok": True,
                "status": status,
                "query_identifier_raw": (
                    query_identifier
                ),
                "query_identifier_normalized": (
                    query_identifier
                ),
                "query_identifier_type": (
                    classify_device_identifier(
                        query_identifier
                    )
                ),
                "header_line": header_line,
                "column_count": len(
                    header
                ),
                "columns": header,
                "record_count": record_count,
                "rejected_line_count": rejected,
                "observed_identifier_count": len(
                    observed_counter
                ),
                "observed_identifiers_preview": [
                    {
                        "identifier": identifier,
                        "identifier_type": (
                            classify_device_identifier(
                                identifier
                            )
                        ),
                        "record_count": count,
                        "match_relation": (
                            classify_match_relation(
                                query_identifier,
                                identifier,
                            )
                        ),
                    }
                    for identifier, count in (
                        observed_counter.most_common(
                            20
                        )
                    )
                ],
                "match_relation_counts": dict(
                    relation_counter
                ),
                "metadata": _extract_metadata(
                    text
                ),
                "message": message,
            }
        )

        return result

    except Exception as error:
        result[
            "message"
        ] = (
            f"{type(error).__name__}: {error}"
        )

        return result


def inspect_imei_evidence_folder(
    folder: str | Path,
    *,
    recursive: bool = True,
) -> dict[str, Any]:
    """Inspect all supported dedicated IMEI reports in one folder."""

    source_folder = Path(
        folder
    ).expanduser().resolve()

    iterator = (
        source_folder.rglob(
            "*"
        )
        if recursive
        else source_folder.glob(
            "*"
        )
    )

    paths = sorted(
        (
            path
            for path in iterator
            if (
                path.is_file()
                and path.suffix.lower()
                in SUPPORTED_SUFFIXES
            )
        ),
        key=lambda path: str(
            path
        ).lower(),
    )

    file_results = [
        inspect_imei_evidence_file(
            path
        )
        for path in paths
    ]

    status_counts = Counter(
        str(
            result.get(
                "status",
                STATUS_ERROR,
            )
        )
        for result in file_results
    )

    format_counts = Counter(
        str(
            result.get(
                "format_id",
                FORMAT_UNKNOWN,
            )
        )
        for result in file_results
    )

    return {
        "ok": any(
            bool(
                result.get(
                    "ok"
                )
            )
            for result in file_results
        ),
        "folder": str(
            source_folder
        ),
        "file_count": len(
            file_results
        ),
        "file_results": file_results,
        "status_counts": dict(
            status_counts
        ),
        "format_counts": dict(
            format_counts
        ),
    }

def _empty_imei_cdr_dataframe() -> pd.DataFrame:
    """Return one empty canonical IMEI CDR DataFrame."""

    return pd.DataFrame(
        columns=IMEI_CDR_CANONICAL_COLUMNS
    )


def _row_dictionary(
    header: list[str],
    values: list[str],
) -> dict[str, str]:
    """Map a source row using canonicalized header names."""

    return {
        _canonical_header(
            column
        ): _clean_value(
            value
        )
        for column, value in zip(
            header,
            values,
        )
    }


def _pick_row_value(
    record: dict[str, str],
    *aliases: str,
) -> str:
    """Return the first available source value for known aliases."""

    for alias in aliases:
        value = _clean_value(
            record.get(
                _canonical_header(
                    alias
                ),
                "",
            )
        )

        if value:
            return value

    return ""


def _number_or_missing(
    value: Any,
) -> int | float | None:
    """Convert numeric evidence without replacing missing values with zero."""

    cleaned = _clean_value(
        value
    )

    if (
        not cleaned
        or cleaned
        in {
            "-",
            "--",
        }
    ):
        return None

    converted = pd.to_numeric(
        pd.Series(
            [
                cleaned
            ]
        ),
        errors="coerce",
    ).iloc[
        0
    ]

    if pd.isna(
        converted
    ):
        return None

    if float(
        converted
    ).is_integer():
        return int(
            converted
        )

    return float(
        converted
    )


def _cdr_direction(
    raw_call_type: Any,
) -> str:
    """Infer call direction from standard and operator-specific labels."""

    canonical = _canonical_header(
        raw_call_type
    )

    compact = canonical.replace(
        " ",
        "",
    )

    exact_incoming = {
        "in",
        "incoming",
        "ainwifi",
        "ainwv",
        "ainvw",
    }

    exact_outgoing = {
        "out",
        "outgoing",
        "aout",
        "aoutwifi",
        "aoutwv",
        "aoutvw",
        "p2aout",
        "p2pout",
    }

    if compact in exact_incoming:
        return "incoming"

    if compact in exact_outgoing:
        return "outgoing"

    if "smsin" in compact:
        return "incoming"

    if "smsout" in compact:
        return "outgoing"

    if canonical.endswith(
        " in"
    ):
        return "incoming"

    if canonical.endswith(
        " out"
    ):
        return "outgoing"

    return "unknown"


def _canonical_cdr_call_type(
    raw_call_type: Any,
    service_type: Any,
) -> str:
    """Return a stable call/SMS type while retaining the raw source value."""

    direction = _cdr_direction(
        raw_call_type
    )

    raw_canonical = _canonical_header(
        raw_call_type
    )

    service_canonical = _canonical_header(
        service_type
    )

    is_sms = (
        "sms" in raw_canonical
        or "sms" in service_canonical
    )

    if direction in {
        "incoming",
        "outgoing",
    }:
        if is_sms:
            return (
                f"{direction}_sms"
            )

        return direction

    return (
        raw_canonical.replace(
            " ",
            "_",
        )
        or "unknown"
    )


def _base_cdr_record(
    *,
    inspection: dict[str, Any],
    source_path: Path,
    source_row_number: int,
    target: Any,
    call_date: Any,
    call_time: Any,
    raw_call_type: Any,
    b_party: Any,
    call_duration: Any,
    observed_imei: Any,
    imsi: Any,
    first_cell_id: Any,
    last_cell_id: Any,
    service_type: Any,
) -> dict[str, Any]:
    """Build one canonical IMEI CDR record."""

    query_raw = _clean_value(
        inspection.get(
            "query_identifier_raw",
            "",
        )
    )

    query_normalized = _digits(
        inspection.get(
            "query_identifier_normalized",
            query_raw,
        )
    )

    observed_raw = _clean_value(
        observed_imei
    )

    observed_normalized = _digits(
        observed_raw
    )

    raw_call_type_clean = _clean_value(
        raw_call_type
    )

    service_type_clean = _clean_value(
        service_type
    )

    return {
        "target": _clean_value(
            target
        ),
        "call_date": _clean_value(
            call_date
        ),
        "call_time": _clean_value(
            call_time
        ),
        "call_type": _canonical_cdr_call_type(
            raw_call_type_clean,
            service_type_clean,
        ),
        "raw_call_type": raw_call_type_clean,
        "call_direction": _cdr_direction(
            raw_call_type_clean
        ),
        "b_party": _clean_value(
            b_party
        ),
        "call_duration": _number_or_missing(
            call_duration
        ),
        "imei": observed_normalized,
        "imsi": _digits(
            imsi
        ),
        "first_cell_id": _clean_value(
            first_cell_id
        ),
        "last_cell_id": _clean_value(
            last_cell_id
        ),
        "service_type": service_type_clean,
        "query_identifier_raw": query_raw,
        "query_identifier_normalized": (
            query_normalized
        ),
        "query_identifier_type": str(
            inspection.get(
                "query_identifier_type",
                classify_device_identifier(
                    query_normalized
                ),
            )
        ),
        "observed_imei_raw": observed_raw,
        "observed_imei_normalized": (
            observed_normalized
        ),
        "match_relation": classify_match_relation(
            query_normalized,
            observed_normalized,
        ),
        "detected_operator": str(
            inspection.get(
                "operator",
                "Unknown",
            )
        ),
        "detected_format": str(
            inspection.get(
                "format_id",
                FORMAT_UNKNOWN,
            )
        ),
        "source_file": source_path.name,
        "source_path": str(
            source_path
        ),
        "source_row_number": int(
            source_row_number
        ),
    }


def _normalize_standard_imei_cdr_row(
    *,
    record: dict[str, str],
    inspection: dict[str, Any],
    source_path: Path,
    source_row_number: int,
) -> dict[str, Any]:
    """Normalize VIL and Search-Criteria/BSNL IMEI CDR rows."""

    return _base_cdr_record(
        inspection=inspection,
        source_path=source_path,
        source_row_number=source_row_number,
        target=_pick_row_value(
            record,
            "Target /A PARTY NUMBER",
            "Target/A-Party Number",
        ),
        call_date=_pick_row_value(
            record,
            "Call date",
            "Call Date",
        ),
        call_time=_pick_row_value(
            record,
            "Call Initiation Time",
        ),
        raw_call_type=_pick_row_value(
            record,
            "CALL_TYPE",
            "Call Type",
        ),
        b_party=_pick_row_value(
            record,
            "B PARTY NUMBER",
            "Other/B-party Number",
        ),
        call_duration=_pick_row_value(
            record,
            "Call Duration",
        ),
        observed_imei=_pick_row_value(
            record,
            "IMEI",
        ),
        imsi=_pick_row_value(
            record,
            "IMSI",
        ),
        first_cell_id=_pick_row_value(
            record,
            "First Cell Global Id",
            "First Cell Global ID",
        ),
        last_cell_id=_pick_row_value(
            record,
            "Last Cell Global Id",
            "Last Cell Global ID",
        ),
        service_type=_pick_row_value(
            record,
            "Service Type",
        ),
    )


def _normalize_jio_imei_cdr_row(
    *,
    record: dict[str, str],
    inspection: dict[str, Any],
    source_path: Path,
    source_row_number: int,
) -> dict[str, Any]:
    """Normalize Jio IMEI CDR rows using direction-aware party alignment."""

    calling_party = _pick_row_value(
        record,
        "Calling Party Telephone Number",
    )

    called_party = _pick_row_value(
        record,
        "Called Party Telephone Number",
    )

    raw_call_type = _pick_row_value(
        record,
        "Call Type",
    )

    direction = _cdr_direction(
        raw_call_type
    )

    if direction == "incoming":
        target = called_party
        b_party = calling_party

    else:
        target = calling_party
        b_party = called_party

    service_type = (
        "SMS"
        if "sms"
        in _canonical_header(
            raw_call_type
        )
        else "Voice"
    )

    return _base_cdr_record(
        inspection=inspection,
        source_path=source_path,
        source_row_number=source_row_number,
        target=target,
        call_date=_pick_row_value(
            record,
            "Call Date",
        ),
        call_time=_pick_row_value(
            record,
            "Call Time",
        ),
        raw_call_type=raw_call_type,
        b_party=b_party,
        call_duration=_pick_row_value(
            record,
            "Call Duration",
        ),
        observed_imei=_pick_row_value(
            record,
            "IMEI",
        ),
        imsi=_pick_row_value(
            record,
            "IMSI",
        ),
        first_cell_id=_pick_row_value(
            record,
            "First Cell ID",
        ),
        last_cell_id=_pick_row_value(
            record,
            "Last Cell ID",
        ),
        service_type=service_type,
    )


def normalize_imei_cdr_file(
    path: str | Path,
    inspection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize one recognized dedicated IMEI CDR report.

    The result keeps requested and observed device identifiers separate.
    Valid no-data reports return an empty canonical DataFrame and remain
    successful evidence acquisitions.
    """

    source_path = Path(
        path
    ).expanduser().resolve()

    inspection_result = (
        dict(
            inspection
        )
        if isinstance(
            inspection,
            dict,
        )
        else inspect_imei_evidence_file(
            source_path
        )
    )

    result: dict[str, Any] = {
        "ok": False,
        "status": STATUS_ERROR,
        "source_path": str(
            source_path
        ),
        "source_file": source_path.name,
        "format_id": str(
            inspection_result.get(
                "format_id",
                FORMAT_UNKNOWN,
            )
        ),
        "operator": str(
            inspection_result.get(
                "operator",
                "Unknown",
            )
        ),
        "query_identifier": str(
            inspection_result.get(
                "query_identifier_normalized",
                "",
            )
        ),
        "data": _empty_imei_cdr_dataframe(),
        "records_read": 0,
        "records_normalized": 0,
        "rejected_line_count": 0,
        "warnings": [],
        "errors": [],
        "inspection": inspection_result,
        "message": "",
    }

    if not inspection_result.get(
        "ok"
    ):
        result[
            "status"
        ] = str(
            inspection_result.get(
                "status",
                STATUS_ERROR,
            )
        )

        result[
            "message"
        ] = str(
            inspection_result.get(
                "message",
                "IMEI evidence inspection failed.",
            )
        )

        return result

    format_id = str(
        inspection_result.get(
            "format_id",
            FORMAT_UNKNOWN,
        )
    )

    source_type = str(
        inspection_result.get(
            "source_type",
            "UNKNOWN",
        )
    ).upper()

    if (
        source_type != "CDR"
        or format_id
        not in IMEI_CDR_SUPPORTED_FORMATS
    ):
        result[
            "status"
        ] = STATUS_UNSUPPORTED

        result[
            "message"
        ] = (
            "Recognized IMEI report is not a "
            "supported CDR evidence format."
        )

        return result

    inspection_status = str(
        inspection_result.get(
            "status",
            STATUS_ERROR,
        )
    )

    if (
        inspection_status
        == STATUS_EMPTY_NO_DATA
    ):
        result.update(
            {
                "ok": True,
                "status": STATUS_EMPTY_NO_DATA,
                "message": (
                    "Valid IMEI CDR report contains "
                    "no data records."
                ),
            }
        )

        return result

    try:
        text = _read_text(
            source_path
        )

        lines = text.splitlines()

        header_line, header = _find_header(
            lines
        )

        numbered_rows, rejected = (
            _extract_rows_with_line_numbers(
                lines=lines,
                header_line=header_line,
                header=header,
            )
        )

        normalized_records: list[
            dict[str, Any]
        ] = []

        for (
            source_row_number,
            values,
        ) in numbered_rows:
            source_record = _row_dictionary(
                header,
                values,
            )

            if format_id in {
                FORMAT_VIL_IMEI_CDR,
                FORMAT_SEARCH_CRITERIA_IMEI_CDR,
            }:
                normalized = (
                    _normalize_standard_imei_cdr_row(
                        record=source_record,
                        inspection=inspection_result,
                        source_path=source_path,
                        source_row_number=(
                            source_row_number
                        ),
                    )
                )

            elif (
                format_id
                == FORMAT_JIO_IMEI_CDR
            ):
                normalized = (
                    _normalize_jio_imei_cdr_row(
                        record=source_record,
                        inspection=inspection_result,
                        source_path=source_path,
                        source_row_number=(
                            source_row_number
                        ),
                    )
                )

            else:
                continue

            normalized_records.append(
                normalized
            )

        dataframe = pd.DataFrame(
            normalized_records,
            columns=IMEI_CDR_CANONICAL_COLUMNS,
        )

        expected_records = int(
            inspection_result.get(
                "record_count",
                0,
            )
            or 0
        )

        warnings: list[str] = []

        if (
            expected_records
            != len(
                numbered_rows
            )
        ):
            warnings.append(
                "Inspection and normalization row "
                "counts are different."
            )

        if dataframe.empty:
            result.update(
                {
                    "status": STATUS_ERROR,
                    "records_read": len(
                        numbered_rows
                    ),
                    "rejected_line_count": rejected,
                    "warnings": warnings,
                    "errors": [
                        (
                            "No canonical CDR rows were "
                            "produced from a data report."
                        )
                    ],
                    "message": (
                        "IMEI CDR normalization produced "
                        "no usable rows."
                    ),
                }
            )

            return result

        result.update(
            {
                "ok": True,
                "status": STATUS_HAS_DATA,
                "data": dataframe,
                "records_read": len(
                    numbered_rows
                ),
                "records_normalized": len(
                    dataframe
                ),
                "rejected_line_count": rejected,
                "warnings": warnings,
                "message": (
                    "Dedicated IMEI CDR report "
                    "normalized successfully."
                ),
            }
        )

        return result

    except Exception as error:
        result[
            "errors"
        ] = [
            f"{type(error).__name__}: {error}"
        ]

        result[
            "message"
        ] = (
            "IMEI CDR normalization failed."
        )

        return result

def normalize_imei_ipdr_file(
    path: str | Path,
    inspection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize one recognized dedicated IMEI IPDR report.

    Canonical IPDR parsing remains owned by ``ipdr_loader``. This wrapper
    adds requested-versus-observed IMEI context without changing raw
    evidence or truncating IMEI/IMEISV values.
    """

    source_path = Path(
        path
    ).expanduser().resolve()

    inspection_result = (
        dict(
            inspection
        )
        if isinstance(
            inspection,
            dict,
        )
        else inspect_imei_evidence_file(
            source_path
        )
    )

    result: dict[str, Any] = {
        "ok": False,
        "status": STATUS_ERROR,
        "source_path": str(
            source_path
        ),
        "source_file": source_path.name,
        "format_id": str(
            inspection_result.get(
                "format_id",
                FORMAT_UNKNOWN,
            )
        ),
        "operator": str(
            inspection_result.get(
                "operator",
                "Unknown",
            )
        ),
        "query_identifier": str(
            inspection_result.get(
                "query_identifier_normalized",
                "",
            )
        ),
        "data": pd.DataFrame(),
        "rejected_rows": pd.DataFrame(),
        "records_read": 0,
        "records_normalized": 0,
        "rejected_line_count": 0,
        "warnings": [],
        "errors": [],
        "inspection": inspection_result,
        "canonical_metadata": {},
        "message": "",
    }

    if not inspection_result.get(
        "ok"
    ):
        result[
            "status"
        ] = str(
            inspection_result.get(
                "status",
                STATUS_ERROR,
            )
        )

        result[
            "message"
        ] = str(
            inspection_result.get(
                "message",
                "IMEI evidence inspection failed.",
            )
        )

        return result

    format_id = str(
        inspection_result.get(
            "format_id",
            FORMAT_UNKNOWN,
        )
    )

    source_type = str(
        inspection_result.get(
            "source_type",
            "UNKNOWN",
        )
    ).upper()

    if (
        source_type != "IPDR"
        or format_id
        not in IMEI_IPDR_SUPPORTED_FORMATS
    ):
        result[
            "status"
        ] = STATUS_UNSUPPORTED

        result[
            "message"
        ] = (
            "Recognized IMEI report is not a "
            "supported IPDR evidence format."
        )

        return result

    try:
        # Lazy import avoids coupling module initialization.
        from modules.loader.ipdr_loader import (
            load_ipdr_file,
        )

        canonical_result = load_ipdr_file(
            source_path
        )

        canonical_metadata = dict(
            canonical_result.get(
                "metadata",
                {},
            )
            or {}
        )

        result[
            "canonical_metadata"
        ] = canonical_metadata

        warnings: list[str] = []
        errors: list[str] = []

        canonical_warning = str(
            canonical_result.get(
                "warning",
                "",
            )
            or ""
        ).strip()

        canonical_error = str(
            canonical_result.get(
                "error",
                "",
            )
            or ""
        ).strip()

        if canonical_warning:
            warnings.append(
                canonical_warning
            )

        if canonical_error:
            errors.append(
                canonical_error
            )

        if canonical_result.get(
            "ok"
        ) is not True:
            result.update(
                {
                    "warnings": warnings,
                    "errors": errors or [
                        (
                            "Canonical IPDR loader did "
                            "not accept the report."
                        )
                    ],
                    "message": (
                        "IMEI IPDR normalization failed "
                        "in the canonical IPDR loader."
                    ),
                }
            )

            return result

        canonical_data = canonical_result.get(
            "data"
        )

        if not isinstance(
            canonical_data,
            pd.DataFrame,
        ):
            result.update(
                {
                    "errors": [
                        (
                            "Canonical IPDR loader did not "
                            "return a DataFrame."
                        )
                    ],
                    "message": (
                        "IMEI IPDR normalization failed."
                    ),
                }
            )

            return result

        dataframe = canonical_data.copy(
            deep=True
        )

        rejected_rows = canonical_result.get(
            "rejected_rows"
        )

        if not isinstance(
            rejected_rows,
            pd.DataFrame,
        ):
            rejected_rows = pd.DataFrame()

        else:
            rejected_rows = rejected_rows.copy(
                deep=True
            )

        if "imei" not in dataframe.columns:
            result.update(
                {
                    "errors": [
                        (
                            "Canonical IPDR output is "
                            "missing the IMEI column."
                        )
                    ],
                    "message": (
                        "IMEI IPDR normalization failed."
                    ),
                }
            )

            return result

        query_raw = str(
            inspection_result.get(
                "query_identifier_raw",
                "",
            )
            or ""
        ).strip()

        query_normalized = str(
            inspection_result.get(
                "query_identifier_normalized",
                "",
            )
            or ""
        ).strip()

        if not query_normalized:
            query_normalized = _digits(
                query_raw
            )

        query_type = str(
            inspection_result.get(
                "query_identifier_type",
                "",
            )
            or ""
        ).strip()

        if not query_type:
            query_type = classify_device_identifier(
                query_normalized
            )

        observed_raw = (
            dataframe[
                "imei"
            ]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        observed_normalized = observed_raw.map(
            _digits
        )

        # The dedicated report header explicitly states that the query
        # scope is IMEI. This enrichment is local to this wrapper.
        if "report_scope" in dataframe.columns:
            dataframe[
                "report_scope"
            ] = "IMEI"

        dataframe[
            "query_identifier_raw"
        ] = query_raw

        dataframe[
            "query_identifier_normalized"
        ] = query_normalized

        dataframe[
            "query_identifier_type"
        ] = query_type

        dataframe[
            "observed_imei_raw"
        ] = observed_raw

        dataframe[
            "observed_imei_normalized"
        ] = observed_normalized

        dataframe[
            "match_relation"
        ] = observed_normalized.map(
            lambda observed: classify_match_relation(
                query_normalized,
                observed,
            )
        )

        dataframe[
            "detected_operator"
        ] = str(
            inspection_result.get(
                "operator",
                "Unknown",
            )
        )

        dataframe[
            "detected_format"
        ] = format_id

        dataframe[
            "source_path"
        ] = str(
            source_path
        )

        if "source_file" not in dataframe.columns:
            dataframe[
                "source_file"
            ] = source_path.name

        expected_records = int(
            inspection_result.get(
                "record_count",
                0,
            )
            or 0
        )

        if expected_records != len(
            dataframe
        ):
            warnings.append(
                "Inspection and canonical IPDR row "
                "counts are different."
            )

        if not rejected_rows.empty:
            warnings.append(
                f"{len(rejected_rows):,} canonical "
                "IPDR row(s) were quarantined."
            )

        inspection_status = str(
            inspection_result.get(
                "status",
                STATUS_ERROR,
            )
        )

        if (
            inspection_status == STATUS_HAS_DATA
            and dataframe.empty
        ):
            result.update(
                {
                    "data": dataframe,
                    "rejected_rows": rejected_rows,
                    "records_read": expected_records,
                    "rejected_line_count": len(
                        rejected_rows
                    ),
                    "warnings": warnings,
                    "errors": [
                        (
                            "No canonical IPDR rows were "
                            "produced from a data report."
                        )
                    ],
                    "message": (
                        "IMEI IPDR normalization produced "
                        "no usable rows."
                    ),
                }
            )

            return result

        status = (
            STATUS_EMPTY_NO_DATA
            if dataframe.empty
            else STATUS_HAS_DATA
        )

        message = (
            "Valid IMEI IPDR report contains "
            "no data records."
            if status == STATUS_EMPTY_NO_DATA
            else (
                "Dedicated IMEI IPDR report "
                "normalized successfully."
            )
        )

        result.update(
            {
                "ok": True,
                "status": status,
                "data": dataframe,
                "rejected_rows": rejected_rows,
                "records_read": expected_records,
                "records_normalized": len(
                    dataframe
                ),
                "rejected_line_count": len(
                    rejected_rows
                ),
                "warnings": warnings,
                "errors": errors,
                "message": message,
            }
        )

        return result

    except Exception as error:
        result[
            "errors"
        ] = [
            f"{type(error).__name__}: {error}"
        ]

        result[
            "message"
        ] = (
            "IMEI IPDR normalization failed."
        )

        return result


IMEI_GPRS_EXTRA_COLUMNS = (
    "query_identifier_raw",
    "query_identifier_normalized",
    "query_identifier_type",
    "observed_imei_raw",
    "observed_imei_normalized",
    "match_basis",
    "match_relation",
    "detected_operator",
    "detected_format",
    "source_path",
    "access_point_name",
    "pgw_ip",
)


def _empty_imei_gprs_dataframe() -> pd.DataFrame:
    """Return the canonical dedicated IMEI GPRS frame contract."""

    from modules.loader.gprs_dump_loader import (
        NORMALIZED_COLUMNS,
    )

    columns = list(
        NORMALIZED_COLUMNS
    )

    for column in IMEI_GPRS_EXTRA_COLUMNS:
        if column not in columns:
            columns.append(
                column
            )

    return pd.DataFrame(
        columns=columns
    )


def _imei_gprs_clean_text(
    value: pd.Series,
) -> pd.Series:
    result = (
        value.astype(
            "string"
        )
        .fillna(
            ""
        )
        .str.strip()
    )

    return result.mask(
        result.str.casefold().isin(
            {
                "",
                "-",
                "na",
                "n/a",
                "nan",
                "none",
                "null",
            }
        ),
        "",
    )


def _imei_gprs_header_key(
    value: object,
) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        str(
            value
        ).strip().casefold(),
    ).strip()


def _imei_gprs_column(
    dataframe: pd.DataFrame,
    candidates: tuple[str, ...],
) -> pd.Series:
    lookup = {
        _imei_gprs_header_key(
            column
        ): column
        for column in dataframe.columns
    }

    for candidate in candidates:
        source_column = lookup.get(
            _imei_gprs_header_key(
                candidate
            )
        )

        if source_column is not None:
            return _imei_gprs_clean_text(
                dataframe[
                    source_column
                ]
            )

    return pd.Series(
        "",
        index=dataframe.index,
        dtype="string",
    )


def _read_dedicated_imei_gprs_rows(
    path: Path,
    *,
    header_line: int,
) -> pd.DataFrame:
    last_error: Exception | None = None

    for encoding in (
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin1",
    ):
        try:
            dataframe = pd.read_csv(
                path,
                skiprows=max(
                    int(
                        header_line
                    )
                    - 1,
                    0,
                ),
                dtype=str,
                keep_default_na=False,
                encoding=encoding,
                engine="python",
                on_bad_lines="skip",
            )

            dataframe = dataframe.loc[
                :,
                [
                    column
                    for column in dataframe.columns
                    if not str(
                        column
                    ).strip().casefold().startswith(
                        "unnamed"
                    )
                ],
            ]

            dataframe = dataframe.dropna(
                how="all"
            ).reset_index(
                drop=True
            )

            return dataframe

        except Exception as error:
            last_error = error

    raise ValueError(
        "Dedicated IMEI GPRS CSV could not be parsed."
        + (
            f" {type(last_error).__name__}: {last_error}"
            if last_error is not None
            else ""
        )
    )


def _augment_imei_gprs_provenance(
    dataframe: pd.DataFrame,
    *,
    path: Path,
    inspection: dict[str, Any],
) -> pd.DataFrame:
    work = dataframe.copy(
        deep=True
    )

    query_raw = str(
        inspection.get(
            "query_identifier_raw",
            "",
        )
        or ""
    ).strip()

    query_normalized = str(
        inspection.get(
            "query_identifier_normalized",
            "",
        )
        or ""
    ).strip()

    query_type = str(
        inspection.get(
            "query_identifier_type",
            "",
        )
        or ""
    ).strip()

    if "imei_raw" not in work.columns:
        work[
            "imei_raw"
        ] = ""

    if "imei" not in work.columns:
        work[
            "imei"
        ] = ""

    observed_raw = _imei_gprs_clean_text(
        work[
            "imei_raw"
        ]
    )

    observed_normalized = _imei_gprs_clean_text(
        work[
            "imei"
        ]
    ).map(
        normalize_imei
    ).fillna(
        ""
    )

    work[
        "imei"
    ] = observed_normalized

    work[
        "query_identifier_raw"
    ] = query_raw

    work[
        "query_identifier_normalized"
    ] = query_normalized

    work[
        "query_identifier_type"
    ] = query_type

    work[
        "observed_imei_raw"
    ] = observed_raw

    work[
        "observed_imei_normalized"
    ] = observed_normalized

    work[
        "match_basis"
    ] = "QUERY_SCOPE"

    work[
        "match_relation"
    ] = observed_normalized.map(
        lambda observed: (
            classify_match_relation(
                query_normalized,
                observed,
            )
            if observed
            else "UNAVAILABLE"
        )
    )

    work[
        "detected_operator"
    ] = str(
        inspection.get(
            "operator",
            "",
        )
        or ""
    )

    work[
        "detected_format"
    ] = str(
        inspection.get(
            "format_id",
            "",
        )
        or ""
    )

    work[
        "source_path"
    ] = str(
        path.resolve()
    )

    if "source_file" not in work.columns:
        work[
            "source_file"
        ] = path.name

    else:
        work[
            "source_file"
        ] = _imei_gprs_clean_text(
            work[
                "source_file"
            ]
        ).mask(
            lambda values: values.eq(
                ""
            ),
            path.name,
        )

    if "source_relative_path" not in work.columns:
        work[
            "source_relative_path"
        ] = path.name

    for column in (
        "access_point_name",
        "pgw_ip",
    ):
        if column not in work.columns:
            work[
                column
            ] = ""

    canonical = _empty_imei_gprs_dataframe()

    ordered_columns = list(
        canonical.columns
    )

    remaining_columns = [
        column
        for column in work.columns
        if column not in ordered_columns
    ]

    for column in ordered_columns:
        if column not in work.columns:
            work[
                column
            ] = pd.NA

    return work[
        ordered_columns
        + remaining_columns
    ].reset_index(
        drop=True
    )


def _normalize_vil_imei_gprs_rows(
    path: Path,
    *,
    inspection: dict[str, Any],
) -> tuple[pd.DataFrame, int]:
    from modules.loader.telecom_identifiers import (
        normalize_imsi,
    )

    header_line = int(
        inspection.get(
            "header_line",
            0,
        )
        or 0
    )

    if header_line <= 0:
        raise ValueError(
            "VIL IMEI GPRS header line was not detected."
        )

    raw = _read_dedicated_imei_gprs_rows(
        path,
        header_line=header_line,
    )

    if raw.empty:
        return (
            _empty_imei_gprs_dataframe(),
            0,
        )

    raw[
        "_source_index"
    ] = raw.index

    subscriber_raw = _imei_gprs_column(
        raw,
        (
            "Target /A PARTY NUMBER",
            "A PARTY NUMBER",
            "MSISDN",
            "Mobile No.",
        ),
    )

    imei_raw = _imei_gprs_column(
        raw,
        (
            "IMEI",
            "IMEISV",
        ),
    )

    observed_imei = imei_raw.map(
        normalize_imei
    ).fillna(
        ""
    )

    imsi_raw = _imei_gprs_column(
        raw,
        (
            "IMSI",
        ),
    )

    imsi = imsi_raw.map(
        normalize_imsi
    ).fillna(
        ""
    )

    ip_raw = _imei_gprs_column(
        raw,
        (
            "IP Address",
            "PDP Address IPv4",
        ),
    )

    ipv4 = ip_raw.where(
        ip_raw.str.contains(
            r"\.",
            regex=True,
            na=False,
        ),
        "",
    )

    ipv6 = ip_raw.where(
        ip_raw.str.contains(
            ":",
            regex=False,
            na=False,
        ),
        "",
    )

    date_value = _imei_gprs_column(
        raw,
        (
            "Call date",
            "Session Date",
        ),
    )

    time_value = _imei_gprs_column(
        raw,
        (
            "Call Initiation Time",
            "Session Start Time",
        ),
    )

    session_start = _parse_imei_gprs_session_start(
        date_value,
        time_value,
    )

    duration = pd.to_numeric(
        _imei_gprs_column(
            raw,
            (
                "Call Duration",
                "Session Duration",
                "Duration in sec",
            ),
        ).str.replace(
            ",",
            "",
            regex=False,
        ),
        errors="coerce",
    )

    session_end = (
        session_start
        + pd.to_timedelta(
            duration.fillna(
                0
            ),
            unit="s",
        )
    )

    uplink = pd.to_numeric(
        _imei_gprs_column(
            raw,
            (
                "Data Uplink Volume",
                "Uplink Vol",
                "Data Volume Uplink",
            ),
        ).str.replace(
            ",",
            "",
            regex=False,
        ),
        errors="coerce",
    )

    downlink = pd.to_numeric(
        _imei_gprs_column(
            raw,
            (
                "Data Downlink Volume",
                "Downlink Vol",
                "Data Volume Downlink",
            ),
        ).str.replace(
            ",",
            "",
            regex=False,
        ),
        errors="coerce",
    )

    total = pd.to_numeric(
        _imei_gprs_column(
            raw,
            (
                "Data Volume",
                "Total Vol",
                "Total Volume",
            ),
        ).str.replace(
            ",",
            "",
            regex=False,
        ),
        errors="coerce",
    )

    volume_expected = (
        uplink
        + downlink
    )

    volume_difference = (
        total
        - volume_expected
    )

    volume_tolerance = pd.Series(
        1.0,
        index=raw.index,
        dtype="float64",
    )

    volume_present = (
        uplink.notna()
        & downlink.notna()
        & total.notna()
    )

    volume_consistent = (
        volume_present
        & volume_difference.abs().le(
            volume_tolerance
        )
    )

    normalized = pd.DataFrame(
        {
            "record_type": "IMEI_GPRS_SESSION",
            "source_format": str(
                inspection.get(
                    "format_id",
                    "",
                )
                or ""
            ),
            "operator": str(
                inspection.get(
                    "operator",
                    "",
                )
                or ""
            ),
            "subscriber_number_raw": subscriber_raw,
            "subscriber_number": subscriber_raw,
            "identifier_type": "MSISDN",
            "ipv4_address_raw": ipv4,
            "ipv4_address": ipv4,
            "ipv6_address_raw": ipv6,
            "ipv6_address": ipv6,
            "imei_raw": imei_raw,
            "imei": observed_imei,
            "imsi_raw": imsi_raw,
            "imsi": imsi,
            "downlink_volume": downlink,
            "uplink_volume": uplink,
            "total_volume": total,
            "session_start": session_start,
            "session_end": session_end,
            "session_duration_seconds": duration,
            "session_time_valid": (
                session_start.notna()
                & session_end.notna()
                & session_end.ge(
                    session_start
                )
            ),
            "pre_post": _imei_gprs_column(
                raw,
                (
                    "Type of Connection",
                    "Pre/Post",
                ),
            ),
            "roaming_circle": _imei_gprs_column(
                raw,
                (
                    "Roaming Network/Circle",
                    "Roaming Circle",
                ),
            ),
            "technology": _imei_gprs_column(
                raw,
                (
                    "Service Type",
                    "2g/4g/5g",
                    "RAT",
                ),
            ),
            "icr_operator": "",
            "home_circle": "",
            "searched_cell_id": _imei_gprs_column(
                raw,
                (
                    "First Cell Global Id",
                    "First Cell ID",
                    "CGI",
                ),
            ),
            "cgi_latitude": "",
            "cgi_longitude": "",
            "volume_fields_present": volume_present,
            "volume_expected_total": volume_expected,
            "volume_difference": volume_difference,
            "volume_tolerance": volume_tolerance,
            "volume_consistent": volume_consistent,
            "volume_mismatch": (
                volume_present
                & ~volume_consistent
            ),
            "is_zero_volume": (
                total.fillna(
                    0
                ).eq(
                    0
                )
            ),
            "source_file": path.name,
            "source_relative_path": path.name,
            "spot_id": "",
            "spot_name": "",
            "spot_folder": "",
            "source_row_number": (
                raw[
                    "_source_index"
                ].astype(
                    "int64"
                )
                + header_line
                + 1
            ),
            "access_point_name": _imei_gprs_column(
                raw,
                (
                    "APN",
                    "Access Point Name",
                ),
            ),
            "pgw_ip": _imei_gprs_column(
                raw,
                (
                    "PGW IP",
                    "PGW IP address",
                ),
            ),
        }
    )

    valid_mask = normalized[
        "imei"
    ].astype(
        "string"
    ).fillna(
        ""
    ).ne(
        ""
    )

    rejected_count = int(
        (
            ~valid_mask
        ).sum()
    )

    normalized = normalized.loc[
        valid_mask
    ].reset_index(
        drop=True
    )

    normalized = _augment_imei_gprs_provenance(
        normalized,
        path=path,
        inspection=inspection,
    )

    return (
        normalized,
        rejected_count,
    )


def normalize_imei_gprs_file(
    path: str | Path,
    *,
    inspection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize one dedicated IMEI GPRS report.

    Airtel session rows reuse the canonical GPRS loader. Vodafone
    Idea dedicated GPRS rows use the source-specific mapping above.
    Non-GPRS evidence is rejected without altering the source file.
    """

    from modules.loader.gprs_dump_loader import (
        STATUS_EMPTY_NO_DATA as GPRS_EMPTY_NO_DATA,
        load_gprs_dump_file,
    )

    file_path = Path(
        path
    ).expanduser().resolve()

    inspection_value = dict(
        inspection
        if isinstance(
            inspection,
            dict,
        )
        else inspect_imei_evidence_file(
            file_path
        )
    )

    source_type = str(
        inspection_value.get(
            "source_type",
            "",
        )
        or ""
    ).strip().upper()

    format_id = str(
        inspection_value.get(
            "format_id",
            "",
        )
        or ""
    ).strip()

    query_identifier = str(
        inspection_value.get(
            "query_identifier_normalized",
            "",
        )
        or ""
    ).strip()

    base_result = {
        "source_type": source_type,
        "format_id": format_id,
        "operator": str(
            inspection_value.get(
                "operator",
                "",
            )
            or ""
        ),
        "query_identifier_raw": str(
            inspection_value.get(
                "query_identifier_raw",
                "",
            )
            or ""
        ),
        "query_identifier_normalized": query_identifier,
        "query_identifier_type": str(
            inspection_value.get(
                "query_identifier_type",
                "",
            )
            or ""
        ),
        "records_read": 0,
        "records_normalized": 0,
        "rejected_line_count": int(
            inspection_value.get(
                "rejected_line_count",
                0,
            )
            or 0
        ),
        "warnings": [],
        "errors": [],
        "rejected_rows": pd.DataFrame(),
        "data": _empty_imei_gprs_dataframe(),
    }

    if (
        not inspection_value.get(
            "ok"
        )
        or source_type != "GPRS"
        or format_id not in {
            FORMAT_AIRTEL_IMEI_GPRS,
            FORMAT_VIL_IMEI_GPRS,
        }
    ):
        return {
            **base_result,
            "ok": False,
            "status": STATUS_UNSUPPORTED,
            "message": (
                "The selected evidence is not a supported "
                "dedicated IMEI GPRS report."
            ),
        }

    if not normalize_imei(
        query_identifier
    ):
        return {
            **base_result,
            "ok": False,
            "status": "ERROR",
            "errors": [
                "A valid report-query IMEI/IMEISV was not detected."
            ],
            "message": (
                "A valid report-query IMEI/IMEISV was not detected."
            ),
        }

    inspection_status = str(
        inspection_value.get(
            "status",
            "",
        )
        or ""
    ).strip().upper()

    if inspection_status == STATUS_EMPTY_NO_DATA:
        return {
            **base_result,
            "ok": True,
            "status": STATUS_EMPTY_NO_DATA,
            "message": (
                "Valid dedicated IMEI GPRS report loaded "
                "with no session rows."
            ),
        }

    try:
        if format_id == FORMAT_AIRTEL_IMEI_GPRS:
            loaded = load_gprs_dump_file(
                file_path
            )

            if not loaded.get(
                "ok"
            ):
                return {
                    **base_result,
                    "ok": False,
                    "status": "ERROR",
                    "warnings": list(
                        loaded.get(
                            "warnings",
                            [],
                        )
                        or []
                    ),
                    "errors": list(
                        loaded.get(
                            "errors",
                            [],
                        )
                        or []
                    ),
                    "message": (
                        "; ".join(
                            str(error)
                            for error in loaded.get(
                                "errors",
                                [],
                            )
                            or []
                        )
                        or "Airtel IMEI GPRS normalization failed."
                    ),
                }

            dataframe = loaded.get(
                "df"
            )

            if not isinstance(
                dataframe,
                pd.DataFrame,
            ):
                dataframe = _empty_imei_gprs_dataframe()

            dataframe = _augment_imei_gprs_provenance(
                dataframe,
                path=file_path,
                inspection=inspection_value,
            )

            rejected_rows = loaded.get(
                "rejected_rows"
            )

            if not isinstance(
                rejected_rows,
                pd.DataFrame,
            ):
                rejected_rows = pd.DataFrame()

            rejected_count = len(
                rejected_rows
            )

            warnings = list(
                loaded.get(
                    "warnings",
                    [],
                )
                or []
            )

            data_status = str(
                loaded.get(
                    "data_status",
                    "",
                )
                or ""
            ).strip().upper()

            status = (
                STATUS_EMPTY_NO_DATA
                if data_status == GPRS_EMPTY_NO_DATA
                else STATUS_HAS_DATA
            )

        else:
            (
                dataframe,
                rejected_count,
            ) = _normalize_vil_imei_gprs_rows(
                file_path,
                inspection=inspection_value,
            )

            rejected_rows = pd.DataFrame()
            warnings = []
            status = (
                STATUS_HAS_DATA
                if not dataframe.empty
                else STATUS_EMPTY_NO_DATA
            )

    except Exception as error:
        return {
            **base_result,
            "ok": False,
            "status": "ERROR",
            "errors": [
                f"{type(error).__name__}: {error}"
            ],
            "message": (
                f"{type(error).__name__}: {error}"
            ),
        }

    records_normalized = len(
        dataframe
    )

    return {
        **base_result,
        "ok": True,
        "status": status,
        "records_read": int(
            inspection_value.get(
                "record_count",
                records_normalized,
            )
            or records_normalized
        ),
        "records_normalized": records_normalized,
        "rejected_line_count": int(
            rejected_count
        ),
        "warnings": warnings,
        "errors": [],
        "rejected_rows": rejected_rows,
        "data": dataframe,
        "message": (
            f"Normalized {records_normalized:,} dedicated "
            "IMEI GPRS session row(s)."
            if records_normalized
            else (
                "Valid dedicated IMEI GPRS report loaded "
                "with no session rows."
            )
        ),
    }
