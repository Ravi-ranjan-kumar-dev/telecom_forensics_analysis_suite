# Telecom Forensics Analysis Suite - Production Runbook

## 1. Project Start

Always open the project folder first:

    cd ~/Desktop/telecom_forensics_analysis_suite

Activate virtual environment:

    source .venv/bin/activate

Start the software:

    python3 -u main.py

Meaning:
- python3 runs the Python application.
- -u shows terminal output immediately without buffering.
- main.py starts the Telecom Forensics Analysis Suite.

## 2. Health Check

Before and after major changes, run:

    python3 tools/health_check.py

Expected result:

    [OK] All checks passed.

This verifies:
- Required Python packages
- Project imports
- Latest Tower IPDR report files
- TXT / CSV / Excel / Manifest availability
- User-facing wording check
- Git working tree cleanliness

## 3. Dependency Setup

On a new system:

    source .venv/bin/activate
    pip install -r requirements.txt

Important packages:
- pandas
- openpyxl
- duckdb
- pyarrow

If No module named duckdb appears, first confirm .venv is active.

## 4. Git Safety Commands

Check current changes:

    git status --short

View recent commits:

    git log --oneline -10

Commit a completed change:

    git add <file_name>
    git commit -m "clear commit message"

## 5. Stable Rollback Point

Current stable Tower IPDR milestone:

    tower-ipdr-partwise-v1

View tag:

    git show tower-ipdr-partwise-v1 --stat

Emergency rollback only:

    git checkout tower-ipdr-partwise-v1

Do not use rollback during normal development unless needed.

## 6. Tower IPDR Workflow

Menu path:

    Main Menu
    2. Tower Dump Analysis
    3. Tower IPDR Dump Analysis

Recommended workflow:

    1. Load Dump Data
    2. Create Date-Time Parts
    3. Run Part-wise Analysis
    4. View / Export Report

Date-Time Parts rule:

    Part 1 Start to Part 1 End = Part 1
    Part 2 Start to Part 2 End = Part 2

Internal rule:

    start_time <= event_time < end_time

This prevents duplicate boundary records.

## 7. Tower IPDR Investigation Output

Important report sections:
- Common Numbers
- Uncommon / New Visitor Numbers
- Multi-Cell Presence
- Repeat Presence
- IMEI / IMSI Consistency
- Suspicious Timing / High Activity
- Priority Leads
- Data Scope Warning
- Date-Time Part Overlap Warning

Investigation rule:

    Tower/IPDR presence is a lead, not final proof.
    Always verify with CDR, SDR/CAF, IMEI/IMSI, operator records and field/local input.

## 8. Report Locations

Latest Tower IPDR part-wise report is shown in:

    Main Menu
    5. View Case Reports

Generated files are usually stored under:

    cases/active/<CASE_ID>/reports/tower_dump/ipdr/partwise_range/

Expected files:
- investigation_summary_all_parts.txt
- all_parts_summary.csv
- tower_ipdr_partwise_investigation_report.xlsx
- manifest.json

## 9. Runtime Files and Git

Runtime case files are ignored by Git.

Examples:
- cases/active/*/
- output/logs/
- output/reports/
- *.duckdb
- *.parquet

This keeps the code repository clean and prevents generated evidence/report files from being committed accidentally.

## 10. Final Check Before Next Development

Before starting a new module or major change:

    python3 tools/health_check.py
    git status --short

Expected:
- Health check: [OK] All checks passed.
- git status --short should show no output.
