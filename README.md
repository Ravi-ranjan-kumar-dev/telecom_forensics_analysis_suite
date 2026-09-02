# Telecom Forensics Analysis Suite

**Release:** 1.0.0
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

The desktop login uses application accounts stored by the backend. PostgreSQL
credentials are not application login credentials, and no default application
username or password is provided.

Start the local backend first:

```bash
cd backend
cp -n .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
chmod 600 .env
```

Paste the generated value after `SECRET_KEY=` in `backend/.env`, then run:

```bash
docker compose up -d --build
docker compose ps
cd ..
```

The first time the GUI opens, select **First-time Setup** and create the first
application administrator. This action is accepted only while the backend has
zero users; later attempts are rejected.

```bash
python main.py
```

Desktop GUI:

```bash
python3 -u run_gui.py
```

If an application password is forgotten, issue a private 15-minute reset token
on the backend host:

```bash
docker compose -f backend/docker-compose.yml exec api \
  python -m app.cli reset-token USERNAME
```

Open **Forgot Password?** in the login window and paste the complete token.
The token is tied to the current password hash, so it becomes unusable after a
successful password change. The backend never returns reset tokens from the
public forgot-password endpoint.

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

In **IPDR Analysis**, select Single or Multiple Subscriber IPDR Analysis and
choose the folder containing the related CSV, TXT, XLSX or XLS evidence. The
workflow runs in the background and returns the generated Excel report to the
GUI. CELL ID_IPDRNAT tower evidence remains under **Tower Dump Analysis**.

In **IMEI / Device Analysis**, select dedicated CDR, IPDR, GPRS or unified
IMEI evidence. The GUI reads report-query IMEI/IMEISV values from the evidence
headers, runs one analysis per detected identifier, and creates a common
cross-device report where the backend supports it. No manual identifier entry
is required when the evidence contains a valid query identifier.

In **Lookup Services**, use the SDR and CGI tabs for exact master-data lookups.
The Master Data Import tab accepts one SDR or CGI file and uses the existing
validated backup, type detection, duplicate handling and import-log workflow.

**Case Details** is a read-only view of the active case metadata, audit status,
registered targets, current evidence files and recent analysis runs.

### CDR report outputs

- Single CDR reports use separate sheets for incoming/outgoing voice, incoming/
  outgoing SMS, tower intelligence, probable home/work towers, each movement
  function and each activity-period function. The Executive Summary contains
  roaming plus normalized Top 10 and Bottom 10 Indian mobile contacts. Bottom
  contacts include batched SDR details, and Bottom 10 CGI/Towers include
  batched CGI site and address details. The Device & SIM sheet separates
  device groups, SIM identities and unconfirmed change indicators.
- Multiple CDR reports contain the 12 investigator sheets from Cross Summary
  through Source Files. Common Numbers, Direct Links and Contact Matrix include
  SDR profiles; Common Towers includes CGI details; Tower Matrix includes CGI
  details plus the linked targets' SDR profiles.
- Multiple CDR uses a common-report fast mode by default. The GUI can optionally
  generate the full 23-sheet individual report for every target when required.
  Stage timings are printed in Live Progress for large-case diagnosis.
- Single and Multiple CDR runs create deterministic `_contact_map.html` and
  `_movement_route.html` sidecars when the required CGI coordinates are
  available. The GUI discovers these beside the generated Excel workbook.

### Tower CDR Dump report outputs

- Tower CDR Dump reports contain 15 investigator sheets. Rare/Uncommon,
  Repeat Visitors, every Multi-Spot function, Device Consistency, Shared IMEI
  and Shared IMSI are separate sheets.
- Priority, Rare/Uncommon, Repeat Visitor and Device/SIM mobile numbers include
  bounded batch SDR details. Multi-Spot sheets also show the highest-event
  searched CGI for each row with its batch CGI address details.
- The Normalized Sample excludes source-row and potential-duplicate technical
  columns and includes subscriber SDR plus searched-CGI address details.
- Data Quality, Backend Data Guide, Analysis Status and Methodology sheets are
  excluded from the investigator workbook. Technical diagnostics remain in
  logs and the indexed backend.

## Safe upgrade from an older project

Extract this release to a separate directory, then run:

```bash
python tools/install_or_upgrade.py \
  --destination ~/Desktop/telecom_forensics_analysis_suite
```

The tool creates a dated full backup beside the destination and preserves runtime evidence, cases, reports and database data. Read `docs/INSTALL_UPGRADE_HINDI.md` before upgrading.

The full installer needs enough free space for backup and staging copies. For a
verified source-only release and a project with a very large local database,
use the documented source-overlay procedure instead.

## Management commands

```bash
python manage.py cgi-import data/cgi/raw
python manage.py cgi-status
python manage.py cgi-verify <CGI>
python manage.py case-audit-verify [CASE_ID]
python manage.py release-check
python manage.py release-check --with-db
python manage.py auth-create-admin <USERNAME>
python manage.py auth-reset-token <USERNAME>
python manage.py auth-reset-password <USERNAME>
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
