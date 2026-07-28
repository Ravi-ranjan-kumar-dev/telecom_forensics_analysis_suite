"""Airtel GPRS session-dump loader.

Phase-5 initially supports only the verified Bharti Airtel GPRS session format.
Unknown formats are rejected explicitly rather than being guessed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from modules.loader.identity import normalize_msisdn
from modules.loader.telecom_identifiers import canonical_ip, normalize_imei, normalize_imsi
from modules.loader.evidence_csv import (
    empty_reject_ledger,
    quarantine_dataframe_rows,
    read_csv_with_quarantine,
)
from modules.loader.tower_spot_layout import build_tower_spot_layout


FORMAT_AIRTEL_GPRS_SESSION = "AIRTEL_GPRS_SESSION"
SUPPORTED_SUFFIXES = {".csv", ".txt"}

# GPRS_EMPTY_NO_DATA_V1
STATUS_LOADED = "LOADED"
STATUS_EMPTY_NO_DATA = "EMPTY_NO_DATA"
STATUS_FAILED = "FAILED"


def _is_valid_empty_gprs_report(
    path: str | Path,
    detection: dict[str, Any],
) -> bool:
    """Return True only for a recognised Airtel zero-record report."""

    if (
        detection.get("source_format")
        != FORMAT_AIRTEL_GPRS_SESSION
    ):
        return False

    file_path = Path(
        path
    ).expanduser().resolve()

    preferred_encoding = str(
        detection.get(
            "encoding",
            "",
        )
        or ""
    ).strip()

    encodings = [
        preferred_encoding,
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin1",
    ]

    text = ""

    for encoding in encodings:
        if not encoding:
            continue

        try:
            text = file_path.read_text(
                encoding=encoding,
                errors="strict",
            )
            break

        except (
            UnicodeError,
            LookupError,
        ):
            continue

    if not text:
        try:
            text = file_path.read_bytes().decode(
                "latin1",
                errors="replace",
            )

        except OSError:
            return False

    normalized = re.sub(
        r"\s+",
        " ",
        text,
    ).strip().casefold()

    has_report_identity = (
        (
            "gprs of cell id" in normalized
            or "gprs of imei" in normalized
        )
        and re.search(
            r"\bmobile\s+no\.?\b",
            normalized,
        )
        is not None
    )

    has_explicit_no_data_marker = (
        "no records found" in normalized
    )

    return bool(
        has_report_identity
        and has_explicit_no_data_marker
    )

NORMALIZED_COLUMNS = [
    "record_type",
    "source_format",
    "operator",
    "subscriber_number_raw",
    "subscriber_number",
    "identifier_type",
    "ipv4_address_raw",
    "ipv4_address",
    "ipv6_address_raw",
    "ipv6_address",
    "imei_raw",
    "imei",
    "imsi_raw",
    "imsi",
    "downlink_volume",
    "uplink_volume",
    "total_volume",
    "session_start",
    "session_end",
    "session_duration_seconds",
    "session_time_valid",
    "pre_post",
    "roaming_circle",
    "technology",
    "icr_operator",
    "home_circle",
    "searched_cell_id",
    "cgi_latitude",
    "cgi_longitude",
    "volume_fields_present",
    "volume_expected_total",
    "volume_difference",
    "volume_tolerance",
    "volume_consistent",
    "volume_mismatch",
    "is_zero_volume",
    "source_file",
    "source_relative_path",
    "spot_id",
    "spot_name",
    "spot_folder",
    "source_row_number",
]

COLUMN_MAP = {
    "mobile no.": "subscriber_number_raw",
    "mobile no": "subscriber_number_raw",
    "ip address": "ipv4_address",
    "imei": "imei",
    "imsi": "imsi",
    "downlink vol": "downlink_volume",
    "uplink vol": "uplink_volume",
    "total vol": "total_volume",
    "session start time": "session_start",
    "session end time": "session_end",
    "pre/post": "pre_post",
    "roaming circle": "roaming_circle",
    "2g/4g/5g": "technology",
    "icr operator name": "icr_operator",
    "home circle": "home_circle",
    "ip": "ipv6_address",
    "cgi latitude": "cgi_latitude",
    "cgi longitude": "cgi_longitude",
    "cgi": "searched_cell_id",
}


def _clean_header(value: Any) -> str:
    text = str(value).replace("\ufeff", "").strip().lower()
    return re.sub(r"\s+", " ", text)


def _read_preview(path: Path, limit: int = 40) -> tuple[list[str], str]:
    encodings = ("utf-8-sig", "utf-8", "cp1252", "latin1")
    last_error: Exception | None = None

    for encoding in encodings:
        try:
            with path.open("r", encoding=encoding, errors="strict") as handle:
                lines = []
                for _ in range(limit):
                    line = handle.readline()
                    if line == "":
                        break
                    lines.append(line.rstrip("\r\n"))
            return lines, encoding
        except UnicodeError as error:
            last_error = error

    raise ValueError(f"File encoding could not be read: {last_error}")


def _find_header_row(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        clean = _clean_header(line)
        required = (
            "mobile no" in clean
            and "session start time" in clean
            and "session end time" in clean
            and "cgi" in clean
        )
        if required:
            return index
    return None


def _parse_preamble(lines: list[str]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "operator": "",
        "searched_cell_id": "",
        "requested_start": "",
        "requested_end": "",
        "report_title": "",
    }

    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()

        if "BHARTI AIRTEL" in upper:
            metadata["operator"] = "Airtel"

        if "GPRS OF CELL ID" in upper:
            metadata["report_title"] = stripped
            match = re.search(
                r"GPRS\s+OF\s+CELL\s+ID\s*:\s*(.*?)\s+from\s+"
                r"(.+?)\s+to\s+(.+?)\s*$",
                stripped,
                flags=re.IGNORECASE,
            )
            if match:
                metadata["searched_cell_id"] = match.group(1).strip()
                metadata["requested_start"] = match.group(2).strip()
                metadata["requested_end"] = match.group(3).strip()

    return metadata


def detect_gprs_format(path: str | Path) -> dict[str, Any]:
    """Detect supported Airtel Cell-ID or dedicated IMEI GPRS reports."""

    file_path = Path(
        path
    ).expanduser().resolve()

    if not file_path.is_file():
        raise FileNotFoundError(
            file_path
        )

    lines, encoding = _read_preview(
        file_path
    )

    header_row = _find_header_row(
        lines
    )

    metadata = _parse_preamble(
        lines
    )

    source_format = ""

    report_title = str(
        metadata.get(
            "report_title",
            "",
        )
        or ""
    ).casefold()

    preview_text = " ".join(
        str(
            line
        )
        for line in lines
    ).casefold()

    is_supported_report_title = any(
        marker in report_title
        or marker in preview_text
        for marker in (
            "gprs of cell id",
            "gprs of imei",
        )
    )

    if (
        header_row is not None
        and metadata.get(
            "operator"
        ) == "Airtel"
        and is_supported_report_title
    ):
        source_format = (
            FORMAT_AIRTEL_GPRS_SESSION
        )

    return {
        "source_format": source_format,
        "header_row": header_row,
        "encoding": encoding,
        "metadata": metadata,
    }

def _string_series(dataframe: pd.DataFrame, column: str) -> pd.Series:
    if column not in dataframe.columns:
        return pd.Series("", index=dataframe.index, dtype="string")

    return (
        dataframe[column]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace({"nan": "", "None": "", "<NA>": ""})
    )


def _classify_identifier(value: str) -> str:
    text = str(value).strip()

    if re.fullmatch(r"[6-9]\d{9}", text):
        return "MSISDN"

    if re.fullmatch(r"\d+", text):
        return "NON_STANDARD_SUBSCRIBER_ID"

    return "INVALID_OR_UNVERIFIED"


def _normalize_airtel(
    raw: pd.DataFrame,
    *,
    path: Path,
    header_row: int,
    metadata: dict[str, Any],
) -> pd.DataFrame:
    raw = raw.copy()
    raw.columns = [_clean_header(column) for column in raw.columns]

    rename_map = {
        column: COLUMN_MAP[column]
        for column in raw.columns
        if column in COLUMN_MAP
    }
    raw = raw.rename(columns=rename_map)

    if "_source_row_number" not in raw.columns:
        raw["_source_row_number"] = pd.RangeIndex(
            start=header_row + 2,
            stop=header_row + 2 + len(raw),
        )

    subscriber_values = _string_series(
        raw,
        "subscriber_number_raw",
    )
    data_mask = subscriber_values.str.fullmatch(r"\d+", na=False)
    discarded_non_data_rows = int((~data_mask).sum())
    non_data_rejects = quarantine_dataframe_rows(
        raw,
        ~data_mask,
        source_file=path,
        reason="NON_DATA_OR_INVALID_SUBSCRIBER_ROW",
    )
    raw = raw.loc[data_mask].copy().reset_index(drop=True)

    dataframe = pd.DataFrame(index=raw.index)

    for column in (
        "subscriber_number_raw",
        "ipv4_address",
        "ipv6_address",
        "imei",
        "imsi",
        "pre_post",
        "roaming_circle",
        "technology",
        "icr_operator",
        "home_circle",
        "searched_cell_id",
    ):
        dataframe[column] = _string_series(raw, column)

    dataframe["ipv4_address_raw"] = dataframe["ipv4_address"].copy()
    dataframe["ipv6_address_raw"] = dataframe["ipv6_address"].copy()
    dataframe["imei_raw"] = dataframe["imei"].copy()
    dataframe["imsi_raw"] = dataframe["imsi"].copy()
    dataframe["ipv4_address"] = dataframe["ipv4_address"].map(canonical_ip)
    dataframe["ipv6_address"] = dataframe["ipv6_address"].map(canonical_ip)
    dataframe["imei"] = dataframe["imei"].map(normalize_imei)
    dataframe["imsi"] = dataframe["imsi"].map(normalize_imsi)

    dataframe["subscriber_number"] = dataframe[
        "subscriber_number_raw"
    ].map(lambda value: normalize_msisdn(value) or str(value).strip())
    dataframe["identifier_type"] = dataframe[
        "subscriber_number"
    ].map(_classify_identifier)

    for column in (
        "downlink_volume",
        "uplink_volume",
        "total_volume",
        "cgi_latitude",
        "cgi_longitude",
    ):
        dataframe[column] = pd.to_numeric(
            raw[column] if column in raw.columns else pd.Series(index=raw.index),
            errors="coerce",
        )

    dataframe["session_start"] = pd.to_datetime(
        raw["session_start"] if "session_start" in raw.columns else None,
        format="%d-%b-%Y %H:%M:%S",
        errors="coerce",
    )
    dataframe["session_end"] = pd.to_datetime(
        raw["session_end"] if "session_end" in raw.columns else None,
        format="%d-%b-%Y %H:%M:%S",
        errors="coerce",
    )

    duration = (
        dataframe["session_end"] - dataframe["session_start"]
    ).dt.total_seconds()

    dataframe["session_duration_seconds"] = duration
    dataframe["session_time_valid"] = (
        dataframe["session_start"].notna()
        & dataframe["session_end"].notna()
        & duration.ge(0)
    )

    dataframe["volume_fields_present"] = (
        dataframe["downlink_volume"].notna()
        & dataframe["uplink_volume"].notna()
        & dataframe["total_volume"].notna()
    )
    expected_total = dataframe["downlink_volume"] + dataframe["uplink_volume"]
    difference = (dataframe["total_volume"] - expected_total).abs()
    tolerance = expected_total.abs().mul(1e-6).clip(lower=1.0)
    dataframe["volume_expected_total"] = expected_total
    dataframe["volume_difference"] = difference
    dataframe["volume_tolerance"] = tolerance
    dataframe["volume_consistent"] = (
        dataframe["volume_fields_present"] & difference.le(tolerance)
    )
    dataframe["volume_mismatch"] = (
        dataframe["volume_fields_present"] & difference.gt(tolerance)
    )
    dataframe["is_zero_volume"] = (
        dataframe["total_volume"].notna()
        & dataframe["total_volume"].eq(0)
    )

    fallback_cgi = str(metadata.get("searched_cell_id", "")).strip()
    if fallback_cgi:
        dataframe["searched_cell_id"] = dataframe[
            "searched_cell_id"
        ].replace("", fallback_cgi)

    dataframe.insert(0, "operator", "Airtel")
    dataframe.insert(0, "source_format", FORMAT_AIRTEL_GPRS_SESSION)
    dataframe.insert(0, "record_type", "GPRS_SESSION")
    dataframe["source_file"] = str(path)
    dataframe["source_row_number"] = pd.to_numeric(
        raw["_source_row_number"],
        errors="coerce",
    ).astype("Int64")

    for column in NORMALIZED_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = pd.NA

    dataframe = dataframe[NORMALIZED_COLUMNS].reset_index(drop=True)

    dataframe.attrs["metadata"] = {
        **metadata,
        "source_file": str(path),
        "source_format": FORMAT_AIRTEL_GPRS_SESSION,
        "header_row": header_row + 1,
        "discarded_non_data_rows": discarded_non_data_rows,
    }
    dataframe.attrs["rejected_rows"] = non_data_rejects.reset_index(drop=True)
    return dataframe


def load_gprs_dump_file(path: str | Path) -> dict[str, Any]:
    file_path = Path(path).expanduser().resolve()
    detection = detect_gprs_format(file_path)
    errors: list[str] = []
    warnings: list[str] = []

    if detection["source_format"] != FORMAT_AIRTEL_GPRS_SESSION:
        return {
            "ok": False,
            "has_records": False,
            "data_status": STATUS_FAILED,
            "df": pd.DataFrame(columns=NORMALIZED_COLUMNS),
            "file": str(file_path),
            "source_format": detection["source_format"] or "UNKNOWN",
            "metadata": detection["metadata"],
            "warnings": warnings,
            "errors": [
                "Unsupported GPRS format. Phase-5 currently supports "
                "only Airtel GPRS session dumps."
            ],
        }

    if _is_valid_empty_gprs_report(
        file_path,
        detection,
    ):
        metadata = {
            **detection["metadata"],
            "header_row": (
                int(detection["header_row"])
                + 1
            ),
            "encoding": detection["encoding"],
            "records": 0,
            "has_records": False,
            "valid_empty_report": True,
            "data_status": STATUS_EMPTY_NO_DATA,
            "invalid_session_time_rows": 0,
            "missing_volume_rows": 0,
            "volume_mismatch_rows": 0,
            "non_standard_identifier_rows": 0,
            "discarded_non_data_rows": 0,
            "zero_volume_rows": 0,
            "exact_duplicate_rows": 0,
            "rejected_rows": 0,
            "adjusted_rows": 0,
        }

        return {
            "ok": True,
            "has_records": False,
            "data_status": STATUS_EMPTY_NO_DATA,
            "df": pd.DataFrame(
                columns=NORMALIZED_COLUMNS
            ),
            "file": str(file_path),
            "source_format": (
                FORMAT_AIRTEL_GPRS_SESSION
            ),
            "metadata": metadata,
            "rejected_rows": (
                empty_reject_ledger()
            ),
            "warnings": [],
            "errors": [],
        }

    try:
        raw, parser_rejects, ingestion_metadata = read_csv_with_quarantine(
            file_path,
            skiprows=int(detection["header_row"]),
            sep=",",
            encoding=str(detection["encoding"]),
        )
        raw = raw.loc[
            :,
            [
                column
                for column in raw.columns
                if not str(column).strip().lower().startswith("unnamed")
            ],
        ]
        raw = raw.dropna(how="all").reset_index(drop=True)

        dataframe = _normalize_airtel(
            raw,
            path=file_path,
            header_row=int(detection["header_row"]),
            metadata=detection["metadata"],
        )
        rejected_rows = pd.concat(
            [
                parser_rejects,
                dataframe.attrs.get("rejected_rows", empty_reject_ledger()),
            ],
            ignore_index=True,
        )

    except Exception as error:
        return {
            "ok": False,
            "has_records": False,
            "data_status": STATUS_FAILED,
            "df": pd.DataFrame(columns=NORMALIZED_COLUMNS),
            "file": str(file_path),
            "source_format": FORMAT_AIRTEL_GPRS_SESSION,
            "metadata": detection["metadata"],
            "warnings": warnings,
            "errors": [f"{type(error).__name__}: {error}"],
        }

    invalid_time = int((~dataframe["session_time_valid"]).sum())
    missing_volume = int((~dataframe["volume_fields_present"]).sum())
    inconsistent_volume = int(dataframe["volume_mismatch"].sum())
    non_standard = int(
        dataframe["identifier_type"].ne("MSISDN").sum()
    )
    zero_volume = int(dataframe["is_zero_volume"].sum())
    duplicate_columns = [
        column
        for column in NORMALIZED_COLUMNS
        if column not in {
            "source_file",
            "source_relative_path",
            "spot_id",
            "spot_name",
            "spot_folder",
            "source_row_number",
        }
    ]
    exact_duplicates = int(
        dataframe.duplicated(subset=duplicate_columns).sum()
    )

    if invalid_time:
        warnings.append(f"{invalid_time} invalid/negative session time rows.")
    if missing_volume:
        warnings.append(f"{missing_volume} sessions have missing volume fields.")
    if inconsistent_volume:
        warnings.append(f"{inconsistent_volume} volume mismatch rows.")
    if non_standard:
        warnings.append(
            f"{non_standard} rows contain non-standard subscriber identifiers."
        )
    if zero_volume:
        warnings.append(f"{zero_volume} zero-volume sessions.")
    if exact_duplicates:
        warnings.append(
            f"{exact_duplicates} exact duplicate rows detected; not removed."
        )

    metadata = {
        **detection["metadata"],
        "header_row": int(detection["header_row"]) + 1,
        "encoding": detection["encoding"],
        "records": len(dataframe),
        "invalid_session_time_rows": invalid_time,
        "missing_volume_rows": missing_volume,
        "volume_mismatch_rows": inconsistent_volume,
        "non_standard_identifier_rows": non_standard,
        "discarded_non_data_rows": int(
            dataframe.attrs.get("metadata", {}).get(
                "discarded_non_data_rows",
                0,
            )
        ),
        "zero_volume_rows": zero_volume,
        "exact_duplicate_rows": exact_duplicates,
        "rejected_rows": int(len(rejected_rows)),
        "adjusted_rows": int(ingestion_metadata.get("adjusted_rows", 0)),
    }

    has_records = not dataframe.empty

    if not has_records and not errors:
        errors.append(
            "Recognised Airtel GPRS report did not "
            "contain valid session records and did not "
            "carry the explicit 'No Records Found' marker."
        )

    data_status = (
        STATUS_LOADED
        if has_records
        else STATUS_FAILED
    )

    metadata["has_records"] = has_records
    metadata["valid_empty_report"] = False
    metadata["data_status"] = data_status

    return {
        "ok": has_records,
        "has_records": has_records,
        "data_status": data_status,
        "df": dataframe,
        "file": str(file_path),
        "source_format": FORMAT_AIRTEL_GPRS_SESSION,
        "metadata": metadata,
        "rejected_rows": rejected_rows.reset_index(
            drop=True
        ),
        "warnings": warnings,
        "errors": errors,
    }


def load_gprs_dump_case(
    folder: str | Path,
    *,
    recursive: bool = True,
) -> dict[str, Any]:
    root = Path(folder).expanduser().resolve()

    if not root.is_dir():
        return {
            "ok": False,
            "df": pd.DataFrame(columns=NORMALIZED_COLUMNS),
            "files": [],
            "file_results": [],
            "file_summary": pd.DataFrame(),
            "spot_summary": pd.DataFrame(),
            "operators": [],
            "cell_ids": [],
            "metadata": {
                "files_found": 0,
                "files_loaded": 0,
                "files_empty_no_data": 0,
                "files_processed_count": 0,
                "files_failed": 0,
                "records": 0,
            },
            "warnings": [],
            "errors": [f"GPRS input folder not found: {root}"],
        }

    iterator = root.rglob("*") if recursive else root.glob("*")
    files = sorted(
        path
        for path in iterator
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )

    results: list[dict[str, Any]] = []
    frames: list[pd.DataFrame] = []
    warnings: list[str] = []
    errors: list[str] = []
    summary_rows: list[dict[str, Any]] = []
    reject_frames: list[pd.DataFrame] = []

    spot_layout = build_tower_spot_layout(
        root,
        files,
    )
    spot_assignments = spot_layout.get(
        "assignments",
        {},
    )
    warnings.extend(
        spot_layout.get(
            "warnings",
            [],
        )
    )

    for path in files:
        relative_path = str(
            path.relative_to(root)
        )

        assignment = dict(
            spot_assignments.get(
                str(path.resolve()),
                {
                    "spot_id": "UNASSIGNED-ROOT",
                    "spot_name": "ROOT_LEVEL_FILES",
                    "spot_folder": ".",
                    "source_relative_path": (
                        relative_path
                    ),
                    "is_root_file": True,
                },
            )
        )

        result = load_gprs_dump_file(path)

        result["spot_id"] = assignment[
            "spot_id"
        ]
        result["spot_name"] = assignment[
            "spot_name"
        ]
        result["spot_folder"] = assignment[
            "spot_folder"
        ]
        result["source_relative_path"] = (
            assignment[
                "source_relative_path"
            ]
        )

        result_metadata = dict(
            result.get(
                "metadata",
                {},
            )
            or {}
        )
        result_metadata.update(
            {
                "spot_id": assignment[
                    "spot_id"
                ],
                "spot_name": assignment[
                    "spot_name"
                ],
                "spot_folder": assignment[
                    "spot_folder"
                ],
                "source_relative_path": (
                    assignment[
                        "source_relative_path"
                    ]
                ),
            }
        )
        result["metadata"] = result_metadata

        results.append(result)

        rejected = result.get("rejected_rows")
        if isinstance(rejected, pd.DataFrame) and not rejected.empty:
            reject_frames.append(rejected)

        if result.get("ok"):
            frame = result.get("df")

            if (
                isinstance(frame, pd.DataFrame)
                and not frame.empty
            ):
                frame = frame.copy()

                frame["source_relative_path"] = (
                    assignment[
                        "source_relative_path"
                    ]
                )
                frame["spot_id"] = assignment[
                    "spot_id"
                ]
                frame["spot_name"] = assignment[
                    "spot_name"
                ]
                frame["spot_folder"] = assignment[
                    "spot_folder"
                ]

                result["df"] = frame
                frames.append(frame)
        else:
            for item in result.get("errors", []):
                errors.append(f"{path.name}: {item}")

        for item in result.get("warnings", []):
            warnings.append(f"{path.name}: {item}")

        metadata = result.get("metadata", {}) or {}
        summary_rows.append(
            {
                "source_file": str(path),
                "source_relative_path": assignment[
                    "source_relative_path"
                ],
                "spot_id": assignment["spot_id"],
                "spot_name": assignment["spot_name"],
                "spot_folder": assignment[
                    "spot_folder"
                ],
                "file_name": path.name,
                "status": result.get(
                    "data_status",
                    (
                        STATUS_LOADED
                        if result.get("ok")
                        else STATUS_FAILED
                    ),
                ),
                "source_format": result.get("source_format", ""),
                "operator": metadata.get("operator", ""),
                "searched_cell_id": metadata.get("searched_cell_id", ""),
                "requested_start": metadata.get("requested_start", ""),
                "requested_end": metadata.get("requested_end", ""),
                "header_row": metadata.get("header_row", ""),
                "records": metadata.get("records", 0),
                "warning_count": len(result.get("warnings", [])),
                "error_count": len(result.get("errors", [])),
            }
        )

    combined = (
        pd.concat(frames, ignore_index=True, sort=False)
        if frames
        else pd.DataFrame(columns=NORMALIZED_COLUMNS)
    )

    duplicate_columns = [
        column
        for column in NORMALIZED_COLUMNS
        if column not in {
            "source_file",
            "source_relative_path",
            "spot_id",
            "spot_name",
            "spot_folder",
            "source_row_number",
        }
    ]
    exact_duplicates = (
        int(combined.duplicated(subset=duplicate_columns).sum())
        if not combined.empty
        else 0
    )

    if exact_duplicates:
        warnings.append(
            f"Combined data contains {exact_duplicates} exact duplicate rows; "
            "raw evidence preserved and rows not removed."
        )

    operators = sorted(
        value
        for value in combined.get(
            "operator", pd.Series(dtype="string")
        ).dropna().astype(str).unique()
        if value
    )
    cell_ids = sorted(
        value
        for value in combined.get(
            "searched_cell_id", pd.Series(dtype="string")
        ).dropna().astype(str).unique()
        if value
    )

    spot_summary = pd.DataFrame(
        spot_layout.get(
            "spot_summary",
            [],
        )
    )

    files_loaded_count = sum(
        str(
            result.get(
                "data_status",
                "",
            )
        ).upper()
        == STATUS_LOADED
        for result in results
    )

    files_empty_no_data = sum(
        str(
            result.get(
                "data_status",
                "",
            )
        ).upper()
        == STATUS_EMPTY_NO_DATA
        for result in results
    )

    files_failed_count = sum(
        str(
            result.get(
                "data_status",
                "",
            )
        ).upper()
        == STATUS_FAILED
        for result in results
    )

    files_processed_count = (
        files_loaded_count
        + files_empty_no_data
    )

    metadata = {
        "input_folder": str(root),
        "files_found": len(files),
        "files_loaded": files_loaded_count,
        "files_empty_no_data": files_empty_no_data,
        "files_processed_count": files_processed_count,
        "files_failed": files_failed_count,
        "records": len(combined),
        "exact_duplicate_rows": exact_duplicates,
        "supported_format": FORMAT_AIRTEL_GPRS_SESSION,
        "input_mode": spot_layout.get(
            "input_mode",
            "LEGACY_ROOT_FILES",
        ),
        "spot_count": int(
            spot_layout.get(
                "spot_count",
                0,
            )
        ),
        "spot_names": list(
            spot_layout.get(
                "spot_names",
                [],
            )
        ),
        "root_level_file_count": int(
            spot_layout.get(
                "root_level_file_count",
                0,
            )
        ),
        "rejected_rows": int(sum(len(item) for item in reject_frames)),
    }

    return {
        "ok": (
            files_processed_count > 0
            and files_failed_count == 0
        ),
        "df": combined,
        "files": [str(path) for path in files],
        "file_results": results,
        "file_summary": pd.DataFrame(summary_rows),
        "spot_summary": spot_summary,
        "operators": operators,
        "cell_ids": cell_ids,
        "metadata": metadata,
        "rejected_rows": (
            pd.concat(reject_frames, ignore_index=True)
            if reject_frames
            else empty_reject_ledger()
        ),
        "warnings": warnings,
        "errors": errors,
    }
