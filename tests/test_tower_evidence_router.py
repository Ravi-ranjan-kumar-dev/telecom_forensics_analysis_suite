"""Run: pytest -q tests/test_tower_evidence_router.py"""
from pathlib import Path
import gzip
import zipfile

from modules.loader.tower_evidence_router import classify_tower_evidence, load_tower_evidence_file


def test_unknown_is_not_guessed(tmp_path):
    p = tmp_path / 'unknown.csv'
    p.write_text('a,b\n1,2\n')
    assert classify_tower_evidence(p)[0] == 'UNRECOGNIZED'
    result = load_tower_evidence_file(p)
    assert not result['ok']


def test_gzip_tower_cdr(tmp_path):
    payload = ('Search Criteria : FIRST_CELL_ID\nSearch Value : 40475829A5AEC802\n\n'
               'Target/A-Party Number,Call Type,First Cell Global ID,Call Date\n'
               '9876543210,OUT,40475829A5AEC802,15/10/2026\n')
    path = tmp_path / 'sample.csv.gz'
    with gzip.open(path, 'wb') as stream:
        stream.write(payload.encode())
    result = load_tower_evidence_file(path)
    assert result['file_results'][0]['evidence_category'] == 'TOWER_CDR'
    assert result['source_sha256']


def test_zip_path_traversal_blocked(tmp_path):
    path = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('../outside.csv', 'anything')
    result = load_tower_evidence_file(path)
    assert not result['ok']
    assert 'Unsafe archive' in str(result['errors'])
    assert not (tmp_path / 'outside.csv').exists()


def test_zip_unknown_rejected(tmp_path):
    path = tmp_path / 'unknown.zip'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('unknown.csv', 'a,b\n1,2\n')
    assert not load_tower_evidence_file(path)['ok']
