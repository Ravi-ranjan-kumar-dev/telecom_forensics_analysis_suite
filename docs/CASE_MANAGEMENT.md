# Common Case Management

All Single CDR, Multiple CDR, Tower Dump and future IPDR analyses must run
inside one selected investigation case.

## Canonical modules

- `modules/cases/models.py`: case metadata model
- `modules/cases/repository.py`: atomic JSON storage and folder operations
- `modules/cases/service.py`: public case API
- `modules/cases/audit.py`: append-only JSONL audit trail
- `modules/controllers/case_controller.py`: interactive case menus
- `modules/controllers/app_controller.py`: application and analysis workflow
- `main.py`: lightweight entry point only

## Case output ownership

Generated reports are written under:

```text
cases/active/<CASE_ID>/reports/
```

The legacy `output/reports/` folders remain available for earlier reports but
new case-based runs use the selected case directory.

## Evidence handling

Phase 4B registers case metadata, targets, reports, runs and audit events.
Existing shared staging folders continue to work.

Tower Dump checks the case evidence folder first:

```text
cases/active/<CASE_ID>/evidence/tower_dump/normal/
```

If it is empty, it falls back to:

```text
data/tower_dump/input/
```

A later evidence-import phase will add controlled copy/link operations and
automatic source-file registration for all analysis types.

## Phase-1 integrity rules

- Archived cases are read-only through the public case-management API.
- Evidence registration is append-only and preserves every historical hash.
- New run/report manifests store portable case-relative paths.
- Case-local path construction must use the canonical safe-path helpers.
- JSON metadata writes must use `modules.cases.repository.write_json()`.

Implementation details and validation commands are documented in
`docs/PHASE1_FORENSIC_INTEGRITY_FIXES.md`.
