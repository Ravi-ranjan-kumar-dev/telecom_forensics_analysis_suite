# Phase 3 — Report Security and Interpretation Controls

## Implemented controls

1. One shared Excel security boundary now sanitizes values written by Single CDR, Multiple CDR, Tower CDR Dump, Tower GPRS, Tower IPDR/NAT, target/reverse IPDR and CCTV partition reports.
2. Values beginning with `=`, `+`, `-` or `@` (including after leading whitespace/control characters) are preserved as literal text instead of executable spreadsheet formulas.
3. Report guidance is retained where it is operationally useful. The compact
   Single CDR and Multiple CDR investigator workbooks intentionally omit
   developer-oriented methodology/data-quality sheets; their generated tables,
   maps and source controls still use neutral cautions and safe values.
4. CDR behavioral output uses neutral descriptive wording and does not infer guilt, criminality, relationship type, intent, exact location, evasion or organized activity from frequency data alone.
5. Previously assertive report labels were renamed to **Behavioral Observations** and **Review Indicators**.
6. Component-level behavioral-analysis failures are now visible as analysis-availability observations instead of being silently discarded.

## Validation

Run from the project root:

```bash
python -m compileall -q .
python -m pytest -q
```

Expected Phase 3 baseline:

```text
29 passed
```

## Interpretation rule

Generated scores and indicators are prioritization aids. They must not be presented as proof of identity, exact location, relationship, intent, participation or guilt without independent corroboration and review of the original operator records.
