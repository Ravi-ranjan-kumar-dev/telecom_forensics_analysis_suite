# Changelog

## 0.9.0-rc2 — 2026-07-12

- Starts in direct analysis mode by default while the product is under development.
- Bypasses the case creation/opening menu and silently reuses `DEV-WORKSPACE`.
- Retains the full case-management menu behind `TELECOM_FORENSICS_CASE_MANAGEMENT=1`.
- Fixed Single CDR FCLC report generation when `DataFrame.attrs` contains the rejected-row ledger.
- Added regression tests for direct startup and the pandas concat/attrs failure.

## 0.9.0-rc1 — 2026-07-12

- Added append-only evidence version history and SHA-256 provenance.
- Added hash-chained case audit logs with tamper verification.
- Enforced read-only archived cases and controlled reopen reasons.
- Added locked atomic JSON updates and safe case-relative paths.
- Unified GPRS, Tower IPDR, IPDR and partition run persistence.
- Added source/configuration/table/report fingerprints to manifests.
- Added CGI schema versioning, backups and source-record provenance.
- Added conservative target detection and strict single-file/header behavior.
- Added CGI/location-aware partition filtering and rejected-row ledgers.
- Retained potential duplicates rather than deleting evidence records.
- Added Excel/CSV formula-injection protection and neutral report language.
- Added collision-resistant UTC run and report names.
- Added identifier/IP canonicalization while preserving raw values.
- Reduced dependencies to direct runtime requirements.
- Expanded automated tests and release tooling.
