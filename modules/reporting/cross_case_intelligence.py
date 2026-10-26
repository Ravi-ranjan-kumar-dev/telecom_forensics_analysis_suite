"""Ultra-Fast Cross-Case Intelligence Search Engine for EthicalArmor.

Uses vectorized column matching and DuckDB SQL pushdown to scan saved cases,
Excel reports, Parquet stage files, and evidence CSVs in sub-second time.
"""

from __future__ import annotations

from pathlib import Path
import re
from time import perf_counter
from typing import Any
import pandas as pd


_PRIORITY_COL_KEYWORDS = (
    "subscriber", "party", "number", "msisdn", "target", "contact",
    "mobile", "caller", "callee", "imei", "imsi", "cgi", "cell",
    "tower", "ip", "entity", "identifier", "suspect",
)

_SKIP_DIR_NAMES = {
    ".git", ".venv", "venv", "env", "__pycache__", "build", "dist",
    "master", "sdr_master", "cgi_master", "postgres", "migrations",
}

_SKIP_FILE_KEYWORDS = (
    "cgi_master", "sdr_master", "telecom_master", "master_sdr",
    "master_cgi", "india_cgi", "bihar_sdr", "all_sdr",
)

_SKIP_DUCKDB_TABLES = {
    "sdr_records", "cgi_records", "sdr_master", "cgi_master",
    "telecom_master", "master_sdr", "master_cgi",
}


def normalize_search_tokens(raw_query: str | list[str]) -> dict[str, set[str]]:
    """Return mapping of canonical user query -> set of normalized match variants."""
    if isinstance(raw_query, str):
        parts = [p.strip() for p in re.split(r"[,;\n\r\t]+", raw_query) if p.strip()]
    else:
        parts = [str(p).strip() for p in raw_query if str(p).strip()]

    token_map: dict[str, set[str]] = {}
    for item in parts:
        variants = {item.lower()}
        digits = re.sub(r"\D+", "", item)
        if len(digits) >= 10:
            variants.add(digits)
            core_10 = digits[-10:]
            if len(core_10) == 10:
                variants.add(core_10)
                variants.add(f"91{core_10}")
                variants.add(f"+91{core_10}")
                variants.add(f"0{core_10}")
        token_map[item] = variants
    return token_map


def _infer_case_and_category(file_path: Path, project_root: Path) -> tuple[str, str]:
    try:
        rel = file_path.resolve().relative_to(project_root.resolve())
        parts = rel.parts
    except Exception:
        parts = file_path.parts

    case_id = "Global / Unassigned"
    category = "General Evidence"

    for i, part in enumerate(parts):
        p_low = part.lower()
        if p_low in {"cases", "case_data", "investigations"} and i + 1 < len(parts):
            case_id = parts[i + 1]
        elif p_low.startswith("case_") or p_low.startswith("fir_"):
            case_id = part

        if p_low in {"cdr", "tower_dump", "ipdr", "gprs", "imei", "sdr", "cgi"}:
            category = part.upper().replace("_", " ")

    if case_id == "Global / Unassigned":
        stem_parts = file_path.stem.split("_")
        if len(stem_parts) >= 2:
            case_id = f"{stem_parts[0]}_{stem_parts[1]}"

    return case_id, category


def _select_searchable_columns(df: pd.DataFrame) -> list[Any]:
    cols = list(df.columns)
    priority = [
        c for c in cols
        if any(k in str(c).strip().lower() for k in _PRIORITY_COL_KEYWORDS)
    ]
    if priority:
        return priority
    return cols[:10]


def _match_dataframe(
    df: pd.DataFrame,
    token_map: dict[str, set[str]],
    *,
    case_id: str,
    category: str,
    file_path: Path,
    sheet_name: str,
    max_hits: int = 100,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if df is None or df.empty:
        return [], []

    summary_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []

    search_cols = _select_searchable_columns(df)
    if not search_cols:
        return [], []

    col_series: list[pd.Series] = []
    for c in search_cols:
        try:
            s = df[c].astype("object").fillna("").astype(str)
            col_series.append(s)
        except Exception:
            continue

    if not col_series:
        return [], []

    for canonical_q, variants in token_map.items():
        pattern = "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True) if v)
        if not pattern:
            continue

        mask = pd.Series(False, index=df.index)
        for s in col_series:
            mask = mask | s.str.contains(pattern, case=False, na=False, regex=True)

        match_count = int(mask.sum())
        if match_count == 0:
            continue

        matched_slice = df.loc[mask].head(max_hits).astype("object").fillna("").astype(str)
        preview_cols = list(matched_slice.columns[:8])
        first_row = matched_slice.iloc[0]
        first_row_preview = " | ".join(
            f"{c}: {first_row[c]}"
            for c in preview_cols
            if str(first_row[c]).strip() not in {"", "nan", "None", "<NA>", "-"}
        )

        summary_rows.append(
            {
                "Searched Entity": canonical_q,
                "Case ID / Folder": case_id,
                "Category": category,
                "File Name": file_path.name,
                "Sheet / Table": sheet_name,
                "Total Matches": match_count,
                "Sample Match Preview": first_row_preview[:220],
                "File Path": str(file_path),
            }
        )

        for row_dict in matched_slice.to_dict(orient="records"):
            non_empty_pairs = [
                f"{col}={val}"
                for col, val in list(row_dict.items())[:14]
                if str(val).strip() not in {"", "nan", "None", "<NA>", "-"}
            ]
            detail_rows.append(
                {
                    "Searched Entity": canonical_q,
                    "Case ID / Folder": case_id,
                    "Category": category,
                    "File Name": file_path.name,
                    "Sheet / Table": sheet_name,
                    "Matched Record Details": " | ".join(non_empty_pairs),
                    "File Path": str(file_path),
                }
            )

    return summary_rows, detail_rows


def _iter_candidate_files(project_root: Path) -> list[Path]:
    search_roots = [
        project_root / "cases",
        project_root / "output",
        project_root / "reports",
        project_root / "data",
    ]
    seen: set[Path] = set()
    files: list[Path] = []
    allowed_exts = {".parquet", ".xlsx", ".csv", ".tsv", ".duckdb"}

    for base in search_roots:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if any(part.lower() in _SKIP_DIR_NAMES for part in p.parts):
                continue
            name_low = p.name.lower()
            if name_low.startswith(".") or name_low.startswith("~$"):
                continue
            ext = p.suffix.lower()
            if ext not in allowed_exts:
                continue
            if any(skip in name_low for skip in _SKIP_FILE_KEYWORDS):
                continue
            try:
                size_mb = p.stat().st_size / (1024 * 1024)
                if size_mb > 80:
                    continue
            except Exception:
                continue

            resolved = p.resolve()
            if resolved not in seen:
                seen.add(resolved)
                files.append(p)

    def _sort_key(path: Path) -> tuple[int, float]:
        in_cases = 1 if "cases" in [pt.lower() for pt in path.parts] else 0
        mtime = path.stat().st_mtime if path.exists() else 0.0
        return (in_cases, mtime)

    files.sort(key=_sort_key, reverse=True)
    return files[:120]


def search_across_all_cases(
    raw_query: str | list[str],
    *,
    project_root: Path | None = None,
    max_hits_per_file: int = 100,
    max_scan_seconds: float = 6.0,
) -> dict[str, pd.DataFrame]:
    """Scan saved case folders and reports for matching Mobile Numbers, IMEIs, IMSIs, CGIs, or IPs."""
    root = (project_root or Path.cwd()).resolve()
    token_map = normalize_search_tokens(raw_query)
    if not token_map:
        return {
            "Cross-Case Summary": pd.DataFrame(),
            "Cross-Case Detailed Hits": pd.DataFrame(),
        }

    started = perf_counter()
    all_summaries: list[dict[str, Any]] = []
    all_details: list[dict[str, Any]] = []

    candidate_files = _iter_candidate_files(root)

    for fpath in candidate_files:
        if (perf_counter() - started) > max_scan_seconds:
            break

        ext = fpath.suffix.lower()
        case_id, category = _infer_case_and_category(fpath, root)

        try:
            if ext == ".parquet":
                df = pd.read_parquet(fpath)
                s_rows, d_rows = _match_dataframe(
                    df.head(50_000),
                    token_map,
                    case_id=case_id,
                    category=category,
                    file_path=fpath,
                    sheet_name="Parquet Stage",
                    max_hits=max_hits_per_file,
                )
                all_summaries.extend(s_rows)
                all_details.extend(d_rows)

            elif ext in {".csv", ".tsv"}:
                sep = "\t" if ext == ".tsv" else ","
                df = pd.read_csv(fpath, sep=sep, dtype=str, nrows=30_000, on_bad_lines="skip")
                s_rows, d_rows = _match_dataframe(
                    df,
                    token_map,
                    case_id=case_id,
                    category=category,
                    file_path=fpath,
                    sheet_name="Raw Evidence CSV",
                    max_hits=max_hits_per_file,
                )
                all_summaries.extend(s_rows)
                all_details.extend(d_rows)

            elif ext == ".xlsx":
                xl = pd.ExcelFile(fpath, engine="openpyxl")
                for sname in xl.sheet_names:
                    if (perf_counter() - started) > max_scan_seconds:
                        break
                    if "methodology" in sname.lower() or "chain_of_custody" in sname.lower():
                        continue
                    df = xl.parse(sname, dtype=str, nrows=15_000)
                    s_rows, d_rows = _match_dataframe(
                        df,
                        token_map,
                        case_id=case_id,
                        category=category,
                        file_path=fpath,
                        sheet_name=sname,
                        max_hits=max_hits_per_file,
                    )
                    all_summaries.extend(s_rows)
                    all_details.extend(d_rows)

            elif ext == ".duckdb":
                import duckdb
                con = duckdb.connect(str(fpath), read_only=True)
                try:
                    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
                    for tbl in tables:
                        if str(tbl).lower() in _SKIP_DUCKDB_TABLES:
                            continue
                        if (perf_counter() - started) > max_scan_seconds:
                            break
                        df = con.execute(f'SELECT * FROM "{tbl}" LIMIT 25000').df()
                        s_rows, d_rows = _match_dataframe(
                            df,
                            token_map,
                            case_id=case_id,
                            category=category,
                            file_path=fpath,
                            sheet_name=f"DuckDB:{tbl}",
                            max_hits=max_hits_per_file,
                        )
                        all_summaries.extend(s_rows)
                        all_details.extend(d_rows)
                finally:
                    con.close()
        except Exception:
            continue

    summary_df = pd.DataFrame(all_summaries)
    detail_df = pd.DataFrame(all_details)

    if not summary_df.empty:
        summary_df = summary_df.sort_values(by=["Total Matches"], ascending=False).reset_index(drop=True)
        summary_df.attrs["preserve_excel_columns"] = True
    if not detail_df.empty:
        detail_df.attrs["preserve_excel_columns"] = True

    return {
        "Cross-Case Summary": summary_df,
        "Cross-Case Detailed Hits": detail_df,
    }
