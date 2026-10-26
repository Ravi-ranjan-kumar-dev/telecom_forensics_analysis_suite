# SQL Identifier & Table Name Validation Guard for DuckDB / SQLite queries
from __future__ import annotations

import re

_VALID_IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')

ALLOWED_FORENSIC_TABLES: set[str] = {
    'cdr_records', 'cdr_events', 'ipdr_records', 'ipdr_events',
    'tower_dump', 'tower_records', 'tower_events', 'sdr_records',
    'cgi_master', 'imei_evidence', 'audit_logs', 'case_runs',
    'staging_records', 'subscriber_master', 'cell_towers',
}


def validate_sql_identifier(identifier: str, *, check_allowlist: bool = False) -> str:
    clean = str(identifier).strip()
    if not _VALID_IDENTIFIER_RE.match(clean):
        raise ValueError(f'Unsafe SQL identifier rejected: {identifier!r}')
    if check_allowlist and clean not in ALLOWED_FORENSIC_TABLES:
        raise ValueError(f'Table name not in ALLOWED_FORENSIC_TABLES: {clean!r}')
    return clean
