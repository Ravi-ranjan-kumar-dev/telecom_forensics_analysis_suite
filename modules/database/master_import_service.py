"""Safe one-click SDR and CGI master-data import service."""

from __future__ import annotations

import csv, hashlib, json, re, shutil, time, uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from .cgi_master_reader import read_cgi_master_file
from .db_paths import master_duckdb_path
from .master_importer import (
    _detect_delimiter, _detect_header_line, _normalise_column_name,
    _prepare_sdr_dataframe, _read_input_file,
    import_cgi_master_file,   # <-- यह
    import_sdr_master_file,   # <-- और यह
)


SUPPORTED_MASTER_SUFFIXES = {
    ".csv",
    ".txt",
    ".tsv",
    ".xlsx",
    ".xls",
    ".xlsb",
}

TEXT_MASTER_SUFFIXES = {
    ".csv",
    ".txt",
    ".tsv",
}

SDR_COLUMN_ALIASES = {
    "mobile_number": [
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
    "subscriber_name": [
        "subscriber_name",
        "name",
        "customer_name",
        "caf_name",
    ],
    "father_name": [
        "father_name",
        "father",
        "guardian_name",
    ],
    "address": [
        "address",
        "subscriber_address",
        "caf_address",
    ],
    "id_type": [
        "id_type",
        "identity_type",
        "poi_type",
    ],
    "id_number": [
        "id_number",
        "identity_number",
        "poi_number",
    ],
    "operator": [
        "operator",
        "tsp",
        "service_provider",
    ],
    "circle": [
        "circle",
        "lsa",
    ],
    "activation_date": [
        "activation_date",
        "date_of_activation",
        "doa",
    ],
    "caf_number": [
        "caf_number",
        "caf",
        "caf_no",
    ],
}

CGI_SCORE_COLUMNS = {
    "cgi",
    "ecgi",
    "cell",
    "cell_id",
    "cellid",
    "cell_global_id",
    "cell_global_identity",
    "mcc_mnc",
    "lac",
    "cid",
    "tac_id",
    "tac_id_decimal",
    "site_id",
    "gnb_id",
    "azimuth",
    "technology",
}

SDR_SCORE_COLUMNS = {
    "mobile_number",
    "mobile",
    "msisdn",
    "phone",
    "phone_number",
    "subscriber_number",
    "subscriber_name",
    "father_name",
    "caf_number",
    "id_number",
}

SDR_TARGET_COLUMNS = [
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

SDR_COMPARE_COLUMNS = [
    "subscriber_name",
    "father_name",
    "address",
    "id_type",
    "id_number",
    "operator",
    "circle",
    "activation_date",
    "caf_number",
]

CGI_TARGET_COLUMNS = [
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

CGI_COMPARE_COLUMNS = [
    column
    for column in CGI_TARGET_COLUMNS
    if column not in {
        "cgi",
        "source_file",
    }
]


@dataclass
class MasterImportResult:
    """Structured result for one master-data import."""

    run_id: str
    status: str = "FAILED"
    import_type: str = ""
    source_file: str = ""
    source_size_bytes: int = 0
    source_mtime_ns: int = 0
    fingerprint: str = ""
    backup_path: str = ""
    log_path: str = ""
    target_table: str = ""
    base_rows: int = 0
    before_count: int = 0
    after_count: int = 0
    rows_read: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    duplicate_rows: int = 0
    inserted_rows: int = 0
    updated_rows: int = 0
    skipped_rows: int = 0
    duration_seconds: float = 0.0
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_datetime() -> datetime:
    """Return a timezone-neutral UTC datetime for DuckDB."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _new_run_id() -> str:
    """Create a readable unique import run identifier."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"MASTER-{timestamp}-{suffix}"


def _quote_identifier(value: str) -> str:
    """Quote one DuckDB identifier."""
    return '"' + str(value).replace('"', '""') + '"'


def _sql_literal(value: object) -> str:
    """Return one safely quoted SQL string literal."""
    return "'" + str(value).replace("'", "''") + "'"


def _table_exists(connection: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    """Check whether one table exists in the current database."""
    row = connection.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = 'main'
          AND table_name = ?
        """,
        [table_name],
    ).fetchone()
    return bool(row and int(row[0]))


def _table_count(connection: duckdb.DuckDBPyConnection, table_name: str) -> int:
    """Return a table count using DuckDB metadata when possible."""
    if not _table_exists(connection, table_name):
        return 0
    quoted = _quote_identifier(table_name)
    row = connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()
    return int(row[0]) if row else 0


def _ensure_master_tables(connection: duckdb.DuckDBPyConnection) -> None:
    """Create canonical master and import-control tables."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS cgi_addresses (
            cgi VARCHAR PRIMARY KEY,
            operator VARCHAR,
            circle VARCHAR,
            state VARCHAR,
            district VARCHAR,
            police_station VARCHAR,
            address VARCHAR,
            latitude DOUBLE,
            longitude DOUBLE,
            source_file VARCHAR,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            site_name VARCHAR,
            town VARCHAR,
            landmark VARCHAR,
            azimuth VARCHAR,
            technology VARCHAR,
            status VARCHAR,
            status_change_date VARCHAR,
            mcc_mnc VARCHAR,
            lac VARCHAR,
            cid VARCHAR,
            tac_id VARCHAR,
            site_id VARCHAR,
            gnb_id VARCHAR,
            cell_id VARCHAR
        )
        """
    )

    cgi_optional_columns = {
        "site_name": "VARCHAR",
        "town": "VARCHAR",
        "landmark": "VARCHAR",
        "azimuth": "VARCHAR",
        "technology": "VARCHAR",
        "status": "VARCHAR",
        "status_change_date": "VARCHAR",
        "mcc_mnc": "VARCHAR",
        "lac": "VARCHAR",
        "cid": "VARCHAR",
        "tac_id": "VARCHAR",
        "site_id": "VARCHAR",
        "gnb_id": "VARCHAR",
        "cell_id": "VARCHAR",
    }

    for column_name, column_type in cgi_optional_columns.items():
        connection.execute(
            f"""
            ALTER TABLE cgi_addresses
            ADD COLUMN IF NOT EXISTS
            {_quote_identifier(column_name)}
            {column_type}
            """
        )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sdr_subscribers (
            mobile_number VARCHAR PRIMARY KEY,
            subscriber_name VARCHAR,
            father_name VARCHAR,
            address VARCHAR,
            id_type VARCHAR,
            id_number VARCHAR,
            operator VARCHAR,
            circle VARCHAR,
            activation_date VARCHAR,
            caf_number VARCHAR,
            source_file VARCHAR,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS master_import_runs (
            run_id VARCHAR PRIMARY KEY,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            status VARCHAR,
            import_type VARCHAR,
            source_file VARCHAR,
            source_size_bytes BIGINT,
            source_mtime_ns BIGINT,
            fingerprint VARCHAR,
            backup_path VARCHAR,
            log_path VARCHAR,
            target_table VARCHAR,
            base_rows BIGINT,
            before_count BIGINT,
            after_count BIGINT,
            rows_read BIGINT,
            valid_rows BIGINT,
            invalid_rows BIGINT,
            duplicate_rows BIGINT,
            inserted_rows BIGINT,
            updated_rows BIGINT,
            skipped_rows BIGINT,
            duration_seconds DOUBLE,
            message VARCHAR
        )
        """
    )


def _save_run(connection: duckdb.DuckDBPyConnection, result: MasterImportResult, *, started_at: datetime, completed_at: datetime | None) -> None:
    """Insert or update one import-run record."""
    connection.execute(
        """
        DELETE FROM master_import_runs
        WHERE run_id = ?
        """,
        [result.run_id],
    )
    connection.execute(
        """
        INSERT INTO master_import_runs (
            run_id,
            started_at,
            completed_at,
            status,
            import_type,
            source_file,
            source_size_bytes,
            source_mtime_ns,
            fingerprint,
            backup_path,
            log_path,
            target_table,
            base_rows,
            before_count,
            after_count,
            rows_read,
            valid_rows,
            invalid_rows,
            duplicate_rows,
            inserted_rows,
            updated_rows,
            skipped_rows,
            duration_seconds,
            message
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        [
            result.run_id,
            started_at,
            completed_at,
            result.status,
            result.import_type,
            result.source_file,
            result.source_size_bytes,
            result.source_mtime_ns,
            result.fingerprint,
            result.backup_path,
            result.log_path,
            result.target_table,
            result.base_rows,
            result.before_count,
            result.after_count,
            result.rows_read,
            result.valid_rows,
            result.invalid_rows,
            result.duplicate_rows,
            result.inserted_rows,
            result.updated_rows,
            result.skipped_rows,
            result.duration_seconds,
            result.message,
        ],
    )


def _successful_fingerprint_exists(connection: duckdb.DuckDBPyConnection, fingerprint: str) -> bool:
    """Check whether the same file was already imported."""
    row = connection.execute(
        """
        SELECT COUNT(*)
        FROM master_import_runs
        WHERE fingerprint = ?
          AND status = 'SUCCESS'
        """,
        [fingerprint],
    ).fetchone()
    return bool(row and int(row[0]))


def _fast_file_fingerprint(path: Path) -> str:
    """Build a fast duplicate-detection fingerprint."""
    stat = path.stat()
    digest = hashlib.sha256()
    digest.update(path.name.encode("utf-8", errors="replace"))
    digest.update(str(stat.st_size).encode())
    digest.update(str(stat.st_mtime_ns).encode())
    block_size = 1024 * 1024
    with path.open("rb") as handle:
        digest.update(handle.read(block_size))
        if stat.st_size > block_size:
            handle.seek(max(stat.st_size - block_size, 0))
            digest.update(handle.read(block_size))
    return digest.hexdigest()


def _find_header_companion(path: Path) -> tuple[list[str], str, Path] | None:
    """Find a separate header file only for a headerless export."""
    stem = path.stem
    is_data_export = bool(re.search(r"_data$", stem, flags=re.IGNORECASE))
    candidates = [path.with_name(f"{stem}_header.txt")]
    if is_data_export:
        base_stem = re.sub(r"_data$", "", stem, flags=re.IGNORECASE)
        candidates.extend([path.with_name(f"{base_stem}_header.txt"), path.parent / "sdr_master_export_header.txt"])
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen or not candidate.is_file():
            continue
        seen.add(candidate)
        lines = candidate.read_text(encoding="utf-8", errors="ignore").splitlines()
        header_line = next((line.strip() for line in lines if line.strip()), "")
        if not header_line:
            continue
        delimiter = _guess_delimiter(header_line)
        columns = [item.strip().replace("\ufeff", "") for item in header_line.split(delimiter)]
        if len(columns) < 2:
            continue
        return columns, delimiter, candidate
    return None


def _guess_delimiter(text: str) -> str:
    """Detect a simple tabular delimiter."""
    try:
        dialect = csv.Sniffer().sniff(text, delimiters=["|", "\t", ",", ";"])
        return str(dialect.delimiter)
    except csv.Error:
        counts = {d: text.count(d) for d in ("|", "\t", ",", ";")}
        return max(counts, key=counts.get)


def _read_text_preview(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read only a small preview from a text master file."""
    companion = _find_header_companion(path)
    if companion is not None:
        columns, delimiter, companion_path = companion
        dataframe = pd.read_csv(
            path,
            names=columns,
            header=None,
            dtype=str,
            sep=delimiter,
            engine="python",
            nrows=100,
            encoding_errors="ignore",
            on_bad_lines="skip",
        )
        return dataframe, {"header_line": None, "delimiter": delimiter, "header_companion": str(companion_path), "header_columns": columns}

    header_line = _detect_header_line(path)
    delimiter = _detect_delimiter(path, header_line)
    if not delimiter:
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","

    dataframe = pd.read_csv(
        path,
        dtype=str,
        sep=delimiter,
        engine="python",
        header=header_line,
        nrows=100,
        encoding_errors="ignore",
        on_bad_lines="skip",
    )
    dataframe.columns = [str(column).strip().replace("\ufeff", "") for column in dataframe.columns]
    return dataframe, {"header_line": int(header_line), "delimiter": delimiter, "header_companion": "", "header_columns": []}


def detect_master_data_type(file_path: object) -> dict[str, Any]:
    """Detect whether one file contains SDR or CGI master data."""
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Master data file not found: {path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_MASTER_SUFFIXES:
        raise ValueError(f"Unsupported master data file type: {suffix or '[no extension]'}")
    metadata: dict[str, Any]
    if suffix in TEXT_MASTER_SUFFIXES:
        preview, metadata = _read_text_preview(path)
    else:
        preview = _read_input_file(path)
        metadata = {"header_line": None, "delimiter": "", "header_companion": "", "header_columns": []}

    normalized_columns = {_normalise_column_name(column) for column in preview.columns}

    sdr_score = len(normalized_columns.intersection(SDR_SCORE_COLUMNS))
    cgi_score = len(normalized_columns.intersection(CGI_SCORE_COLUMNS))

    strong_sdr = bool(normalized_columns.intersection({"mobile_number", "mobile", "msisdn", "subscriber_number", "phone_number"}))
    strong_cgi = bool(normalized_columns.intersection({"cgi", "ecgi", "cell_global_id", "cell_global_identity", "mcc_mnc"}))

    if strong_sdr:
        sdr_score += 5
    if strong_cgi:
        cgi_score += 5

    if sdr_score <= 0 and cgi_score <= 0:
        raise ValueError(f"Could not detect SDR or CGI master-data columns. Columns found: {list(preview.columns)}")

    if sdr_score == cgi_score:
        if strong_sdr and not strong_cgi:
            import_type = "SDR"
        elif strong_cgi and not strong_sdr:
            import_type = "CGI"
        else:
            raise ValueError("The file contains ambiguous SDR and CGI columns. Use a clean source file with one master-data type.")
    else:
        import_type = "SDR" if sdr_score > cgi_score else "CGI"

    return {
        "import_type": import_type,
        "file_path": str(path),
        "file_name": path.name,
        "suffix": suffix,
        "columns": [str(column) for column in preview.columns],
        "sdr_score": int(sdr_score),
        "cgi_score": int(cgi_score),
        **metadata,
    }


def _create_database_backup(*, run_id: str, source_size_bytes: int) -> Path:
    """Create one consistent pre-import DuckDB backup."""
    database_path = Path(master_duckdb_path()).resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"Master database not found: {database_path}")
    backup_dir = database_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    database_size = database_path.stat().st_size
    free_bytes = shutil.disk_usage(backup_dir).free
    safety_margin = max(512 * 1024 * 1024, min(int(source_size_bytes * 0.02), 4 * 1024 * 1024 * 1024))
    required_bytes = database_size + safety_margin
    if free_bytes < required_bytes:
        raise RuntimeError(
            f"Insufficient free space for the automatic database backup. "
            f"Required approximately {required_bytes / 1024 / 1024 / 1024:.2f} GiB; "
            f"available {free_bytes / 1024 / 1024 / 1024:.2f} GiB."
        )
    with duckdb.connect(str(database_path), read_only=False) as connection:
        connection.execute("CHECKPOINT")
    backup_path = backup_dir / f"{database_path.stem}_pre_master_import_{run_id}.duckdb"
    shutil.copy2(database_path, backup_path)
    return backup_path


def _write_json_log(result: MasterImportResult) -> Path:
    """Write one durable JSON import log."""
    database_path = Path(master_duckdb_path()).resolve()
    log_dir = database_path.parent / "import_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"master_import_{result.run_id}.json"
    result.log_path = str(log_path)
    temporary_path = log_path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(log_path)
    return log_path


def _match_column(columns: list[str], aliases: list[str]) -> str | None:
    """Find one source column by normalized aliases."""
    by_normalized = {_normalise_column_name(column): column for column in columns}
    for alias in aliases:
        matched = by_normalized.get(_normalise_column_name(alias))
        if matched is not None:
            return matched
    return None


def _text_expression(source_column: str | None) -> str:
    """Return a safe text expression for one optional column."""
    if source_column is None:
        return "NULL"
    quoted = _quote_identifier(source_column)
    return f"NULLIF(TRIM(CAST({quoted} AS VARCHAR)), '')"


def _mobile_expression(source_column: str) -> str:
    """Return canonical Indian mobile-number SQL."""
    quoted = _quote_identifier(source_column)
    digits = f"regexp_replace(CAST({quoted} AS VARCHAR), '[^0-9]', '', 'g')"
    return f"""
        CASE
            WHEN length({digits}) = 12 AND starts_with({digits}, '91')
                THEN right({digits}, 10)
            WHEN length({digits}) = 11 AND starts_with({digits}, '0')
                THEN right({digits}, 10)
            WHEN length({digits}) = 10
                THEN {digits}
            ELSE ''
        END
    """.strip()


def _text_relation_sql(path: Path, detection: dict[str, Any]) -> str:
    """Build a DuckDB relation for one text master file."""
    file_literal = _sql_literal(str(path))
    delimiter = str(detection.get("delimiter", "") or ("\t" if path.suffix.lower() == ".tsv" else ","))
    delimiter_literal = _sql_literal(delimiter)
    header_columns = detection.get("header_columns", [])
    if header_columns:
        column_map = ", ".join(f"{_sql_literal(column)}: 'VARCHAR'" for column in header_columns)
        return f"read_csv({file_literal}, delim={delimiter_literal}, header=false, columns={{{column_map}}}, null_padding=true)"
    header_line = int(detection.get("header_line", 0) or 0)
    return f"read_csv_auto({file_literal}, delim={delimiter_literal}, header=true, skip={header_line}, all_varchar=true, sample_size=200000, null_padding=true)"


def _relation_columns(connection: duckdb.DuckDBPyConnection, relation_sql: str) -> list[str]:
    """Return source relation column names."""
    rows = connection.execute(f"DESCRIBE SELECT * FROM {relation_sql}").fetchall()
    return [str(row[0]) for row in rows]


def _create_sdr_text_stage(connection: duckdb.DuckDBPyConnection, path: Path, detection: dict[str, Any]) -> dict[str, int]:
    """Stream a text SDR file into a canonical temporary table."""
    relation_sql = _text_relation_sql(path, detection)
    columns = _relation_columns(connection, relation_sql)
    mobile_column = _match_column(columns, SDR_COLUMN_ALIASES["mobile_number"])
    if mobile_column is None:
        raise ValueError(f"Mobile/MSISDN column was not found in the SDR file. Columns found: {columns}")

    expressions: dict[str, str] = {"mobile_number": _mobile_expression(mobile_column)}
    for target_column in (column for column in SDR_TARGET_COLUMNS if column not in {"mobile_number", "source_file"}):
        source_column = _match_column(columns, SDR_COLUMN_ALIASES[target_column])
        expressions[target_column] = _text_expression(source_column)

    source_file_literal = _sql_literal(path.name)

    connection.execute("DROP TABLE IF EXISTS incoming_sdr_all")
    connection.execute("DROP TABLE IF EXISTS incoming_sdr_valid")
    connection.execute(
        f"""
        CREATE TEMP TABLE incoming_sdr_all AS
        WITH source_rows AS (
            SELECT *, row_number() OVER () AS source_row_number
            FROM {relation_sql}
        )
        SELECT
            {expressions["mobile_number"]} AS mobile_number,
            {expressions["subscriber_name"]} AS subscriber_name,
            {expressions["father_name"]} AS father_name,
            {expressions["address"]} AS address,
            {expressions["id_type"]} AS id_type,
            {expressions["id_number"]} AS id_number,
            {expressions["operator"]} AS operator,
            {expressions["circle"]} AS circle,
            {expressions["activation_date"]} AS activation_date,
            {expressions["caf_number"]} AS caf_number,
            {source_file_literal} AS source_file,
            current_timestamp AS imported_at,
            source_row_number
        FROM source_rows
        """
    )

    rows_read = int(connection.execute("SELECT COUNT(*) FROM incoming_sdr_all").fetchone()[0])
    valid_raw = int(connection.execute("SELECT COUNT(*) FROM incoming_sdr_all WHERE regexp_matches(mobile_number, '^[6-9][0-9]{9}$')").fetchone()[0])
    connection.execute(
        """
        CREATE TEMP TABLE incoming_sdr_valid AS
        SELECT * EXCLUDE (dedupe_rank)
        FROM (
            SELECT *, row_number() OVER (PARTITION BY mobile_number ORDER BY source_row_number DESC) AS dedupe_rank
            FROM incoming_sdr_all
            WHERE regexp_matches(mobile_number, '^[6-9][0-9]{9}$')
        )
        WHERE dedupe_rank = 1
        """
    )
    valid_rows = int(connection.execute("SELECT COUNT(*) FROM incoming_sdr_valid").fetchone()[0])
    return {
        "rows_read": rows_read,
        "valid_rows": valid_rows,
        "invalid_rows": rows_read - valid_raw,
        "duplicate_rows": valid_raw - valid_rows,
    }


def _normalize_mobile_python(value: object) -> str:
    """Normalize one mobile number for Excel import counting."""
    digits = re.sub(r"\D+", "", str(value if value is not None else ""))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[-10:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[-10:]
    if len(digits) == 10 and digits[0] in {"6", "7", "8", "9"}:
        return digits
    return ""


def _create_sdr_excel_stage(connection: duckdb.DuckDBPyConnection, path: Path) -> dict[str, int]:
    """Prepare a normal-sized Excel SDR file."""
    raw = _read_input_file(path)
    prepared = _prepare_sdr_dataframe(raw, path.name)
    columns = [str(column) for column in raw.columns]
    mobile_column = _match_column(columns, SDR_COLUMN_ALIASES["mobile_number"])
    if mobile_column is None:
        raise ValueError("Mobile/MSISDN column was not found.")
    normalized = raw[mobile_column].map(_normalize_mobile_python)
    valid_raw = int(normalized.ne("").sum())
    rows_read = int(len(raw))
    valid_rows = int(len(prepared))
    dataframe = prepared.copy()
    connection.register("incoming_sdr_dataframe", dataframe)
    connection.execute("DROP TABLE IF EXISTS incoming_sdr_valid")
    connection.execute(
        """
        CREATE TEMP TABLE incoming_sdr_valid AS
        SELECT
            mobile_number,
            subscriber_name,
            father_name,
            address,
            id_type,
            id_number,
            operator,
            circle,
            activation_date,
            caf_number,
            source_file,
            current_timestamp AS imported_at,
            row_number() OVER () AS source_row_number
        FROM incoming_sdr_dataframe
        """
    )
    connection.unregister("incoming_sdr_dataframe")
    return {
        "rows_read": rows_read,
        "valid_rows": valid_rows,
        "invalid_rows": rows_read - valid_raw,
        "duplicate_rows": valid_raw - valid_rows,
    }


def _null_safe_difference(left_alias: str, right_alias: str, columns: list[str]) -> str:
    """Build a null-safe changed-row predicate."""
    comparisons = []
    for column in columns:
        quoted = _quote_identifier(column)
        comparisons.append(f"(CAST({left_alias}.{quoted} AS VARCHAR) IS DISTINCT FROM CAST({right_alias}.{quoted} AS VARCHAR))")
    return " OR ".join(comparisons) if comparisons else "FALSE"


def _create_existing_sdr_stage(connection: duckdb.DuckDBPyConnection) -> int:
    """Resolve current SDR records with primary-table priority."""
    connection.execute("DROP TABLE IF EXISTS existing_sdr_best")
    connection.execute(
        """
        CREATE TEMP TABLE existing_sdr_best AS
        SELECT
            primary_data.mobile_number,
            primary_data.subscriber_name,
            primary_data.father_name,
            primary_data.address,
            primary_data.id_type,
            primary_data.id_number,
            primary_data.operator,
            primary_data.circle,
            primary_data.activation_date,
            primary_data.caf_number,
            primary_data.source_file
        FROM sdr_subscribers AS primary_data
        INNER JOIN incoming_sdr_valid AS incoming
            ON incoming.mobile_number = primary_data.mobile_number
        """
    )
    base_rows = 0
    if _table_exists(connection, "sdr_subscribers_large"):
        base_rows = _table_count(connection, "sdr_subscribers_large")
        connection.execute(
            """
            INSERT INTO existing_sdr_best
            SELECT
                mobile_number,
                subscriber_name,
                father_name,
                address,
                id_type,
                id_number,
                operator,
                circle,
                activation_date,
                caf_number,
                source_file
            FROM (
                SELECT
                    large_data.mobile_number,
                    large_data.subscriber_name,
                    large_data.father_name,
                    large_data.address,
                    large_data.id_type,
                    large_data.id_number,
                    large_data.operator,
                    large_data.circle,
                    large_data.activation_date,
                    large_data.caf_number,
                    large_data.source_file,
                    row_number() OVER (
                        PARTITION BY large_data.mobile_number
                        ORDER BY TRY_CAST(large_data.activation_date AS DATE) DESC NULLS LAST,
                                 TRY_CAST(large_data.caf_number AS BIGINT) DESC NULLS LAST
                    ) AS ranking
                FROM sdr_subscribers_large AS large_data
                INNER JOIN incoming_sdr_valid AS incoming
                    ON incoming.mobile_number = large_data.mobile_number
                LEFT JOIN sdr_subscribers AS primary_data
                    ON primary_data.mobile_number = large_data.mobile_number
                WHERE primary_data.mobile_number IS NULL
            )
            WHERE ranking = 1
            """
        )
    return base_rows


def _upsert_sdr_stage(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Apply canonical SDR delta rows atomically."""
    before_count = _table_count(connection, "sdr_subscribers")
    base_rows = _create_existing_sdr_stage(connection)
    difference = _null_safe_difference("incoming", "existing", SDR_COMPARE_COLUMNS)
    connection.execute("DROP TABLE IF EXISTS incoming_sdr_changes")
    connection.execute(
        f"""
        CREATE TEMP TABLE incoming_sdr_changes AS
        SELECT incoming.*, existing.mobile_number AS existing_mobile_number
        FROM incoming_sdr_valid AS incoming
        LEFT JOIN existing_sdr_best AS existing
            ON existing.mobile_number = incoming.mobile_number
        WHERE existing.mobile_number IS NULL OR ({difference})
        """
    )
    inserted_rows = int(connection.execute("SELECT COUNT(*) FROM incoming_sdr_changes WHERE existing_mobile_number IS NULL").fetchone()[0])
    updated_rows = int(connection.execute("SELECT COUNT(*) FROM incoming_sdr_changes WHERE existing_mobile_number IS NOT NULL").fetchone()[0])
    valid_rows = int(connection.execute("SELECT COUNT(*) FROM incoming_sdr_valid").fetchone()[0])
    skipped_rows = valid_rows - inserted_rows - updated_rows

    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute(
            """
            DELETE FROM sdr_subscribers
            WHERE mobile_number IN (SELECT mobile_number FROM incoming_sdr_changes)
            """
        )
        connection.execute(
            """
            INSERT INTO sdr_subscribers (
                mobile_number, subscriber_name, father_name, address, id_type, id_number,
                operator, circle, activation_date, caf_number, source_file, imported_at
            )
            SELECT
                mobile_number, subscriber_name, father_name, address, id_type, id_number,
                operator, circle, activation_date, caf_number, source_file, imported_at
            FROM incoming_sdr_changes
            """
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise

    after_count = _table_count(connection, "sdr_subscribers")
    return {
        "base_rows": base_rows,
        "before_count": before_count,
        "after_count": after_count,
        "inserted_rows": inserted_rows,
        "updated_rows": updated_rows,
        "skipped_rows": skipped_rows,
    }


def _prepare_cgi_dataframe(path: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    """Read and deduplicate one CGI master workbook or file."""
    prepared_frames = read_cgi_master_file(path)
    usable_frames = [frame for frame in prepared_frames if frame is not None and not frame.empty]
    if not usable_frames:
        raise ValueError("No valid CGI rows were found in the selected file.")
    rows_read = sum(len(frame) for frame in usable_frames)
    combined = pd.concat(usable_frames, ignore_index=True)
    combined = combined.drop_duplicates(subset=["cgi"], keep="last")
    for column in CGI_TARGET_COLUMNS:
        if column not in combined.columns:
            combined[column] = None
    combined = combined[CGI_TARGET_COLUMNS].copy()
    valid_rows = int(len(combined))
    return combined, {"rows_read": int(rows_read), "valid_rows": valid_rows, "invalid_rows": 0, "duplicate_rows": int(rows_read) - valid_rows}


def _upsert_cgi_dataframe(connection: duckdb.DuckDBPyConnection, dataframe: pd.DataFrame) -> dict[str, int]:
    """Apply one CGI dataframe atomically."""
    before_count = _table_count(connection, "cgi_addresses")
    connection.register("incoming_cgi_dataframe", dataframe)
    connection.execute("DROP TABLE IF EXISTS incoming_cgi_valid")
    quoted_columns = ", ".join(_quote_identifier(column) for column in CGI_TARGET_COLUMNS)
    connection.execute(
        f"""
        CREATE TEMP TABLE incoming_cgi_valid AS
        SELECT {quoted_columns}, current_timestamp AS imported_at
        FROM incoming_cgi_dataframe
        """
    )
    connection.unregister("incoming_cgi_dataframe")
    difference = _null_safe_difference("incoming", "existing", CGI_COMPARE_COLUMNS)
    connection.execute("DROP TABLE IF EXISTS incoming_cgi_changes")
    connection.execute(
        f"""
        CREATE TEMP TABLE incoming_cgi_changes AS
        SELECT incoming.*, existing.cgi AS existing_cgi
        FROM incoming_cgi_valid AS incoming
        LEFT JOIN cgi_addresses AS existing
            ON existing.cgi = incoming.cgi
        WHERE existing.cgi IS NULL OR ({difference})
        """
    )
    inserted_rows = int(connection.execute("SELECT COUNT(*) FROM incoming_cgi_changes WHERE existing_cgi IS NULL").fetchone()[0])
    updated_rows = int(connection.execute("SELECT COUNT(*) FROM incoming_cgi_changes WHERE existing_cgi IS NOT NULL").fetchone()[0])
    valid_rows = int(len(dataframe))
    skipped_rows = valid_rows - inserted_rows - updated_rows
    insert_columns = [*CGI_TARGET_COLUMNS, "imported_at"]
    insert_csv = ", ".join(_quote_identifier(column) for column in insert_columns)
    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute(
            f"""
            DELETE FROM cgi_addresses
            WHERE cgi IN (SELECT cgi FROM incoming_cgi_changes)
            """
        )
        connection.execute(
            f"""
            INSERT INTO cgi_addresses ({insert_csv})
            SELECT {insert_csv} FROM incoming_cgi_changes
            """
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise

    after_count = _table_count(connection, "cgi_addresses")
    return {"base_rows": 0, "before_count": before_count, "after_count": after_count, "inserted_rows": inserted_rows, "updated_rows": updated_rows, "skipped_rows": skipped_rows}


def _large_sdr_source_exists(connection: duckdb.DuckDBPyConnection, source_file: str) -> bool:
    """Check whether a large historical SDR source was already loaded."""
    if not _table_exists(connection, "sdr_subscribers_large"):
        return False
    row = connection.execute("SELECT 1 FROM sdr_subscribers_large WHERE source_file = ? LIMIT 1", [source_file]).fetchone()
    return row is not None


def import_master_data_file(file_path: object, *, create_backup: bool = True) -> dict[str, Any]:
    """
    Auto-detect, validate, back up and import one master-data file.
    Raw source files are opened read-only and are never modified.
    """
    run_id = _new_run_id()
    started_at = _utc_datetime()
    started_clock = time.perf_counter()
    result = MasterImportResult(run_id=run_id)
    database_path = Path(master_duckdb_path()).resolve()

    try:
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Master data file not found: {path}")
        stat = path.stat()
        result.source_file = str(path)
        result.source_size_bytes = int(stat.st_size)
        result.source_mtime_ns = int(stat.st_mtime_ns)
        result.fingerprint = _fast_file_fingerprint(path)
        detection = detect_master_data_type(path)
        result.import_type = str(detection["import_type"])
        result.target_table = "sdr_subscribers" if result.import_type == "SDR" else "cgi_addresses"

        database_path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(database_path), read_only=False) as connection:
            _ensure_master_tables(connection)
            if _successful_fingerprint_exists(connection, result.fingerprint):
                result.status = "SKIPPED_DUPLICATE"
                result.message = "The same master-data file was already imported successfully."
                result.duration_seconds = round(time.perf_counter() - started_clock, 3)
                _write_json_log(result)
                _save_run(connection, result, started_at=started_at, completed_at=_utc_datetime())
                return result.to_dict()

            if result.import_type == "SDR" and result.source_size_bytes >= 1024 * 1024 * 1024 and _large_sdr_source_exists(connection, path.name):
                result.status = "SKIPPED_EXISTING_BASE"
                result.base_rows = _table_count(connection, "sdr_subscribers_large")
                result.message = "This large SDR source file is already present in the historical SDR base table."
                result.duration_seconds = round(time.perf_counter() - started_clock, 3)
                _write_json_log(result)
                _save_run(connection, result, started_at=started_at, completed_at=_utc_datetime())
                return result.to_dict()

            result.status = "RUNNING"
            result.message = "Master-data import started."
            _save_run(connection, result, started_at=started_at, completed_at=None)

        if create_backup:
            backup_path = _create_database_backup(run_id=run_id, source_size_bytes=result.source_size_bytes)
            result.backup_path = str(backup_path)

        with duckdb.connect(str(database_path), read_only=False) as connection:
            _ensure_master_tables(connection)
            if result.import_type == "SDR":
                if path.suffix.lower() in TEXT_MASTER_SUFFIXES:
                    preparation = _create_sdr_text_stage(connection, path, detection)
                else:
                    preparation = _create_sdr_excel_stage(connection, path)
                changes = _upsert_sdr_stage(connection)
            else:
                dataframe, preparation = _prepare_cgi_dataframe(path)
                changes = _upsert_cgi_dataframe(connection, dataframe)

            for key, value in preparation.items():
                setattr(result, key, int(value))
            for key, value in changes.items():
                setattr(result, key, int(value))

            result.status = "SUCCESS"
            result.message = "Master data imported and verified successfully."
            result.duration_seconds = round(time.perf_counter() - started_clock, 3)
            _write_json_log(result)
            _save_run(connection, result, started_at=started_at, completed_at=_utc_datetime())

        return result.to_dict()

    except Exception as error:
        result.status = "FAILED"
        result.message = f"{type(error).__name__}: {error}"
        result.duration_seconds = round(time.perf_counter() - started_clock, 3)
        try:
            _write_json_log(result)
        except Exception:
            pass
        try:
            database_path.parent.mkdir(parents=True, exist_ok=True)
            with duckdb.connect(str(database_path), read_only=False) as connection:
                _ensure_master_tables(connection)
                _save_run(connection, result, started_at=started_at, completed_at=_utc_datetime())
        except Exception:
            pass
        return result.to_dict()


# -----------------------------------------------------------------------------
# 🆕 Folder Import Function (एक साथ पूरे फ़ोल्डर की फ़ाइलें import करने के लिए)
# -----------------------------------------------------------------------------

def import_master_folder(folder_path: str, import_type: str = "auto") -> int:
    """
    Import all supported SDR/CGI master files from a folder.

    import_type:
        - "auto": auto-detect each file (SDR or CGI)
        - "sdr": force SDR import for all files
        - "cgi": force CGI import for all files
    """
    from pathlib import Path

    folder = Path(folder_path).expanduser().resolve()

    if not folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {folder}")

    supported_suffixes = {".csv", ".txt", ".tsv", ".xlsx", ".xls", ".xlsb"}
    files = [
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in supported_suffixes
    ]

    if not files:
        print(f"[-] No supported files found in {folder}")
        return 0

    total_rows = 0

    for file_path in files:
        try:
            # import_master_data_file already does:
            # - fingerprint check (duplicate skip)
            # - auto-detect SDR/CGI
            # - backup (create_backup=False to avoid many backups)
            result = import_master_data_file(
                file_path,
                create_backup=False,   # backup already handled separately if needed
            )

            status = result.get("status", "")
            if status == "SUCCESS":
                inserted = int(result.get("inserted_rows", 0))
                updated = int(result.get("updated_rows", 0))
                total_rows += inserted + updated
                print(f"[+] Imported {file_path.name}: {inserted + updated:,} rows (inserted: {inserted:,}, updated: {updated:,})")
            elif status.startswith("SKIPPED"):
                print(f"[=] Skipped {file_path.name}: {result.get('message', 'already imported')}")
            else:
                print(f"[-] Failed to import {file_path.name}: {result.get('message', '')}")
        except Exception as e:
            print(f"[-] Failed to import {file_path.name}: {e}")

    return total_rows