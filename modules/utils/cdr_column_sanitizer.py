# Consolidates duplicate CDR columns and enforces the exact 11-column canonical sequence
# on Full CDR Data: target_number, b_party, date, time, duration, call_type,
# first_cgi, last_cgi, imei, imsi, tower_address
from __future__ import annotations

from typing import Any
import pandas as pd

CANONICAL_CDR_SEQUENCE: list[str] = [
    'target_number',
    'b_party',
    'date',
    'time',
    'duration',
    'call_type',
    'first_cgi',
    'last_cgi',
    'imei',
    'imsi',
]

COLUMN_ALIAS_GROUPS: dict[str, list[str]] = {
    'target_number': [
        'target_number', 'target_no', 'target_msisdn', 'target_num', 'target',
        'a_party', 'aparty', 'party_a', 'partya', 'a_party_number', 'a_party_no',
        'a_number', 'anumber', 'a_no', 'calling_number', 'calling_no',
        'calling_party', 'calling_party_number', 'calling_msisdn',
        'caller_number', 'caller_no', 'caller', 'msisdn', 'served_msisdn',
        'served_number', 'subscriber_number', 'subscriber_no', 'subscriber_msisdn',
        'source_number', 'orig_number', 'originating_number',
    ],
    'b_party': [
        'b_party', 'bparty', 'party_b', 'partyb', 'b_party_number', 'b_party_no',
        'b_number', 'bnumber', 'b_no', 'b_msisdn', 'other_party',
        'other_party_number', 'other_number', 'other_no', 'other_msisdn',
        'called_number', 'called_no', 'called_party', 'called_party_number',
        'called_msisdn', 'callee_number', 'callee_no', 'callee',
        'counter_party', 'counterparty', 'remote_party', 'dialed_number',
        'dialled_number', 'dialed_no', 'dialled_no', 'destination_number',
        'dest_number', 'term_number', 'terminating_number',
    ],
    'date': [
        'date', 'call_date', 'event_date', 'start_date', 'cdr_date',
        'record_date', 'date_of_call', 'call_start_date', 'activity_date',
    ],
    'time': [
        'time', 'call_time', 'event_time', 'start_time', 'cdr_time',
        'record_time', 'time_of_call', 'call_start_time', 'activity_time',
    ],
    'duration': [
        'duration', 'call_duration', 'duration_sec', 'duration_seconds',
        'dur', 'talk_time', 'talktime', 'bill_sec', 'billed_seconds',
        'charge_duration', 'call_dur',
    ],
    'call_type': [
        'raw_call_type', 'call_type_raw', 'type_of_call', 'toc',
        'call_type', 'calltype',
    ],
    'first_cgi': [
        'first_cgi', 'first_cell_id', 'first_cell', 'first_cell_cgi',
        'cgi_first', 'start_cgi', 'orig_cgi', 'source_cgi', 'cgi',
        'cell_id', 'cellid', 'first_cgi_id', 'normalized_first_cgi',
        'raw_first_cgi', 'first_lac_cell',
    ],
    'last_cgi': [
        'last_cgi', 'last_cell_id', 'last_cell', 'last_cell_cgi',
        'cgi_last', 'end_cgi', 'term_cgi', 'dest_cgi', 'last_cgi_id',
        'normalized_last_cgi', 'raw_last_cgi', 'last_lac_cell',
    ],
    'imei': [
        'imei', 'imei_number', 'imei_no', 'served_imei', 'device_imei',
        'handset_imei', 'normalized_imei', 'raw_imei', 'imei_norm',
    ],
    'imsi': [
        'imsi', 'imsi_number', 'imsi_no', 'served_imsi', 'subscriber_imsi',
        'normalized_imsi', 'raw_imsi', 'imsi_norm',
    ],
    'tower_address': [
        'tower_address', 'site_address', 'cell_address', 'first_tower_address',
        'first_site_address', 'tower_location', 'location_address',
        'cell_site_address', 'bts_address', 'address', 'site_name',
        'tower_name', 'first_tower_location', 'location', 'landmark',
    ],
}


def _norm_key(col: Any) -> str:
    s = ''.join(ch if ch.isalnum() else '_' for ch in str(col).strip().lower())
    while '__' in s:
        s = s.replace('__', '_')
    return s.strip('_')


def _coalesce_series(df: pd.DataFrame, cols: list[str], preferred: list[str]) -> pd.Series:
    col_map = {c: _norm_key(c) for c in cols}
    ordered = sorted(
        cols,
        key=lambda c: (
            preferred.index(col_map[c]) if col_map[c] in preferred else 999,
            cols.index(c),
        ),
    )
    sub = df.loc[:, ~df.columns.duplicated()][list(dict.fromkeys(ordered))].copy()
    sub.attrs = {}
    for _c in sub.columns:
        sub[_c] = sub[_c].fillna('').astype(str).str.strip()
    sub = sub.replace({
        '': pd.NA, 'nan': pd.NA, 'None': pd.NA, 'null': pd.NA,
        '<NA>': pd.NA, 'NaT': pd.NA, 'nat': pd.NA,
    })
    return sub.bfill(axis=1).iloc[:, 0].fillna('')


def _split_datetime_fallback(df: pd.DataFrame) -> None:
    col_map = {col: _norm_key(col) for col in df.columns}
    dt_aliases = {'datetime', 'call_datetime', 'event_datetime', 'timestamp', 'start_datetime', 'date_time'}
    dt_cols = [c for c, k in col_map.items() if k in dt_aliases]
    if not dt_cols:
        return
    dt_series = df[dt_cols[0]].astype(str).str.strip()
    parts = dt_series.str.split(r'\s+|T', n=1, expand=True)
    if 'date' not in df.columns or (df['date'].astype(str).str.strip() == '').all():
        if parts.shape[1] >= 1:
            df['date'] = parts[0].replace({'nan': '', 'None': '', 'NaT': ''}).fillna('')
    if 'time' not in df.columns or (df['time'].astype(str).str.strip() == '').all():
        if parts.shape[1] >= 2:
            df['time'] = parts[1].replace({'nan': '', 'None': '', 'NaT': ''}).fillna('')


def sanitize_cdr_sheet_columns(df: pd.DataFrame, sheet_name: str = '') -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df

    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()].copy()
    else:
        df = df.copy()

    col_map = {col: _norm_key(col) for col in df.columns}
    target_set = set(COLUMN_ALIAS_GROUPS['target_number'])
    bparty_set = set(COLUMN_ALIAS_GROUPS['b_party'])
    has_target = any(k in target_set for k in col_map.values())
    has_bparty = any(k in bparty_set for k in col_map.values())

    sname = str(sheet_name).strip().lower()
    is_full_cdr_sheet = sname in {
        'full cdr data', 'full_cdr_data', 'full cdr', 'cdr data',
        'cdr_data', 'all_cdr', 'raw cdr data', 'clean cdr data',
    } or ('full' in sname and 'cdr' in sname)
    is_row_level_cdr = is_full_cdr_sheet

    if not is_row_level_cdr:
        return df

    # Consolidate the visible canonical columns from all matching alias columns
    for canonical_col in CANONICAL_CDR_SEQUENCE:
        preferred_list = COLUMN_ALIAS_GROUPS[canonical_col]
        alias_set = set(preferred_list)
        col_map = {col: _norm_key(col) for col in df.columns}
        matching_cols = [c for c, k in col_map.items() if k in alias_set]
        if matching_cols:
            if canonical_col == 'call_type':
                ordered = sorted(matching_cols, key=lambda c: preferred_list.index(_norm_key(c)))
                merged_series = df[ordered[0]].astype("string").fillna("")
            else:
                merged_series = _coalesce_series(df, matching_cols, preferred_list)
            first_idx = min(int(df.columns.get_loc(c)) for c in matching_cols)
            df.drop(columns=matching_cols, inplace=True)
            df.insert(first_idx, canonical_col, merged_series)
        elif is_full_cdr_sheet:
            df[canonical_col] = ''

    # Populate date/time from combined datetime column if either is blank
    _split_datetime_fallback(df)

    if is_full_cdr_sheet:
        # Enforce the visible column sequence for Full CDR Data
        for col in CANONICAL_CDR_SEQUENCE:
            if col not in df.columns:
                df[col] = ''
        df = df[CANONICAL_CDR_SEQUENCE].copy()
    else:
        # For other row-level tables, place present canonical columns first in exact sequence
        front_cols = [c for c in CANONICAL_CDR_SEQUENCE if c in df.columns]
        other_cols = [c for c in df.columns if c not in front_cols]
        df = df[front_cols + other_cols].copy()

    return df


def sanitize_sheets_dict(sheets: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    if not sheets or not isinstance(sheets, dict):
        return sheets
    cleaned: dict[str, pd.DataFrame] = {}
    for name, df in sheets.items():
        if isinstance(df, pd.DataFrame):
            cleaned[str(name)] = sanitize_cdr_sheet_columns(df, sheet_name=str(name))
        else:
            cleaned[str(name)] = pd.DataFrame(df) if df is not None else pd.DataFrame()
    return cleaned


# --- REMOVE_TOWER_ADDRESS_PATCH ---
_base_sanitize_cdr_sheet_columns = sanitize_cdr_sheet_columns

def sanitize_cdr_sheet_columns(df, sheet_name: str = ""):
    saved_attrs = dict(getattr(df, "attrs", {}) or {}) if isinstance(df, pd.DataFrame) else {}
    if df is not None and hasattr(df, "attrs"):
        df = df.copy()
        df.attrs = {}
    res = _base_sanitize_cdr_sheet_columns(df, sheet_name)
    if isinstance(res, pd.DataFrame) and saved_attrs:
        res.attrs.update(saved_attrs)
    return res


