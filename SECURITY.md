# Security and Privacy

This project processes sensitive telecom and investigative records. Keep the application and runtime data on controlled systems with least-privilege filesystem permissions. Do not commit or upload source evidence, case workspaces, operational SQLite databases, reports, logs, credentials or subscriber information.

Spreadsheet exports treat formula-like text as literal text. This does not make arbitrary third-party files safe; inspect source provenance and open untrusted files in a controlled environment.

Report security defects, evidence-integrity defects and path-handling defects through the organization's authorized internal channel. Do not include real case data in a defect report.

## Application authentication

- The software has no default application username or password.
- PostgreSQL credentials must never be accepted as desktop application login credentials.
- First-time setup can create one administrator only while the user table is empty.
- `SECRET_KEY` must be a private random value containing at least 32 characters.
- Password-reset tokens are issued only from the backend host, expire after 15 minutes by default and become invalid after the password changes.
- Public forgot-password responses never reveal whether a username exists and never return a reset token.
- Do not place `.env` files, access tokens or password-reset tokens in source archives, logs, reports or case material.
