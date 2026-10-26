"""Format-aware Tower evidence importer. Keeps CDR, GPRS and IPDR separate.

No data is uploaded; compressed evidence is expanded only in a temporary directory.
Source provenance and SHA-256 are retained in the returned metadata.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 200
ALLOWED = {'.csv', '.txt', '.tsv'}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _preview(path: Path) -> str:
    with path.open('rb') as stream:
        data = stream.read(32768)
    return data.decode('utf-8-sig', errors='replace').lower()



def is_jio_cell_target_report(path: str | Path, preview: str | None = None) -> bool:
    """Require record-level evidence that a Jio VVM is *cell-targeted*.

    Both subscriber CDRs and cell dump reports can contain Ticket Number,
    Calling Party Telephone Number and First Cell ID. Those headers alone do
    not identify a tower dump. Verify that the queried identifier from report
    metadata actually occurs in the *cell* columns of sampled records.

    If the evidence is insufficient, return False (fail closed).  This never
    derives a tower report from the filename or the MCC/MNC prefix alone.
    """
    content = preview if preview is not None else _preview(Path(path))
    if 'ticket number' not in content or 'calling party telephone number' not in content:
        return False
    lines = content.splitlines()
    target = None
    header_idx = None
    cell_positions: list[int] = []

    def clean(value: str) -> str:
        return re.sub(r'[^a-z0-9]', '', str(value).lower())

    for index, line in enumerate(lines[:100]):
        try:
            cells = next(csv.reader([line]))
        except (csv.Error, StopIteration):
            continue
        if cells and cells[0].strip().lower().startswith('input value') and len(cells) > 1:
            target = clean(cells[1])
        if header_idx is None and len(cells) >= 3:
            normalized = [re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', c.lower())).strip() for c in cells]
            if 'calling party telephone number' in normalized:
                cell_positions = [i for i, name in enumerate(normalized)
                                  if name in {'first cell id','last cell id','first cell global id',
                                              'last cell global id', 'first cell global identity',
                                              'last cell global identity'}]
                if cell_positions:
                    header_idx = index
    if not target or len(target) < 6 or header_idx is None:
        return False
    for line in lines[header_idx + 1:header_idx + 151]:
        try:
            values = next(csv.reader([line]))
        except (csv.Error, StopIteration):
            continue
        if any(pos < len(values) and clean(values[pos]) == target for pos in cell_positions):
            return True
    return False


def classify_tower_evidence(path: str | Path) -> tuple[str, str]:
    """Return (category, operator) from report signatures, not just filename."""
    content = _preview(Path(path))
    if 'bharti airtel' in content and 'ipdr of cell id' in content and 'session_start_time' in content:
        return 'TOWER_IPDR', 'Airtel'
    if 'landline/msisdn/mdn/leased circuit id for internet access' in content and 'translated ip address' in content:
        return 'TOWER_IPDR', 'Jio'
    if 'bharti airtel' in content and 'gprs of cell id' in content:
        return 'TOWER_GPRS', 'Airtel'
    if ('bharti airtel' in content and 'call details of cell id' in content
            and 'first cgi' in content and 'target no' in content):
        return 'TOWER_CDR', 'Airtel'
    if 'vodafone idea call data records' in content and 'report type :- gprs report' in content:
        return 'TOWER_GPRS', 'Vi'
    if ('vodafone idea call data records' in content and 'report type :-' in content
            and re.search(r'(?m)^\s*cellid\s*:\s*-?\s*\S+', content)):
        return 'TOWER_CDR', 'Vi'
    if is_jio_cell_target_report(path, content):
        return 'TOWER_CDR', 'Jio'
    if 'search criteria : first_cell_id' in content and 'first cell global id' in content:
        return 'TOWER_CDR', 'BSNL/MTNL (unverified identity)'
    return 'UNRECOGNIZED', 'Unknown'


def _safe_members(path: Path, folder: Path):
    if path.suffix.lower() == '.gz':
        name = Path(path.stem).name
        if Path(name).suffix.lower() not in ALLOWED:
            raise ValueError('GZIP does not contain a supported text/CSV file')
        output = folder / name
        with gzip.open(path, 'rb') as source, output.open('wb') as target:
            shutil.copyfileobj(io.BufferedReader(_LimitedReader(source, MAX_MEMBER_BYTES)), target)
        yield output, name
        return
    if path.suffix.lower() == '.zip':
        with zipfile.ZipFile(path) as archive:
            members = [x for x in archive.infolist() if not x.is_dir()]
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise ValueError('Archive contains too many members')
            if sum(x.file_size for x in members) > MAX_ARCHIVE_BYTES:
                raise ValueError('Archive exceeds uncompressed size limit')
            for index, member in enumerate(members):
                name = member.filename
                normalized = name.replace('\\', '/')
                if (normalized.startswith('/') or '..' in Path(normalized).parts or
                    re.match(r'^[A-Za-z]:', normalized)):
                    raise ValueError('Unsafe archive member path')
                if Path(normalized).suffix.lower() not in ALLOWED:
                    continue
                if member.file_size > MAX_MEMBER_BYTES:
                    raise ValueError('Archive member exceeds size limit')
                output = folder / f'{index:04d}_{Path(normalized).name}'
                with archive.open(member) as source, output.open('wb') as target:
                    shutil.copyfileobj(io.BufferedReader(_LimitedReader(source, MAX_MEMBER_BYTES)), target)
                yield output, normalized
        return
    if path.suffix.lower() in ALLOWED:
        yield path, path.name
        return
    raise ValueError('Supported evidence: CSV/TXT/TSV/ZIP/CSV.GZ')


class _LimitedReader(io.RawIOBase):
    def __init__(self, source, limit: int):
        self.source, self.remaining = source, limit
    def readable(self):
        return True
    def readinto(self, buffer):
        data = self.source.read(min(len(buffer), self.remaining + 1))
        if len(data) > self.remaining:
            raise ValueError('Decompressed evidence exceeds size limit')
        buffer[:len(data)] = data
        self.remaining -= len(data)
        return len(data)


def load_tower_evidence_file(path: str | Path) -> dict[str, Any]:
    """Import one CSV or archive and return separate per-member results.

    This is a new opt-in entry point; existing loader APIs remain unchanged.
    """
    original = Path(path).expanduser().resolve()
    output: dict[str, Any] = {'ok': False, 'source_file': str(original), 'source_sha256': None,
                              'file_results': [], 'warnings': [], 'errors': []}
    if not original.is_file():
        output['errors'].append('Evidence file not found')
        return output
    output['source_sha256'] = _sha256(original)
    try:
        with tempfile.TemporaryDirectory(prefix='ethicalarmor_tower_') as temp:
            for extracted, member_name in _safe_members(original, Path(temp)):
                category, operator = classify_tower_evidence(extracted)
                if category == 'TOWER_IPDR':
                    from modules.loader.tower_ipdr_loader import load_tower_ipdr_file
                    result = load_tower_ipdr_file(extracted)
                elif category == 'TOWER_GPRS' and operator == 'Airtel':
                    from modules.loader.gprs_dump_loader import load_gprs_dump_file
                    result = load_gprs_dump_file(extracted)
                elif category in {'TOWER_GPRS', 'TOWER_CDR'}:
                    from modules.loader.tower_dump_loader import load_tower_dump
                    result = load_tower_dump(extracted, enrich_cgi=False)
                else:
                    result = {'ok': False, 'errors': ['Unrecognized tower evidence format'], 'warnings': []}
                metadata = dict(result.get('metadata') or {})
                metadata.update({'source_file': str(original) + ('::' + member_name if original != extracted else ''),
                                 'original_source_file': str(original), 'original_source_sha256': output['source_sha256'],
                                 'archive_member': member_name, 'evidence_category': category,
                                 'detected_operator': operator})
                result['metadata'] = metadata
                result['evidence_category'] = category
                result['detected_operator'] = operator
                result['archive_member'] = member_name
                # Never retain a deleted temporary file as a valid source location.
                result['file'] = str(original) + ('::' + member_name if original != extracted else '')
                frame = result.get('df')
                if frame is not None and hasattr(frame, 'columns'):
                    frame['original_source_file'] = str(original)
                    frame['original_source_sha256'] = output['source_sha256']
                    frame['archive_member'] = member_name
                    if 'source_file' in frame.columns:
                        frame['source_file'] = result['file']
                output['file_results'].append(result)
        if not output['file_results']:
            output['errors'].append('No supported evidence members found')
        output['ok'] = bool(output['file_results']) and all(r.get('ok') for r in output['file_results'])
        for result in output['file_results']:
            output['errors'].extend(result.get('errors', []))
            output['warnings'].extend(result.get('warnings', []))
    except Exception as exc:
        output['errors'].append(f'{type(exc).__name__}: {exc}')
    return output
