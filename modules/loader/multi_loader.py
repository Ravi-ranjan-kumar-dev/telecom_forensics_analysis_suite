# modules/loader/multi_loader.py

import os
import traceback
import hashlib
from pathlib import Path

import pandas as pd

from modules.loader.duplicate_flags import flag_potential_duplicates
from modules.loader.identity import (
    detect_target,
    detect_target_from_dataframe as _detect_target_from_dataframe,
    detect_target_from_filename as _detect_target_from_filename,
    detect_target_from_metadata as _detect_target_from_metadata,
    normalize_msisdn,
)
from modules.loader.evidence_csv import (
    quarantine_dataframe_rows,
    read_csv_with_quarantine,
)

from modules.loader.single_loader import (
    find_header_row,
    clean_and_standardise_columns,
    clean_data_values,
    realign_target_and_b_party,
)


# ==============================================================
# ERROR DISPLAY
# ==============================================================


# MULTI_CDR_EXACT_DUPLICATE_FILE_GUARD_V1
def _sha256_file_for_duplicate_guard(file_path):
    """Return SHA256 hash of an input CDR file without changing file content."""
    digest = hashlib.sha256()

    candidate_path = Path(file_path)

    if not candidate_path.is_absolute() and not candidate_path.exists():
        possible_paths = [
            Path.cwd() / candidate_path,
            Path("data/cdr/multiple") / candidate_path,
        ]

        for possible_path in possible_paths:
            if possible_path.exists():
                candidate_path = possible_path
                break

    with open(candidate_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _remove_exact_duplicate_input_files(files):
    """
    Keep only one copy of an exactly identical input file.

    This prevents double-counting when the same CDR file is present with two
    names, for example cdr1.csv and original LEA...csv.
    """
    seen_hashes = {}
    unique_files = []
    duplicate_files = []

    for file_path in files:
        try:
            file_hash = _sha256_file_for_duplicate_guard(file_path)
        except Exception as error:
            print(f"[!] Could not hash file for duplicate check: {file_path} | {error}")
            unique_files.append(file_path)
            continue

        if file_hash in seen_hashes:
            duplicate_files.append(
                {
                    "duplicate": file_path,
                    "original": seen_hashes[file_hash],
                    "sha256": file_hash,
                }
            )
            continue

        seen_hashes[file_hash] = file_path
        unique_files.append(file_path)

    return unique_files, duplicate_files

def print_loader_error(title, error):
    """Error ka readable message aur short traceback print karta hai."""

    print(f"\n[-] {title}")
    print(f"    Error Type : {type(error).__name__}")
    print(f"    Message    : {error}")
    print("    Error Trace:")
    print(traceback.format_exc(limit=3).rstrip())


# ==============================================================
# MOBILE NUMBER NORMALIZATION
# ==============================================================

def normalize_mobile_number(value):
    """Backward-compatible wrapper around canonical MSISDN normalization."""

    return normalize_msisdn(value)


def detect_target_from_metadata(file_path):
    return _detect_target_from_metadata(file_path)


def detect_target_from_filename(file_name):
    return _detect_target_from_filename(file_name)


def detect_target_from_dataframe(df):
    return _detect_target_from_dataframe(df).target


def detect_target_number(file_path, file_name, df):
    result = detect_target(
        file_path=file_path,
        file_name=file_name,
        dataframe=df,
    )
    if result.warning:
        print(f"[!] Target detection: {result.warning}")
    return result.target, result.method


def detect_target_number_fallback(file_name, df):
    target = _detect_target_from_filename(file_name)
    if target:
        return target
    return _detect_target_from_dataframe(df).target


# ==============================================================
# SINGLE FILE PARSER
# ==============================================================

def load_one_cdr_file(file_path, file_name):
    """
    Ek CDR file ko parse, clean, target-detect aur realign karta hai.

    Returns:
        Dictionary:
            {
                "file": file_name,
                "target": target,
                "target_method": method,
                "df": DataFrame
            }

        Error ya invalid file hone par None.
    """

    print(f"\n[+] Loading: {file_name}")

    try:
        # ------------------------------------------------------
        # 1. SMART HEADER DETECTION
        # ------------------------------------------------------

        (
            header_index,
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
            f"[+] Header Line: {header_index + 1} | "
            f"Delimiter: {delimiter_name} | "
            f"Columns: {detected_columns}"
        )

        # ------------------------------------------------------
        # 2. SAFE CSV PARSING
        # ------------------------------------------------------

        df, rejected_rows, ingestion_metadata = read_csv_with_quarantine(
            file_path,
            skiprows=header_index,
            sep=delimiter,
            encoding="utf-8-sig",
        )

        if not rejected_rows.empty:
            print(
                f"[!] {file_name}: quarantined "
                f"{len(rejected_rows)} malformed row(s)."
            )

        if df is None or df.empty:
            print(
                f"[-] Empty data returned from file: {file_name}"
            )
            return None

        # ------------------------------------------------------
        # 3. COLUMN STANDARDIZATION
        # ------------------------------------------------------

        df = clean_and_standardise_columns(df)

        if df is None or df.empty:
            print(
                f"[-] Column standardization failed: {file_name}"
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
                f"[-] Required columns missing in {file_name}: "
                f"{missing_columns}"
            )

            print(
                f"    Available columns: {df.columns.tolist()}"
            )

            return None

        # ------------------------------------------------------
        # 4. VALUE CLEANING
        # ------------------------------------------------------

        df = clean_data_values(df)

        if df is None or df.empty:
            print(
                f"[-] Data cleaning returned empty data: {file_name}"
            )
            return None

        # ------------------------------------------------------
        # 5. REMOVE FOOTER / INVALID ROWS
        # ------------------------------------------------------

        if "datetime" in df.columns:
            valid_datetime_count = int(
                df["datetime"].notna().sum()
            )

            invalid_datetime_count = int(
                df["datetime"].isna().sum()
            )

            # Invalid rows tabhi remove karein jab kuch valid
            # datetime records available hon.
            if (
                valid_datetime_count > 0
                and invalid_datetime_count > 0
            ):
                print(
                    f"[!] Quarantining {invalid_datetime_count} "
                    "footer/metadata/invalid row(s)."
                )
                invalid_mask = df["datetime"].isna()
                validation_rejects = quarantine_dataframe_rows(
                    df,
                    invalid_mask,
                    source_file=file_path,
                    reason="INVALID_OR_NON_DATA_CDR_TIMESTAMP",
                )
                rejected_rows = pd.concat(
                    [rejected_rows, validation_rejects],
                    ignore_index=True,
                )
                df = df.loc[df["datetime"].notna()].copy()

        df = (
            df
            .dropna(how="all")
            .reset_index(drop=True)
        )

        if df.empty:
            print(
                f"[-] No valid CDR records found: {file_name}"
            )
            return None

        # ------------------------------------------------------
        # 6. TARGET DETECTION
        # ------------------------------------------------------

        target, detection_method = detect_target_number(
            file_path,
            file_name,
            df,
        )

        if not target:
            print(
                f"[-] Target number not detected in "
                f"{file_name}. File skipped."
            )
            return None

        print(
            f"[+] Target Detected: {target} "
            f"(Method: {detection_method})"
        )

        # ------------------------------------------------------
        # 7. TARGET-CENTRIC REALIGNMENT
        # ------------------------------------------------------

        df = realign_target_and_b_party(
            df,
            target,
        )

        if df is None or df.empty:
            print(
                f"[-] Realignment failed: {file_name}"
            )
            return None

        if "b_party" not in df.columns:
            print(
                f"[-] b_party not created after "
                f"realignment: {file_name}"
            )
            return None

        # Evidence-source tracking. Physical source row is preserved by
        # read_csv_with_quarantine and survives column standardisation.
        df["source_file"] = file_name
        df.attrs["rejected_rows"] = rejected_rows.reset_index(drop=True)
        df.attrs["ingestion_metadata"] = ingestion_metadata

        print(
            f"[+] Successfully Loaded: "
            f"{file_name} ({len(df)} records)"
        )

        return {
            "file": file_name,
            "target": target,
            "target_method": detection_method,
            "df": df,
            "rejected_rows": rejected_rows.reset_index(drop=True),
            "ingestion_metadata": ingestion_metadata,
        }

    except Exception as error:
        print_loader_error(
            f"Error while loading '{file_name}'.",
            error,
        )

        return None


# ==============================================================
# DUPLICATE TARGET MERGING
# ==============================================================

def merge_same_target_cdrs(cdrs):
    """
    Ek hi target ki multiple files ko ek DataFrame mein merge karta hai.

    Isse cdr_controller.py mein dictionary overwrite problem nahi hogi.
    """

    merged_targets = {}

    for item in cdrs:
        target = item["target"]

        # DataFrame attrs mein rejected_rows DataFrame ho sakta hai.
        # Pandas concat attrs compare karta hai, isliye merge copy
        # se attrs hata diye jaate hain.
        source_df = item["df"].copy()
        source_df.attrs = {}

        if target not in merged_targets:
            merged_targets[target] = {
                "file_names": [item["file"]],
                "target": target,
                "target_method": item.get(
                    "target_method",
                    "unknown",
                ),
                "df": source_df,
                "rejected_rows": [
                    item.get("rejected_rows")
                ] if isinstance(
                    item.get("rejected_rows"),
                    pd.DataFrame,
                ) else [],
                "ingestion_metadata": [
                    item.get("ingestion_metadata", {})
                ],
            }
            continue

        merged_targets[target]["file_names"].append(
            item["file"]
        )

        merged_targets[target]["df"] = pd.concat(
            [
                merged_targets[target]["df"],
                source_df,
            ],
            ignore_index=True,
            sort=False,
        )

        rejected = item.get("rejected_rows")
        if isinstance(rejected, pd.DataFrame):
            merged_targets[target]["rejected_rows"].append(
                rejected
            )

        merged_targets[target]["ingestion_metadata"].append(
            item.get("ingestion_metadata", {})
        )

    final_cdrs = []

    for target, item in merged_targets.items():
        combined_df = item["df"]

        # Forensic records are never deleted merely because their displayed
        # attributes match. Potential duplicates are retained and flagged.
        combined_df = flag_potential_duplicates(combined_df)

        duplicate_count = int(
            combined_df.get(
                "is_potential_duplicate",
                pd.Series(False, index=combined_df.index),
            ).sum()
        )

        if duplicate_count:
            print(
                f"[!] Target {target}: {duplicate_count} record(s) "
                "flagged as potential duplicates; none removed."
            )

        combined_df = combined_df.reset_index(drop=True)

        rejected_frames = [
            frame
            for frame in item.get("rejected_rows", [])
            if isinstance(frame, pd.DataFrame) and not frame.empty
        ]

        rejected_rows = (
            pd.concat(
                rejected_frames,
                ignore_index=True,
                sort=False,
            )
            if rejected_frames
            else pd.DataFrame()
        )

        combined_df.attrs["rejected_rows"] = rejected_rows
        combined_df.attrs["ingestion_metadata"] = item.get(
            "ingestion_metadata",
            [],
        )

        final_cdrs.append(
            {
                "file": ", ".join(item["file_names"]),
                "files": item["file_names"],
                "target": target,
                "target_method": item["target_method"],
                "df": combined_df,
                "rejected_rows": rejected_rows,
                "ingestion_metadata": item.get(
                    "ingestion_metadata",
                    [],
                ),
            }
        )

    return final_cdrs


# ==============================================================
# MULTIPLE CDR LOADER
# ==============================================================

def load_multiple_cdr(folder):
    """
    Multiple folder ke sabhi CSV files safely load karta hai.

    Kisi ek file mein error hone par:
    - error print hoga;
    - file skip hogi;
    - baaki files process hoti rahengi.
    """

    if not os.path.isdir(folder):
        print(f"[-] Folder nahi mila: {folder}")
        return []

    files = sorted(
        file_name
        for file_name in os.listdir(folder)
        if file_name.lower().endswith(".csv")
    )

    if not files:
        print(
            f"[-] Folder '{folder}' mein koi CSV file nahi mili."
        )
        return []

    print("\n" + "=" * 70)
    print("MULTIPLE CDR LOADER")
    print("=" * 70)
    print(f"[+] CSV Files Found: {len(files)}")

    files, exact_duplicate_files = _remove_exact_duplicate_input_files(files)

    for duplicate_info in exact_duplicate_files:
        duplicate_path = duplicate_info["duplicate"]
        original_path = duplicate_info["original"]
        print(
            "[!] Skipping exact duplicate CDR input file: "
            f"{duplicate_path.name} | Original already loaded: {original_path.name}"
        )

    if exact_duplicate_files:
        print(f"[+] Exact duplicate input files skipped: {len(exact_duplicate_files)}")

    loaded_cdrs = []
    failed_files = []

    for file_name in files:
        file_path = os.path.join(
            folder,
            file_name,
        )

        result = load_one_cdr_file(
            file_path,
            file_name,
        )

        if result is None:
            failed_files.append(file_name)
            continue

        loaded_cdrs.append(result)

    # Same target ki files merge karein
    loaded_cdrs = merge_same_target_cdrs(
        loaded_cdrs
    )

    # ==========================================================
    # SUMMARY
    # ==========================================================

    print("\n" + "=" * 75)
    print(f"{'LOADED CDR TARGET SUMMARY':^75}")
    print("=" * 75)

    if not loaded_cdrs:
        print("No valid CDR files loaded.")

    else:
        for index, cdr in enumerate(
            loaded_cdrs,
            start=1,
        ):
            print(
                f"{index:<3} "
                f"Target: {cdr['target']:<15} "
                f"Files: {len(cdr.get('files', [])):<4} "
                f"Records: {len(cdr['df'])}"
            )

            for file_name in cdr.get(
                "files",
                [],
            ):
                print(f"      - {file_name}")

    print("-" * 75)
    print(
        f"Unique Targets Loaded : {len(loaded_cdrs)}"
    )
    print(
        f"Files Failed/Skipped  : {len(failed_files)}"
    )
    print("=" * 75)

    if failed_files:
        print("\n[-] Failed or skipped files:")

        for file_name in failed_files:
            print(f"    - {file_name}")

    return loaded_cdrs
