# Final Hardening Summary — 0.9.0-rc1

This release consolidates the earlier staged fixes into one installable source package.

## Case and chain of custody

- Append-only evidence versions with SHA-256 and previous-evidence links
- Hash-chained, locked and fsynced audit JSONL
- Archived-case read-only enforcement and reasoned reopen workflow
- Safe case-relative paths, atomic JSON and concurrent update locks
- Case health and audit verification from CLI and `manage.py`

## Analysis and loader correctness

- Conservative target detection; ambiguous contacts are not selected as targets
- Strict recognized CDR headers and strict one-file Single CDR mode
- Explicit day-first parsing for verified Jio formats
- CGI/location-aware Tower CDR, GPRS and Tower IPDR partitions
- Rejected-row provenance ledgers and retained potential-duplicate flags
- Year-aware week/month grouping and canonical datetimes
- Raw/canonical telecom identifier fields, IP normalization and coordinate range checks
- Tolerant and disclosed GPRS volume reconciliation

## Persistence and database

- Shared run-store implementation for GPRS, Tower IPDR, IPDR and partitions
- Source/evidence/configuration/table/report hashes in manifests
- Hash-verified `latest.json` pointers and collision-resistant run IDs
- SQLite schema versioning, automatic pre-migration backups and source-row provenance
- Strict read-only SQLite opening without creating missing databases

## Reports

- Shared Excel and CSV formula-injection protection
- Timezone-aware timestamps represented safely
- Neutral investigative wording and methodology/limitations sheets
- Versioned, disclosed heuristic scoring formulas
- Unique report filenames to prevent silent overwrite

## Engineering and release

- Direct dependencies reduced to NumPy, pandas and OpenPyXL
- Self-contained pytest suite with no real evidence dependency
- Safe upgrade tool preserving cases, data, outputs and databases
- Release gate covering compilation, tests and source hygiene
- Empty duplicate placeholder modules removed

## Validation

The final source package must pass:

```bash
python -m compileall -q .
python -m pytest -q
python tools/release_check.py
```

This release remains a release candidate. Representative anonymized operator samples and controlled field acceptance testing are required before organizational production approval.
