"""Read-only, bounded, full-record GPRS / IPDR search for EthicalArmor.

Search never loads the whole dataset into pandas. It refuses an unverified, stale,
or incomplete stage; the investigator must rerun Complete Analysis for exactly the
selected evidence files/spots. Query counts reflect the full verified stage, while
rows displayed/exported by the GUI are explicitly limited previews.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


class StageUnavailable(RuntimeError):
    """Search cannot safely claim a complete current source dataset."""


def _ident(s: str) -> str:
    return '"' + str(s).replace('"', '""') + '"'


def _literal(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def _first(cols: set[str], *options: str) -> str | None:
    return next((x for x in options if x in cols), None)


def _digits(col: str | None) -> str:
    if not col:
        return "''"
    raw = f"TRIM(COALESCE(CAST({_ident(col)} AS VARCHAR), ''))"
    num = (f"CASE WHEN regexp_matches({raw}, '^[0-9]+[.]0+$') "
           f"THEN split_part({raw}, '.', 1) ELSE {raw} END")
    return f"regexp_replace(({num}), '[^0-9]', '', 'g')"


def _mobile(col: str | None) -> str:
    d = _digits(col)
    return (f"CASE WHEN length({d})=12 AND starts_with({d}, '91') THEN right({d},10) "
            f"WHEN length({d})=11 AND starts_with({d}, '0') THEN right({d},10) "
            f"ELSE {d} END")


def _varchar(col: str | None) -> str:
    return f"CAST({_ident(col)} AS VARCHAR)" if col else "''"


def _number(col: str | None) -> str:
    return f"GREATEST(COALESCE(TRY_CAST({_ident(col)} AS DOUBLE),0),0)" if col else "0"


def _parse(query: object) -> tuple[list[str], list[str], list[str]]:
    """Exact telecom identifier matching (never substring or fuzzy suffix)."""
    from modules.analysis.towerdump.full_dump_search import parse_target_numbers
    vals = parse_target_numbers(query)
    if not vals or len(vals) > 50:
        raise ValueError('Enter 1 to 50 mobile numbers, IMEIs or IMSIs.')
    invalid = [x for x in vals if not (len(x)==10 or 14 <= len(x) <= 16)]
    if invalid:
        raise ValueError('Use 10-digit mobile numbers or 14–16-digit device/SIM identifiers.')
    mobile = [x for x in vals if len(x)==10]
    devices = [x for x in vals if 14 <= len(x) <= 16]
    return vals, mobile, devices


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(2*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _verified_gprs(case_id: str, folder: Path, selected: Iterable[str] | None, include_root: bool):
    from modules.loader.gprs_dump_loader import SUPPORTED_SUFFIXES
    from modules.pipeline.scalable_analysis_pipeline import (
        build_input_fingerprint, latest_pipeline_state_path,
    )
    from modules.staging.tower_gprs_staging import (
        TOWER_GPRS_WORKFLOW, tower_gprs_parquet_path,
    )
    state_file = latest_pipeline_state_path(case_id, TOWER_GPRS_WORKFLOW)
    if not state_file.is_file():
        raise StageUnavailable('GPRS stage missing. Run Complete Analysis for these files/spots first.')
    state = json.loads(state_file.read_text(encoding='utf-8'))
    if state.get('ok') is not True:
        raise StageUnavailable('GPRS stage is not marked complete.')
    saved = state.get('input_fingerprint')
    if not isinstance(saved, dict) or not saved.get('file_count'):
        raise StageUnavailable('GPRS stage has no complete input fingerprint.')
    # Fail closed if Excel evidence is present: the verified GPRS loader only
    # supports CSV/TXT, so it must not be advertised as a full mixed-file search.
    from modules.loader.tower_spot_layout import select_tower_evidence_files
    all_candidates = [p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in {'.csv','.txt','.xlsx','.xls'}]
    selected_any = select_tower_evidence_files(
        folder, all_candidates, selected_spot_folders=selected,
        include_root_files=include_root,
    )
    if any(p.suffix.lower() not in set(SUPPORTED_SUFFIXES) for p in selected_any):
        raise StageUnavailable('GPRS selection has Excel evidence that the current stage cannot include.')
    # Require hashes, not just names and mtimes, to prevent stale-data reuse.
    if not all(isinstance(f, dict) and f.get('sha256') for f in saved.get('files', [])):
        raise StageUnavailable('GPRS stage has no SHA-256 per-file proof. Rerun Complete Analysis.')
    current = build_input_fingerprint(
        folder, supported_suffixes=set(SUPPORTED_SUFFIXES),
        selected_spot_folders=selected, include_root_files=include_root,
    )
    def canonical(fp: dict) -> dict:
        return {**fp, 'files': sorted(fp.get('files', []), key=lambda x: x['path'])}
    if canonical(current) != canonical(saved) or not current.get('file_count'):
        raise StageUnavailable('GPRS files or Spot selection changed. Rerun Complete Analysis.')
    parquet = tower_gprs_parquet_path(case_id)
    stage = state.get('stage') or {}
    if not parquet.is_file() or Path(str(stage.get('parquet_path') or '')).resolve() != parquet.resolve():
        raise StageUnavailable('GPRS normalized Parquet does not match the verified pipeline stage.')
    expected_rows = int(stage.get('record_count', -1))
    if expected_rows <= 0:
        raise StageUnavailable('GPRS stage record count missing or invalid.')
    return f'read_parquet({_literal(str(parquet.resolve()))})', expected_rows


def _verified_ipdr(case_id: str, folder: Path, selected: Iterable[str] | None, include_root: bool):
    from modules.staging.tower_ipdr_staging import (
        _candidate_files, tower_ipdr_manifest_path, tower_ipdr_database_path,
        TABLE_EVENTS,
    )
    from modules.loader.tower_spot_layout import select_tower_evidence_files
    db = tower_ipdr_database_path(case_id)
    man = tower_ipdr_manifest_path(case_id)
    if not db.is_file() or not man.is_file():
        raise StageUnavailable('IPDR DuckDB/manifest missing. Run Complete Analysis first.')
    # Detect *all* relevant source files; the legacy importer supports CSV/TXT only.
    all_candidates = [p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in {'.csv','.txt','.xlsx','.xls'}]
    all_selected = select_tower_evidence_files(
        folder, all_candidates, selected_spot_folders=selected,
        include_root_files=include_root,
    )
    if not all_selected:
        raise StageUnavailable('No IPDR evidence files selected.')
    if any(p.suffix.lower() not in {'.csv','.txt'} for p in all_selected):
        raise StageUnavailable('IPDR selection includes Excel files not supported by the staging importer.')
    selected_files = _candidate_files(
        folder, recursive=True, selected_spot_folders=selected,
        include_root_files=include_root,
    )
    paths = {str(p.resolve()): p for p in selected_files}
    if set(paths) != {str(p.resolve()) for p in all_selected}:
        raise StageUnavailable('IPDR selected files do not match the loader inventory.')
    manifest = json.loads(man.read_text(encoding='utf-8'))
    records = manifest.get('files')
    if not isinstance(records, list) or not records:
        raise StageUnavailable('IPDR file manifest is incomplete.')
    loaded = {}
    for rec in records:
        if not isinstance(rec, dict) or rec.get('status') != 'LOADED':
            raise StageUnavailable('IPDR staging has missing/failed files; rerun Complete Analysis.')
        source = str(Path(str(rec.get('source_path') or '')).resolve())
        if source in loaded:
            raise StageUnavailable('IPDR staging manifest contains duplicate file paths.')
        loaded[source] = rec
    if set(loaded) != set(paths):
        raise StageUnavailable('IPDR stage contains different/additional/missing evidence files. Rebuild stage for this selection.')
    expected = 0
    for name, path in paths.items():
        before = path.stat()
        checksum = _sha(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise StageUnavailable('IPDR source changed while checking its SHA-256.')
        rec = loaded[name]
        if checksum != rec.get('sha256'):
            raise StageUnavailable('IPDR source differs from staged evidence: ' + path.name)
        loaded_rows = int(rec.get('rows_loaded') or 0)
        if loaded_rows <= 0:
            raise StageUnavailable('IPDR staging file has invalid row count: ' + path.name)
        expected += loaded_rows
    if not expected:
        raise StageUnavailable('IPDR stage has no loaded records.')
    return db, _ident(TABLE_EVENTS), expected


def search_verified_tower_sessions(
    case_id: str, *, source_type: str, input_folder: str | Path,
    selected_spot_folders: Iterable[str] | None = None,
    include_root_files: bool = True, query: object,
    preview_limit: int = 5000, endpoint_limit: int = 2000,
) -> dict[str, Any]:
    """Search all staged GPRS or IPDR events with a fixed-size GUI result preview."""
    mode = str(source_type).lower().strip()
    if mode not in {'gprs','ipdr'}:
        raise ValueError('Expected Tower GPRS or Tower IPDR source type.')
    if not 1 <= preview_limit <= 5000 or not 1 <= endpoint_limit <= 2000:
        raise ValueError('Invalid search result preview size.')
    targets, mobile, devices = _parse(query)
    folder = Path(input_folder).expanduser().resolve()
    if not folder.is_dir():
        raise StageUnavailable('Input evidence folder missing.')
    if mode == 'gprs':
        source, expected = _verified_gprs(str(case_id), folder, selected_spot_folders, include_root_files)
    else:
        db, source, expected = _verified_ipdr(str(case_id), folder, selected_spot_folders, include_root_files)

    import duckdb
    # Keep temporary views in a disposable in-memory connection. For IPDR,
    # attach the case database as READ_ONLY so the stage can never be modified.
    with duckdb.connect(database=':memory:') as con:
        if mode == 'ipdr':
            con.execute('ATTACH '+_literal(str(db.resolve()))+' AS ea_case (READ_ONLY)')
            source = 'ea_case.'+source
        desc = con.execute(f'SELECT * FROM {source} LIMIT 0').description
        original_cols = [x[0] for x in desc]
        cols = set(original_cols)
        sub = _first(cols, 'subscriber_number')
        imei = _first(cols, 'imei')
        imsi = _first(cols, 'imsi')
        if mobile and not sub:
            raise StageUnavailable('This stage has no subscriber/mobile column.')
        if devices and not (imei or imsi):
            raise StageUnavailable('This stage has no IMEI/IMSI columns.')
        count = int(con.execute(f'SELECT COUNT(*) FROM {source}').fetchone()[0])
        if count != expected:
            raise StageUnavailable('Staged row count does not match verified manifest/pipeline. Rebuild Complete Analysis.')
        # Views are lazy: no full pandas frame, no giant materialized hit table.
        con.execute('CREATE TEMP VIEW ea_normalized AS SELECT s.*, '
                    + f'{_mobile(sub)} AS "__ea_num", '
                    + f'{_digits(imei)} AS "__ea_imei", {_digits(imsi)} AS "__ea_imsi" '
                    + f'FROM {source} AS s')
        predicates = []
        if mobile:
            predicates.append('"__ea_num" IN (' + ','.join(_literal(x) for x in mobile) + ')')
        if devices:
            for col in ('__ea_imei','__ea_imsi'):
                predicates.append(_ident(col) + ' IN (' + ','.join(_literal(x) for x in devices) + ')')
        conditions = ' OR '.join(predicates)
        con.execute('CREATE TEMP VIEW ea_hits AS SELECT * FROM ea_normalized WHERE ' + conditions)
        matched = int(con.execute('SELECT COUNT(*) FROM ea_hits').fetchone()[0])
        time_col = _first(cols, 'session_start','event_time','allocation_start')
        dur_col = _first(cols, 'session_duration_seconds','event_duration_seconds','allocation_duration_seconds')
        cell = _first(cols,'searched_cell_id','first_cell_id')
        spot = _first(cols,'spot_name')
        total_volume = _first(cols,'total_volume')
        # GPRS has assigned IP addresses, NOT remote counterparties.
        if mode == 'gprs':
            ip_expr = (f'COALESCE(NULLIF(TRIM({_varchar("ipv4_address" if "ipv4_address" in cols else None)}),\'\'), '
                       f'NULLIF(TRIM({_varchar("ipv6_address" if "ipv6_address" in cols else None)}),\'\'))')
            endpoint_label = 'Assigned IP (not remote B-Party)'
        else:
            dip = _varchar('destination_ip' if 'destination_ip' in cols else None)
            port = _varchar('destination_port' if 'destination_port' in cols else None)
            ip_expr = f'NULLIF(TRIM({dip}),\'\')'
            endpoint_label = 'Destination IP / Port (remote endpoint)'
        if not ('ipv4_address' in cols or 'ipv6_address' in cols) and mode=='gprs':
            raise StageUnavailable('GPRS stage lacks both subscriber IP columns.')
        if mode=='ipdr' and 'destination_ip' not in cols:
            raise StageUnavailable('IPDR stage lacks destination_ip column.')

        def agg_one(target: str) -> dict[str, Any]:
            pred = ('"__ea_num" = ' + _literal(target)) if len(target)==10 else (
                '("__ea_imei" = '+_literal(target)+' OR "__ea_imsi" = '+_literal(target)+')')
            row = con.execute(
                f'SELECT COUNT(*), COALESCE(SUM({_number(dur_col)}),0), '
                f'COALESCE(SUM({_number(total_volume)}),0), '
                f'MIN({_varchar(time_col)}), MAX({_varchar(time_col)}), '
                f'COUNT(DISTINCT NULLIF(TRIM({_varchar(spot)}),\'\')), '
                f'COUNT(DISTINCT NULLIF(TRIM({_varchar(cell)}),\'\')) '
                f'FROM ea_hits WHERE {pred}'
            ).fetchone()
            hits,dur,vol,first,last,spots,cells = row
            return {'Suspected Number':target, 'Role in Tower Dump':
                    'SUBSCRIBER SESSION' if len(target)==10 else 'DEVICE / SIM MATCH',
                    'Total Hits':int(hits or 0), 'Total Duration (Sec)':int(dur or 0),
                    'Total Volume':int(vol or 0), 'Unique Spots':int(spots or 0),
                    'Unique Cells':int(cells or 0),'First Seen':first or '', 'Last Seen':last or ''}

        overview = [agg_one(t) for t in targets]
        endpoint_rows=[]
        endpoint_truncated=False
        for target in targets:
            remain=endpoint_limit-len(endpoint_rows)
            if remain<=0:
                endpoint_truncated=True
                break
            pred = ('"__ea_num" = ' + _literal(target)) if len(target)==10 else (
                '("__ea_imei" = '+_literal(target)+' OR "__ea_imsi" = '+_literal(target)+')')
            if mode == 'ipdr' and 'destination_port' in cols:
                clean_port = f"NULLIF(TRIM({port}), '')"
                ep_col = f"CASE WHEN {clean_port} IS NOT NULL THEN {ip_expr} || ':' || {clean_port} ELSE {ip_expr} END"
            else:
                ep_col = ip_expr
            query_sql = (
                'SELECT endpoint, COUNT(*) AS events, '
                f'SUM({_number(dur_col)}) AS duration, SUM({_number(total_volume)}) AS volume '
                'FROM (SELECT '+ep_col+' AS endpoint, '
                + ','.join(_ident(c) for c in (dur_col,total_volume) if c) + (',' if dur_col or total_volume else '')
                + '1 AS dummy FROM ea_hits WHERE '+pred+') g '
                "WHERE endpoint IS NOT NULL AND endpoint <> '' "
                'GROUP BY endpoint ORDER BY events DESC LIMIT '+str(remain+1)
            )
            ep_rows=con.execute(query_sql).fetchall()
            if len(ep_rows)>remain:
                endpoint_truncated=True
            for endpoint,events,duration,volume in ep_rows[:remain]:
                endpoint_rows.append({'Suspected Number':target,
                                      endpoint_label:str(endpoint),
                                      'Total Events':int(events),
                                      'Total Duration (Sec)':int(duration or 0),
                                      'Total Volume':int(volume or 0)})
        original_select = ', '.join(_ident(c) for c in original_cols)
        order = ' ORDER BY '+_ident(time_col) if time_col else ''
        preview = con.execute(
            'SELECT '+original_select+' FROM ea_hits'+order+' LIMIT ?', [preview_limit]
        ).df()
    return {
        'targets':targets,'total_dump_records':count,'matched_count':matched,
        'suspect_summary':pd.DataFrame(overview),
        'counterparty_summary':pd.DataFrame(endpoint_rows),
        'matched_records':preview,
        'matched_preview_limited':matched>len(preview),
        'counterparty_preview_limited':endpoint_truncated,
        'endpoint_mode':True,
        'endpoint_description':'Assigned subscriber IP addresses' if mode=='gprs' else 'Destination IP endpoints',
        'source':'Verified '+mode.upper()+' staged SQL (read-only)',
    }
