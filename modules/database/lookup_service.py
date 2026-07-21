"""Canonical SDR and CGI lookup service.

This module does not duplicate SDR or CGI repositories.

SDR:
    Uses the existing large DuckDB SDR lookup first and the primary
    SDR table as fallback through lookup_sdr_subscribers().

CGI:
    Uses the existing canonical CGI repository.

Every new public lookup returns a structured status so DATABASE_ERROR
is not incorrectly displayed as NOT_FOUND.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from modules.enrichment.sdr_subscriber_enrichment import (
    lookup_sdr_subscribers,
    normalize_mobile_number,
)

from .cgi_repository import (
    create_cgi_table,
    lookup_cgi,
    normalize_cgi,
)

from .sdr_repository import (
    create_sdr_table,
    lookup_mobile,
)


MATCHED = "MATCHED"
NOT_FOUND = "NOT_FOUND"
INVALID_INPUT = "INVALID_INPUT"
DATABASE_ERROR = "DATABASE_ERROR"


def _clean_text(value: object) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (
        TypeError,
        ValueError,
    ):
        pass

    text = str(value).strip()

    if text.casefold() in {
        "",
        "nan",
        "none",
        "<na>",
        "null",
    }:
        return ""

    return text


def clean_display_address(
    value: object,
) -> str:
    """Create a readable display copy without changing raw SDR data."""

    text = _clean_text(value)

    if not text:
        return ""

    # Telecom master files often use !, | or ^ as field separators.
    text = re.sub(
        r"[!|^]+",
        ", ",
        text,
    )

    text = re.sub(
        r"\s*,\s*",
        ", ",
        text,
    )

    text = re.sub(
        r"(?:,\s*){2,}",
        ", ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip(
        " ,"
    )


def lookup_sdr_profile(
    number: object,
) -> dict[str, Any]:
    """Return one structured SDR lookup result."""

    entered_number = _clean_text(
        number
    )

    normalized_number = (
        normalize_mobile_number(
            entered_number
        )
    )

    if not normalized_number:
        return {
            "status": INVALID_INPUT,
            "found": False,
            "entered_number": entered_number,
            "normalized_number": "",
            "record": {},
            "records": [],
            "message": (
                "Valid 10-digit Indian mobile number required hai."
            ),
        }

    try:
        dataframe = lookup_sdr_subscribers(
            [
                normalized_number,
            ]
        )

    except Exception as error:
        return {
            "status": DATABASE_ERROR,
            "found": False,
            "entered_number": entered_number,
            "normalized_number": normalized_number,
            "record": {},
            "records": [],
            "error_type": type(error).__name__,
            "error": str(error),
            "message": (
                "SDR database query execute nahi hui."
            ),
        }

    if (
        not isinstance(
            dataframe,
            pd.DataFrame,
        )
        or dataframe.empty
    ):
        return {
            "status": NOT_FOUND,
            "found": False,
            "entered_number": entered_number,
            "normalized_number": normalized_number,
            "record": {},
            "records": [],
            "message": (
                "SDR profile database mein nahi mila."
            ),
        }

    work = dataframe.copy()

    if "sdr_found" in work.columns:
        found_mask = (
            work["sdr_found"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.casefold()
            .isin(
                {
                    "yes",
                    "true",
                    "1",
                    "found",
                }
            )
        )

        work = work.loc[
            found_mask
        ].copy()

    if work.empty:
        return {
            "status": NOT_FOUND,
            "found": False,
            "entered_number": entered_number,
            "normalized_number": normalized_number,
            "record": {},
            "records": [],
            "message": (
                "Number normalize hua, lekin SDR profile nahi mila."
            ),
        }

    records: list[
        dict[str, Any]
    ] = []

    for _, row in work.iterrows():
        raw_address = _clean_text(
            row.get(
                "subscriber_address",
                row.get(
                    "address",
                    "",
                ),
            )
        )

        records.append(
            {
                "mobile_number": _clean_text(
                    row.get(
                        "lookup_mobile",
                        row.get(
                            "mobile_number",
                            normalized_number,
                        ),
                    )
                )
                or normalized_number,
                "subscriber_name": _clean_text(
                    row.get(
                        "subscriber_name",
                        "",
                    )
                ),
                "father_name": _clean_text(
                    row.get(
                        "father_name",
                        "",
                    )
                ),
                "raw_address": raw_address,
                "clean_address": clean_display_address(
                    raw_address
                ),
                "id_type": _clean_text(
                    row.get(
                        "id_type",
                        "",
                    )
                ),
                "id_number": _clean_text(
                    row.get(
                        "id_number",
                        "",
                    )
                ),
                # Some SDR sources contain a dataset/source category
                # in this field instead of a verified telecom operator.
                "operator_or_source_category": _clean_text(
                    row.get(
                        "operator",
                        "",
                    )
                ),
                "circle": _clean_text(
                    row.get(
                        "circle",
                        "",
                    )
                ),
                "activation_date": _clean_text(
                    row.get(
                        "activation_date",
                        "",
                    )
                ),
                "caf_number": _clean_text(
                    row.get(
                        "caf_number",
                        "",
                    )
                ),
                "source_file": _clean_text(
                    row.get(
                        "source_file",
                        "",
                    )
                ),
            }
        )

    return {
        "status": MATCHED,
        "found": True,
        "entered_number": entered_number,
        "normalized_number": normalized_number,
        "record": records[0],
        "records": records,
        "match_count": len(records),
        "message": (
            "SDR profile matched."
        ),
    }


def lookup_cgi_profile(
    cgi_value: object,
) -> dict[str, Any]:
    """Return one structured CGI/Cell lookup result."""

    entered_cgi = _clean_text(
        cgi_value
    )

    normalized_cgi = normalize_cgi(
        entered_cgi
    )

    if not normalized_cgi:
        return {
            "status": INVALID_INPUT,
            "found": False,
            "entered_cgi": entered_cgi,
            "normalized_cgi": "",
            "record": {},
            "message": (
                "Valid CGI / Cell ID required hai."
            ),
        }

    try:
        result = lookup_cgi(
            normalized_cgi
        )

    except Exception as error:
        return {
            "status": DATABASE_ERROR,
            "found": False,
            "entered_cgi": entered_cgi,
            "normalized_cgi": normalized_cgi,
            "record": {},
            "error_type": type(error).__name__,
            "error": str(error),
            "message": (
                "CGI database query execute nahi hui."
            ),
        }

    if not isinstance(
        result,
        dict,
    ) or not result:
        return {
            "status": NOT_FOUND,
            "found": False,
            "entered_cgi": entered_cgi,
            "normalized_cgi": normalized_cgi,
            "record": {},
            "message": (
                "CGI / Cell database mein nahi mila."
            ),
        }

    record = {
        "cgi": _clean_text(
            result.get(
                "cgi",
                normalized_cgi,
            )
        )
        or normalized_cgi,
        "operator": _clean_text(
            result.get(
                "operator",
                "",
            )
        ),
        "circle": _clean_text(
            result.get(
                "circle",
                "",
            )
        ),
        "state": _clean_text(
            result.get(
                "state",
                "",
            )
        ),
        "district": _clean_text(
            result.get(
                "district",
                "",
            )
        ),
        "police_station": _clean_text(
            result.get(
                "police_station",
                "",
            )
        ),
        "address": _clean_text(
            result.get(
                "address",
                "",
            )
        ),
        "town": _clean_text(
            result.get(
                "town",
                "",
            )
        ),
        "landmark": _clean_text(
            result.get(
                "landmark",
                "",
            )
        ),
        "site_name": _clean_text(
            result.get(
                "site_name",
                "",
            )
        ),
        "latitude": _clean_text(
            result.get(
                "latitude",
                "",
            )
        ),
        "longitude": _clean_text(
            result.get(
                "longitude",
                "",
            )
        ),
        "azimuth": _clean_text(
            result.get(
                "azimuth",
                "",
            )
        ),
        "technology": _clean_text(
            result.get(
                "technology",
                "",
            )
        ),
        "status": _clean_text(
            result.get(
                "status",
                "",
            )
        ),
        "status_change_date": _clean_text(
            result.get(
                "status_change_date",
                "",
            )
        ),
        "mcc_mnc": _clean_text(
            result.get(
                "mcc_mnc",
                "",
            )
        ),
        "lac": _clean_text(
            result.get(
                "lac",
                "",
            )
        ),
        "cid": _clean_text(
            result.get(
                "cid",
                "",
            )
        ),
        "tac_id": _clean_text(
            result.get(
                "tac_id",
                "",
            )
        ),
        "site_id": _clean_text(
            result.get(
                "site_id",
                "",
            )
        ),
        "gnb_id": _clean_text(
            result.get(
                "gnb_id",
                "",
            )
        ),
        "cell_id": _clean_text(
            result.get(
                "cell_id",
                "",
            )
        ),
        "source_file": _clean_text(
            result.get(
                "source_file",
                "",
            )
        ),
    }

    return {
        "status": MATCHED,
        "found": True,
        "entered_cgi": entered_cgi,
        "normalized_cgi": normalized_cgi,
        "record": record,
        "message": (
            "CGI / Cell record matched."
        ),
    }


# ------------------------------------------------------------------
# Existing compatibility API
# ------------------------------------------------------------------

def initialize_master_lookup_database() -> None:
    create_cgi_table()
    create_sdr_table()


def lookup_number_identity(
    number: str,
):
    """Legacy exact primary-table SDR lookup."""

    return lookup_mobile(
        number
    )


def lookup_tower_address(
    cgi: str,
):
    """Legacy exact CGI lookup."""

    return lookup_cgi(
        cgi
    )
