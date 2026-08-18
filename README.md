# Telecom Forensics Analysis Suite

**Release:** 0.9.0-rc1
**Python:** 3.11 or newer
**Primary platform:** Kali Linux / Linux

A case-oriented analysis suite for CDR, Tower CDR Dump, Airtel GPRS Dump, Jio Tower IPDR/NAT and subscriber IPDR records. The software creates investigative leads and derived reports; it does **not** establish identity, intent, guilt, exact device location or legal conclusions without independent corroboration.

## Main workflows

- Single and Multiple CDR analysis
- Tower CDR, GPRS and IPDR Dump analysis with exact Date-Time Partitioning
- Airtel GPRS session-dump analysis
- Jio Tower IPDR/NAT multi-cell analysis
- Target/subscriber IPDR analysis
- Common case management, evidence ledger, report ledger and audit trail
- CGI database import, lookup and integrity verification

## Integrity controls in this release

- Original source files are not modified by loaders.
- Evidence registration is append-only and records SHA-256 hashes.
- Analysis manifests link source hashes, evidence IDs, configuration snapshots and derived-file hashes.
- Case audit logs use a verified SHA-256 hash chain.
- Archived cases are read-only and require a reasoned reopen workflow.
- Case JSON and manifests use atomic, locked writes.
- Backend CSV and Excel reports neutralize formula-like text.
- Rejected or malformed input rows are retained in a provenance ledger.
- Target detection is conservative and refuses ambiguous frequency fallbacks.
- Run/report identifiers are UTC-based and collision resistant.
- SQLite uses versioned migrations, pre-migration backups and CGI source-record provenance.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For development and tests:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Start the application

```bash
python main.py
```

Desktop GUI:

```bash
python3 -u run_gui.py
```

In **Tower Dump Analysis**, select the source type, parent evidence folder
and required Spot folders. Use **Create / Manage Date-Time Parts** to save
one Spot-aware Start/End pair per Part, then use **Run Part-wise Analysis**.
The range rule is `start_time <= event_time < end_time`.

The first Tower CDR or GPRS run parses and indexes the selected evidence.
Later Complete or Part-wise runs reuse the verified normalized Parquet and
DuckDB stage when the input files and Spot selection are unchanged. Any file,
size, modification-time or selection change invalidates the cache and safely
refreshes the backend. The GUI log reports whether the index was reused or
refreshed.

## Safe upgrade from an older project

Extract this release to a separate directory, then run:

```bash
python tools/install_or_upgrade.py \
  --destination ~/Desktop/telecom_forensics_analysis_suite
```

The tool creates a dated full backup beside the destination and preserves runtime evidence, cases, reports and database data. Read `docs/INSTALL_UPGRADE_HINDI.md` before upgrading.

## Management commands

```bash
python manage.py cgi-import data/cgi/raw
python manage.py cgi-status
python manage.py cgi-verify <CGI>
python manage.py case-audit-verify [CASE_ID]
python manage.py release-check
python manage.py release-check --with-db
```

## Release gate

```bash
python tools/release_check.py
```

A valid source release must compile, pass all automated tests and contain no operational database or compiled Python artifacts.

## Important limitations

- Tower and CGI records indicate network association, not exact physical location.
- IMEI, IMSI, MSISDN and IP identifiers can be reassigned, shared, translated or incorrectly recorded.
- Operator timestamps and time zones must be verified against the original response.
- Rankings and thresholds are prioritization aids, not probabilities or findings.
- Source acquisition, legal authority, operator certification and external corroboration remain investigator responsibilities.

## Runtime data that must not be shared in source-review ZIP files

- `data/`
- `cases/`
- generated `output/`
- `database/*.db`, `*.db-wal`, `*.db-shm`
- import logs and case reports
- credentials, tokens or personal subscriber information

## Documentation

- `docs/INSTALL_UPGRADE_HINDI.md`
- `docs/DATA_INTEGRITY.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/CASE_MANAGEMENT.md`
- `docs/PROJECT_STRUCTURE.md`
