"""Folder-based loader for Jio Tower IPDR/NAT dumps.

Phase-6A intentionally supports only the verified Jio ``CELL ID_IPDRNAT``
format. Unknown formats are rejected explicitly instead of being guessed.
Raw rows are never silently deduplicated; duplicate status is added as a flag.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import pandas as pd

from modules.loader.telecom_identifiers import canonical_ip, normalize_imei, normalize_imsi, normalize_subscriber
from modules.loader.evidence_csv import (
    empty_reject_ledger,
    quarantine_dataframe_rows,
    read_csv_with_quarantine,
)
from modules.loader.tower_spot_layout import build_tower_spot_layout


FORMAT_JIO_TOWER_IPDR_NAT = "JIO_TOWER_IPDR_NAT"
SUPPORTED_SUFFIXES = {".csv", ".txt"}

NORMALIZED_COLUMNS = [
    "record_type",
    "source_format",
    "operator",
    "subscriber_number_raw",
    "subscriber_number",
    "identifier_type",
    "user_id",
    "source_ip_raw",
    "source_ip",
    "source_ip_version",
    "source_port",
    "translated_ip_raw",
    "translated_ip",
    "translated_ip_version",
    "translated_port",
    "destination_ip_raw",
    "destination_ip",
    "destination_ip_version",
    "destination_port",
    "allocation_type",
    "allocation_start",
    "allocation_end",
    "allocation_duration_seconds",
    "allocation_time_valid",
    "allocation_key",
    "allocation_volume_key",
    "imei_raw",
    "imei",
    "imsi_raw",
    "imsi",
    "pgw_ip_raw",
    "pgw_ip",
    "pgw_ip_version",
    "apn",
    "searched_cell_id",
    "first_cell_id",
    "last_cell_id",
    "first_cell_matches_searched",
    "last_cell_matches_searched",
    "cell_transition_type",
    "event_time",
    "event_duration_seconds",
    "event_duration_valid",
    "event_duration_negative",
    "event_zero_duration",
    "event_within_allocation",
    "uplink_volume",
    "downlink_volume",
    "total_volume",
    "volume_fields_present",
    "roaming_indicator",
    "roaming_circle",
    "sim_type",
    "exact_duplicate_flag",
    "source_file",
    "source_relative_path",
    "spot_id",
    "spot_name",
    "spot_folder",
    "source_row_number",
]

COLUMN_MAP = {
    "landline/msisdn/mdn/leased circuit id for internet access": "subscriber_number_raw",
    "user id for internet access based on authentication": "user_id",
    "source ip address": "source_ip",
    "source port": "source_port",
    "translated ip address": "translated_ip",
    "translated port": "translated_port",
    "destination ip address": "destination_ip",
    "destination port": "destination_port",
    "static/dynamic ip address allocation": "allocation_type",
    "ist start time of public ip address allocation (hh:mm:ss)": "allocation_start_time",
    "ist end time of public ip address allocation (hh:mm:ss)": "allocation_end_time",
    "start date of public ip address allocation (dd/mm/yyyy)": "allocation_start_date",
    "end date of public ip address allocation (dd/mm/yyyy)": "allocation_end_date",
    "source mac-id address/other device identification number": "imei",
    "imsi": "imsi",
    "pgw ip address": "pgw_ip",
    "access point name": "apn",
    "first cell id": "first_cell_id",
    "last cell id": "last_cell_id",
    "time1 (dd/mm/yyyy hh:mm:ss)": "event_time",
    "session duration (seconds)": "event_duration_seconds",
    "data volume up link": "uplink_volume",
    "data volume down link": "downlink_volume",
    "roaming circle indicator": "roaming_indicator",
    "roaming circle": "roaming_circle",
    "sim type": "sim_type",
}

REQUIRED_NORMALIZED_COLUMNS = {
    "subscriber_number_raw",
    "source_ip",
    "destination_ip",
    "allocation_start_time",
    "allocation_end_time",
    "allocation_start_date",
    "allocation_end_date",
    "imei",
    "imsi",
    "first_cell_id",
    "event_time",
}


def _clean_header(value: Any) -> str:
    text = str(value).replace("\ufeff", "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _read_columns(path: Path) -> tuple[list[str], str]:
    encodings = ("utf-8-sig", "utf-8", "cp1252", "latin1")
    last_error: Exception | None = None

    for encoding in encodings:
        try:
            preview = pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
                nrows=0,
                encoding=encoding,
            )
            return list(preview.columns), encoding
        except UnicodeError as error:
            last_error = error
        except Exception as error:
            last_error = error
            break

    raise ValueError(f"Header read nahi ho saka: {last_error}")


def _filename_metadata(path: Path) -> dict[str, Any]:
    name = unquote(path.name)
    match = re.search(
        r"CELL\s*ID_IPDRNAT_(?P<cell>[^_]+)_"
        r"(?P<start>\d{14})_(?P<end>\d{14})_(?P<part>\d+)",
        name,
        flags=re.IGNORECASE,
    )

    metadata: dict[str, Any] = {
        "operator": "Jio",
        "searched_cell_id": "",
        "requested_start": "",
        "requested_end": "",
        "file_part": "",
    }

    if not match:
        return metadata

    metadata["searched_cell_id"] = match.group("cell").strip()
    metadata["requested_start"] = pd.to_datetime(
        match.group("start"),
        format="%Y%m%d%H%M%S",
        errors="coerce",
    )
    metadata["requested_end"] = pd.to_datetime(
        match.group("end"),
        format="%Y%m%d%H%M%S",
        errors="coerce",
    )
    metadata["file_part"] = match.group("part")
    return metadata


def detect_tower_ipdr_format(path: str | Path) -> dict[str, Any]:
    file_path = Path(path).expanduser().resolve()

    if not file_path.is_file():
        raise FileNotFoundError(file_path)

    columns, encoding = _read_columns(file_path)
    cleaned = {_clean_header(column) for column in columns}
    mapped = {COLUMN_MAP[column] for column in cleaned if column in COLUMN_MAP}
    metadata = _filename_metadata(file_path)

    source_format = ""

    if REQUIRED_NORMALIZED_COLUMNS.issubset(mapped):
        source_format = FORMAT_JIO_TOWER_IPDR_NAT

    return {
        "source_format": source_format,
        "header_row": 0,
        "encoding": encoding,
        "metadata": metadata,
        "columns": columns,
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


def _normalize_subscriber(value: Any) -> tuple[str, str]:
    digits = re.sub(r"\D+", "", str(value or ""))

    if re.fullmatch(r"91[6-9]\d{9}", digits):
        return digits[-10:], "MSISDN_WITH_COUNTRY_CODE"

    if re.fullmatch(r"[6-9]\d{9}", digits):
        return digits, "MSISDN"

    if digits:
        return digits, "NON_STANDARD_SUBSCRIBER_ID"

    return "", "INVALID_OR_MISSING"


def _ip_version(value: Any) -> str:
    text = str(value or "").strip()

    if not text:
        return ""

    try:
        version = ipaddress.ip_address(text).version
        return f"IPv{version}"
    except ValueError:
        return "INVALID"


def _parse_datetime(date_values: pd.Series, time_values: pd.Series) -> pd.Series:
    combined = (
        date_values.fillna("").astype(str).str.strip()
        + " "
        + time_values.fillna("").astype(str).str.strip()
    ).str.strip()

    parsed = pd.to_datetime(
        combined,
        format="%Y/%m/%d %H:%M:%S",
        errors="coerce",
    )
    missing = parsed.isna() & combined.ne("")

    if missing.any():
        parsed.loc[missing] = pd.to_datetime(
            combined.loc[missing],
            dayfirst=True,
            errors="coerce",
        )

    return parsed


def _parse_event_time(values: pd.Series) -> pd.Series:
    text = values.fillna("").astype(str).str.strip()
    parsed = pd.to_datetime(
        text,
        format="%Y/%m/%d %H:%M:%S",
        errors="coerce",
    )
    missing = parsed.isna() & text.ne("")

    if missing.any():
        parsed.loc[missing] = pd.to_datetime(
            text.loc[missing],
            dayfirst=True,
            errors="coerce",
        )

    return parsed


def _stable_key(dataframe: pd.DataFrame, columns: list[str]) -> pd.Series:
    work = pd.DataFrame(index=dataframe.index)

    for column in columns:
        values = dataframe[column] if column in dataframe.columns else ""

        if isinstance(values, pd.Series):
            if pd.api.types.is_datetime64_any_dtype(values):
                values = values.dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")
            else:
                values = values.fillna("").astype(str).str.strip().str.lower()
        else:
            values = pd.Series(str(values), index=dataframe.index)

        work[column] = values

    joined = work.astype(str).agg("|".join, axis=1)
    return joined.map(
        lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    )


def _cell_transition(first: str, last: str, searched: str) -> str:
    first = str(first or "").strip()
    last = str(last or "").strip()
    searched = str(searched or "").strip()

    if not first and not last:
        return "CELL_DATA_MISSING"
    if first == searched and last == searched:
        return "SAME_SEARCHED_CELL"
    if first == searched and last and last != searched:
        return "STARTED_AT_SEARCHED_CELL_LAST_CELL_CHANGED"
    if first and first != searched:
        return "FIRST_CELL_DIFFERS_FROM_SEARCHED"
    return "UNCLASSIFIED"


def _normalize_jio(
    raw: pd.DataFrame,
    *,
    path: Path,
    metadata: dict[str, Any],
) -> pd.DataFrame:
    raw = raw.copy()
    raw.columns = [_clean_header(column) for column in raw.columns]
    raw = raw.rename(
        columns={
            column: COLUMN_MAP[column]
            for column in raw.columns
            if column in COLUMN_MAP
        }
    )
    if "_source_row_number" not in raw.columns:
        raw["_source_row_number"] = pd.RangeIndex(
            start=2,
            stop=2 + len(raw),
        )

    subscriber_raw = _string_series(raw, "subscriber_number_raw")
    data_mask = subscriber_raw.str.contains(r"\d", regex=True, na=False)
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
        "user_id",
        "source_ip",
        "translated_ip",
        "destination_ip",
        "allocation_type",
        "imei",
        "imsi",
        "pgw_ip",
        "apn",
        "first_cell_id",
        "last_cell_id",
        "roaming_indicator",
        "roaming_circle",
        "sim_type",
    ):
        dataframe[column] = _string_series(raw, column)

    normalized = dataframe["subscriber_number_raw"].map(normalize_subscriber)
    dataframe["subscriber_number"] = normalized.map(lambda item: item[0])
    dataframe["identifier_type"] = normalized.map(lambda item: item[1])
    for column in ("source_ip", "translated_ip", "destination_ip", "pgw_ip"):
        dataframe[f"{column}_raw"] = dataframe[column].copy()
        dataframe[column] = dataframe[column].map(canonical_ip)
    dataframe["imei_raw"] = dataframe["imei"].copy()
    dataframe["imsi_raw"] = dataframe["imsi"].copy()
    dataframe["imei"] = dataframe["imei"].map(normalize_imei)
    dataframe["imsi"] = dataframe["imsi"].map(normalize_imsi)

    for column in (
        "source_port",
        "translated_port",
        "destination_port",
        "event_duration_seconds",
        "uplink_volume",
        "downlink_volume",
    ):
        dataframe[column] = pd.to_numeric(
            raw[column] if column in raw.columns else pd.Series(index=raw.index),
            errors="coerce",
        )

    for column in ("source_port", "translated_port", "destination_port"):
        dataframe[column] = dataframe[column].round().astype("Int64")

    dataframe["allocation_start"] = _parse_datetime(
        _string_series(raw, "allocation_start_date"),
        _string_series(raw, "allocation_start_time"),
    )
    dataframe["allocation_end"] = _parse_datetime(
        _string_series(raw, "allocation_end_date"),
        _string_series(raw, "allocation_end_time"),
    )
    dataframe["event_time"] = _parse_event_time(
        _string_series(raw, "event_time")
    )

    allocation_duration = (
        dataframe["allocation_end"] - dataframe["allocation_start"]
    ).dt.total_seconds()
    dataframe["allocation_duration_seconds"] = allocation_duration
    dataframe["allocation_time_valid"] = (
        dataframe["allocation_start"].notna()
        & dataframe["allocation_end"].notna()
        & allocation_duration.ge(0)
    )

    event_duration = dataframe["event_duration_seconds"]
    dataframe["event_duration_valid"] = event_duration.notna() & event_duration.ge(0)
    dataframe["event_duration_negative"] = event_duration.lt(0).fillna(False)
    dataframe["event_zero_duration"] = event_duration.eq(0).fillna(False)
    dataframe["event_within_allocation"] = (
        dataframe["event_time"].notna()
        & dataframe["allocation_start"].notna()
        & dataframe["allocation_end"].notna()
        & dataframe["event_time"].ge(dataframe["allocation_start"])
        & dataframe["event_time"].le(dataframe["allocation_end"])
    )

    dataframe["volume_fields_present"] = (
        dataframe["uplink_volume"].notna()
        & dataframe["downlink_volume"].notna()
    )
    dataframe["total_volume"] = (
        dataframe["uplink_volume"] + dataframe["downlink_volume"]
    )

    for column in ("source_ip", "translated_ip", "destination_ip", "pgw_ip"):
        dataframe[f"{column}_version"] = dataframe[column].map(_ip_version)

    searched_cell = str(metadata.get("searched_cell_id", "")).strip()

    if not searched_cell:
        first_cells = dataframe["first_cell_id"].replace("", pd.NA).dropna().unique()
        if len(first_cells) == 1:
            searched_cell = str(first_cells[0])

    dataframe["searched_cell_id"] = searched_cell
    dataframe["first_cell_matches_searched"] = (
        dataframe["first_cell_id"].eq(dataframe["searched_cell_id"])
        & dataframe["searched_cell_id"].ne("")
    )
    dataframe["last_cell_matches_searched"] = (
        dataframe["last_cell_id"].eq(dataframe["searched_cell_id"])
        & dataframe["searched_cell_id"].ne("")
    )
    dataframe["cell_transition_type"] = [
        _cell_transition(first, last, searched)
        for first, last, searched in zip(
            dataframe["first_cell_id"],
            dataframe["last_cell_id"],
            dataframe["searched_cell_id"],
        )
    ]

    dataframe["allocation_key"] = _stable_key(
        dataframe,
        [
            "subscriber_number",
            "source_ip",
            "allocation_start",
            "allocation_end",
            "imei",
            "imsi",
            "apn",
            "searched_cell_id",
        ],
    )
    dataframe["allocation_volume_key"] = _stable_key(
        dataframe,
        [
            "allocation_key",
            "uplink_volume",
            "downlink_volume",
        ],
    )

    dataframe.insert(0, "operator", "Jio")
    dataframe.insert(0, "source_format", FORMAT_JIO_TOWER_IPDR_NAT)
    dataframe.insert(0, "record_type", "IPDR_NAT_EVENT")
    dataframe["source_file"] = str(path)
    dataframe["source_row_number"] = pd.to_numeric(
        raw["_source_row_number"],
        errors="coerce",
    ).astype("Int64")
    dataframe["exact_duplicate_flag"] = False

    for column in NORMALIZED_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = pd.NA

    dataframe = dataframe[NORMALIZED_COLUMNS].reset_index(drop=True)
    dataframe.attrs["metadata"] = {
        **metadata,
        "source_file": str(path),
        "source_format": FORMAT_JIO_TOWER_IPDR_NAT,
        "header_row": 1,
        "discarded_non_data_rows": discarded_non_data_rows,
        "records": len(dataframe),
    }
    dataframe.attrs["rejected_rows"] = non_data_rejects.reset_index(drop=True)
    return dataframe


def load_tower_ipdr_file(path: str | Path) -> dict[str, Any]:
    file_path = Path(path).expanduser().resolve()
    warnings: list[str] = []
    errors: list[str] = []

    try:
        detection = detect_tower_ipdr_format(file_path)
    except Exception as error:
        return {
            "ok": False,
            "df": pd.DataFrame(columns=NORMALIZED_COLUMNS),
            "file": str(file_path),
            "source_format": "UNKNOWN",
            "metadata": {},
            "warnings": warnings,
            "errors": [f"Format detection failed: {type(error).__name__}: {error}"],
        }

    if detection["source_format"] != FORMAT_JIO_TOWER_IPDR_NAT:
        return {
            "ok": False,
            "df": pd.DataFrame(columns=NORMALIZED_COLUMNS),
            "file": str(file_path),
            "source_format": detection["source_format"] or "UNKNOWN",
            "metadata": detection["metadata"],
            "warnings": warnings,
            "errors": ["Unsupported Tower IPDR format. Current parser: Jio CELL ID_IPDRNAT."],
        }

    try:
        raw, parser_rejects, ingestion_metadata = read_csv_with_quarantine(
            file_path,
            skiprows=0,
            sep=",",
            encoding=detection["encoding"],
        )
        dataframe = _normalize_jio(
            raw,
            path=file_path,
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
            "df": pd.DataFrame(columns=NORMALIZED_COLUMNS),
            "file": str(file_path),
            "source_format": detection["source_format"],
            "metadata": detection["metadata"],
            "warnings": warnings,
            "errors": [f"Load failed: {type(error).__name__}: {error}"],
        }

    metadata = dict(dataframe.attrs.get("metadata", {}))
    metadata["operator"] = "Jio"
    metadata["unique_subscribers"] = int(
        dataframe["subscriber_number"].replace("", pd.NA).nunique()
    )
    metadata["unique_imei"] = int(dataframe["imei"].replace("", pd.NA).nunique())
    metadata["unique_imsi"] = int(dataframe["imsi"].replace("", pd.NA).nunique())
    metadata["allocation_count"] = int(dataframe["allocation_key"].nunique())
    metadata["allocation_volume_records"] = int(
        dataframe["allocation_volume_key"].nunique()
    )
    metadata["event_time_min"] = dataframe["event_time"].min()
    metadata["event_time_max"] = dataframe["event_time"].max()
    metadata["allocation_start_min"] = dataframe["allocation_start"].min()
    metadata["allocation_end_max"] = dataframe["allocation_end"].max()
    metadata["negative_duration_rows"] = int(
        dataframe["event_duration_negative"].fillna(False).sum()
    )
    metadata["zero_duration_rows"] = int(
        dataframe["event_zero_duration"].fillna(False).sum()
    )
    metadata["rejected_rows"] = int(len(rejected_rows))
    metadata["adjusted_rows"] = int(ingestion_metadata.get("adjusted_rows", 0))

    if dataframe.empty:
        errors.append("No valid IPDR/NAT event row found.")

    if not dataframe["first_cell_matches_searched"].all():
        warnings.append(
            "Some First Cell IDs do not match the searched Cell ID parsed from filename."
        )

    if dataframe["event_duration_negative"].any():
        warnings.append(
            "Negative event-duration rows preserved and flagged; raw values were not changed."
        )

    return {
        "ok": bool(not dataframe.empty and not errors),
        "df": dataframe,
        "file": str(file_path),
        "source_format": detection["source_format"],
        "metadata": metadata,
        "warnings": warnings,
        "errors": errors,
    }


def _candidate_files(directory: Path, recursive: bool) -> list[Path]:
    iterator = directory.rglob("*") if recursive else directory.glob("*")
    return sorted(
        path
        for path in iterator
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )


def load_tower_ipdr_case(
    directory: str | Path,
    *,
    recursive: bool = True,
) -> dict[str, Any]:
    input_folder = Path(directory).expanduser().resolve()

    if not input_folder.is_dir():
        return {
            "ok": False,
            "df": pd.DataFrame(columns=NORMALIZED_COLUMNS),
            "file_results": [],
            "file_summary": pd.DataFrame(),
            "spot_summary": pd.DataFrame(),
            "operators": [],
            "cell_ids": [],
            "metadata": {"input_folder": str(input_folder)},
            "warnings": [],
            "errors": [f"Input folder not found: {input_folder}"],
        }

    files = _candidate_files(
        input_folder,
        recursive,
    )

    spot_layout = build_tower_spot_layout(
        input_folder,
        files,
    )
    spot_assignments = spot_layout.get(
        "assignments",
        {},
    )

    results: list[dict[str, Any]] = []

    for path in files:
        relative_path = str(
            path.relative_to(input_folder)
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

        result = load_tower_ipdr_file(path)

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

        frame = result.get("df")

        if isinstance(frame, pd.DataFrame):
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

        results.append(result)

    successful = [
        result
        for result in results
        if result.get("ok")
    ]
    warnings = list(dict.fromkeys(
        message
        for result in results
        for message in result.get("warnings", [])
    ))
    errors = list(dict.fromkeys(
        f"{Path(result.get('file', '')).name}: {message}"
        for result in results
        if not result.get("ok")
        for message in result.get("errors", [])
    ))

    warnings = list(
        dict.fromkeys(
            [
                *warnings,
                *spot_layout.get(
                    "warnings",
                    [],
                ),
            ]
        )
    )

    reject_frames = [
        result["rejected_rows"]
        for result in results
        if isinstance(result.get("rejected_rows"), pd.DataFrame)
        and not result["rejected_rows"].empty
    ]
    frames = [result["df"] for result in successful]
    dataframe = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=NORMALIZED_COLUMNS)
    )

    if not dataframe.empty:
        duplicate_columns = [
            column
            for column in NORMALIZED_COLUMNS
            if column not in {
                "exact_duplicate_flag",
                "source_file",
                "source_relative_path",
                "spot_id",
                "spot_name",
                "spot_folder",
                "source_row_number",
            }
        ]
        duplicate_mask = dataframe.duplicated(
            subset=duplicate_columns,
            keep=False,
        )
        dataframe["exact_duplicate_flag"] = duplicate_mask

        if duplicate_mask.any():
            warnings.append(
                f"{int(duplicate_mask.sum())} exact duplicate event rows were flagged and preserved."
            )

    file_rows: list[dict[str, Any]] = []

    for result in results:
        metadata = result.get("metadata", {}) or {}
        file_rows.append(
            {
                "file_name": Path(result.get("file", "")).name,
                "file_path": result.get("file", ""),
                "source_relative_path": result.get(
                    "source_relative_path",
                    "",
                ),
                "spot_id": result.get(
                    "spot_id",
                    "",
                ),
                "spot_name": result.get(
                    "spot_name",
                    "",
                ),
                "spot_folder": result.get(
                    "spot_folder",
                    "",
                ),
                "status": "LOADED" if result.get("ok") else "FAILED",
                "source_format": result.get("source_format", ""),
                "operator": metadata.get("operator", ""),
                "searched_cell_id": metadata.get("searched_cell_id", ""),
                "requested_start": metadata.get("requested_start", ""),
                "requested_end": metadata.get("requested_end", ""),
                "file_part": metadata.get("file_part", ""),
                "records": metadata.get("records", 0),
                "unique_subscribers": metadata.get("unique_subscribers", 0),
                "allocation_count": metadata.get("allocation_count", 0),
                "allocation_volume_records": metadata.get("allocation_volume_records", 0),
                "event_time_min": metadata.get("event_time_min", ""),
                "event_time_max": metadata.get("event_time_max", ""),
                "warnings": " | ".join(result.get("warnings", [])),
                "errors": " | ".join(result.get("errors", [])),
            }
        )

    file_summary = pd.DataFrame(file_rows)
    spot_summary = pd.DataFrame(
        spot_layout.get(
            "spot_summary",
            [],
        )
    )

    cell_ids = sorted(
        value
        for value in dataframe.get("searched_cell_id", pd.Series(dtype=str))
        .fillna("")
        .astype(str)
        .str.strip()
        .unique()
        if value
    )
    operators = sorted(
        value
        for value in dataframe.get("operator", pd.Series(dtype=str))
        .fillna("")
        .astype(str)
        .str.strip()
        .unique()
        if value
    )

    metadata = {
        "input_folder": str(input_folder),
        "files_found": len(files),
        "files_loaded": len(successful),
        "files_failed": len(results) - len(successful),
        "records": len(dataframe),
        "unique_subscribers": int(
            dataframe.get("subscriber_number", pd.Series(dtype=str))
            .replace("", pd.NA)
            .nunique()
        ),
        "unique_cells": len(cell_ids),
        "exact_duplicate_rows": int(
            dataframe.get("exact_duplicate_flag", pd.Series(dtype=bool))
            .fillna(False)
            .sum()
        ),
        "raw_rows_preserved": True,
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
        "ok": bool(successful and not dataframe.empty),
        "df": dataframe,
        "file_results": results,
        "file_summary": file_summary,
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
