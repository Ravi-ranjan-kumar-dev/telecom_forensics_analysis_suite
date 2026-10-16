# Telecom Forensics Analysis Suite - Production Runbook

## Project Start

    cd ~/Desktop/telecom_forensics_analysis_suite
    source .venv/bin/activate
    python3 -u main.py

## Backend and GUI Login

The GUI requires the PostgreSQL-backed API. Database credentials are not
application login credentials, and there is no default application password.

First deployment:

    cd ~/Desktop/telecom_forensics_analysis_suite/backend
    cp -n .env.example .env
    python3 -c "import secrets; print(secrets.token_urlsafe(48))"
    chmod 600 .env

Paste the generated value after `SECRET_KEY=` in `.env`, then start the API:

    docker compose up -d --build
    docker compose ps

Open the GUI and select **First-time Setup** to create the first administrator.
If the password is forgotten, issue a 15-minute reset token on the backend host:

    docker compose exec api python -m app.cli reset-token USERNAME

Paste the complete private token into **Forgot Password?**. Never place the
token or `.env` contents in source archives, logs, reports or case material.

## Health Check

    python3 tools/health_check.py

Expected:

    [OK] All checks passed.

## Dependency Setup

    source .venv/bin/activate
    pip install -r requirements.txt

Important packages:
- pandas
- openpyxl
- duckdb
- pyarrow

If 'No module named duckdb' appears, first confirm .venv is active.

## Git Safety

    git status --short
    git log --oneline -10

Commit completed work:

    git add <file_name>
    git commit -m "clear commit message"

## Stable Rollback Point

Stable tag:

    tower-ipdr-partwise-v1

View tag:

    git show tower-ipdr-partwise-v1 --stat

Emergency rollback only:

    git checkout tower-ipdr-partwise-v1

## Tower IPDR Workflow

Menu path:

    Main Menu
    2. Tower Dump Analysis
    3. Tower IPDR Dump Analysis

Workflow:

    1. Load Dump Data
    2. Create Date-Time Parts
    3. Run Part-wise Analysis
    4. View / Export Report

Date-Time Parts rule:

    Part 1 Start to Part 1 End = Part 1
    Part 2 Start to Part 2 End = Part 2

Internal range rule:

    start_time <= event_time < end_time

## Investigation Output

Important sections:
- Common Numbers
- Uncommon / New Visitor Numbers
- Multi-Cell Presence
- Repeat Presence
- IMEI / IMSI Consistency
- Suspicious Timing / High Activity
- Priority Leads
- Data Scope Warning
- Date-Time Part Overlap Warning

Rule:

    Tower/IPDR presence is a lead, not final proof.
    Always verify with CDR, SDR/CAF, IMEI/IMSI, operator records and field/local input.

## Report Location

Latest Tower IPDR part-wise report:

    Main Menu
    5. View Case Reports

Generated files:

    cases/active/<CASE_ID>/reports/tower_dump/ipdr/partwise_range/

Expected files:
- investigation_summary_all_parts.txt
- all_parts_summary.csv
- tower_ipdr_partwise_investigation_report.xlsx
- manifest.json

## Runtime Files

Runtime files are ignored by Git:
- cases/active/*/
- output/logs/
- output/reports/
- *.duckdb
- *.parquet

## Final Check Before New Development

    python3 tools/health_check.py
    git status --short

Expected:
- Health check: [OK] All checks passed.
- git status should show no output.
