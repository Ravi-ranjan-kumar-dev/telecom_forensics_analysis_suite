from __future__ import annotations


def _safe_join(sep, vals):
    return sep.join(str(v) for v in vals if v is not None and str(v).lower() != "nan")

"""Analytical bundle for target, reverse-IP and broadband IPDR records."""


import ipaddress
from typing import Any

import pandas as pd

from modules.enrichment.telecom_master_enrichment import (
    IPDR_TABLE_SPECS,
    enrich_analysis_bundle,
)
from modules.analysis.ipdr.ip_port_intelligence import (
    annotate_ipdr_with_intelligence,
    build_application_usage_summary,
    build_ipdr_specialized_sheets,
    build_p2p_social_calling_leads,
    build_voip_vpn_highlights,
    classify_ip_and_port,
    identify_ip_owner,
)


def _empty() -> pd.DataFrame:
    return pd.DataFrame()


def _nonempty(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    if frame.empty or column not in frame.columns:
        return frame.iloc[0:0].copy()

    values = frame[column].astype("object").fillna("").astype(str).str.strip()
    return frame.loc[values.ne("")].copy()


def _canonical_ip(value: Any) -> str:
    text = str(value or "").strip()

    if not text:
        return ""

    prefix = ""

    if "/" in text:
        text, prefix = text.split("/", 1)
        prefix = "/" + prefix

    try:
        return ipaddress.ip_address(text).compressed + prefix
    except ValueError:
        return text


def _allocation_records(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return data.copy()

    ordered = data.sort_values(
        ["allocation_start", "event_time", "source_file", "source_row_number"],
        na_position="last",
    )
    allocations = ordered.drop_duplicates(
        subset=["allocation_key"],
        keep="first",
    ).copy()

    variant_table = (
        data.assign(
            volume_variant_key=(
                data["allocation_key"].astype("object").fillna("").astype(str)
                + "|"
                + data["uplink_volume"].astype("object").fillna("").astype(str)
                + "|"
                + data["downlink_volume"].astype("object").fillna("").astype(str)
            )
        )
        .groupby("allocation_key", dropna=False)["volume_variant_key"]
        .nunique()
        .rename("volume_variant_count")
    )
    allocations = allocations.merge(
        variant_table,
        left_on="allocation_key",
        right_index=True,
        how="left",
    )

    keep = [
        "allocation_key",
        "operator",
        "source_format",
        "report_scope",
        "query_value",
        "subscriber_number",
        "subscriber_identifier_type",
        "imei",
        "imsi",
        "allocation_start",
        "allocation_end",
        "source_ip",
        "translated_ip",
        "apn",
        "gateway_ip",
        "first_cell_id",
        "last_cell_id",
        "uplink_volume",
        "downlink_volume",
        "volume_variant_count",
        "source_file",
    ]
    return allocations[[column for column in keep if column in allocations.columns]]


def _summary(
    data: pd.DataFrame,
    allocations: pd.DataFrame,
    search_requests: pd.DataFrame,
    file_summary: pd.DataFrame,
) -> pd.DataFrame:
    events = data[data["record_type"].eq("IPDR_EVENT")]
    allocation_only = data[data["record_type"].eq("IP_ALLOCATION")]

    metrics = [
        ("Files Profiled", len(file_summary), ""),
        ("Files Loaded", int(file_summary["status"].eq("LOADED").sum()) if not file_summary.empty else 0, ""),
        ("Normalized Records", len(data), ""),
        ("IPDR Event Records", len(events), ""),
        ("Allocation-only Records", len(allocation_only), ""),
        ("Unique Allocation Keys", data["allocation_key"].nunique(), ""),
        ("Unique Subscribers/User IDs", _nonempty(data, "subscriber_number")["subscriber_number"].nunique(), ""),
        ("Unique IMEI/Device IDs", _nonempty(data, "imei")["imei"].nunique(), ""),
        ("Unique IMSI", _nonempty(data, "imsi")["imsi"].nunique(), ""),
        ("Unique Source IP", _nonempty(data, "source_ip")["source_ip"].nunique(), ""),
        ("Unique Translated/NAT IP", _nonempty(data, "translated_ip")["translated_ip"].nunique(), ""),
        ("Unique Destination IP", _nonempty(data, "destination_ip")["destination_ip"].nunique(), ""),
        ("Unique Destination Ports", data["destination_port"].dropna().nunique(), ""),
        ("Unique CGI/Cells", _nonempty(data, "cgi")["cgi"].nunique(), ""),
        ("Operators", ", ".join(sorted(set(data["operator"].dropna().astype(str)))) if not data.empty else "", ""),
        ("Report Scopes", ", ".join(sorted(set(data["report_scope"].dropna().astype(str)))) if not data.empty else "", ""),
        ("First Event Time", events["event_time"].min() if not events.empty else pd.NaT, ""),
        ("Last Event Time", events["event_time"].max() if not events.empty else pd.NaT, ""),
        ("Search Request Rows", len(search_requests), ""),
        (
            "Deduplicated Uplink Volume",
            allocations["uplink_volume"].sum(min_count=1) if "uplink_volume" in allocations else 0,
            "One value per allocation key; inspect volume variants before relying on totals.",
        ),
        (
            "Deduplicated Downlink Volume",
            allocations["downlink_volume"].sum(min_count=1) if "downlink_volume" in allocations else 0,
            "One value per allocation key; inspect volume variants before relying on totals.",
        ),
    ]
    return pd.DataFrame(metrics, columns=["Metric", "Value", "Note"])


def _query_summary(data: pd.DataFrame, file_summary: pd.DataFrame) -> pd.DataFrame:
    if file_summary.empty:
        return pd.DataFrame()

    base_columns = [
        "file_name",
        "operator",
        "source_format",
        "report_scope",
        "query_value",
        "query_port",
        "records_loaded",
        "search_requests",
        "status",
    ]
    result = file_summary[
        [column for column in base_columns if column in file_summary.columns]
    ].copy()

    if data.empty:
        return result

    extra = (
        data.groupby("source_file", dropna=False)
        .agg(
            unique_subscribers=("subscriber_number", lambda s: s.replace("", pd.NA).nunique()),
            unique_imei=("imei", lambda s: s.replace("", pd.NA).nunique()),
            unique_imsi=("imsi", lambda s: s.replace("", pd.NA).nunique()),
            unique_source_ip=("source_ip", lambda s: s.replace("", pd.NA).nunique()),
            unique_destination_ip=("destination_ip", lambda s: s.replace("", pd.NA).nunique()),
            unique_cells=("cgi", lambda s: s.replace("", pd.NA).nunique()),
            first_event=("event_time", "min"),
            last_event=("event_time", "max"),
        )
        .reset_index()
        .rename(columns={"source_file": "file_name"})
    )
    return result.merge(extra, on="file_name", how="left")


def _group_identity(
    data: pd.DataFrame,
    column: str,
    label: str,
) -> pd.DataFrame:
    frame = _nonempty(data, column)

    if frame.empty:
        return pd.DataFrame(columns=[label])

    return (
        frame.groupby(column, dropna=False)
        .agg(
            records=("record_type", "size"),
            event_records=("record_type", lambda s: int(s.eq("IPDR_EVENT").sum())),
            allocation_count=("allocation_key", "nunique"),
            subscribers=("subscriber_number", lambda s: s.replace("", pd.NA).nunique()),
            source_files=("source_file", "nunique"),
            operators=("operator", lambda s: ", ".join(sorted(set(s.dropna().astype(str))))),
            report_scopes=("report_scope", lambda s: ", ".join(sorted(set(s.dropna().astype(str))))),
            first_event=("event_time", "min"),
            last_event=("event_time", "max"),
        )
        .reset_index()
        .rename(columns={column: label})
        .sort_values(["source_files", "records"], ascending=[False, False])
    )


def _subscriber_summary(data: pd.DataFrame) -> pd.DataFrame:
    frame = _nonempty(data, "subscriber_number")

    if frame.empty:
        return pd.DataFrame()

    return (
        frame.groupby(
            ["subscriber_number", "subscriber_identifier_type"],
            dropna=False,
        )
        .agg(
            records=("record_type", "size"),
            event_records=("record_type", lambda s: int(s.eq("IPDR_EVENT").sum())),
            allocation_only_records=("record_type", lambda s: int(s.eq("IP_ALLOCATION").sum())),
            allocation_count=("allocation_key", "nunique"),
            source_files=("source_file", "nunique"),
            operators=("operator", lambda s: ", ".join(sorted(set(s.dropna().astype(str))))),
            report_scopes=("report_scope", lambda s: ", ".join(sorted(set(s.dropna().astype(str))))),
            imei_count=("imei", lambda s: s.replace("", pd.NA).nunique()),
            imsi_count=("imsi", lambda s: s.replace("", pd.NA).nunique()),
            source_ip_count=("source_ip", lambda s: s.replace("", pd.NA).nunique()),
            destination_ip_count=("destination_ip", lambda s: s.replace("", pd.NA).nunique()),
            cell_count=("cgi", lambda s: s.replace("", pd.NA).nunique()),
            first_event=("event_time", "min"),
            last_event=("event_time", "max"),
        )
        .reset_index()
        .sort_values(
            ["source_files", "records"],
            ascending=[False, False],
        )
    )


def _presence_matrix(
    data: pd.DataFrame,
    identity_column: str,
    identity_label: str,
) -> pd.DataFrame:
    frame = _nonempty(data, identity_column)

    if frame.empty:
        return pd.DataFrame()

    counts = (
        frame.groupby([identity_column, "source_file"])
        .size()
        .unstack(fill_value=0)
    )
    matrix = counts.gt(0).astype(int)
    matrix.columns = [f"Present_{column}" for column in matrix.columns]
    result = matrix.reset_index().rename(columns={identity_column: identity_label})
    result["Files_Present"] = matrix.sum(axis=1).values
    result["Total_Records"] = counts.sum(axis=1).values
    return result.sort_values(
        ["Files_Present", "Total_Records"],
        ascending=[False, False],
    )


def _destination_endpoints(data: pd.DataFrame) -> pd.DataFrame:
    frame = _nonempty(data, "destination_ip")

    if frame.empty:
        return pd.DataFrame()

    frame = frame.copy()
    frame["destination_port_text"] = (
        frame["destination_port"].astype("object").fillna("").astype(str)
    )
    out_df = (
        frame.groupby(
            ["destination_ip", "destination_port_text"],
            dropna=False,
        )
        .agg(
            records=("record_type", "size"),
            subscribers=("subscriber_number", lambda s: s.replace("", pd.NA).nunique()),
            source_ips=("source_ip", lambda s: s.replace("", pd.NA).nunique()),
            source_files=("source_file", "nunique"),
            operators=("operator", lambda s: ", ".join(sorted(set(s.dropna().astype(str))))),
            first_event=("event_time", "min"),
            last_event=("event_time", "max"),
        )
        .reset_index()
        .rename(columns={"destination_port_text": "destination_port"})
        .sort_values("records", ascending=False)
    )
    if not out_df.empty:
        classified = [
            classify_ip_and_port(ip, port)
            for ip, port in zip(out_df["destination_ip"], out_df["destination_port"])
        ]
        intel = pd.DataFrame(classified, index=out_df.index)
        out_df.insert(2, "ip_company", intel["ip_company"])
        out_df.insert(3, "application_name", intel["application_name"])
        out_df.insert(4, "service_category", intel["service_category"])
        out_df.insert(5, "forensic_significance", intel["forensic_significance"])
    return out_df


def _simple_count(
    data: pd.DataFrame,
    column: str,
    label: str,
) -> pd.DataFrame:
    frame = _nonempty(data, column)

    if frame.empty:
        return pd.DataFrame(columns=[label, "records"])

    return (
        frame.groupby(column, dropna=False)
        .agg(
            records=("record_type", "size"),
            subscribers=("subscriber_number", lambda s: s.replace("", pd.NA).nunique()),
            source_files=("source_file", "nunique"),
            first_event=("event_time", "min"),
            last_event=("event_time", "max"),
        )
        .reset_index()
        .rename(columns={column: label})
        .sort_values("records", ascending=False)
    )


def _hourly_activity(data: pd.DataFrame) -> pd.DataFrame:
    events = data[data["event_time"].notna()].copy()

    if events.empty:
        return pd.DataFrame()

    events["event_date"] = events["event_time"].dt.date
    events["hour"] = events["event_time"].dt.hour
    return (
        events.groupby(["event_date", "hour"], dropna=False)
        .agg(
            records=("record_type", "size"),
            subscribers=("subscriber_number", lambda s: s.replace("", pd.NA).nunique()),
            source_ips=("source_ip", lambda s: s.replace("", pd.NA).nunique()),
            destination_ips=("destination_ip", lambda s: s.replace("", pd.NA).nunique()),
        )
        .reset_index()
        .sort_values(["event_date", "hour"])
    )


def _cell_movement(data: pd.DataFrame) -> pd.DataFrame:
    frame = data[
        data["first_cell_id"].astype("object").fillna("").astype(str).str.strip().ne("")
        | data["last_cell_id"].astype("object").fillna("").astype(str).str.strip().ne("")
    ].copy()

    if frame.empty:
        return pd.DataFrame()

    frame["cell_changed"] = (
        frame["first_cell_id"].astype("object").fillna("").astype(str)
        != frame["last_cell_id"].astype("object").fillna("").astype(str)
    )
    return (
        frame.groupby(
            ["subscriber_number", "first_cell_id", "last_cell_id"],
            dropna=False,
        )
        .agg(
            records=("record_type", "size"),
            cell_changed=("cell_changed", "max"),
            first_event=("event_time", "min"),
            last_event=("event_time", "max"),
            source_files=("source_file", "nunique"),
        )
        .reset_index()
        .sort_values(["cell_changed", "records"], ascending=[False, False])
    )


def _reverse_query_validation(data: pd.DataFrame) -> pd.DataFrame:
    """Validate reverse lookup against the correct endpoint.

    Destination-IP requests are compared with destination_ip.
    Public-IP + port requests are compared with source_ip + source_port.
    """

    scopes = {
        "REVERSE_DESTINATION_IP",
        "REVERSE_PUBLIC_IP_PORT",
    }
    frame = data[data["report_scope"].isin(scopes)].copy()

    if frame.empty:
        return pd.DataFrame()

    frame["query_ip_normalized"] = frame["query_value"].map(_canonical_ip)
    frame["source_ip_normalized"] = frame["source_ip"].map(_canonical_ip)
    frame["destination_ip_normalized"] = (
        frame["destination_ip"].map(_canonical_ip)
    )
    frame["query_port_numeric"] = pd.to_numeric(
        frame.get("query_port"),
        errors="coerce",
    )
    frame["source_port_numeric"] = pd.to_numeric(
        frame["source_port"],
        errors="coerce",
    )

    is_public = frame["report_scope"].eq(
        "REVERSE_PUBLIC_IP_PORT"
    )
    frame["ip_match"] = (
        (
            is_public
            & frame["query_ip_normalized"].eq(
                frame["source_ip_normalized"]
            )
        )
        | (
            ~is_public
            & frame["query_ip_normalized"].eq(
                frame["destination_ip_normalized"]
            )
        )
    )

    frame["port_match"] = (
        ~is_public
        | frame["query_port_numeric"].isna()
        | frame["query_port_numeric"].eq(
            frame["source_port_numeric"]
        )
    )
    frame["query_match"] = (
        frame["ip_match"].fillna(False)
        & frame["port_match"].fillna(False)
    )

    return (
        frame.groupby(
            [
                "source_file",
                "operator",
                "report_scope",
                "query_value",
                "query_port",
                "query_ip_normalized",
            ],
            dropna=False,
        )
        .agg(
            records=("record_type", "size"),
            exact_query_matches=("query_match", "sum"),
            nonmatching_rows=(
                "query_match",
                lambda series: int((~series.fillna(False)).sum()),
            ),
            ip_matches=("ip_match", "sum"),
            port_matches=("port_match", "sum"),
            unique_subscribers=("subscriber_number", "nunique"),
            first_event=("event_time", "min"),
            last_event=("event_time", "max"),
        )
        .reset_index()
    )


def _data_quality(
    data: pd.DataFrame,
    allocations: pd.DataFrame,
    file_summary: pd.DataFrame,
) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame(
            [{"Check": "Normalized records", "Rows": 0, "Severity": "INFO", "Note": "No IPDR result rows loaded."}]
        )

    events = data[data["record_type"].eq("IPDR_EVENT")]
    event_outside = (
        events["event_time"].notna()
        & events["allocation_start"].notna()
        & events["allocation_end"].notna()
        & (
            events["event_time"].lt(events["allocation_start"])
            | events["event_time"].gt(events["allocation_end"])
        )
    )
    exact_subset = [
        "operator",
        "subscriber_number",
        "event_time",
        "allocation_start",
        "allocation_end",
        "source_ip",
        "source_port",
        "destination_ip",
        "destination_port",
        "charging_id",
        "source_file",
    ]
    exact_subset = [column for column in exact_subset if column in data.columns]
    exact_duplicates = data.duplicated(subset=exact_subset, keep=False)
    invalid_source = data["source_ip_version"].eq("INVALID")
    invalid_destination = data["destination_ip_version"].eq("INVALID")
    volume_variants = (
        allocations["volume_variant_count"].gt(1)
        if "volume_variant_count" in allocations
        else pd.Series(False, index=allocations.index)
    )

    duration = pd.to_numeric(
        data["session_duration_seconds"],
        errors="coerce",
    )

    rows = [
        ("Normalized records", len(data), "INFO", ""),
        ("Files failed", int(file_summary["status"].eq("FAILED").sum()) if not file_summary.empty else 0, "ERROR", ""),
        ("Event rows with invalid/missing event time", int(events["event_time"].isna().sum()), "ERROR", ""),
        ("Rows with invalid/missing allocation start", int(data["allocation_start"].isna().sum()), "WARNING", ""),
        ("Rows with allocation end before start", int((data["allocation_end"] < data["allocation_start"]).fillna(False).sum()), "ERROR", ""),
        ("Events outside allocation interval", int(event_outside.sum()), "WARNING", ""),
        ("Negative duration rows", int(duration.lt(0).fillna(False).sum()), "WARNING", "Raw values preserved."),
        ("Zero duration rows", int(duration.eq(0).fillna(False).sum()), "INFO", "May represent instantaneous events."),
        ("Rows missing subscriber/user ID", int(data["subscriber_number"].astype("object").fillna("").astype(str).str.strip().eq("").sum()), "WARNING", ""),
        ("Rows missing source IP", int(data["source_ip"].astype("object").fillna("").astype(str).str.strip().eq("").sum()), "WARNING", ""),
        ("Event rows missing destination IP", int(events["destination_ip"].astype("object").fillna("").astype(str).str.strip().eq("").sum()), "WARNING", ""),
        ("Invalid source IP values", int(invalid_source.sum()), "WARNING", ""),
        ("Invalid destination IP values", int(invalid_destination.sum()), "WARNING", ""),
        ("Exact duplicate event/allocation rows", int(exact_duplicates.sum()), "WARNING", "Rows are preserved and flagged."),
        ("Allocation keys with multiple volume variants", int(volume_variants.sum()), "WARNING", "Do not sum repeated event-level volume blindly."),
    ]
    return pd.DataFrame(rows, columns=["Check", "Rows", "Severity", "Note"])




def _enrich_dest_ip_table(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "destination_ip" not in df.columns:
        return df
    out = df.copy()
    owners = out["destination_ip"].map(lambda ip: identify_ip_owner(str(ip)))
    out.insert(1, "ip_company", owners.map(lambda item: item[0]))
    out.insert(2, "network_role", owners.map(lambda item: item[1]))
    return out


def _enrich_dest_port_table(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "destination_port" not in df.columns:
        return df
    out = df.copy()
    info = out["destination_port"].map(lambda p: classify_ip_and_port("", p))
    out.insert(1, "application_name", info.map(lambda item: item["application_name"]))
    out.insert(2, "service_category", info.map(lambda item: item["service_category"]))
    out.insert(3, "forensic_significance", info.map(lambda item: item["forensic_significance"]))
    return out



def _sanitize_pandas3_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    for col in out.columns:
        dtype_name = str(out[col].dtype)
        if dtype_name in {"Float64", "Float32"}:
            out[col] = pd.to_numeric(out[col].astype("object"), errors="coerce").astype("float64")
        elif dtype_name in {"Int64", "Int32", "UInt64"} and col != "source_row_number":
            out[col] = pd.to_numeric(out[col].astype("object"), errors="coerce").astype("float64")
    return out


def run_ipdr_analysis(
    data: pd.DataFrame,
    *,
    file_summary: pd.DataFrame | None = None,
    search_requests: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Run one reusable IPDR analytical bundle without modifying raw rows."""

    data = _sanitize_pandas3_dtypes(data)
    if not data.empty:
        data = annotate_ipdr_with_intelligence(data)
    file_summary = (
        file_summary.copy()
        if isinstance(file_summary, pd.DataFrame)
        else pd.DataFrame()
    )
    search_requests = (
        search_requests.copy()
        if isinstance(search_requests, pd.DataFrame)
        else pd.DataFrame()
    )

    allocations = _allocation_records(data)
    subscriber_summary = _subscriber_summary(data)
    imei_summary = _group_identity(data, "imei", "imei")
    imsi_summary = _group_identity(data, "imsi", "imsi")

    result = {
        "record_count": len(data),
        "summary": _summary(data, allocations, search_requests, file_summary),
        "file_summary": file_summary,
        "query_summary": _query_summary(data, file_summary),
        "subscriber_summary": subscriber_summary,
        "multi_file_subscribers": subscriber_summary[
            subscriber_summary["source_files"].gt(1)
        ].copy() if not subscriber_summary.empty else _empty(),
        "subscriber_file_presence": _presence_matrix(
            data,
            "subscriber_number",
            "subscriber_number",
        ),
        "imei_summary": imei_summary,
        "shared_imei": imei_summary[
            imei_summary["subscribers"].gt(1)
        ].copy() if not imei_summary.empty else _empty(),
        "imei_file_presence": _presence_matrix(data, "imei", "imei"),
        "imsi_summary": imsi_summary,
        "shared_imsi": imsi_summary[
            imsi_summary["subscribers"].gt(1)
        ].copy() if not imsi_summary.empty else _empty(),
        "imsi_file_presence": _presence_matrix(data, "imsi", "imsi"),
        "source_ip_summary": _group_identity(data, "source_ip", "source_ip"),
        "translated_ip_summary": _group_identity(
            data,
            "translated_ip",
            "translated_ip",
        ),
        **build_ipdr_specialized_sheets(data),
        "application_usage_summary": build_application_usage_summary(data),
        "voip_vpn_highlights": build_voip_vpn_highlights(build_application_usage_summary(data)),
        "p2p_social_calling_leads": build_p2p_social_calling_leads(data),
        "destination_ip_summary": _enrich_dest_ip_table(_group_identity(
            data,
            "destination_ip",
            "destination_ip",
        )),
        "destination_port_summary": _enrich_dest_port_table(_simple_count(
            data,
            "destination_port",
            "destination_port",
        )),
        "destination_endpoint_summary": _destination_endpoints(data),
        "allocation_records": allocations,
        "apn_summary": _simple_count(data, "apn", "apn"),
        "technology_summary": _simple_count(
            data,
            "technology",
            "technology",
        ),
        "cgi_summary": _simple_count(data, "cgi", "cgi"),
        "cell_movement": _cell_movement(data),
        "hourly_activity": _hourly_activity(data),
        "reverse_query_validation": _reverse_query_validation(data),
        "search_requests": search_requests,
        "data_quality": _data_quality(data, allocations, file_summary),
        "normalized_events": data,
    }
    enrichment = enrich_analysis_bundle(
        result,
        table_specs=IPDR_TABLE_SPECS,
    )

    result = enrichment["bundle"]
    result["master_enrichment_summary"] = enrichment[
        "summary"
    ]
    result["master_enrichment_warnings"] = enrichment[
        "warnings"
    ]

    return result


# === IPDR_GUI_RESULT_STORE_HOOK ===
_ORIG_RUN_IPDR_ANALYSIS = run_ipdr_analysis


def run_ipdr_analysis(*args, **kwargs) -> dict:
    res = _ORIG_RUN_IPDR_ANALYSIS(*args, **kwargs)
    try:
        from modules.reporting.gui_bundle_extractor import extract_gui_sheets_from_result
        from modules.reporting.gui_result_store import store_gui_sheets
        sheets = extract_gui_sheets_from_result({"analysis": res}, workflow="ipdr")
        if sheets:
            store_gui_sheets(sheets, title="IPDR Forensic Analysis Results", workflow="ipdr")
    except Exception:
        pass
    return res