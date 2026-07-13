# Canonical Project Structure

The current working modules remain in their existing import locations during
Phase 4A. This prevents CDR and Tower Dump imports from breaking.

```text
telecom_forensics_analysis_suite/
├── cases/
│   ├── active/
│   ├── archived/
│   └── README.md
├── data/
│   ├── cdr/
│   │   ├── single/
│   │   └── multiple/
│   ├── cgi/
│   │   ├── raw/
│   │   ├── processed/
│   │   └── rejected/
│   ├── ipdr/
│   └── tower_dump/
│       ├── input/
│       ├── processed/
│       └── rejected/
├── database/
│   ├── backups/
│   ├── import_logs/
│   └── telecom_forensics.db
├── docs/
│   ├── history/
│   ├── PROJECT_STRUCTURE.md
│   └── FOLDER_OWNERSHIP.md
├── modules/
│   ├── core/
│   │   └── paths.py
│   ├── cases/
│   ├── analysis/
│   │   ├── cdr/
│   │   ├── towerdump/
│   │   └── ipdr/
│   ├── controllers/
│   ├── database/
│   ├── loader/
│   └── reporting/
├── output/
│   ├── logs/
│   └── reports/
├── tests/
├── tools/
├── main.py
├── manage.py
├── README.md
└── requirements.txt
```

## Why `modules/loader` is not renamed now

The existing code imports `modules.loader`. Renaming it to `modules.loaders`
without auditing every Python file would break working CDR and Tower Dump
features. A later controlled refactor may rename it only after all imports and
tests are updated together.

## Items removed by the migration

- Python `__pycache__` directories outside `venv`
- Empty `data/tower_dump/multiple`
- Root-level phase backup after preserving it in one compressed archive

## Items preserved

- Current input data
- CGI database and WAL/SHM files
- Database backups and import logs
- Existing working modules
- Generated reports
- Virtual environment
