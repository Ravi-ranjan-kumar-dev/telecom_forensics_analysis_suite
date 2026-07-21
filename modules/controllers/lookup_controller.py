"""Simple investigator-facing SDR and CGI lookup menu."""

from __future__ import annotations

from typing import Any

from modules.database.lookup_service import (
    DATABASE_ERROR,
    INVALID_INPUT,
    MATCHED,
    NOT_FOUND,
    lookup_cgi_profile,
    lookup_sdr_profile,
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


def _run_sdr_lookup(
    case: dict[str, Any] | None,
) -> None:
    print("\n" + "=" * 86)
    print("SDR NUMBER LOOKUP")
    print("=" * 86)

    number = input(
        "Mobile Number: "
    ).strip()

    result = lookup_sdr_profile(
        number
    )

    status = str(
        result.get(
            "status",
            "",
        )
    )

    _log_lookup_event(
        case,
        lookup_type="SDR",
        query=number,
        status=status,
    )

    if status == INVALID_INPUT:
        print(
            f"[-] {result.get('message')}"
        )
        return

    if status == DATABASE_ERROR:
        print(
            "[-] SDR database lookup failed."
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
            f"[-] {result.get('message')}"
        )
        print(
            "    Normalized Number: "
            f"{result.get('normalized_number', '')}"
        )
        return

    if status != MATCHED:
        print(
            "[-] Unknown SDR lookup status."
        )
        return

    record = dict(
        result.get(
            "record",
            {},
        )
    )

    print("\n" + "-" * 86)
    print("SDR PROFILE FOUND")
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


def _run_cgi_lookup(
    case: dict[str, Any] | None,
) -> None:
    print("\n" + "=" * 86)
    print("CGI / CELL ADDRESS LOOKUP")
    print("=" * 86)

    value = input(
        "CGI / Cell ID: "
    ).strip()

    result = lookup_cgi_profile(
        value
    )

    status = str(
        result.get(
            "status",
            "",
        )
    )

    _log_lookup_event(
        case,
        lookup_type="CGI",
        query=value,
        status=status,
    )

    if status == INVALID_INPUT:
        print(
            f"[-] {result.get('message')}"
        )
        return

    if status == DATABASE_ERROR:
        print(
            "[-] CGI database lookup failed."
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
            f"[-] {result.get('message')}"
        )
        print(
            "    Normalized CGI: "
            f"{result.get('normalized_cgi', '')}"
        )
        return

    if status != MATCHED:
        print(
            "[-] Unknown CGI lookup status."
        )
        return

    record = dict(
        result.get(
            "record",
            {},
        )
    )

    print("\n" + "-" * 86)
    print("CGI / CELL RECORD FOUND")
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


def run_lookup_services(
    case: dict[str, Any] | None = None,
) -> None:
    """Run the simple investigator lookup workspace."""

    while True:
        try:
            print("\n" + "=" * 86)
            print("LOOKUP SERVICES")
            print("=" * 86)
            print("1. SDR Number Lookup")
            print("2. CGI / Cell Address Lookup")
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

            elif choice == "0":
                return

            else:
                print(
                    "[-] Invalid choice. Select 0, 1 or 2."
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
