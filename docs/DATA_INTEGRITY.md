# Data and Evidence Integrity Model

## Original evidence

Loaders read source files and create normalized in-memory/derived records. They do not rewrite the source. Store original operator responses in the case evidence workspace and register each file before analysis.

## Evidence ledger

Every registration creates a new immutable ledger entry containing an evidence ID, source identity, size, SHA-256 and link to the previous version of the same source path. Re-registering an unchanged file creates an `UNCHANGED` event; changed bytes create a `MODIFIED` event without replacing history.

## Analysis provenance

Each run manifest includes source references, current SHA-256 values, matching evidence IDs, provenance status, source timezone, configuration snapshot hash, table hashes and report hash. A changed source after registration is marked `CHANGED_SINCE_REGISTRATION`.

## Audit trail

Audit events are JSONL records with sequence, UTC timestamp, previous hash and current record hash. Existing legacy records are preserved and anchored by a hash of their byte prefix. `python manage.py case-audit-verify CASE_ID` detects editing, deletion, insertion or reordering after the chain starts.

## Case lifecycle

Archived cases are read-only. Reopening requires a non-empty reason and creates audit events before and after the controlled move. Case/report/evidence paths are validated inside the case workspace.

## Derived files

CSV and Excel text is escaped against spreadsheet formulas. Derived tables and reports receive SHA-256 fingerprints. Derived outputs remain analytical artifacts and must not replace original operator evidence.
