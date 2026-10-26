"""Advanced Forensic Intelligence Suite for EthicalArmor.

Provides:
1. Versioned event-based review profiles
2. Offline tower coordinate map (Leaflet HTML)
3. Filterable call association graph (SVG HTML)
4. Analytical brief with derived-snapshot and HTML artifact checksums
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
from typing import Any
import pandas as pd


def _find_col(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    if df is None or df.empty:
        return None
    col_map = {str(c).strip().lower(): str(c) for c in df.columns}
    for cand in candidates:
        if cand.lower() in col_map:
            return col_map[cand.lower()]
    for col_low, orig in col_map.items():
        if any(cand.lower() in col_low for cand in candidates):
            return orig
    return None


def _frames(sheets):
    """Yield authoritative section frames without also counting their parent table."""
    for name in sorted(sheets):
        df = sheets[name]
        if not isinstance(df, pd.DataFrame):
            continue
        sections = df.attrs.get("sections")
        if isinstance(sections, dict) and sections:
            for section in sorted(sections):
                if isinstance(sections[section], pd.DataFrame):
                    yield f"{name} / {section}", sections[section]
        else:
            yield str(name), df


def _cell_text(value):
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (ValueError, TypeError):
        pass
    return str(value)


def compute_sheets_sha256(sheets: dict[str, pd.DataFrame]) -> str:
    """Hash every displayed value, row, column and section using framed JSON v2.

    This is a derived table snapshot digest, not an original-evidence hash or
    chain-of-custody certificate. Row order is intentionally significant.
    """
    hasher = hashlib.sha256(b"EthicalArmor/displayed-table-snapshot/v2\n")
    def put(value):
        blob = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        hasher.update(len(blob).to_bytes(8, "big"))
        hasher.update(blob)
    for name, df in _frames(sheets):
        put([name, list(map(str, df.columns)), len(df)])
        for row in df.itertuples(index=False, name=None):
            put([_cell_text(value) for value in row])
    return hasher.hexdigest().upper()


def generate_auto_suspect_profile(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build a consolidated Suspect & Lead Intelligence Profile from loaded sheets."""
    if not sheets:
        return pd.DataFrame()

    # Only event-level sources have one row per event. Never reinterpret a summary.
    sources = []
    for name, frame in _frames(sheets):
        low = name.lower()
        is_raw = frame.attrs.get("row_level_source") or ("full" in low and ("loaded data" in low or "cdr" in low))
        if is_raw and not frame.empty and not frame.attrs.get("source_truncated", False):
            sources.append((len(frame), name, frame))
    target_df = max(sources, key=lambda item: (item[0], item[1]))[2] if sources else None

    if target_df is None or target_df.empty:
        return pd.DataFrame()

    sub_col = _find_col(
        target_df,
        ("Mobile / Subscriber No.", "subscriber_number", "target_number", "A-Party", "a_party", "Subscriber No."),
    )
    other_col = _find_col(
        target_df,
        ("Other Party (B-Party)", "other_party", "b_party", "B-Party", "Destination IP", "destination_ip"),
    )
    imei_col = _find_col(target_df, ("IMEI", "imei", "device_imei"))
    cell_col = _find_col(
        target_df,
        ("Searched Cell ID", "First Cell ID", "Cell ID / CGI", "first_cgi", "first_cell_id", "cgi", "cell_id"),
    )
    dur_col = _find_col(target_df, ("Duration (Sec)", "duration_seconds", "duration", "call_duration"))

    if not sub_col:
        return pd.DataFrame()

    work = target_df.copy()
    work["_sub"] = work[sub_col].fillna("").astype(str).str.strip()
    work = work[~work["_sub"].str.lower().isin({"", "nan", "none", "<na>", "-"})]
    if work.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    grouped = work.groupby("_sub", sort=False)

    for entity, grp in grouped:
        total_events = len(grp)
        uniq_contacts = (
            grp[other_col].dropna().astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA}).nunique()
            if other_col and other_col in grp.columns
            else 0
        )
        uniq_imeis = (
            grp[imei_col].dropna().astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA}).nunique()
            if imei_col and imei_col in grp.columns
            else 0
        )
        uniq_cells = (
            grp[cell_col].dropna().astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA}).nunique()
            if cell_col and cell_col in grp.columns
            else 0
        )
        top_cell = ""
        if cell_col and cell_col in grp.columns:
            vc = grp[cell_col].dropna().astype(str).str.strip()
            vc = vc[~vc.str.lower().isin({"", "nan", "none"})]
            if not vc.empty:
                top_cell = str(vc.value_counts().index[0])

        total_dur = 0
        if dur_col and dur_col in grp.columns:
            total_dur = int(pd.to_numeric(grp[dur_col], errors="coerce").fillna(0).sum())

        flags: list[str] = []
        score = total_events
        if uniq_imeis > 1:
            flags.append(f"Multi-IMEI ({uniq_imeis})")
            score += uniq_imeis * 15
        if uniq_cells > 3:
            flags.append(f"High Mobility ({uniq_cells} Towers)")
            score += uniq_cells * 5
        if uniq_contacts > 10:
            flags.append(f"High Contact Spread ({uniq_contacts})")
            score += 20
        if not flags:
            flags.append("Standard Activity")

        rows.append(
            {
                "Suspect / Subscriber": entity,
                "Review Priority Score": score,
                "Ruleset": "AUTO-PROFILE-1.0",
                "Score Formula": "events + (IMEIs*15 if >1) + (towers*5 if >3) + (20 if contacts>10)",
                "Source Rows": len(target_df),
                "Source Scope": "Complete loaded event table",
                "Total Events": total_events,
                "Unique B-Parties / Endpoints": uniq_contacts,
                "Unique IMEIs": uniq_imeis,
                "Unique Towers / CGIs": uniq_cells,
                "Primary Tower / CGI": top_cell,
                "Total Duration (Sec)": total_dur,
                "Investigative Indicators": " | ".join(flags),
            }
        )

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(by=["Review Priority Score", "Total Events"], ascending=[False, False]).head(500).reset_index(drop=True)
        out["Profile Rows Included"] = len(out)
        out["Profile Entities Total"] = len(rows)
        out.attrs["preserve_excel_columns"] = True
    return out


def export_interactive_map_html(sheets: dict[str, pd.DataFrame], output_path: str | Path) -> tuple[Path, int]:
    """Export an offline coordinate explorer without assuming a travel route."""
    from .offline_views import render_offline_view
    from .map_data import collect_map_points
    points, diagnostics = collect_map_points(_frames(sheets))
    out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_offline_view("map", {"points": points, "diagnostics": diagnostics}), encoding="utf-8")
    return out, len(points)


def build_call_links(sheets):
    """Aggregate one identified source, never arbitrary first/second columns."""
    candidates = []
    for name, df in _frames(sheets):
        if df.empty or df.attrs.get("source_truncated", False):
            continue
        source = _find_col(df, ("target_number", "a_party", "A-Party", "Target", "subscriber_number", "Mobile / Subscriber No."))
        contact = _find_col(df, ("b_party", "other_party", "Other Party", "Other Party (B-Party)", "B-Party"))
        if not source or not contact or source == contact:
            continue
        low = name.lower()
        raw = bool(df.attrs.get("row_level_source")) or ("full" in low and ("cdr" in low or "loaded data" in low))
        weight = _find_col(df, ("Total Calls", "Total Events", "Event Count"))
        # Timestamp-bearing event tables may be used when full data is absent.
        temporal = _find_col(df, ("datetime", "date", "call_date", "Event Date-Time", "Date-Time"))
        if raw or weight or temporal:
            candidates.append((3 if raw else 2 if weight else 1, len(df), name, df, source, contact, weight if not raw else None))
    if not candidates:
        return {"edges": [], "source_rows": 0, "skipped_rows": 0, "source_sheet": "", "total_links": 0}
    _, _, name, frame, source, contact, weight = max(candidates, key=lambda x: (x[0], x[1], x[2]))
    endpoints = pd.DataFrame({
        "source": frame[source].map(_cell_text).str.strip().to_numpy(),
        "contact": frame[contact].map(_cell_text).str.strip().to_numpy(),
    })
    events = pd.to_numeric(frame[weight], errors="coerce").to_numpy() if weight else [1] * len(frame)
    endpoints["events"] = events
    valid = (
        ~endpoints["source"].str.lower().isin({"", "nan", "none", "-"})
        & ~endpoints["contact"].str.lower().isin({"", "nan", "none", "-"})
        & endpoints["source"].ne(endpoints["contact"])
        & endpoints["events"].notna()
        & endpoints["events"].gt(0)
        & ~endpoints["events"].isin([float("inf"), float("-inf")])
        & endpoints["events"].mod(1).eq(0)
    )
    skipped = int((~valid).sum())
    counts = endpoints.loc[valid].groupby(["source", "contact"], sort=True)["events"].sum().astype("int64").to_dict()
    edges = [{"source": u, "contact": v, "events": int(n)} for (u, v), n in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]
    return {"edges": edges, "source_rows": len(frame), "source_sheet": name, "skipped_rows": skipped, "total_links": len(edges)}


def export_call_link_graph_html(sheets: dict[str, pd.DataFrame], output_path: str | Path) -> tuple[Path, int, int]:
    from .offline_views import render_offline_view
    data = build_call_links(sheets)
    out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_offline_view("graph", data), encoding="utf-8")
    nodes = {endpoint for edge in data["edges"] for endpoint in (edge["source"], edge["contact"])}
    return out, len(nodes), data["total_links"]


def export_court_forensic_brief_html(sheets, output_path, *, report_title="Telecom Analysis Brief"):
    """Printable analytical brief with complete table-snapshot and artifact hashes."""
    from datetime import timezone
    digest = compute_sheets_sha256(sheets)
    frames = list(_frames(sheets))
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sections = []
    for name, df in frames:
        # Display is bounded and labelled; the digest above covers ALL values.
        sample = df.head(25)
        header = "".join("<th>" + html.escape(str(c)) + "</th>" for c in df.columns)
        rows = "".join("<tr>" + "".join("<td>" + html.escape(_cell_text(v)) + "</td>" for v in row) + "</tr>" for row in sample.itertuples(index=False, name=None))
        sections.append(f"<section><h2>{html.escape(name)}</h2><p>Preview: {len(sample)} of {len(df)} rows. Full displayed-table snapshot is hashed.</p><div class='table'><table><thead><tr>{header}</tr></thead><tbody>{rows}</tbody></table></div></section>")
    if not frames:
        raise ValueError("Load analysis tables before creating a brief.")
    doc = """<!doctype html><html><head><meta charset="utf-8"><title>__TITLE__</title><style>
body{font:14px system-ui,sans-serif;margin:30px;color:#172237;line-height:1.6}header{border-bottom:3px solid #168477;padding-bottom:16px}h1{font-size:26px}h2{font-size:18px}section{margin:24px 0}table{border-collapse:collapse;width:100%;font-size:11px}th,td{border:1px solid #ccd4dc;padding:6px;text-align:left;word-break:break-word}th{background:#eaf2f6}.table{overflow:auto}.hash{overflow-wrap:anywhere;font-family:monospace}.notice{padding:14px;background:#eef6f4}button{padding:10px 16px;cursor:pointer}@media print{button{display:none}.table{overflow:visible}thead{display:table-header-group}tr{break-inside:avoid}@page{size:A4 landscape;margin:12mm}}
</style></head><body><header><button onclick="window.print()">Print / Save as PDF</button><h1>EthicalArmor — Analytical Brief</h1><p>__TITLE__<br>Generated: __STAMP__</p></header>
<p class="notice">Derived analytical summary for review. This document is not a chain-of-custody or legal admissibility certificate. Verify findings against original records and independent evidence. Counts across tables may overlap and must not be treated as unique source events.</p>
<h2>Displayed-table snapshot SHA-256 (v2)</h2><p class="hash">__DIGEST__</p><p>Includes every row and column in the loaded tables/sections, including rows beyond the previews. This is not a hash of the original evidence files. The accompanying .sha256 file verifies the exact HTML artifact bytes.</p>__SECTIONS__</body></html>"""
    doc = doc.replace("__TITLE__", html.escape(report_title)).replace("__STAMP__", stamp).replace("__DIGEST__", digest).replace("__SECTIONS__", "".join(sections))
    out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    artifact_hash = hashlib.sha256(out.read_bytes()).hexdigest()
    out.with_suffix(out.suffix + ".sha256").write_text(f"{artifact_hash}  {out.name}\n", encoding="utf-8")
    manifest = {"format": "EthicalArmor/displayed-table-snapshot/v2", "generated_at": stamp, "snapshot_sha256": digest, "html_sha256": artifact_hash, "tables": [{"name": n, "rows": len(f), "columns": list(map(str, f.columns))} for n, f in frames]}
    out.with_suffix(out.suffix + ".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return out, digest
