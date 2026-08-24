# Changelog

## Unreleased

- Connected IMEI / Device Analysis to a background automatic-detection GUI.
- Added SDR, CGI and one-click master-data import tabs to Lookup Services.
- Added a read-only Case Details view with targets, evidence, analysis counts
  and audit-chain status.
- Added focused GUI, worker and service regression tests for the new screens.
- Redesigned the Single CDR workbook into independent voice, SMS, tower,
  movement and activity sheets; added Top 10 and Bottom 10 human contacts and
  moved roaming into the Executive Summary.
- Added batched SDR/CGI enrichment to Multiple CDR common-number, direct-link,
  contact-matrix, common-tower and tower-matrix outputs.
- Added Multiple CDR common-contact and per-target movement-route HTML maps.
- Removed investigator-unneeded priority/data-quality sheets from Single CDR
  and alerts, rejected-row and methodology sheets from Multiple CDR reports.
- Corrected Single CDR contact ranking to normalize valid Indian mobile
  numbers, removed Communication Intel and Activity Summary sheets, simplified
  incoming-call and location columns, and rebuilt Device & SIM intelligence
  with exact-text identifiers, a SIM summary and neutral change indicators.
- Added explicit Bottom 10 contact SDR fields and a Bottom 10 CGI/Towers section
  with batched CGI site, address and coordinate enrichment.
- Added a default Multiple CDR common-report fast mode, optional per-target
  workbooks, stage timings, compact cross-target frames and vectorized shared-
  item filtering. Duplicate signatures are now grouped once and cryptographic
  labels are calculated only for actual duplicate groups.
- Rebuilt the Tower CDR Dump workbook into 15 investigator sheets, removed
  Data Quality, backend/status and methodology sheets, separated Rare,
  Repeat Visitor, Multi-Spot and Device/SIM functions, and removed requested
  technical columns.
- Added bounded batch SDR enrichment to Tower Dump priority, rare, repeat,
  Multi-Spot, Device/SIM and normalized-sample mobile numbers. Multi-Spot and
  normalized records now include clean CGI address fields without technical
  match-confidence/source columns.

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
