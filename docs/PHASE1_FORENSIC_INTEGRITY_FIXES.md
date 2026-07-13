# Phase 1 — Case and Evidence Integrity Fixes

Implemented on 12 July 2026 against the reviewed V2 source snapshot.

## Completed safeguards

### Archived cases are read-only

All public case mutations now call `ensure_case_writable()` before writing.
This includes evidence/report directories, targets, evidence registration,
analysis runs, sightings, CGI groups, backend result stores and report
attachments. The final `CASE_ARCHIVED` audit event is the only deliberate
post-move write during the archive transaction.

### Evidence registration is append-only

`configuration/evidence.json` now receives a new registration record every
time a source is registered. Earlier SHA-256 values are not overwritten.
Each record contains:

- `evidence_id`
- `previous_evidence_id`
- `change_status`: `NEW`, `UNCHANGED`, `MODIFIED` or `MISSING`
- portable `source_file` reference
- `source_path_id`
- file size and SHA-256
- registration metadata

Legacy evidence entries remain readable and can be linked through a generated
`LEGACY-EVD-*` reference when they do not contain an evidence ID.

### Case-local paths are validated

`safe_descendant()` rejects absolute path components, `..`, embedded path
separators, NUL characters and unsupported names. Case evidence/report paths
and run IDs now use this common validation boundary.

### Manifests are portable

New `manifest.json` and `latest.json` files store case-relative paths instead
of machine-specific absolute paths. Project fallback inputs use
`project://...`; truly external inputs are represented as
`external://<filename>` and should be corroborated through evidence hashes.

`resolve_case_path()` can also remap legacy absolute manifest pointers after a
case moves from `cases/active/` to `cases/archived/`.

### JSON writes are atomic

All case manifests and latest pointers now use the repository's canonical
`write_json()` implementation:

1. write to a temporary file in the destination directory;
2. flush and `fsync()` the file;
3. replace the destination atomically;
4. best-effort `fsync()` the parent directory.

### Run IDs avoid same-second collisions

GPRS, Tower IPDR and Tower partition run IDs now include microseconds.

## Added tests

`tests/test_phase1_case_integrity.py` verifies:

- path traversal rejection;
- append-only evidence history;
- archived-case write blocking;
- relative manifests surviving archival;
- atomic JSON cleanup;
- portability across all case run stores;
- run-ID traversal rejection.

Run the focused gate:

```bash
python -m pytest -q tests/test_phase1_case_integrity.py
```

Expected result:

```text
7 passed
```

## Known test-suite blockers not changed in Phase 1

The full test collection still stops because `tests/test_basic.py` opens
`data/cdr1.csv` at import time. `tests/test_gprs_loader.py` also expects an
undefined `sample_path` fixture. These belong to the planned test-suite cleanup
phase and are not regressions introduced by this patch.
