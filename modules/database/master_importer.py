from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd

from .db_paths import master_duckdb_path
from .cgi_repository import CGI_TABLE, create_cgi_table, normalize_cgi
from .sdr_repository import SDR_TABLE, create_sdr_table, normalize_mobile
from .cgi_master_reader import read_cgi_master_file, SUPPORTED_CGI_SUFFIXES


SUPPORTED_IMPORT_SUFFIXES = {".csv", ".xlsx", ".xls", ".xlsb", ".txt", ".tsv"}


def _clean_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _normalise_column_name(value) -> str:
    text = str(value).strip().lower().replace("\ufeff", "")
    cleaned = "".join(character if character.isalnum() else "_" for character in text)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_")


def _first_existing_column(dataframe: pd.DataFrame, candidates: Iterable[str]):
    normalized_columns = {
        _normalise_column_name(column): column
        for column in dataframe.columns
    }

    for candidate in candidates:
        key = _normalise_column_name(candidate)
        if key in normalized_columns:
            return normalized_columns[key]

    return None


def _detect_header_line(file_path: Path) -> int:
    header_keywords = {
        "mobile",
        "mobile number",
        "msisdn",
        "subscriber",
        "subscriber name",
        "number",
        "phone",
        "cgi",
        "cell",
        "cell id",
        "address",
        "operator",
        "circle",
        "name",
        "caf",
    }

    best_line_number = 0
    best_score = -1

    with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
        for line_number, line in enumerate(handle):
            if line_number > 100:
                break

            cleaned = line.strip().lower()
            if not cleaned:
                continue

            delimiter_score = (
                cleaned.count("|")
                + cleaned.count("\t")
                + cleaned.count(",")
                + cleaned.count(";")
            )
            keyword_score = sum(1 for keyword in header_keywords if keyword in cleaned)
            score = keyword_score * 10 + delimiter_score

            if score > best_score:
                best_score = score
                best_line_number = line_number

    return best_line_number


def _detect_delimiter(file_path: Path, header_line: int):
    with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
        lines = handle.readlines()

    if header_line >= len(lines):
        return None

    header = lines[header_line]
    candidates = ["|", "\t", ",", ";"]
    counts = {delimiter: header.count(delimiter) for delimiter in candidates}
    best_delimiter, best_count = max(counts.items(), key=lambda item: item[1])

    return best_delimiter if best_count > 0 else None


def _has_known_master_columns(dataframe: pd.DataFrame) -> bool:
    """
    Check whether parsed dataframe has real SDR/CGI header columns.

    Supports common SDR headers and multiple CGI master formats:
    2G, 4G, 5G, operator-wise cell dumps, and GCI-based CGI sheets.
    """
    known_columns = {
        # SDR
        "mobile_number",
        "mobile",
        "msisdn",
        "subscriber_number",
        "phone_number",
        "subscriber_name",
        "father_name",
        "caf_number",

        # Simple CGI
        "cgi",
        "cell",
        "cell_id",
        "cellid",
        "cell_global_id",
        "cell_global_identity",
        "ecgi",

        # Your CGI master headers
        "cgi_code_in_order_of_cmcc_mnc_lac_ci",
        "cgi_with_gci_mcc_mnc_tac_gci",
        "cgi_mcc_mnc_cid",
        "ci_to_gci_conversion",

        # CGI supporting columns
        "service_provider",
        "tsp_name",
        "zone_circle",
        "circle_id",
        "site_id",
        "site_name",
        "site_address",
        "land_mark",
        "landmark",
        "state",
        "district",
        "town",
        "mcc_mnc",
        "cid",
        "lac",
        "tac_id_decimal",
        "gnb_id",
        "latitude",
        "longitude",
        "azimuth",
        "azimuth_angle",
        "technology",
    }

    normalized = {_normalise_column_name(column) for column in dataframe.columns}

    return bool(normalized.intersection(known_columns))


def _read_text_table_file(file_path: Path) -> pd.DataFrame:
    """
    Read raw SDR/CGI text files safely.

    It tries detected header line plus nearby lines because many
    telecom TXT files contain metadata lines, blank lines or separators
    before the real header.
    """
    detected_header_line = _detect_header_line(file_path)

    candidate_header_lines = []
    for header_line in [
        detected_header_line,
        detected_header_line - 1,
        detected_header_line + 1,
        detected_header_line - 2,
        detected_header_line + 2,
        0,
    ]:
        if header_line >= 0 and header_line not in candidate_header_lines:
            candidate_header_lines.append(header_line)

    valid_fallback = None
    last_error = None

    for header_line in candidate_header_lines:
        detected_delimiter = _detect_delimiter(file_path, header_line)

        delimiters = []
        if detected_delimiter:
            delimiters.append(detected_delimiter)

        for delimiter in ["|", "\t", ",", ";"]:
            if delimiter not in delimiters:
                delimiters.append(delimiter)

        for delimiter in delimiters:
            try:
                dataframe = pd.read_csv(
                    file_path,
                    dtype=str,
                    header=header_line,
                    sep=delimiter,
                    engine="python",
                    encoding_errors="ignore",
                )
                dataframe = dataframe.dropna(how="all")
                dataframe.columns = [
                    str(column).strip().replace("\ufeff", "")
                    for column in dataframe.columns
                ]

                if dataframe.shape[1] < 2:
                    continue

                if _has_known_master_columns(dataframe):
                    return dataframe

                if valid_fallback is None:
                    valid_fallback = dataframe

            except Exception as exc:
                last_error = exc

    try:
        dataframe = pd.read_fwf(
            file_path,
            dtype=str,
            header=detected_header_line,
            encoding_errors="ignore",
        )
        dataframe = dataframe.dropna(how="all")
        dataframe.columns = [
            str(column).strip().replace("\ufeff", "")
            for column in dataframe.columns
        ]

        if dataframe.shape[1] >= 2 and _has_known_master_columns(dataframe):
            return dataframe

        if valid_fallback is None and dataframe.shape[1] >= 2:
            valid_fallback = dataframe

    except Exception as exc:
        last_error = exc

    if valid_fallback is not None:
        return valid_fallback

    raise ValueError(f"Could not read text master file: {file_path} | {last_error}")


def _read_excel_table_file(file_path: Path) -> pd.DataFrame:
    """
    Read Excel/XLSB master files safely.

    Many CGI master workbooks have blank first sheets, title rows,
    merged headers, or real data on a later sheet. This function scans
    all sheets and multiple possible header rows, then chooses the sheet
    that contains known SDR/CGI columns.
    """
    suffix = file_path.suffix.lower()
    engine = "pyxlsb" if suffix == ".xlsb" else None

    try:
        excel_file = pd.ExcelFile(file_path, engine=engine)
    except ImportError as exc:
        raise ImportError(
            "Reading .xlsb files requires pyxlsb. Install it with: pip install pyxlsb"
        ) from exc

    fallback = None
    last_error = None

    for sheet_name in excel_file.sheet_names:
        for header_row in range(0, 41):
            try:
                dataframe = pd.read_excel(
                    file_path,
                    sheet_name=sheet_name,
                    header=header_row,
                    dtype=str,
                    engine=engine,
                )

                dataframe = dataframe.dropna(how="all")
                dataframe = dataframe.dropna(axis=1, how="all")
                dataframe.columns = [
                    str(column).strip().replace("\ufeff", "")
                    for column in dataframe.columns
                ]

                if dataframe.empty or dataframe.shape[1] < 2:
                    continue

                if _has_known_master_columns(dataframe):
                    return dataframe

                if fallback is None:
                    fallback = dataframe

            except Exception as exc:
                last_error = exc

    if fallback is not None:
        return fallback

    raise ValueError(f"Could not read usable Excel sheet from: {file_path} | {last_error}")


def _read_input_file(file_path) -> pd.DataFrame:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in {".csv", ".txt", ".tsv"}:
        return _read_text_table_file(path)

    if suffix in {".xlsx", ".xls", ".xlsb"}:
        return _read_excel_table_file(path)

    raise ValueError(f"Unsupported master import file type: {path}")


def _collect_existing_columns(dataframe: pd.DataFrame, candidates: Iterable[str]):
    found_columns = []
    for candidate in candidates:
        column = _first_existing_column(dataframe, [candidate])
        if column is not None and column not in found_columns:
            found_columns.append(column)
    return found_columns


def _prepare_cgi_dataframe(raw: pd.DataFrame, source_file: str) -> pd.DataFrame:
    """
    Prepare CGI master dataframe.

    Important:
    Some master sheets contain multiple valid tower identifiers in the same row.
    Example:
    - CGI
    - CGI (Code in Order of CMCC/MNC/LAC/CI)
    - CGI (MCC-MNC-CID)
    - CGI with GCI (MCC-MNC-TAC-GCI)
    - CI to GCI Conversion
    - Cell ID
    - CID

    We store each valid identifier as a lookup key with the same tower details.
    This improves matching across CDR, Tower CDR, GPRS and IPDR formats.
    """
    cgi_key_columns = _collect_existing_columns(
        raw,
        [
            "cgi",
            "CGI",
            "CGI (Code in Order of CMCC/MNC/LAC/CI)",
            "CGI with GCI (MCC-MNC-TAC-GCI)",
            "CGI (MCC-MNC-CID)",
            "CI to GCI Conversion",
            "cgi_id",
            "cgi_number",
            "cgi_cell_id",
            "ecgi",
            "cgi_ecgi",
            "cell_global_id",
            "cell_global_identity",
            "cell_global_id_hex",
            "cell_global_identity_hex",
            "Cell Global Id",
            "Cell Global ID",
            "Cell Global Identity",
            "cell",
            "cell_id",
            "Cell ID",
            "cellid",
            "CID",
            "cid",
        ],
    )

    if not cgi_key_columns:
        raise ValueError(f"CGI/Cell ID column not found. Columns found: {list(raw.columns)}")

    mapping = {
        "operator": [
            "operator",
            "tsp",
            "TSP",
            "tsp_name",
            "TSP NAME",
            "TSP Name",
            "service_provider",
            "Service provider",
        ],
        "circle": [
            "circle",
            "Circle",
            "zone_circle",
            "Zone/ Circle",
            "circle_id",
            "Circle ID",
            "lsa",
        ],
        "state": [
            "state",
            "State",
        ],
        "district": [
            "district",
            "District",
            "dist",
        ],
        "town": [
            "town",
            "Town",
            "city",
        ],
        "site_name": [
            "site_name",
            "Site Name",
            "seg_name",
            "Seg Name",
        ],
        "police_station": [
            "police_station",
            "Police Station",
            "ps",
            "thana",
        ],
        "address": [
            "address",
            "Address",
            "site_address",
            "Site Address",
            "tower_address",
            "Tower Address",
            "location",
            "Location",
        ],
        "landmark": [
            "landmark",
            "land_mark",
            "Land Mark",
            "land mark",
        ],
        "latitude": [
            "latitude",
            "Latitude",
            "lat",
        ],
        "longitude": [
            "longitude",
            "Longitude",
            "long",
            "lng",
        ],
        "azimuth": [
            "azimuth",
            "Azimuth",
            "azimuth_angle",
            "Azimuth angle",
            "Azimuth Angle",
        ],
        "technology": [
            "technology",
            "Technology",
            "tech",
        ],
        "status": [
            "status",
            "Status",
            "Status (In-serv.ice/De-commissioned)",
            "Status (In-service/De-commissioned)",
        ],
        "status_change_date": [
            "status_change_date",
            "Status Change Date",
        ],
        "mcc_mnc": [
            "mcc_mnc",
            "MCC-MNC",
            "mcc mnc",
        ],
        "lac": [
            "lac",
            "LAC",
        ],
        "cid": [
            "cid",
            "CID",
        ],
        "tac_id": [
            "tac_id",
            "TAC ID",
            "TAC ID (Decimal)",
        ],
        "site_id": [
            "site_id",
            "Site ID",
        ],
        "gnb_id": [
            "gnb_id",
            "GNB ID",
        ],
        "cell_id": [
            "cell_id",
            "Cell ID",
        ],
    }

    base = pd.DataFrame(index=raw.index)

    for target_column, candidates in mapping.items():
        source_column = _first_existing_column(raw, candidates)
        base[target_column] = raw[source_column].map(_clean_text) if source_column else ""

    base["latitude"] = pd.to_numeric(base["latitude"], errors="coerce")
    base["longitude"] = pd.to_numeric(base["longitude"], errors="coerce")
    base["source_file"] = source_file

    prepared_parts = []

    for cgi_column in cgi_key_columns:
        part = base.copy()
        part["cgi"] = raw[cgi_column].map(normalize_cgi)
        part = part[part["cgi"].astype(str).str.strip().ne("")].copy()

        if part.empty:
            continue

        part["cgi_source_column"] = str(cgi_column)
        prepared_parts.append(part)

    if not prepared_parts:
        return pd.DataFrame(
            columns=[
                "cgi",
                "operator",
                "circle",
                "state",
                "district",
                "police_station",
                "address",
                "latitude",
                "longitude",
                "source_file",
                "site_name",
                "town",
                "landmark",
                "azimuth",
                "technology",
                "status",
                "status_change_date",
                "mcc_mnc",
                "lac",
                "cid",
                "tac_id",
                "site_id",
                "gnb_id",
                "cell_id",
            ]
        )

    output = pd.concat(prepared_parts, ignore_index=True)
    output = output.drop_duplicates(subset=["cgi"], keep="last")

    return output[
        [
            "cgi",
            "operator",
            "circle",
            "state",
            "district",
            "police_station",
            "address",
            "latitude",
            "longitude",
            "source_file",
            "site_name",
            "town",
            "landmark",
            "azimuth",
            "technology",
            "status",
            "status_change_date",
            "mcc_mnc",
            "lac",
            "cid",
            "tac_id",
            "site_id",
            "gnb_id",
            "cell_id",
        ]
    ]


def _prepare_sdr_dataframe(raw: pd.DataFrame, source_file: str) -> pd.DataFrame:
    mobile_col = _first_existing_column(
        raw,
        [
            "mobile_number",
            "mobile",
            "msisdn",
            "phone",
            "phone_number",
            "subscriber_number",
            "subscriber",
            "number",
            "a_party",
            "b_party",
        ],
    )

    if mobile_col is None:
        raise ValueError(f"Mobile/MSISDN column not found. Columns found: {list(raw.columns)}")

    mapping = {
        "subscriber_name": ["subscriber_name", "name", "customer_name", "caf_name"],
        "father_name": ["father_name", "father", "guardian_name"],
        "address": ["address", "subscriber_address", "caf_address"],
        "id_type": ["id_type", "identity_type", "poi_type"],
        "id_number": ["id_number", "identity_number", "poi_number"],
        "operator": ["operator", "tsp", "service_provider"],
        "circle": ["circle", "lsa"],
        "activation_date": ["activation_date", "date_of_activation", "doa"],
        "caf_number": ["caf_number", "caf", "caf_no"],
    }

    output = pd.DataFrame()
    output["mobile_number"] = raw[mobile_col].map(normalize_mobile)

    for target_column, candidates in mapping.items():
        source_column = _first_existing_column(raw, candidates)
        output[target_column] = raw[source_column].map(_clean_text) if source_column else ""

    output["source_file"] = source_file

    output = output[output["mobile_number"].astype(str).str.len().eq(10)].copy()
    output = output.drop_duplicates(subset=["mobile_number"], keep="last")

    return output[
        [
            "mobile_number",
            "subscriber_name",
            "father_name",
            "address",
            "id_type",
            "id_number",
            "operator",
            "circle",
            "activation_date",
            "caf_number",
            "source_file",
        ]
    ]


def _upsert_dataframe(table_name: str, dataframe: pd.DataFrame, key_column: str) -> int:
    if dataframe is None or dataframe.empty:
        return 0

    db_path = master_duckdb_path()

    with duckdb.connect(str(db_path), read_only=False) as connection:
        connection.register("incoming_master_data", dataframe)

        columns = list(dataframe.columns)
        column_csv = ", ".join(columns)
        select_csv = ", ".join([f"incoming_master_data.{column}" for column in columns])

        connection.execute(
            f"""
            DELETE FROM {table_name}
            WHERE {key_column} IN (
                SELECT {key_column}
                FROM incoming_master_data
            )
            """
        )

        connection.execute(
            f"""
            INSERT INTO {table_name} ({column_csv})
            SELECT {select_csv}
            FROM incoming_master_data
            """
        )

    return len(dataframe)


def import_cgi_master_file(file_path) -> int:
    """
    Import CGI master file using smart all-sheet reader.

    Handles:
    - normal CGI header sheets
    - metadata sheets skipped automatically
    - Column1/Column2 Jio dump sheets
    - caret-packed ^ delimiter sheets
    - multiple sheets in one workbook
    """
    create_cgi_table()

    prepared_frames = read_cgi_master_file(file_path)

    total_rows = 0

    for prepared in prepared_frames:
        if prepared is None or prepared.empty:
            continue

        total_rows += _upsert_dataframe(CGI_TABLE, prepared, "cgi")

    return total_rows


def import_sdr_master_file(file_path) -> int:
    create_sdr_table()
    path = Path(file_path)
    raw = _read_input_file(path)
    prepared = _prepare_sdr_dataframe(raw, path.name)
    return _upsert_dataframe(SDR_TABLE, prepared, "mobile_number")


def import_master_folder(folder_path, import_type: str) -> int:
    folder = Path(folder_path)

    if not folder.exists():
        raise FileNotFoundError(f"Master import folder not found: {folder}")

    files = [
        path
        for path in sorted(folder.iterdir())
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMPORT_SUFFIXES
    ]

    total_rows = 0

    for file_path in files:
        if import_type == "cgi":
            total_rows += import_cgi_master_file(file_path)
        elif import_type == "sdr":
            total_rows += import_sdr_master_file(file_path)
        else:
            raise ValueError("import_type must be 'cgi' or 'sdr'")

    return total_rows
