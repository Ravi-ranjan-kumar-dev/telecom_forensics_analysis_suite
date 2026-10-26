"""Read-only full Tower CDR search using a verified normalized DuckDB/Parquet stage.

Never trusts a previously staged dataset until its evidence selection fingerprint matches.
Counts/search aggregations are computed across the entire staged dataset; returned
matched row preview is intentionally capped to keep the desktop UI responsive.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import duckdb
import pandas as pd


class StageUnavailable(RuntimeError):
    """The user's current evidence selection has no verified complete stage."""


def _id(name: str) -> str:
    """Quote a SQL identifier (schema columns are untrusted)."""
    return '"' + str(name).replace('"', '""') + '"'


def _sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _digits(col: str) -> str:
    raw = f"TRIM(COALESCE(CAST(e.{_id(col)} AS VARCHAR), ''))"
    # Telecom IDs sometimes reach loaders as float-looking strings, e.g. 9000000001.0
    stripped = f"(CASE WHEN regexp_matches({raw}, '^[0-9]+[.]0+$') THEN split_part({raw}, '.', 1) ELSE {raw} END)"
    return f"regexp_replace({stripped}, '[^0-9]', '', 'g')"


def _mobile_sql(col: str | None) -> str:
    if col is None:
        return "''"
    d = _digits(col)
    return (f"(CASE WHEN length({d}) = 12 AND starts_with({d}, '91') THEN right({d}, 10) "
            f"WHEN length({d}) = 11 AND starts_with({d}, '0') THEN right({d}, 10) ELSE {d} END)")


def _device_sql(col: str | None) -> str:
    return _digits(col) if col is not None else "''"


def _first(columns: set[str], *names: str) -> str | None:
    return next((n for n in names if n in columns), None)


def _expr(column: str | None) -> str:
    return f'CAST({_id(column)} AS VARCHAR)' if column else "''"


def _safe_num(column: str | None) -> str:
    return f'GREATEST(COALESCE(TRY_CAST({_id(column)} AS DOUBLE), 0), 0)' if column else '0'


def _str_agg(column: str | None) -> str:
    return f"COALESCE(string_agg(DISTINCT NULLIF(TRIM({_expr(column)}), ''), ', '), '')" if column else "''"


def _scan_targets(query: object) -> list[str]:
    from modules.analysis.towerdump.full_dump_search import parse_target_numbers
    return parse_target_numbers(query)


def search_verified_tower_cdr_stage(
    case_id: str, *, input_folder: str | Path,
    selected_spot_folders: Iterable[str] | None = None,
    include_root_files: bool = True, query: object,
    preview_limit: int = 5000, counterparty_limit: int = 2000,
) -> dict[str, Any]:
    """Search ALL rows of a verified Tower CDR stage without pandas-loading the dump.

    Supports mobile A/B party and exact IMEI/IMSI. No fuzzy substring matching.
    Missing or stale stage is an explicit error: never silently search older evidence.
    """
    from modules.staging.tower_cdr_staging import (
        tower_cdr_input_fingerprint, load_latest_tower_cdr_stage,
        tower_cdr_parquet_path,
    )

    targets = _scan_targets(query)
    if not targets:
        raise ValueError('Enter valid mobile numbers or IMEI/IMSI identifiers.')
    mobile = [t for t in targets if len(t) < 14]
    devices = [t for t in targets if len(t) >= 14]
    if len(targets) > 100:
        raise ValueError('Search at most 100 distinct targets at once.')
    if not 1 <= preview_limit <= 100_000 or not 1 <= counterparty_limit <= 100_000:
        raise ValueError('Invalid bounded result size.')

    manifest = load_latest_tower_cdr_stage(str(case_id))
    if not isinstance(manifest, dict) or not isinstance(manifest.get('input_fingerprint'), dict):
        raise StageUnavailable('No verified Tower CDR stage. Run Complete Analysis for these files/spots first.')
    current_fp = tower_cdr_input_fingerprint(
        input_folder, selected_spot_folders=selected_spot_folders,
        include_root_files=include_root_files,
    )
    saved_fp = manifest['input_fingerprint']
    if current_fp != saved_fp or not current_fp.get('file_count'):
        raise StageUnavailable(
            'Tower CDR evidence or selected spots changed since staging. '
            'Run Complete Analysis again before searching; no old cached data was used.'
        )
    parquet = tower_cdr_parquet_path(str(case_id))
    if not parquet.is_file():
        raise StageUnavailable('Verified stage Parquet missing. Run Complete Analysis again.')

    # In-memory DuckDB only owns bounded query state; evidence parquet is read-only.
    # DuckDB may spill large temporary matching sets to its own temporary storage.
    with duckdb.connect(database=':memory:') as con:
        source = f'read_parquet({_sql_literal(str(parquet.resolve()))})'
        header = con.execute(f'SELECT * FROM {source} LIMIT 0').description
        column_order = [x[0] for x in header]
        cols = set(column_order)
        a = _first(cols, 'subscriber_number')
        b = _first(cols, 'other_party', 'b_party')
        imei = _first(cols, 'imei')
        imsi = _first(cols, 'imsi')
        if not (a or b or imei or imsi):
            raise StageUnavailable('The staged Tower CDR has no searchable number/IMEI/IMSI columns.')
        if mobile and not (a or b):
            raise StageUnavailable('The stage has no A/B party number columns.')
        if devices and not (imei or imsi):
            raise StageUnavailable('The stage has no IMEI/IMSI columns.')

        projections = [
            f'{_mobile_sql(a)} AS "_ea_sub"',
            f'{_mobile_sql(b)} AS "_ea_other"',
            f'{_device_sql(imei)} AS "_ea_imei"',
            f'{_device_sql(imsi)} AS "_ea_imsi"',
        ]
        conditions = []
        for field in (('_ea_sub', mobile), ('_ea_other', mobile),
                      ('_ea_imei', devices), ('_ea_imsi', devices)):
            name, values = field
            if values:
                conditions.append(f'{_id(name)} IN ({", ".join(_sql_literal(v) for v in values)})')
        where = ' OR '.join(conditions) or 'FALSE'
        # Single Parquet scan to materialize only target-matching rows in DuckDB.
        con.execute(
            'CREATE TEMP TABLE ea_hits AS '
            'SELECT * FROM (SELECT e.*, ' + ', '.join(projections) +
            f' FROM {source} AS e) AS s WHERE {where}',
        )
        total = int(con.execute(f'SELECT COUNT(*) FROM {source}').fetchone()[0])
        matched = int(con.execute('SELECT COUNT(*) FROM ea_hits').fetchone()[0])

        time_col = _first(cols, 'call_datetime', 'event_time', 'session_start', 'call_date')
        dur_col = _first(cols, 'call_duration', 'session_duration_seconds', 'event_duration_seconds')
        cell_col = _first(cols, 'searched_cell_id', 'first_cell_id', 'cgi')
        spot_col = _first(cols, 'spot_name')
        duration = _safe_num(dur_col)
        time_expr = _expr(time_col)
        spots = _str_agg(spot_col)
        cells = _str_agg(cell_col)
        observed_imei = _str_agg(imei)
        observed_imsi = _str_agg(imsi)
        rows = []
        counterparties = []
        counterparty_truncated = False
        cp_query = (
            "SELECT CASE WHEN _ea_sub = ? THEN _ea_other ELSE _ea_sub END AS counterparty, "
            "CASE WHEN _ea_sub = ? THEN 'Suspect at Tower <-> B-Party' "
            "ELSE 'Tower Subscriber <-> Suspect (as B-Party)' END AS relation, "
            "COUNT(*) AS n, "
            f"SUM({duration}) AS dur, {_str_agg(spot_col)} AS spots, {_str_agg(cell_col)} AS cells, "
            f"MIN({time_expr}) AS first_seen, MAX({time_expr}) AS last_seen, "
            + ("SUM(CASE WHEN regexp_matches(lower(CAST(call_type AS VARCHAR)), 'in|mtc') THEN 1 ELSE 0 END)" if 'call_type' in cols else '0') + ' AS incoming, '
            + ("SUM(CASE WHEN regexp_matches(lower(CAST(call_type AS VARCHAR)), 'out|moc') THEN 1 ELSE 0 END)" if 'call_type' in cols else '0') + ' AS outgoing '
            "FROM ea_hits WHERE _ea_sub = ? OR _ea_other = ? "
            "GROUP BY 1,2 HAVING counterparty IS NOT NULL AND counterparty != '' AND counterparty != ? "
            "ORDER BY n DESC, dur DESC LIMIT ?"
        )
        for t in targets:
            is_device = len(t) >= 14
            clause = ('(_ea_imei = ? OR _ea_imsi = ?)' if is_device else
                      '(_ea_sub = ? OR _ea_other = ?)')
            row = con.execute(
                'SELECT COUNT(*), '
                'COALESCE(SUM(CASE WHEN _ea_sub = ? THEN 1 ELSE 0 END),0), '
                'COALESCE(SUM(CASE WHEN _ea_other = ? THEN 1 ELSE 0 END),0), '
                f'COALESCE(SUM({duration}),0), {spots}, {cells}, '
                f'{observed_imei}, {observed_imsi}, MIN({time_expr}), MAX({time_expr}) '
                f'FROM ea_hits WHERE {clause}', [t,t,t,t],
            ).fetchone()
            hits, sub_hits, b_hits, dur, spot_val, cell_val, imei_val, imsi_val, first_seen, last_seen = row
            role = ('IMEI/IMSI DEVICE MATCH' if is_device else
                    'BOTH (Tower Subscriber + B-Party)' if sub_hits and b_hits else
                    'TOWER_SUBSCRIBER (Present at Tower)' if sub_hits else
                    'B_PARTY_ONLY (Remote Counterparty)' if b_hits else 'NOT_FOUND')
            target_cps = []
            actual_counterparty_count = 0
            if not is_device and hits:
                actual_counterparty_count = int(con.execute(
                    "SELECT COUNT(DISTINCT NULLIF(NULLIF("
                    "CASE WHEN _ea_sub = ? THEN _ea_other ELSE _ea_sub END, ''), ?)) "
                    "FROM ea_hits WHERE (_ea_sub = ? OR _ea_other = ?)",
                    [t, t, t, t],
                ).fetchone()[0])
                remaining = max(0, counterparty_limit - len(counterparties))
                target_cps = con.execute(cp_query, [t,t,t,t,t,remaining+1]).fetchall()
                counterparty_truncated = counterparty_truncated or len(target_cps) > remaining
                for cp, relation, count, cp_dur, sp, ce, fs, ls, inc, out in target_cps[:remaining]:
                    counterparties.append({
                        'Suspected Number': t, 'Counterparty / B-Party': cp,
                        'Interaction Role': relation, 'Total Events': count,
                        'Incoming': inc, 'Outgoing': out,
                        'Total Duration (Sec)': int(cp_dur or 0),
                        'Spots': sp or '', 'Cells / CGI': ce or '',
                        'First Seen': fs or '', 'Last Seen': ls or '',
                    })
            rows.append({
                'Suspected Number': t, 'Role in Tower Dump': role,
                'Total Hits': hits, 'As Tower Subscriber (A-Party)': sub_hits,
                'As Remote B-Party': b_hits,
                'Unique B-Party Contacts': actual_counterparty_count,
                'Total Duration (Sec)': int(dur or 0),
                'Spots Detected': spot_val or '', 'Cells / CGI': cell_val or '',
                'Observed IMEI (at Tower)': imei_val or '',
                'Observed IMSI (at Tower)': imsi_val or '',
                'First Seen': first_seen or '', 'Last Seen': last_seen or '',
            })
        # Order is applied in SQL; no whole-dump pandas copy is constructed.
        keep_cols = ', '.join(_id(c) for c in column_order if not c.startswith('_ea_'))
        if not keep_cols:
            keep_cols = '*'
        order = f' ORDER BY {_id(time_col)}' if time_col else ''
        preview = con.execute(f'SELECT {keep_cols} FROM ea_hits{order} LIMIT ?', [preview_limit]).df()

    suspect = pd.DataFrame(rows)
    cp_df = pd.DataFrame(counterparties)
    # SDR enrichment is intentionally not performed on all possible counterparties.
    # It can be invoked separately on investigator-selected leads.
    return {
        'targets': targets, 'total_dump_records': total,
        'matched_count': matched, 'suspect_summary': suspect,
        'counterparty_summary': cp_df, 'matched_records': preview,
        'matched_preview_limited': matched > len(preview),
        'counterparty_preview_limited': counterparty_truncated,
        'source': 'Verified Parquet / DuckDB SQL (read-only)',
    }
