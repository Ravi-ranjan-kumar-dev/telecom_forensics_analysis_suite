# Security and Privacy

This project processes sensitive telecom and investigative records. Keep the application and runtime data on controlled systems with least-privilege filesystem permissions. Do not commit or upload source evidence, case workspaces, operational SQLite databases, reports, logs, credentials or subscriber information.

Spreadsheet exports treat formula-like text as literal text. This does not make arbitrary third-party files safe; inspect source provenance and open untrusted files in a controlled environment.

Report security defects, evidence-integrity defects and path-handling defects through the organization's authorized internal channel. Do not include real case data in a defect report.
