# Folder Ownership

| Path | Ownership |
|---|---|
| `cases/` | Investigation-specific evidence references, configuration, results, reports and audit logs |
| `data/` | Shared/default input staging and reference datasets |
| `database/` | Runtime SQLite database, database backups and import logs |
| `modules/core/` | Central paths and shared application-level utilities |
| `modules/cases/` | The only case-management implementation |
| `modules/analysis/` | Pure analytical logic; no menu or filesystem ownership |
| `modules/controllers/` | Workflow orchestration between loaders, analysis and reports |
| `modules/loader/` | File parsing and normalization |
| `modules/database/` | Database schema, connection and repositories |
| `modules/reporting/` | Console and Excel rendering |
| `output/` | Non-case legacy/default reports and logs |
| `tools/` | Administrative command-line utilities |
| `tests/` | Automated tests |

## Rules

1. Analysis modules must not create arbitrary folders.
2. All project paths must come from `modules/core/paths.py`.
3. CDR, Tower Dump and IPDR must use the same `modules/cases/` layer.
4. Raw evidence must never be overwritten.
5. Temporary wrappers and duplicate controllers must not be added.
6. One canonical report generator should exist per report type.
7. Old migration backups should be compressed into one archive and removed
   from the project root.
