"""Full-dump suspect and B-Party search across 100% of Tower Dump datasets."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

import duckdb
import pandas as pd

from modules.enrichment.sdr_subscriber_enrichment import (
    lookup_sdr_subscribers,
    normalize_mobile_number,
)
from modules.loader.identity import normalize_msisdn


def clean_mobile_key(value: object) -> str:
    """Normalize phone number to canonical 10-digit Indian mobile where possible."""
    text = str(value if value is not None else "").strip()
    if not text or text.lower() in {"nan", "none", "<na>", "null"}:
        return ""
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    norm = normalize_msisdn(text) or normalize_mobile_number(text)
    if norm:
        return norm
    digits = re.sub(r"\D+", "", text)
    if len(digits) == 12 and digits.startswith("91"):
        return digits[-10:]
    if len(digits) == 11 and digits.startswith("0"):
        return digits[-10:]
    return digits


def parse_target_numbers(query: object) -> list[str]:
    """Parse one or more comma/space/semicolon separated target numbers."""
    raw_items = re.split(r"[,;\s]+", str(query or "").strip())
    cleaned: list[str] = []
    for item in raw_items:
        if not item:
            continue
        mobile = clean_mobile_key(item)
        if len(mobile) >= 8 and mobile not in cleaned:
            cleaned.append(mobile)
    return cleaned


def _joined_unique(series: pd.Series, limit: int = 15) -> str:
    seen: list[str] = []
    for val in series.dropna().astype(str):
        v = val.strip()
        if not v or v.lower() in {"nan", "none", "<na>"}:
            continue
        if v not in seen:
            seen.append(v)
        if len(seen) >= limit:
            break
    return ", ".join(seen)


def load_full_tower_dump_dataframe(
    case_id: str,
    *,
    source_type: str,
    input_folder: str | Path,
    selected_spot_folders: Iterable[str] | None = None,
    include_root_files: bool = True,
) -> pd.DataFrame:
    """Load 100% of the Tower Dump from verified Parquet/DuckDB stage or raw files."""
    mode = str(source_type or "cdr").strip().casefold()
    folder = Path(input_folder).expanduser().resolve()

    if mode == "cdr":
        from modules.controllers.tower_cdr_controller import _load_tower_cdr_with_reuse
        from modules.staging.tower_cdr_staging import (
            save_tower_cdr_reuse_manifest,
            stage_tower_cdr_dataframe,
            tower_cdr_parquet_path,
        )

        res = _load_tower_cdr_with_reuse(
            case_id,
            folder,
            selected_spot_folders=selected_spot_folders,
            include_root_files=include_root_files,
        )
        df = res.get("df")
        if isinstance(df, pd.DataFrame) and not df.empty:
            if not res.get("cache_reused"):
                try:
                    stage_tower_cdr_dataframe(
                        case_id=case_id,
                        dataframe=df,
                        input_folder=folder,
                        stage_reason="tower_cdr_full_search",
                        selected_spot_folders=selected_spot_folders,
                        include_root_files=include_root_files,
                    )
                    save_tower_cdr_reuse_manifest(
                        case_id,
                        folder,
                        df,
                        selected_spot_folders=selected_spot_folders,
                        include_root_files=include_root_files,
                    )
                except Exception:
                    pass
            return df

        parquet_file = tower_cdr_parquet_path(case_id)
        if parquet_file.is_file():
            return pd.read_parquet(parquet_file)
        return pd.DataFrame()

    if mode == "gprs":
        from modules.loader.gprs_dump_loader import load_gprs_dump_case
        from modules.staging.tower_gprs_staging import tower_gprs_parquet_path

        res = load_gprs_dump_case(
            folder,
            recursive=True,
            selected_spot_folders=selected_spot_folders,
            include_root_files=include_root_files,
        )
        df = res.get("df")
        if isinstance(df, pd.DataFrame) and not df.empty:
            return df
        parquet_file = tower_gprs_parquet_path(case_id)
        if parquet_file.is_file():
            return pd.read_parquet(parquet_file)
        return pd.DataFrame()

    if mode == "ipdr":
        from modules.loader.tower_ipdr_loader import load_tower_ipdr_case
        from modules.staging.tower_ipdr_staging import (
            TABLE_EVENTS,
            import_tower_ipdr_folder_to_duckdb,
            tower_ipdr_database_path,
        )

        db_path = tower_ipdr_database_path(case_id)
        if not db_path.is_file():
            try:
                import_tower_ipdr_folder_to_duckdb(
                    case_id,
                    folder,
                    recursive=True,
                    selected_spot_folders=selected_spot_folders,
                    include_root_files=include_root_files,
                )
            except Exception:
                pass
        if db_path.is_file():
            try:
                with duckdb.connect(str(db_path), read_only=True) as con:
                    return con.execute(f"SELECT * FROM {TABLE_EVENTS}").df()
            except Exception:
                pass
        res = load_tower_ipdr_case(folder, recursive=True)
        df = res.get("df")
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()

    raise ValueError(f"Unsupported Tower Dump source type: {source_type}")


def _attach_sdr_columns(df: pd.DataFrame, number_col: str) -> pd.DataFrame:
    if df.empty or number_col not in df.columns:
        return df
    out = df.copy()
    keys = out[number_col].map(clean_mobile_key)
    valid_keys = sorted({k for k in keys if len(k) == 10 and k[0] in "6789"})
    if not valid_keys:
        out["SDR Name"] = ""
        out["SDR Father Name"] = ""
        out["SDR Address"] = ""
        out["SDR Operator"] = ""
        return out

    try:
        sdr_df = lookup_sdr_subscribers(valid_keys)
    except Exception:
        sdr_df = pd.DataFrame()

    sdr_map: dict[str, dict[str, str]] = {}
    if isinstance(sdr_df, pd.DataFrame) and not sdr_df.empty:
        for _, row in sdr_df.iterrows():
            if str(row.get("sdr_found", "")).upper() != "YES":
                continue
            mob = str(row.get("lookup_mobile", "")).strip()
            if mob:
                sdr_map[mob] = {
                    "name": str(row.get("subscriber_name", "") or ""),
                    "father": str(row.get("father_name", "") or ""),
                    "address": str(row.get("subscriber_address", "") or ""),
                    "operator": str(row.get("operator", "") or ""),
                }

    out["SDR Name"] = keys.map(lambda k: sdr_map.get(k, {}).get("name", ""))
    out["SDR Father Name"] = keys.map(lambda k: sdr_map.get(k, {}).get("father", ""))
    out["SDR Address"] = keys.map(lambda k: sdr_map.get(k, {}).get("address", ""))
    out["SDR Operator"] = keys.map(lambda k: sdr_map.get(k, {}).get("operator", ""))
    return out


def search_suspect_and_b_parties_in_dataframe(
    df: pd.DataFrame,
    target_query: object,
    *,
    source_type: str = "cdr",
) -> dict[str, Any]:
    """Search one or more suspected numbers and all their B-Parties across full dump."""
    targets = parse_target_numbers(target_query)
    if not targets:
        raise ValueError("Enter at least one valid 10-digit mobile number to search.")

    if not isinstance(df, pd.DataFrame) or df.empty:
        return {
            "targets": targets,
            "total_dump_records": 0,
            "matched_count": 0,
            "suspect_summary": pd.DataFrame(),
            "counterparty_summary": pd.DataFrame(),
            "matched_records": pd.DataFrame(),
        }

    work = df.copy()
    sub_col = "subscriber_number" if "subscriber_number" in work.columns else None
    other_col = (
        "other_party"
        if "other_party" in work.columns
        else "b_party"
        if "b_party" in work.columns
        else None
    )

    work["_sub_clean"] = (
        work[sub_col].map(clean_mobile_key)
        if sub_col
        else pd.Series("", index=work.index, dtype="string")
    )
    work["_other_clean"] = (
        work[other_col].map(clean_mobile_key)
        if other_col
        else pd.Series("", index=work.index, dtype="string")
    )

    time_col = next(
        (
            c
            for c in ("call_datetime", "event_time", "session_start", "call_date")
            if c in work.columns
        ),
        None,
    )
    dur_col = next(
        (
            c
            for c in (
                "call_duration",
                "session_duration_seconds",
                "event_duration_seconds",
            )
            if c in work.columns
        ),
        None,
    )
    cell_col = next(
        (
            c
            for c in ("searched_cell_id", "first_cell_id", "cgi")
            if c in work.columns
        ),
        None,
    )

    target_set = set(targets)
    is_sub = work["_sub_clean"].isin(target_set)
    is_other = work["_other_clean"].isin(target_set)
    matched_mask = is_sub | is_other

    matched_df = work.loc[matched_mask].copy()

    suspect_rows: list[dict[str, Any]] = []
    counterparty_rows: list[dict[str, Any]] = []

    for target in targets:
        t_sub = work["_sub_clean"].eq(target)
        t_other = work["_other_clean"].eq(target)
        t_all = work.loc[t_sub | t_other]

        sub_hits = int(t_sub.sum())
        other_hits = int(t_other.sum())
        total_hits = int(len(t_all))

        if sub_hits > 0 and other_hits > 0:
            role = "BOTH (Tower Subscriber + B-Party)"
        elif sub_hits > 0:
            role = "TOWER_SUBSCRIBER (Present at Tower)"
        elif other_hits > 0:
            role = "B_PARTY_ONLY (Remote Counterparty)"
        else:
            role = "NOT_FOUND"

        counterparties: set[str] = set()
        if sub_hits > 0 and other_col:
            counterparties.update(
                v for v in work.loc[t_sub, "_other_clean"].tolist() if v and v != target
            )
        if other_hits > 0 and sub_col:
            counterparties.update(
                v for v in work.loc[t_other, "_sub_clean"].tolist() if v and v != target
            )

        spots = _joined_unique(t_all["spot_name"]) if "spot_name" in t_all.columns else ""
        cells = _joined_unique(t_all[cell_col]) if cell_col and cell_col in t_all.columns else ""
        imeis = _joined_unique(work.loc[t_sub, "imei"]) if "imei" in work.columns and sub_hits else ""
        imsis = _joined_unique(work.loc[t_sub, "imsi"]) if "imsi" in work.columns and sub_hits else ""

        first_seen = ""
        last_seen = ""
        if time_col and not t_all.empty:
            ts = pd.to_datetime(t_all[time_col], errors="coerce").dropna()
            if not ts.empty:
                first_seen = str(ts.min())
                last_seen = str(ts.max())

        total_dur = 0
        if dur_col and not t_all.empty:
            total_dur = int(
                pd.to_numeric(t_all[dur_col], errors="coerce").fillna(0).clip(lower=0).sum()
            )

        suspect_rows.append(
            {
                "Suspected Number": target,
                "Role in Tower Dump": role,
                "Total Hits": total_hits,
                "As Tower Subscriber (A-Party)": sub_hits,
                "As Remote B-Party": other_hits,
                "Unique B-Party Contacts": len(counterparties),
                "Total Duration (Sec)": total_dur,
                "Spots Detected": spots,
                "Cells / CGI": cells,
                "Observed IMEI (at Tower)": imeis,
                "Observed IMSI (at Tower)": imsis,
                "First Seen": first_seen,
                "Last Seen": last_seen,
            }
        )

        # Build Counterparty / B-Party breakdown for this suspect
        if not t_all.empty and other_col:
            temp = t_all.copy()
            temp["_counterparty"] = temp["_other_clean"].where(
                temp["_sub_clean"].eq(target),
                temp["_sub_clean"],
            )
            temp["_relation"] = temp["_sub_clean"].eq(target).map(
                lambda is_s: "Suspect at Tower <-> B-Party"
                if is_s
                else "Tower Subscriber <-> Suspect (as B-Party)"
            )
            temp = temp[temp["_counterparty"].ne("") & temp["_counterparty"].ne(target)]

            for (cp_num, rel), grp in temp.groupby(["_counterparty", "_relation"], dropna=False):
                ctype = (
                    grp["call_type"].fillna("").astype(str).str.lower()
                    if "call_type" in grp.columns
                    else pd.Series("", index=grp.index)
                )
                inc = int(ctype.str.contains("in|mtc", regex=True).sum())
                outg = int(ctype.str.contains("out|moc", regex=True).sum())
                dur_val = (
                    int(pd.to_numeric(grp[dur_col], errors="coerce").fillna(0).clip(lower=0).sum())
                    if dur_col
                    else 0
                )
                cp_first, cp_last = "", ""
                if time_col:
                    ts_cp = pd.to_datetime(grp[time_col], errors="coerce").dropna()
                    if not ts_cp.empty:
                        cp_first = str(ts_cp.min())
                        cp_last = str(ts_cp.max())

                counterparty_rows.append(
                    {
                        "Suspected Number": target,
                        "Counterparty / B-Party": str(cp_num),
                        "Interaction Role": str(rel),
                        "Total Events": len(grp),
                        "Incoming": inc,
                        "Outgoing": outg,
                        "Total Duration (Sec)": dur_val,
                        "Spots": _joined_unique(grp["spot_name"]) if "spot_name" in grp.columns else "",
                        "Cells / CGI": _joined_unique(grp[cell_col]) if cell_col else "",
                        "First Seen": cp_first,
                        "Last Seen": cp_last,
                    }
                )
        elif not t_all.empty and str(source_type).casefold() == "ipdr" and "destination_ip" in t_all.columns:
            from modules.analysis.ipdr.ip_port_intelligence import classify_ip_and_port

            temp = t_all[t_all["destination_ip"].fillna("").astype(str).str.strip().ne("")].copy()
            temp["_dport"] = (
                pd.to_numeric(temp.get("destination_port"), errors="coerce")
                .astype("Int64")
                .astype(str)
                .replace("<NA>", "")
            )
            for (dip, dport), grp in temp.groupby(["destination_ip", "_dport"], dropna=False):
                info = classify_ip_and_port(str(dip), dport)
                cp_first, cp_last = "", ""
                if time_col:
                    ts_cp = pd.to_datetime(grp[time_col], errors="coerce").dropna()
                    if not ts_cp.empty:
                        cp_first = str(ts_cp.min())
                        cp_last = str(ts_cp.max())
                counterparty_rows.append(
                    {
                        "Suspected Number": target,
                        "Counterparty / B-Party": f"{dip}:{dport}" if dport else str(dip),
                        "Interaction Role": f"{info['application_name']} ({info['ip_company']})",
                        "Total Events": len(grp),
                        "Incoming": 0,
                        "Outgoing": len(grp),
                        "Total Duration (Sec)": int(
                            pd.to_numeric(grp[dur_col], errors="coerce").fillna(0).clip(lower=0).sum()
                        )
                        if dur_col
                        else 0,
                        "Spots": _joined_unique(grp["spot_name"]) if "spot_name" in grp.columns else "",
                        "Cells / CGI": _joined_unique(grp[cell_col]) if cell_col else "",
                        "First Seen": cp_first,
                        "Last Seen": cp_last,
                    }
                )

    suspect_df = _attach_sdr_columns(pd.DataFrame(suspect_rows), "Suspected Number")
    counterparty_df = _attach_sdr_columns(
        pd.DataFrame(counterparty_rows),
        "Counterparty / B-Party",
    )
    if not counterparty_df.empty and "Total Events" in counterparty_df.columns:
        counterparty_df = counterparty_df.sort_values(
            ["Total Events", "Total Duration (Sec)"],
            ascending=[False, False],
            ignore_index=True,
        )

    clean_records = matched_df.drop(
        columns=[c for c in ("_sub_clean", "_other_clean") if c in matched_df.columns]
    )
    if time_col and time_col in clean_records.columns:
        clean_records = clean_records.sort_values(time_col, kind="stable").reset_index(drop=True)

    return {
        "targets": targets,
        "total_dump_records": len(df),
        "matched_count": len(clean_records),
        "suspect_summary": suspect_df,
        "counterparty_summary": counterparty_df,
        "matched_records": clean_records,
    }
