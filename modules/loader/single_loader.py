# modules/loader/single_loader.py

import csv
import os
import re
import traceback

import numpy as np
import pandas as pd

from modules.loader.identity import target_match_mask
from modules.loader.evidence_csv import (
    empty_reject_ledger,
    quarantine_dataframe_rows,
    read_csv_with_quarantine,
)


# ==============================================================
# COLUMN MAPPING
# ==============================================================

COLUMN_MAPPER = {
    # ----------------------------------------------------------
    # A-PARTY / TARGET
    # ----------------------------------------------------------
    "calling_party_telephone_number": "a_party",
    "target_no": "a_party",
    "target_a_party_number": "a_party",
    "a_party_number": "a_party",
    "a_party": "a_party",
    "msisdn": "a_party",
    "calling_no": "a_party",
    "calling_number": "a_party",

    # ----------------------------------------------------------
    # B-PARTY / OPPOSITE PARTY
    # ----------------------------------------------------------
    "called_party_telephone_number": "b_party",
    "b_party_no": "b_party",
    "b_party_number": "b_party",
    "other_b_party_number": "b_party",
    "other_party_number": "b_party",
    "called_no": "b_party",
    "called_number": "b_party",
    "dialled_no": "b_party",
    "dialed_no": "b_party",
    "b_party": "b_party",

    # ----------------------------------------------------------
    # DATE AND TIME
    # ----------------------------------------------------------
    "call_date": "call_date",
    "date": "call_date",
    "start_date": "call_date",

    "call_time": "call_time",
    "time": "call_time",
    "start_time": "call_time",
    "call_initiation_time": "call_time",

    "call_termination_time": "call_end_time",
    "end_time": "call_end_time",

    # ----------------------------------------------------------
    # DURATION
    # ----------------------------------------------------------
    "call_duration": "call_duration",
    "duration": "call_duration",
    "dur_s": "call_duration",
    "call_duration_sec": "call_duration",
    "call_duration_seconds": "call_duration",

    # ----------------------------------------------------------
    # CELL / LOCATION
    # ----------------------------------------------------------
    "first_cell_id": "first_cell_id",
    "cell_id": "first_cell_id",
    "first_cgi": "first_cell_id",
    "first_cell_global_id": "first_cell_id",

    "last_cell_id": "last_cell_id",
    "last_cgi": "last_cell_id",
    "last_cell_global_id": "last_cell_id",

    "first_bts_location": "first_location",
    "last_bts_location": "last_location",

    # ----------------------------------------------------------
    # DEVICE AND SUBSCRIBER IDENTITY
    # ----------------------------------------------------------
    "imei": "imei",
    "imei_number": "imei",

    "imsi": "imsi",
    "imsi_number": "imsi",

    # ----------------------------------------------------------
    # CALL / SERVICE TYPE
    # ----------------------------------------------------------
    "call_type": "call_type",
    "service_type": "service_type",
    "type_of_connection": "connection_type",
    "toc": "connection_type",

    # ----------------------------------------------------------
    # SMS CENTRE
    # ----------------------------------------------------------
    "sms_center_number": "smsc",
    "sms_centre_number": "smsc",
    "sms_centre_no": "smsc",
    "smsc_no": "smsc",

    # ----------------------------------------------------------
    # ROAMING
    # ----------------------------------------------------------
    "roaming_circle_name": "roaming_circle",
    "roaming_network_circle": "roaming_circle",
    "roam_nw": "roaming_circle",
}


# ==============================================================
# CALL TYPE STANDARDIZATION
# ==============================================================

CALL_TYPE_MAPPING = {
    # Outgoing voice
    "a_out": "outgoing",
    "moc": "outgoing",
    "mo": "outgoing",
    "out": "outgoing",
    "outgoing": "outgoing",
    "outgoing_call": "outgoing",
    "v_out": "outgoing",
    "vdo_out": "outgoing",
    "voice_out": "outgoing",

    # Incoming voice
    "a_in": "incoming",
    "mtc": "incoming",
    "mt": "incoming",
    "in": "incoming",
    "incoming": "incoming",
    "incoming_call": "incoming",
    "v_in": "incoming",
    "vdo_in": "incoming",
    "voice_in": "incoming",

    # Incoming SMS
    "a2p_smsin": "smsin",
    "p2p_smsin": "smsin",
    "smt": "smsin",
    "smsin": "smsin",
    "sms_in": "smsin",
    "sms_mt": "smsin",
    "incoming_sms": "smsin",

    # Outgoing SMS
    "p2pout": "smsout",
    "p2aout": "smsout",
    "p2p_smsout": "smsout",
    "smo": "smsout",
    "smsout": "smsout",
    "sms_out": "smsout",
    "sms_mo": "smsout",
    "outgoing_sms": "smsout",

    # Generic SMS
    "sms": "sms",
    "sms_generic": "sms",
}


IDENTIFIER_COLUMNS = [
    "a_party",
    "b_party",
    "target_number",
    "opposite_party",
    "imei",
    "imsi",
    "first_cell_id",
    "last_cell_id",
    "smsc",
]


# ==============================================================
# ERROR DISPLAY
# ==============================================================

def print_loader_error(title, error):
    """Loader error ko readable format mein print karta hai."""

    print(f"\n[-] {title}")
    print(f"    Error Type : {type(error).__name__}")
    print(f"    Message    : {error}")
    print("    Error Trace:")
    print(traceback.format_exc(limit=3).rstrip())


# ==============================================================
# COLUMN NAME NORMALIZATION
# ==============================================================

def normalize_column_name(column_name):
    """
    Raw operator column name ko lowercase underscore format mein
    convert karta hai.

    Example:
        Target /A PARTY NUMBER -> target_a_party_number
        Dur(s)                 -> dur_s
    """

    text = str(column_name)

    text = text.replace("\ufeff", "")
    text = text.strip().lower()

    text = re.sub(
        r"[^a-z0-9]+",
        "_",
        text,
    )

    text = re.sub(
        r"_+",
        "_",
        text,
    )

    return text.strip("_")


def merge_duplicate_columns(df):
    """
    Agar multiple raw columns same canonical name par map ho jaayen,
    to unhe safely combine karta hai.
    """

    if not df.columns.duplicated().any():
        return df

    output = pd.DataFrame(index=df.index)
    processed_columns = set()

    for column_name in df.columns:
        if column_name in processed_columns:
            continue

        processed_columns.add(column_name)

        matching_columns = df.loc[
            :,
            df.columns == column_name,
        ]

        if matching_columns.shape[1] == 1:
            output[column_name] = matching_columns.iloc[:, 0]

        else:
            matching_columns = matching_columns.replace(
                r"^\s*$",
                pd.NA,
                regex=True,
            )

            output[column_name] = (
                matching_columns
                .bfill(axis=1)
                .iloc[:, 0]
            )

    return output


def clean_and_standardise_columns(df):
    """
    Operator-specific column names ko project ke common schema
    mein convert karta hai.
    """

    if df is None:
        print("[-] Column standardization: DataFrame is None.")
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame):
        print(
            "[-] Column standardization: Invalid input type: "
            f"{type(df).__name__}"
        )
        return pd.DataFrame()

    try:
        data = df.copy()
        new_columns = []

        for column in data.columns:
            normalized_column = normalize_column_name(column)

            mapped_column = COLUMN_MAPPER.get(
                normalized_column,
                normalized_column,
            )

            if not mapped_column:
                mapped_column = "unnamed_column"

            new_columns.append(mapped_column)

        data.columns = new_columns

        data = merge_duplicate_columns(data)

        if "first_cell_id" in data.columns:
            data["location"] = data["first_cell_id"]

        return data

    except Exception as error:
        print_loader_error(
            "Column standardization failed.",
            error,
        )
        return pd.DataFrame()


# ==============================================================
# CALL TYPE NORMALIZATION
# ==============================================================

def normalize_call_type(value):
    """
    Single call-type value ko canonical format mein convert karta hai.
    """

    if pd.isna(value):
        return "unknown"

    normalized = normalize_column_name(value)

    # Jio variants:
    # a_in_wifi, a_out_wifi, A2P_SMSIN_wifi, etc.
    normalized = re.sub(
        r"_(wifi|wv|vw)$",
        "",
        normalized,
    )

    return CALL_TYPE_MAPPING.get(
        normalized,
        normalized or "unknown",
    )


# ==============================================================
# DATA VALUE CLEANING
# ==============================================================

def clean_data_values(df):
    """
    Raw CDR values ko clean aur standardize karta hai.

    Features:
    - Quotes aur null-like values clean karta hai.
    - Identifier fields ko string rakhta hai.
    - Original call type/date/time/duration preserve karta hai.
    - Call type standardize karta hai.
    - Datetime column create karta hai.
    - Call duration numeric seconds mein convert karta hai.
    """

    if df is None:
        print("[-] Data cleaning: DataFrame is None.")
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame):
        print(
            "[-] Data cleaning: Invalid input type: "
            f"{type(df).__name__}"
        )
        return pd.DataFrame()

    if df.empty:
        return df.copy()

    data = df.copy()

    # ----------------------------------------------------------
    # 1. CLEAN STRING VALUES
    # ----------------------------------------------------------

    for column in data.columns:
        try:
            if (
                pd.api.types.is_object_dtype(data[column])
                or pd.api.types.is_string_dtype(data[column])
            ):
                data[column] = (
                    data[column]
                    .astype("string")
                    .str.strip()
                    .str.strip("'\"")
                    .str.strip()
                )

                data[column] = data[column].replace(
                    r"(?i)^(?:nan|none|null|n/?a|<na>)$",
                    pd.NA,
                    regex=True,
                )

                data[column] = data[column].replace(
                    "",
                    pd.NA,
                )

        except Exception as error:
            print(
                f"[-] Value cleaning warning in '{column}': "
                f"{type(error).__name__}: {error}"
            )

    # ----------------------------------------------------------
    # 2. IDENTIFIER FIELDS
    # ----------------------------------------------------------

    for column in IDENTIFIER_COLUMNS:
        if column not in data.columns:
            continue

        try:
            data[column] = (
                data[column]
                .astype("string")
                .str.strip()
                .str.replace(
                    r"\.0$",
                    "",
                    regex=True,
                )
            )

            data[column] = data[column].replace(
                {
                    "": pd.NA,
                    "<NA>": pd.NA,
                }
            )

        except Exception as error:
            print(
                f"[-] Identifier cleaning warning in '{column}': "
                f"{type(error).__name__}: {error}"
            )

    # ----------------------------------------------------------
    # 3. CALL TYPE STANDARDIZATION
    # ----------------------------------------------------------

    if "call_type" in data.columns:
        try:
            if "raw_call_type" not in data.columns:
                data["raw_call_type"] = (
                    data["call_type"].copy()
                )

            data["call_type"] = (
                data["call_type"]
                .map(normalize_call_type)
                .astype("string")
            )

            # Vi format:
            # Call Type = Incoming/Outgoing
            # Service Type = SMS/Voice
            if "service_type" in data.columns:
                service_type = (
                    data["service_type"]
                    .astype("string")
                    .fillna("")
                    .str.lower()
                    .str.strip()
                )

                is_sms = service_type.str.contains(
                    "sms",
                    na=False,
                )

                data.loc[
                    is_sms
                    & data["call_type"].eq("incoming"),
                    "call_type",
                ] = "smsin"

                data.loc[
                    is_sms
                    & data["call_type"].eq("outgoing"),
                    "call_type",
                ] = "smsout"

                data.loc[
                    is_sms
                    & data["call_type"].eq("unknown"),
                    "call_type",
                ] = "sms"

        except Exception as error:
            print(
                "[-] Call type standardization warning: "
                f"{type(error).__name__}: {error}"
            )

    else:
        data["call_type"] = "unknown"

        print(
            "[!] Warning: call_type column nahi mili. "
            "Direction party-number comparison se detect hogi."
        )

    # ----------------------------------------------------------
    # 4. CALL DURATION
    # ----------------------------------------------------------

    if "call_duration" in data.columns:
        try:
            if "raw_call_duration" not in data.columns:
                data["raw_call_duration"] = (
                    data["call_duration"].copy()
                )

            numeric_duration = pd.to_numeric(
                data["call_duration"],
                errors="coerce",
            )

            failed_duration = (
                numeric_duration.isna()
                & data["call_duration"].notna()
            )

            # HH:MM:SS format fallback
            if failed_duration.any():
                converted_duration = pd.to_timedelta(
                    data.loc[
                        failed_duration,
                        "call_duration",
                    ].astype("string"),
                    errors="coerce",
                ).dt.total_seconds()

                numeric_duration.loc[
                    failed_duration
                ] = converted_duration

            data["call_duration"] = (
                numeric_duration
                .fillna(0)
                .clip(lower=0)
                .round()
                .astype("int64")
            )

        except Exception as error:
            print(
                "[-] Duration conversion warning: "
                f"{type(error).__name__}: {error}"
            )

            data["call_duration"] = 0

    else:
        data["call_duration"] = 0

    # ----------------------------------------------------------
    # 5. DATETIME CREATION
    # ----------------------------------------------------------

    if (
        "call_date" in data.columns
        and "call_time" in data.columns
    ):
        try:
            if "raw_call_date" not in data.columns:
                data["raw_call_date"] = (
                    data["call_date"].copy()
                )

            if "raw_call_time" not in data.columns:
                data["raw_call_time"] = (
                    data["call_time"].copy()
                )

            combined_datetime = (
                data["call_date"]
                .astype("string")
                .fillna("")
                .str.strip()
                + " "
                + data["call_time"]
                .astype("string")
                .fillna("")
                .str.strip()
            ).str.strip()

            try:
                parsed_datetime = pd.to_datetime(
                    combined_datetime,
                    errors="coerce",
                    dayfirst=True,
                    format="mixed",
                )

            except (TypeError, ValueError):
                # Older pandas fallback
                parsed_datetime = pd.to_datetime(
                    combined_datetime,
                    errors="coerce",
                    dayfirst=True,
                )

            data["datetime"] = parsed_datetime

            valid_datetime = parsed_datetime.notna()

            # Common standard date and time format
            data.loc[
                valid_datetime,
                "call_date",
            ] = parsed_datetime.loc[
                valid_datetime
            ].dt.strftime("%d-%m-%Y")

            data.loc[
                valid_datetime,
                "call_time",
            ] = parsed_datetime.loc[
                valid_datetime
            ].dt.strftime("%H:%M:%S")

        except Exception as error:
            print(
                "[-] Datetime creation warning: "
                f"{type(error).__name__}: {error}"
            )

            data["datetime"] = pd.NaT

    return data


# ==============================================================
# TARGET MATCHING
# ==============================================================

# Canonical exact target matching is imported from modules.loader.identity.


# ==============================================================
# TARGET AND B-PARTY REALIGNMENT
# ==============================================================

def realign_target_and_b_party(df, target):
    """
    CDR ko target-centric format mein realign karta hai.

    Important:
    - Airtel, Vi aur BSNL mein a_party har row mein target ho sakta hai.
    - Isliye canonical call_type ko direction detection mein priority milti hai.
    - Jio-style CDR mein party-number matching fallback ke roop mein use hota hai.
    """

    if df is None:
        print("[-] Realignment failed: DataFrame is None.")
        return df

    if not isinstance(df, pd.DataFrame):
        print(
            "[-] Realignment failed: Invalid input type: "
            f"{type(df).__name__}"
        )
        return df

    if df.empty:
        return df.copy()

    data = df.copy()
    target = str(target).strip()

    if not target:
        print("[-] Realignment failed: Target number is empty.")
        return data

    required_columns = [
        "a_party",
        "b_party",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in data.columns
    ]

    if missing_columns:
        print(
            "[-] Direction realignment failed. "
            f"Missing columns: {missing_columns}"
        )
        return data

    try:
        # Original evidence values preserve karein
        if "raw_a_party" not in data.columns:
            data["raw_a_party"] = data["a_party"].copy()

        if "raw_b_party" not in data.columns:
            data["raw_b_party"] = data["b_party"].copy()

        data["a_party"] = (
            data["a_party"]
            .astype("string")
            .fillna("")
            .str.strip()
        )

        data["b_party"] = (
            data["b_party"]
            .astype("string")
            .fillna("")
            .str.strip()
        )

        a_party_is_target = target_match_mask(
            data["a_party"],
            target,
        )

        b_party_is_target = target_match_mask(
            data["b_party"],
            target,
        )

        # ------------------------------------------------------
        # Party-number based direction
        # ------------------------------------------------------

        inferred_direction = np.select(
            [
                a_party_is_target & ~b_party_is_target,
                b_party_is_target & ~a_party_is_target,
            ],
            [
                "OUTGOING",
                "INCOMING",
            ],
            default="UNKNOWN",
        )

        # ------------------------------------------------------
        # Explicit call-type based direction
        # ------------------------------------------------------

        explicit_direction = pd.Series(
            "UNKNOWN",
            index=data.index,
            dtype="string",
        )

        if "call_type" in data.columns:
            normalized_call_type = (
                data["call_type"]
                .astype("string")
                .fillna("")
                .str.lower()
                .str.strip()
            )

            explicit_direction.loc[
                normalized_call_type.isin(
                    [
                        "outgoing",
                        "smsout",
                    ]
                )
            ] = "OUTGOING"

            explicit_direction.loc[
                normalized_call_type.isin(
                    [
                        "incoming",
                        "smsin",
                    ]
                )
            ] = "INCOMING"

        # Explicit operator direction gets first priority.
        data["call_direction"] = np.where(
            explicit_direction.ne("UNKNOWN"),
            explicit_direction,
            inferred_direction,
        )

        # ------------------------------------------------------
        # FIND OPPOSITE PARTY
        # ------------------------------------------------------

        opposite_party = np.where(
            a_party_is_target & ~b_party_is_target,
            data["b_party"],
            np.where(
                b_party_is_target & ~a_party_is_target,
                data["a_party"],
                data["b_party"],
            ),
        )

        data["opposite_party"] = pd.Series(
            opposite_party,
            index=data.index,
            dtype="string",
        )

        data["opposite_party"] = (
            data["opposite_party"]
            .replace("", pd.NA)
        )

        # Existing analysis modules b_party use karte hain.
        data["b_party"] = data["opposite_party"]

        data["target_number"] = target

        unknown_count = int(
            (
                data["call_direction"]
                == "UNKNOWN"
            ).sum()
        )

        print(
            "[+] Direction realignment complete. "
            f"Target: {target}"
        )

        if unknown_count > 0:
            print(
                f"[!] Direction Warning: {unknown_count} rows "
                "ki direction identify nahi hui."
            )

        return data

    except Exception as error:
        print_loader_error(
            "Target direction realignment failed.",
            error,
        )
        return data


# ==============================================================
# HEADER DETECTION
# ==============================================================

def split_header_line(line, delimiter):
    """CSV-aware header line splitting."""

    try:
        return next(
            csv.reader(
                [line],
                delimiter=delimiter,
            )
        )

    except Exception:
        return line.rstrip("\n").split(delimiter)


def find_header_row(file_path, max_lines=200):
    """
    Actual CDR table header detect karta hai.

    Maximum-columns-only approach ke bajay known telecom columns ka
    score calculate karta hai.
    """

    lines = []

    with open(
        file_path,
        "r",
        encoding="utf-8-sig",
        errors="ignore",
    ) as file:
        for index, line in enumerate(file):
            if index >= max_lines:
                break

            lines.append(line)

    best_match = None

    possible_delimiters = [
        ",",
        "\t",
        "|",
    ]

    core_columns = {
        "a_party",
        "b_party",
        "call_date",
        "call_time",
        "call_duration",
        "call_type",
        "imei",
        "imsi",
        "first_cell_id",
    }

    for line_index, line in enumerate(lines):
        for delimiter in possible_delimiters:
            fields = split_header_line(
                line,
                delimiter,
            )

            if len(fields) < 2:
                continue

            normalized_fields = [
                normalize_column_name(field)
                for field in fields
            ]

            mapped_fields = [
                COLUMN_MAPPER.get(field)
                for field in normalized_fields
            ]

            recognized_count = sum(
                field is not None
                for field in mapped_fields
            )

            recognized_core = {
                field
                for field in mapped_fields
                if field in core_columns
            }

            score = (
                recognized_count * 20
                + len(recognized_core) * 30
                + len(fields)
            )

            if len(recognized_core) < 3:
                continue

            if (
                best_match is None
                or score > best_match["score"]
            ):
                best_match = {
                    "score": score,
                    "line_index": line_index,
                    "delimiter": delimiter,
                    "column_count": len(fields),
                }

    if best_match is not None:
        return (
            best_match["line_index"],
            best_match["delimiter"],
            best_match["column_count"],
        )

    raise ValueError(
        "Recognized CDR header not found. The file was not parsed using an "
        "unverified widest-row fallback."
    )


# ==============================================================
# SINGLE FILE LOADER
# ==============================================================

def get_single_file(folder):
    """
    Single CDR folder se first CSV file load karta hai.

    Pipeline:
    1. File validation
    2. Smart header detection
    3. Safe CSV parsing
    4. Column standardization
    5. Required-column validation
    6. Data cleaning
    7. Footer / invalid row removal
    """

    if not os.path.isdir(folder):
        print(f"[-] Directory nahi mili: {folder}")
        return None

    files = sorted(
        file
        for file in os.listdir(folder)
        if file.lower().endswith(".csv")
    )

    if not files:
        print(
            f"[-] Folder '{folder}' mein koi CSV file nahi mili."
        )
        return None

    if len(files) > 1:
        print(
            f"[-] Single CDR folder mein {len(files)} CSV files hain. "
            "Ambiguous input ko auto-select nahi kiya gaya. "
            "Sirf ek CSV rakhein ya Multiple CDR workflow use karein."
        )
        return None

    file_name = files[0]
    file_path = os.path.join(
        folder,
        file_name,
    )

    print(f"[+] Processing file: {file_name}")

    try:
        (
            actual_header_index,
            delimiter,
            detected_columns,
        ) = find_header_row(file_path)

        delimiter_name = {
            ",": "COMMA",
            "\t": "TAB",
            "|": "PIPE",
        }.get(
            delimiter,
            repr(delimiter),
        )

        print(
            f"[+] Real data header found at line: "
            f"{actual_header_index + 1}"
        )

        print(
            f"[+] Delimiter: {delimiter_name} | "
            f"Detected columns: {detected_columns}"
        )

        # Malformed rows are quarantined with physical line provenance.
        df, rejected_rows, ingestion_metadata = read_csv_with_quarantine(
            file_path,
            skiprows=actual_header_index,
            sep=delimiter,
            encoding="utf-8-sig",
        )

        if not rejected_rows.empty:
            print(
                f"[!] Quarantined {len(rejected_rows)} malformed CSV row(s)."
            )

        if df is None or df.empty:
            print("[-] CSV parser returned empty data.")
            return None

        df = clean_and_standardise_columns(df)

        if df.empty:
            print(
                "[-] Column standardization ke baad "
                "DataFrame empty hai."
            )
            return None

        required_columns = [
            "a_party",
            "b_party",
            "call_date",
            "call_time",
        ]

        missing_columns = [
            column
            for column in required_columns
            if column not in df.columns
        ]

        if missing_columns:
            print(
                "[-] Required CDR columns missing: "
                f"{missing_columns}"
            )

            print(
                f"[+] Available columns: "
                f"{df.columns.tolist()}"
            )

            return None

        df = clean_data_values(df)

        # ------------------------------------------------------
        # REMOVE FOOTER, DISCLAIMER AND INVALID ROWS
        # ------------------------------------------------------

        if "datetime" in df.columns:
            invalid_datetime = df["datetime"].isna()
            invalid_count = int(invalid_datetime.sum())

            if invalid_count > 0:
                print(
                    f"[!] Quarantining {invalid_count} footer, metadata "
                    "or invalid date/time row(s)."
                )
                validation_rejects = quarantine_dataframe_rows(
                    df,
                    invalid_datetime,
                    source_file=file_path,
                    reason="INVALID_OR_NON_DATA_CDR_TIMESTAMP",
                )
                rejected_rows = pd.concat(
                    [rejected_rows, validation_rejects],
                    ignore_index=True,
                )
                df = df.loc[~invalid_datetime].copy()

        df = df.dropna(
            how="all"
        ).reset_index(
            drop=True
        )

        if df.empty:
            print(
                "[-] Valid CDR records nahi mile."
            )
            return None

        print(
            "[+] Data loaded and standardized successfully."
        )

        print(
            f"[+] Valid CDR records: {len(df)}"
        )

        print(
            f"[+] Standardized columns: "
            f"{df.columns.tolist()}"
        )

        df.attrs["rejected_rows"] = rejected_rows.reset_index(drop=True)
        df.attrs["ingestion_metadata"] = ingestion_metadata
        df.attrs["source_file"] = str(file_path)
        return df

    except Exception as error:
        print_loader_error(
            f"Error loading file '{file_name}'.",
            error,
        )
        return None