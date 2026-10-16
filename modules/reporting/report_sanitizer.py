"""Smart forensic Excel report sanitizer: drops empty sheets, blank columns, and internal fields."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


INTERNAL_UNWANTED_COLUMNS = {
    "record_type",
    "source_format",
    "report_scope",
    "subscriber_identifier_type",
    "identifier_type",
    "subscriber_number_raw",
    "ipv4_address_raw",
    "ipv6_address_raw",
    "source_ip_raw",
    "translated_ip_raw",
    "destination_ip_raw",
    "pgw_ip_raw",
    "imei_raw",
    "imsi_raw",
    "source_ip_version",
    "translated_ip_version",
    "destination_ip_version",
    "pgw_ip_version",
    "volume_scope",
    "allocation_key",
    "allocation_volume_key",
    "volume_variant_count",
    "source_row_number",
    "source_row",
    "_source_row_number",
    "spot_folder",
    "exact_duplicate_flag",
    "potential_duplicate",
    "is_potential_duplicate",
    "allocation_time_valid",
    "session_time_valid",
    "event_duration_valid",
    "event_duration_negative",
    "event_zero_duration",
    "event_within_allocation",
    "volume_fields_present",
    "volume_expected_total",
    "volume_difference",
    "volume_tolerance",
    "volume_consistent",
    "volume_mismatch",
    "is_zero_volume",
    "first_cell_matches_searched",
    "last_cell_matches_searched",
    "first_cell_matches_search",
    "last_cell_matches_search",
    "present_at_searched_cell",
    "query_ip_normalized",
    "source_ip_normalized",
    "destination_ip_normalized",
    "query_port_numeric",
    "source_port_numeric",
}

FRIENDLY_HEADER_MAP = {
    "subscriber_number": "Mobile / Subscriber No.",
    "a_party": "A-Party",
    "b_party": "B-Party",
    "other_party": "Other Party (B-Party)",
    "imei": "IMEI",
    "imsi": "IMSI",
    "event_time": "Event Date-Time",
    "session_start": "Session Start",
    "session_end": "Session End",
    "allocation_start": "Allocation Start",
    "allocation_end": "Allocation End",
    "session_duration_seconds": "Duration (Sec)",
    "event_duration_seconds": "Duration (Sec)",
    "estimated_duration_seconds": "Active Duration (Sec)",
    "readable_duration": "Active Duration",
    "activity_span_seconds": "Time Span (Sec)",
    "readable_activity_span": "Time Span",
    "source_ip": "Source / Public IP",
    "source_port": "Source Port",
    "translated_ip": "NAT / Translated IP",
    "translated_port": "NAT Port",
    "destination_ip": "Destination IP",
    "destination_port": "Destination Port",
    "ip_company": "IP Company / ISP",
    "application_name": "Application / Service",
    "service_category": "Category",
    "forensic_significance": "Forensic Priority",
    "nat64_embedded_ipv4": "Decoded NAT64 IPv4",
    "cgi": "Cell ID / CGI",
    "first_cell_id": "First Cell ID",
    "last_cell_id": "Last Cell ID",
    "searched_cell_id": "Searched Cell ID",
    "uplink_volume": "Upload (Bytes)",
    "downlink_volume": "Download (Bytes)",
    "total_volume": "Total Data (Bytes)",
    "apn": "APN",
    "technology": "Network (2G/4G/5G)",
    "operator": "Operator",
    "source_file": "Source File",
}


def is_series_effectively_empty(series: pd.Series) -> bool:
    """Return True if all values in series are null, empty string, or N/A."""
    if series is None or series.empty:
        return True
    cleaned = (
        series.astype("object")
        .fillna("")
        .astype(str)
        .str.strip()
    )
    non_empty = cleaned[
        ~cleaned.str.lower().isin({"", "nan", "none", "<na>", "null", "-", "n/a"})
    ]
    return non_empty.empty


def clean_report_dataframe(
    dataframe: Any,
    *,
    drop_internal: bool = True,
    drop_empty_columns: bool = True,
    clean_headers: bool = True,
    keep_columns: set[str] | None = None,
) -> pd.DataFrame:
    """Remove unwanted internal columns, 100% empty columns, and ugly enrichment prefixes."""
    if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
        return dataframe.copy() if isinstance(dataframe, pd.DataFrame) else pd.DataFrame()

    df = dataframe.copy()
    protected = set(keep_columns or ())

    cols_to_drop: list[str] = []
    for col in df.columns:
        col_str = str(col)
        col_lower = col_str.strip().lower()

        if col_str in protected:
            continue

        if drop_internal and col_lower in INTERNAL_UNWANTED_COLUMNS:
            cols_to_drop.append(col)
            continue

        if drop_internal and (
            col_lower.endswith("_lookup_status")
            or col_lower.endswith("_lookup_key")
            or col_lower.endswith("_sdr_source_file")
            or col_lower.endswith("_cgi_source_file")
            or col_lower in {"sdr_found", "tower_address_found", "cgi_address_found"}
        ):
            cols_to_drop.append(col)
            continue

        if drop_empty_columns and is_series_effectively_empty(df[col]):
            cols_to_drop.append(col)
            continue

    if cols_to_drop:
        df = df.drop(columns=cols_to_drop, errors="ignore")

    if "source_ip" in df.columns:
        for extra_src in ("source_public_ipv4", "source_public_ipv6", "source_private_ipv4"):
            if extra_src in df.columns and extra_src not in protected:
                df = df.drop(columns=[extra_src], errors="ignore")

    if "destination_ip" in df.columns:
        for extra_dst in ("destination_ipv4", "destination_ipv6"):
            if extra_dst in df.columns and extra_dst not in protected:
                df = df.drop(columns=[extra_dst], errors="ignore")

    if clean_headers and not df.empty:
        new_cols: list[str] = []
        seen_names: set[str] = set()
        for col in df.columns:
            col_str = str(col)
            if col_str in protected:
                mapped = col_str
            else:
                mapped = FRIENDLY_HEADER_MAP.get(col_str)
                if not mapped:
                    sdr_match = re.search(r"_sdr_(.+)$", col_str, flags=re.I)
                    cgi_match = re.search(r"_cgi_(.+)$", col_str, flags=re.I)
                    if sdr_match:
                        suffix = sdr_match.group(1).replace("_", " ").title()
                        mapped = f"SDR {suffix}" if not suffix.startswith("Subscriber") else suffix
                    elif cgi_match:
                        suffix = cgi_match.group(1).replace("_", " ").title()
                        mapped = f"Tower {suffix}"
                    else:
                        mapped = col_str

            candidate = mapped
            counter = 2
            while candidate.lower() in seen_names:
                candidate = f"{mapped} ({counter})"
                counter += 1
            seen_names.add(candidate.lower())
            new_cols.append(candidate)
        df.columns = new_cols

    return df
