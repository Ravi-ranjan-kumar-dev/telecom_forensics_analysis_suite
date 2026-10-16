# Central in-memory store for GUI-First interactive analysis tables.

from typing import Any
import re
import pandas as pd

from modules.reporting.report_sanitizer import clean_report_dataframe

_LATEST_GUI_SHEETS: dict[str, pd.DataFrame] = {}
_LATEST_GUI_META: dict[str, Any] = {}

COACTIVITY_PROTECTED = {
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

_IP_IN_CGI_REGEX = re.compile(
    r"^(?:(?:\d{1,3}\.){3}\d{1,3}|.*:.*|.*(?:wlan|wifi|epdg|ipv4|ipv6).*)$",
    re.IGNORECASE,
)


def is_ip_or_vowifi_value(val: object) -> bool:
    if val is None:
        return False
    s = str(val).strip()
    if not s:
        return False
    if _IP_IN_CGI_REGEX.match(s):
        return True
    parts = [p.strip() for p in re.split(r"[-./:\s]+", s) if p.strip()]
    if len(parts) == 4 and parts[0] not in {"404", "405"} and all(
        p.isdigit() and 0 <= int(p) <= 255 for p in parts
    ):
        return True
    return False


def strip_ips_from_cgi_columns(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df
    out = df.copy()
    for col in list(out.columns):
        col_low = str(col).strip().lower()
        is_cell_col = any(
            k in col_low
            for k in (
                "cell_id",
                "cell id",
                "cgi",
                "tower",
                "first_cell",
                "last_cell",
                "first_location",
                "last_location",
                "location",
            )
        ) and not any(
            skip in col_low
            for skip in ("address", "site_name", "town", "circle", "operator", "count", "calls", "duration")
        )
        if is_cell_col:
            s = out[col].astype("object").fillna("").astype(str).str.strip()
            mask_ip = s.map(is_ip_or_vowifi_value)
            if mask_ip.any():
                out[col] = s.where(~mask_ip, "")

    if len(out.columns) > 0:
        first_col_low = str(out.columns[0]).strip().lower()
        if any(k in first_col_low for k in ("tower", "cell", "cgi", "location")):
            s0 = out.iloc[:, 0].astype("object").fillna("").astype(str).str.strip()
            out = out[s0.ne("") & ~s0.str.lower().isin({"nan", "none", "unknown", "-"})].reset_index(drop=True)
    return out


def store_gui_sheets(
    sheets: dict[str, pd.DataFrame],
    *,
    title: str = "Forensic Analysis Results",
    workflow: str = "general",
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, pd.DataFrame]:
    cleaned_sheets: dict[str, pd.DataFrame] = {}
    for name, df in (sheets or {}).items():
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        frame = df.head(100_000).copy()
        if "ipdr" not in workflow.lower():
            frame = strip_ips_from_cgi_columns(frame)
        cleaned = clean_report_dataframe(
            frame,
            keep_columns=COACTIVITY_PROTECTED,
            clean_headers=True,
        )
        if not cleaned.empty and len(cleaned.columns) > 0:
            cleaned_sheets[str(name)] = cleaned

    if cleaned_sheets:
        _LATEST_GUI_SHEETS.clear()
        _LATEST_GUI_SHEETS.update(cleaned_sheets)
        _LATEST_GUI_META.clear()
        _LATEST_GUI_META["title"] = title
        _LATEST_GUI_META["workflow"] = workflow
        if extra_meta:
            _LATEST_GUI_META.update(extra_meta)
    return cleaned_sheets


def get_latest_gui_sheets() -> dict[str, pd.DataFrame]:
    return dict(_LATEST_GUI_SHEETS)


def get_latest_gui_meta() -> dict[str, Any]:
    return dict(_LATEST_GUI_META)
