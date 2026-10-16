"""Extract clean, non-empty analyzed sheets for interactive GUI viewing and on-demand Excel export."""

from __future__ import annotations

from typing import Any
import pandas as pd

from modules.reporting.report_sanitizer import clean_report_dataframe


COACTIVITY_PROTECTED_COLS = {
    "Subscriber No.",
    "Operator",
    "IP Version",
    "Destination IP",
    "Destination Port",
    "IP Company",
    "Application",
    "Session From",
    "Session To",
    "Part",
    "Same Time Apps",
    "Same Time Companies",
}


def _add_if_valid(
    sheets: dict[str, pd.DataFrame],
    title: str,
    df_like: Any,
    *,
    keep_columns: set[str] | None = None,
    clean_headers: bool = True,
    max_rows: int = 100_000,
) -> None:
    if not isinstance(df_like, pd.DataFrame) or df_like.empty:
        return
    cleaned = clean_report_dataframe(
        df_like.head(max_rows),
        keep_columns=keep_columns,
        clean_headers=clean_headers,
    )
    if not cleaned.empty and len(cleaned.columns) > 0:
        sheets[title] = cleaned


def extract_gui_sheets_from_result(
    result: dict[str, Any] | None,
    *,
    workflow: str = "general",
) -> dict[str, pd.DataFrame]:
    """Convert any controller result (CDR, IPDR, Tower Dump, IMEI) into ordered GUI sheets."""
    if not isinstance(result, dict):
        return {}

    sheets: dict[str, pd.DataFrame] = {}

    pre_built = result.get("gui_sheets")
    if isinstance(pre_built, dict) and pre_built:
        for k, v in pre_built.items():
            _add_if_valid(sheets, str(k), v, keep_columns=COACTIVITY_PROTECTED_COLS)
        if sheets:
            return sheets

    analysis = result.get("analysis")
    if not isinstance(analysis, dict):
        analysis = result

    partition = result.get("partition") if isinstance(result.get("partition"), dict) else None

    raw_df = (
        result.get("df")
        if isinstance(result.get("df"), pd.DataFrame)
        else result.get("dataframe")
        if isinstance(result.get("dataframe"), pd.DataFrame)
        else analysis.get("normalized_events")
        if isinstance(analysis.get("normalized_events"), pd.DataFrame)
        else None
    )
    if isinstance(raw_df, pd.DataFrame) and not raw_df.empty:
        _add_if_valid(
            sheets,
            f"Full Loaded Data ({len(raw_df):,} rows)",
            raw_df,
            max_rows=100_000,
        )

    ipdr_priority_order = [
        ("Session & Same-Time Apps", "session_coactivity", COACTIVITY_PROTECTED_COLS),
        ("App & VPN Usage", "application_usage_summary", None),
        ("VPN & VoIP Alerts", "voip_vpn_highlights", None),
        ("Social Calling IPs (B-Party)", "p2p_social_calling_leads", None),
        ("IPv4", "ipv4_sessions", COACTIVITY_PROTECTED_COLS),
        ("IPv6", "ipv6_sessions", COACTIVITY_PROTECTED_COLS),
        ("Source IP", "source_ip_summary", None),
        ("Destination IP", "destination_endpoint_summary", None),
        ("Destination IP Summary", "destination_ip_summary", None),
        ("Airtel", "airtel_ips", COACTIVITY_PROTECTED_COLS),
        ("Jio", "jio_ips", COACTIVITY_PROTECTED_COLS),
        ("Vi", "vi_ips", COACTIVITY_PROTECTED_COLS),
        ("BSNL", "bsnl_ips", COACTIVITY_PROTECTED_COLS),
        ("Others", "other_company_ips", COACTIVITY_PROTECTED_COLS),
        ("Subscribers", "subscriber_summary", None),
        ("Priority Review Queue", "priority_review_queue", None),
        ("Multi-Spot Intelligence", "multi_spot_intelligence", None),
        ("Subscriber Activity", "subscriber_activity", None),
        ("Rare / Uncommon Presence", "rare_presence", None),
        ("Uncommon Numbers", "uncommon_numbers", None),
        ("IMEI Summary", "imei_summary", None),
        ("IMSI Summary", "imsi_summary", None),
        ("Device & SIM Alerts", "device_sim_alerts", None),
        ("Shared IMEI", "shared_imei", None),
        ("Cell Towers (CGI)", "cgi_summary", None),
        ("Cell Summary", "cell_summary", None),
        ("Spot & Cell Summary", "spot_cell_summary", None),
        ("Cell Movement", "cell_movement", None),
        ("Hourly Activity", "hourly_activity", None),
    ]

    for label, key, keep_cols in ipdr_priority_order:
        src_df = (
            partition.get(key)
            if isinstance(partition, dict) and isinstance(partition.get(key), pd.DataFrame)
            else analysis.get(key)
        )
        _add_if_valid(sheets, label, src_df, keep_columns=keep_cols)

    if isinstance(partition, dict):
        part_order = [
            ("Partition Summary", "partition_summary"),
            ("Common in 2+ Parts (N-of-M)", "n_of_m_candidates"),
            ("Common in All Parts (Strict)", "strict_common_candidates"),
            ("Event N-of-M Candidates", "event_n_of_m_candidates"),
            ("Event Strict Common", "event_strict_common_candidates"),
            ("Allocation N-of-M Candidates", "allocation_n_of_m_candidates"),
            ("Actual Event Hits", "actual_event_hits"),
        ]
        for label, key in part_order:
            _add_if_valid(sheets, label, partition.get(key))

    nested_results = analysis.get("results") if isinstance(analysis.get("results"), dict) else {}
    for key, val in nested_results.items():
        if key in {"master_enrichment_summary", "master_enrichment_warnings"}:
            continue
        pretty = str(key).replace("_", " ").title()
        if pretty not in sheets:
            _add_if_valid(sheets, pretty, val)

    skip_keys = {
        "normalized_events",
        "rejected_rows",
        "master_enrichment_summary",
        "master_enrichment_warnings",
        "data_quality",
        "analysis_status",
        "methodology_limits",
        "duckdb_sql_presence_status",
        "status",
    }
    for key, val in analysis.items():
        if key in skip_keys or not isinstance(val, pd.DataFrame):
            continue
        already_added = any(val is existing for existing in sheets.values())
        if not already_added:
            pretty = str(key).replace("_", " ").title()
            if pretty not in sheets:
                _add_if_valid(sheets, pretty, val)

    return sheets
