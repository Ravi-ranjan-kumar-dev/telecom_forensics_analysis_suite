"""Simple investigator-facing SDR and CGI lookup menu."""

from __future__ import annotations

from typing import Any

from modules.database.lookup_service import (
    DATABASE_ERROR,
    INVALID_INPUT,
    MATCHED,
    NOT_FOUND,
    lookup_sdr_profiles,   # 🆕 batch function
    lookup_cgi_profiles,   # 🆕 batch function
)


def _display_value(
    value: object,
) -> str:
    text = str(
        value
        if value is not None
        else ""
    ).strip()

    return text or "-"


def _print_fields(
    record: dict[str, Any],
    fields: list[
        tuple[str, str]
    ],
) -> None:
    for key, label in fields:
        print(
            f"{label:<28}: "
            f"{_display_value(record.get(key, ''))}"
        )


def _log_lookup_event(
    case: dict[str, Any] | None,
    *,
    lookup_type: str,
    query: str,
    status: str,
) -> None:
    """Log minimal lookup metadata without copying subscriber details."""

    if not isinstance(
        case,
        dict,
    ):
        return

    case_id = str(
        case.get(
            "case_id",
            "",
        )
    ).strip()

    if not case_id:
        return

    try:
        from modules.cases import (
            log_case_event,
        )

        clean_query = str(
            query
        ).strip()

        log_case_event(
            case_id,
            action=(
                f"{lookup_type.upper()}_LOOKUP"
            ),
            details={
                "lookup_type": (
                    lookup_type.upper()
                ),
                "query_length": len(
                    clean_query
                ),
                "query_last_four": (
                    clean_query[-4:]
                    if clean_query
                    else ""
                ),
                "status": status,
            },
        )

    except Exception:
        # Lookup must not fail only because audit logging failed.
        return


def _print_sdr_result(
    result: dict[str, Any],
    *,
    index: int = 1,
) -> None:
    """Print one SDR lookup result in structured format."""
    status = str(
        result.get(
            "status",
            "",
        )
    )

    if status == INVALID_INPUT:
        print(
            f"\n[{index}] {result.get('message')}"
        )
        return

    if status == DATABASE_ERROR:
        print(
            f"\n[{index}] SDR database lookup failed."
        )
        print(
            f"    Error Type : "
            f"{result.get('error_type', '')}"
        )
        print(
            f"    Message    : "
            f"{result.get('error', '')}"
        )
        return

    if status == NOT_FOUND:
        print(
            f"\n[{index}] {result.get('message')}"
        )
        print(
            "    Normalized Number: "
            f"{result.get('normalized_number', '')}"
        )
        return

    if status != MATCHED:
        print(
            f"\n[{index}] Unknown SDR lookup status."
        )
        return

    record = dict(
        result.get(
            "record",
            {},
        )
    )

    print("\n" + "-" * 86)
    print(f"SDR PROFILE FOUND (Result {index})")
    print("-" * 86)

    _print_fields(
        record,
        [
            (
                "mobile_number",
                "Mobile Number",
            ),
            (
                "subscriber_name",
                "Subscriber Name",
            ),
            (
                "father_name",
                "Father / Husband Name",
            ),
            (
                "clean_address",
                "Readable Address",
            ),
            (
                "raw_address",
                "Raw SDR Address",
            ),
            (
                "id_type",
                "Identity Type",
            ),
            (
                "id_number",
                "Identity Number",
            ),
            (
                "operator_or_source_category",
                "Operator / Source Category",
            ),
            (
                "circle",
                "Circle",
            ),
            (
                "activation_date",
                "Activation Date",
            ),
            (
                "caf_number",
                "CAF Number",
            ),
            (
                "source_file",
                "Source File",
            ),
        ],
    )

    print(
        f"Match Count                 : "
        f"{result.get('match_count', 1)}"
    )

    print("\n[+] SDR profile found.")
    print(
        "[!] Identity and address ko CAF/operator "
        "record se verify karein."
    )


def _print_cgi_result(
    result: dict[str, Any],
    *,
    index: int = 1,
) -> None:
    """Print one CGI lookup result in structured format."""
    status = str(
        result.get(
            "status",
            "",
        )
    )

    if status == INVALID_INPUT:
        print(
            f"\n[{index}] {result.get('message')}"
        )
        return

    if status == DATABASE_ERROR:
        print(
            f"\n[{index}] CGI database lookup failed."
        )
        print(
            f"    Error Type : "
            f"{result.get('error_type', '')}"
        )
        print(
            f"    Message    : "
            f"{result.get('error', '')}"
        )
        return

    if status == NOT_FOUND:
        print(
            f"\n[{index}] {result.get('message')}"
        )
        print(
            "    Normalized CGI: "
            f"{result.get('normalized_cgi', '')}"
        )
        return

    if status != MATCHED:
        print(
            f"\n[{index}] Unknown CGI lookup status."
        )
        return

    record = dict(
        result.get(
            "record",
            {},
        )
    )

    print("\n" + "-" * 86)
    print(f"CGI / CELL RECORD FOUND (Result {index})")
    print("-" * 86)

    _print_fields(
        record,
        [
            (
                "cgi",
                "CGI / Cell ID",
            ),
            (
                "operator",
                "Operator",
            ),
            (
                "technology",
                "Technology",
            ),
            (
                "circle",
                "Circle",
            ),
            (
                "state",
                "State",
            ),
            (
                "district",
                "District",
            ),
            (
                "police_station",
                "Police Station",
            ),
            (
                "address",
                "Tower Address",
            ),
            (
                "town",
                "Town",
            ),
            (
                "landmark",
                "Landmark",
            ),
            (
                "site_name",
                "Site Name",
            ),
            (
                "latitude",
                "Latitude",
            ),
            (
                "longitude",
                "Longitude",
            ),
            (
                "azimuth",
                "Azimuth",
            ),
            (
                "status",
                "Tower Status",
            ),
            (
                "status_change_date",
                "Status Change Date",
            ),
            (
                "mcc_mnc",
                "MCC-MNC",
            ),
            (
                "lac",
                "LAC",
            ),
            (
                "cid",
                "CID",
            ),
            (
                "tac_id",
                "TAC",
            ),
            (
                "site_id",
                "Site ID",
            ),
            (
                "gnb_id",
                "gNB ID",
            ),
            (
                "cell_id",
                "Cell ID",
            ),
            (
                "source_file",
                "Source File",
            ),
        ],
    )

    print("\n[+] CGI / Cell record found.")
    print(
        "[!] Tower address aur coordinates ko current "
        "field/operator information se verify karein."
    )


def _run_sdr_lookup(
    case: dict[str, Any] | None,
) -> None:
    print("\n" + "=" * 86)
    print("SDR NUMBER LOOKUP")
    print("=" * 86)
    print("Ek se zyada numbers comma (,) ya space se alag karke enter karein.")
    print("Example: 9999999999, 1234567890")

    numbers_input = input(
        "Mobile Number(s): "
    ).strip()

    if not numbers_input:
        print("[-] No numbers entered.")
        return

    results = lookup_sdr_profiles(numbers_input)

    for idx, result in enumerate(results, start=1):
        _print_sdr_result(
            result,
            index=idx,
        )


def _run_cgi_lookup(
    case: dict[str, Any] | None,
) -> None:
    print("\n" + "=" * 86)
    print("CGI / CELL ADDRESS LOOKUP")
    print("=" * 86)
    print("Ek se zyada CGI comma (,) ya space se alag karke enter karein.")
    print("Example: 405-52-3347-232803094, 405-55-1234-56789012")

    cgi_input = input(
        "CGI / Cell ID(s): "
    ).strip()

    if not cgi_input:
        print("[-] No CGI entered.")
        return

    results = lookup_cgi_profiles(cgi_input)

    for idx, result in enumerate(results, start=1):
        _print_cgi_result(
            result,
            index=idx,
        )


def _run_master_data_import(
    case: dict[str, Any] | None = None,
) -> None:
    """Run the one-file SDR or CGI master-data import."""

    del case

    print("\n" + "=" * 86)
    print("MASTER DATA IMPORT")
    print("=" * 86)
    print(
        "Select one SDR or CGI master-data file. "
        "The data type and columns are detected automatically."
    )

    entered_path = input(
        "\nMaster data file path: "
    ).strip()

    entered_path = entered_path.strip(
        "\"'"
    )

    if not entered_path:
        print(
            "[-] No master data file was selected."
        )
        return

    from modules.database.master_import_service import (
        import_master_data_file,
    )

    result = import_master_data_file(
        entered_path,
        create_backup=True,
    )

    print("\n" + "-" * 86)
    print("MASTER DATA IMPORT RESULT")
    print("-" * 86)

    labels = (
        ("Status", "status"),
        ("Detected Type", "import_type"),
        ("Target Table", "target_table"),
        ("Source File", "source_file"),
        ("Rows Read", "rows_read"),
        ("Valid Rows", "valid_rows"),
        ("Invalid Rows", "invalid_rows"),
        ("Duplicate Rows", "duplicate_rows"),
        ("Inserted Rows", "inserted_rows"),
        ("Updated Rows", "updated_rows"),
        ("Skipped Rows", "skipped_rows"),
        ("Before Count", "before_count"),
        ("After Count", "after_count"),
        ("Historical Base Rows", "base_rows"),
        ("Duration Seconds", "duration_seconds"),
        ("Backup", "backup_path"),
        ("Import Log", "log_path"),
        ("Message", "message"),
    )

    for label, key in labels:
        value = result.get(
            key,
            "",
        )

        if value in {
            "",
            None,
        }:
            continue

        if isinstance(
            value,
            int,
        ):
            display_value = f"{value:,}"
        else:
            display_value = str(
                value
            )

        print(
            f"{label:<22}: "
            f"{display_value}"
        )

    status = str(
        result.get(
            "status",
            "",
        )
    )

    if status == "SUCCESS":
        print(
            "\n[+] Master data import completed successfully."
        )
    elif status.startswith(
        "SKIPPED"
    ):
        print(
            "\n[=] Master data import was safely skipped."
        )
    else:
        print(
            "\n[-] Master data import failed. "
            "Review the message and JSON import log."
        )


def run_lookup_services(
    case: dict[str, Any] | None = None,
) -> None:
    """Run the simple investigator lookup workspace."""

    while True:
        try:
            print("\n" + "=" * 86)
            print("LOOKUP SERVICES")
            print("=" * 86)
            print("1. SDR Number Lookup (Multiple allowed)")
            print("2. CGI / Cell Address Lookup (Multiple allowed)")
            print("3. Master Data Import")
            print("0. Back")

            choice = input(
                "\nChoose Action: "
            ).strip()

            if choice == "1":
                _run_sdr_lookup(
                    case
                )

            elif choice == "2":
                _run_cgi_lookup(
                    case
                )

            elif choice == "3":
                _run_master_data_import(
                    case
                )

            elif choice == "0":
                return

            else:
                print(
                    "[-] Invalid choice. "
                    "Select 0, 1, 2 or 3."
                )

        except KeyboardInterrupt:
            print(
                "\n[-] Returning to Case Workspace."
            )
            return

        except EOFError:
            return

        except Exception as error:
            print(
                "\n[-] Lookup Services failed."
            )
            print(
                f"    Error Type : "
                f"{type(error).__name__}"
            )
            print(
                f"    Message    : {error}"
            )