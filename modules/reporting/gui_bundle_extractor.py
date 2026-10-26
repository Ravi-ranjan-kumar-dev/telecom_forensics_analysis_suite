"""Extract clean, non-empty analyzed sheets for interactive GUI viewing and on-demand Excel export."""

from __future__ import annotations

from pathlib import Path
import tempfile
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


def _dedupe_headers(raw_headers: list[str]) -> list[str]:
    headers: list[str] = []
    seen: set[str] = set()
    for i, h_raw in enumerate(raw_headers):
        h = str(h_raw or "").strip() or f"Column {i + 1}"
        cand = h
        cnt = 2
        while cand.lower() in seen:
            cand = f"{h} ({cnt})"
            cnt += 1
        seen.add(cand.lower())
        headers.append(cand)
    return headers


def _parse_blocks_from_worksheet(ws: Any) -> dict[str, pd.DataFrame]:
    """Fallback parser for worksheets that do not use ReportSection borders."""
    rows_raw = list(ws.iter_rows(values_only=True))
    blocks: dict[str, pd.DataFrame] = {}
    current_title = ws.title
    current_headers: list[str] | None = None
    current_rows: list[list[str]] = []

    def flush_block(title: str, headers: list[str] | None, rows: list[list[str]]) -> None:
        if not headers:
            return
        max_col = len(headers)
        norm_rows = [
            (r[:max_col] + [""] * max(0, max_col - len(r)))
            for r in rows
            if any(c != "" for c in r)
        ]
        df = pd.DataFrame(norm_rows, columns=_dedupe_headers(headers))
        df.attrs["preserve_excel_columns"] = True
        b_title = title.strip() or ws.title
        cand = b_title
        idx = 2
        while cand in blocks:
            cand = f"{b_title} ({idx})"
            idx += 1
        blocks[cand] = df

    i = 0
    n = len(rows_raw)
    while i < n:
        r = [("" if c is None else str(c).strip()) for c in rows_raw[i]]
        non_empty = [c for c in r if c != ""]
        if not non_empty:
            if current_headers is not None and current_rows:
                flush_block(current_title, current_headers, current_rows)
                current_headers = None
                current_rows = []
            i += 1
            continue

        # Single-cell banner/title row
        if len(non_empty) == 1 and current_headers is None:
            text_val = non_empty[0]
            # Skip long guidance sentences if we already have a section title
            if len(text_val) < 95 and not text_val.endswith("."):
                current_title = text_val
            i += 1
            continue

        if current_headers is None and len(non_empty) >= 2:
            last_idx = max(idx for idx, val in enumerate(r) if val != "")
            current_headers = r[: last_idx + 1]
            current_rows = []
            i += 1
            continue

        if current_headers is not None:
            current_rows.append(r)
        i += 1

    if current_headers is not None:
        flush_block(current_title, current_headers, current_rows)

    if not blocks:
        df = pd.DataFrame({"Info": ["No records available for this sheet."]})
        df.attrs["preserve_excel_columns"] = True
        blocks[ws.title] = df

    return blocks


def _resolve_raw_dataframe(result: dict[str, Any] | None) -> pd.DataFrame | None:
    if not isinstance(result, dict):
        return None
    analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}

    for candidate in (
        result.get("df"),
        result.get("dataframe"),
        result.get("normalized_df"),
        result.get("events_df"),
        analysis.get("normalized_events"),
        analysis.get("df"),
        analysis.get("dataframe"),
    ):
        if isinstance(candidate, pd.DataFrame) and not candidate.empty:
            return candidate

    # Multi-target CDR or grouped frames fallback
    for dict_key in ("target_frames", "targets", "dataframes"):
        mapping = result.get(dict_key)
        if isinstance(mapping, dict) and mapping:
            frames: list[pd.DataFrame] = []
            for k, v in mapping.items():
                if isinstance(v, pd.DataFrame) and not v.empty:
                    part = v.copy()
                    if "target_number" not in part.columns:
                        part.insert(0, "target_number", str(k))
                    frames.append(part)
                elif isinstance(v, dict) and isinstance(v.get("df"), pd.DataFrame) and not v["df"].empty:
                    part = v["df"].copy()
                    if "target_number" not in part.columns:
                        part.insert(0, "target_number", str(k))
                    frames.append(part)
            if frames:
                return pd.concat(frames, ignore_index=True)

    return None


def _build_full_loaded_data_sheet(raw_df: pd.DataFrame, max_rows: int | None = None) -> pd.DataFrame:
    df = clean_report_dataframe(
        (raw_df if max_rows is None else raw_df.head(max_rows)).copy(),
        keep_columns=COACTIVITY_PROTECTED_COLS,
        clean_headers=True,
    )
    df.attrs.update(preserve_excel_columns=True, row_level_source=True, source_total_rows=len(raw_df), included_rows=len(df), source_truncated=len(df) < len(raw_df))
    return df


def append_full_loaded_data_tab(
    sheets: dict[str, pd.DataFrame],
    result: dict[str, Any] | None,
    *,
    max_rows: int | None = None,
) -> dict[str, pd.DataFrame]:
    """Ensure 'Full Loaded Data (X rows)' tab is present at the end of sheets dict."""
    if not isinstance(sheets, dict):
        sheets = {}
    raw_df = _resolve_raw_dataframe(result)
    if not isinstance(raw_df, pd.DataFrame) or raw_df.empty:
        return sheets

    # Remove any old Full Loaded Data key so it sits cleanly at the end
    existing_full_keys = [k for k in list(sheets.keys()) if k.startswith("Full Loaded Data")]
    for k in existing_full_keys:
        sheets.pop(k, None)

    full_df = _build_full_loaded_data_sheet(raw_df, max_rows=max_rows)
    if not full_df.empty and len(full_df.columns) > 0:
        tab_title = (f"Preview Loaded Data ({len(full_df):,} of {len(raw_df):,} rows)"
                     if len(full_df) < len(raw_df) else f"Full Loaded Data ({len(raw_df):,} rows)")
        sheets[tab_title] = full_df

    try:
        from modules.reporting.forensic_intelligence_suite import generate_auto_suspect_profile
        profile_source = full_df if max_rows is None else _build_full_loaded_data_sheet(raw_df)
        profile_df = generate_auto_suspect_profile({"Full Loaded Data": profile_source})
        if isinstance(profile_df, pd.DataFrame) and not profile_df.empty:
            sheets["Auto Suspect Profile"] = profile_df
    except Exception as error:
        sheets["Profile Status"] = pd.DataFrame({
            "Status": ["PROFILE_UNAVAILABLE"],
            "Message": [f"Review profile generation failed ({type(error).__name__}); other tables remain available."],
        })

    return sheets


def extract_sheets_from_excel_workbook(
    excel_path: str | Path,
    *,
    result: dict[str, Any] | None = None,
) -> dict[str, pd.DataFrame]:
    """Read exact sheet names, section titles, column headers, and rows from an Excel report."""
    path = Path(excel_path).expanduser()
    if not path.is_file():
        return {}

    from openpyxl import load_workbook
    from modules.reporting.report_section_reader import (
        discover_report_sections,
        read_report_section_rows,
    )

    wb = load_workbook(path, data_only=True)
    out_sheets: dict[str, pd.DataFrame] = {}

    try:
        for ws in wb.worksheets:
            sections = discover_report_sections(ws)
            if sections:
                sec_map: dict[str, pd.DataFrame] = {}
                for sec in sections:
                    sec_title = str(sec.title or ws.title).strip()
                    if sec.headers:
                        rows = read_report_section_rows(ws, sec, offset=0, limit=max(sec.record_count, 1))
                        sec_df = pd.DataFrame(
                            [[("" if c is None else str(c)) for c in row] for row in rows],
                            columns=_dedupe_headers([str(h) for h in sec.headers]),
                        )
                    else:
                        sec_df = pd.DataFrame(
                            [["No records available for this section."]],
                            columns=[sec_title],
                        )
                    sec_df.attrs["preserve_excel_columns"] = True
                    cand_title = sec_title
                    idx = 2
                    while cand_title in sec_map:
                        cand_title = f"{sec_title} ({idx})"
                        idx += 1
                    sec_map[cand_title] = sec_df
            else:
                sec_map = _parse_blocks_from_worksheet(ws)

            if len(sec_map) == 1:
                only_df = next(iter(sec_map.values())).copy()
                only_df.attrs["preserve_excel_columns"] = True
                out_sheets[ws.title] = only_df
            else:
                primary_key = next(iter(sec_map.keys()))
                for k, candidate_df in sec_map.items():
                    if any(w in k.upper() for w in ("RECORD SAMPLE", "CELL", "SUMMARY", "LEADS")):
                        if not candidate_df.empty and len(candidate_df.columns) >= len(sec_map[primary_key].columns):
                            primary_key = k
                            break
                main_df = sec_map[primary_key].copy()
                main_df.attrs["preserve_excel_columns"] = True
                main_df.attrs["sections"] = sec_map
                main_df.attrs["default_section"] = primary_key
                out_sheets[ws.title] = main_df
    finally:
        wb.close()

    if result is not None:
        out_sheets = append_full_loaded_data_tab(out_sheets, result)

    return out_sheets


def _find_excel_report_paths(result: dict[str, Any]) -> list[Path]:
    found: list[Path] = []
    for key in ("excel_path", "report_path", "workbook_path", "output_path"):
        val = result.get(key)
        if val:
            p = Path(str(val)).expanduser()
            if p.is_file() and p.suffix.lower() == ".xlsx" and p not in found:
                found.append(p)
    paths = result.get("report_paths")
    if isinstance(paths, (list, tuple)):
        for val in paths:
            if val:
                p = Path(str(val)).expanduser()
                if p.is_file() and p.suffix.lower() == ".xlsx" and p not in found:
                    found.append(p)
    return found


def _add_if_valid(
    sheets: dict[str, pd.DataFrame],
    title: str,
    df_like: Any,
    *,
    keep_columns: set[str] | None = None,
    clean_headers: bool = True,
    max_rows: int | None = None,
) -> None:
    if not isinstance(df_like, pd.DataFrame):
        return
    if getattr(df_like, "attrs", {}).get("preserve_excel_columns"):
        sheets[title] = df_like
        return
    if df_like.empty:
        return
    cleaned = clean_report_dataframe(
        df_like if max_rows is None else df_like.head(max_rows),
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
    # Keep GUI preview small. Complete datasets stay in DuckDB/Parquet backend.
    def _add_preview(*args, **kwargs):
        if result and result.get("gui_export_only"):
            kwargs["max_rows"] = min(kwargs.get("max_rows", 100_000), 500)
        return _add_if_valid(*args, **kwargs)
    if not isinstance(result, dict):
        return {}

    def _compact_report_tabs(tabs):
        """Compact displayed/exported reports without modifying source evidence."""
        import re
        tower_cdr = ("tower" in workflow.lower() and
                     "ipdr" not in workflow.lower() and
                     "gprs" not in workflow.lower())
        result_tabs = {}
        for title, frame in tabs.items():
            normalized = re.sub(r"[^a-z0-9]+", " ", str(title).lower()).strip()
            if tower_cdr and ("hourly activity" in normalized or "daily activity" in normalized):
                continue
            if not isinstance(frame, pd.DataFrame):
                continue
            # Only remove unambiguous serialization/implementation artifacts.
            keep_positions = []
            seen = set()
            for pos, col in enumerate(frame.columns):
                label = str(col).strip()
                canon = label.casefold()
                if (not label or canon.startswith("unnamed:") or
                    canon in {"level_0", "__index_level_0__"} or
                    label.startswith("__") or canon in seen):
                    continue
                seen.add(canon)
                keep_positions.append(pos)
            result_tabs[title] = frame.iloc[:, keep_positions] if len(keep_positions) != len(frame.columns) else frame
        return result_tabs

    # 1. If an Excel workbook was already generated, read exact sheets from it
    excel_paths = _find_excel_report_paths(result)
    if excel_paths:
        merged_excel_sheets: dict[str, pd.DataFrame] = {}
        multi_files = len(excel_paths) > 1
        for p in excel_paths:
            wb_sheets = extract_sheets_from_excel_workbook(p, result=None)
            prefix = f"[{p.stem.split('_')[0]}] " if multi_files else ""
            for s_name, s_df in wb_sheets.items():
                merged_excel_sheets[f"{prefix}{s_name}"] = s_df
        if merged_excel_sheets:
            merged_excel_sheets = append_full_loaded_data_tab(merged_excel_sheets, result)
            result["gui_sheets"] = merged_excel_sheets
            return _compact_report_tabs(merged_excel_sheets)

    # 2. If pre_built gui_sheets exist, ensure Full Loaded Data is appended at the end
    pre_built = result.get("gui_sheets")
    if isinstance(pre_built, dict) and pre_built:
        sheets: dict[str, pd.DataFrame] = {}
        for k, v in pre_built.items():
            _add_preview(sheets, str(k), v, keep_columns=COACTIVITY_PROTECTED_COLS)
        if sheets:
            sheets = append_full_loaded_data_tab(sheets, result)
            result["gui_sheets"] = sheets
            return _compact_report_tabs(sheets)

    analysis = result.get("analysis")
    if not isinstance(analysis, dict):
        analysis = result
    nested_results = analysis.get("results") if isinstance(analysis.get("results"), dict) else {}

    # 3. On-demand Tower CDR Excel generation if called before Excel phase
    is_tower_cdr = (
        "tower_cdr_uncommon_numbers" in nested_results
        or "n_of_m_spot_presence" in nested_results
        or ("tower" in workflow.lower() and "ipdr" not in workflow.lower() and "gprs" not in workflow.lower())
    )
    if is_tower_cdr and nested_results and not result.get("gui_export_only"):
        try:
            from modules.reporting.tower_dump_excel import generate_tower_dump_excel_report
            with tempfile.TemporaryDirectory() as tmp_dir:
                gen_path = generate_tower_dump_excel_report(result, output_dir=tmp_dir)
                excel_sheets = extract_sheets_from_excel_workbook(gen_path, result=result)
                if excel_sheets:
                    result["gui_sheets"] = excel_sheets
                    return _compact_report_tabs(excel_sheets)
        except Exception:
            pass

    # 4. Fallback dictionary extraction + Full Loaded Data at the end
    sheets = {}
    partition = result.get("partition") if isinstance(result.get("partition"), dict) else None

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
        _add_preview(sheets, label, src_df, keep_columns=keep_cols)

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
            _add_preview(sheets, label, partition.get(key))

    for key, val in nested_results.items():
        if key in {"master_enrichment_summary", "master_enrichment_warnings"}:
            continue
        pretty = str(key).replace("_", " ").title()
        if pretty not in sheets:
            _add_preview(sheets, pretty, val)

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
                _add_preview(sheets, pretty, val)
    sheets = append_full_loaded_data_tab(
        sheets, result, max_rows=2000 if result.get("gui_export_only") else 200_000
    )
    return _compact_report_tabs(sheets)

class sheets(dict):
    """Convenience wrapper around a mapping of sheet-name to pandas DataFrame."""

    def __init__(
        self,
        initial: dict[str, pd.DataFrame] | None = None,
        **kwargs: pd.DataFrame,
    ) -> None:
        super().__init__()
        if isinstance(initial, dict):
            for key, value in initial.items():
                self[key] = value
        for key, value in kwargs.items():
            self[key] = value

    @classmethod
    def from_result(
        cls,
        result: dict[str, Any] | None,
        *,
        workflow: str = "general",
    ) -> "sheets":
        return cls(extract_gui_sheets_from_result(result, workflow=workflow))

    @classmethod
    def from_excel(
        cls,
        excel_path: str | Path,
        *,
        result: dict[str, Any] | None = None,
    ) -> "sheets":
        return cls(extract_sheets_from_excel_workbook(excel_path, result=result))

    def add(
        self,
        title: str,
        df_like: Any,
        *,
        keep_columns: set[str] | None = None,
        clean_headers: bool = True,
        max_rows: int | None = None,
    ) -> "sheets":
        _add_if_valid(
            self,
            str(title),
            df_like,
            keep_columns=keep_columns,
            clean_headers=clean_headers,
            max_rows=max_rows,
        )
        return self

    def append_full_loaded_data(
        self,
        result: dict[str, Any] | None,
        *,
        max_rows: int | None = None,
    ) -> "sheets":
        self.update(append_full_loaded_data_tab(dict(self), result, max_rows=max_rows))
        return self

    def as_dict(self) -> dict[str, pd.DataFrame]:
        return dict(self)

    def copy(self) -> "sheets":
        return sheets(dict(self))

    def __setitem__(self, key: str, value: Any) -> None:
        if not isinstance(value, pd.DataFrame):
            raise TypeError("sheets values must be pandas DataFrames")
        super().__setitem__(str(key), value)
    
    @property
    def names(self) -> list[str]:
        return list(self.keys())