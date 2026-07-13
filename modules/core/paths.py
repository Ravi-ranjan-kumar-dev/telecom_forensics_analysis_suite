"""Central project paths for the Telecom Forensics Analysis Suite."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CASES_DIR = PROJECT_ROOT / "cases"
ACTIVE_CASES_DIR = CASES_DIR / "active"
ARCHIVED_CASES_DIR = CASES_DIR / "archived"

DATA_DIR = PROJECT_ROOT / "data"
CDR_DATA_DIR = DATA_DIR / "cdr"
CGI_DATA_DIR = DATA_DIR / "cgi"
IPDR_DATA_DIR = DATA_DIR / "ipdr"
TOWER_DUMP_DATA_DIR = DATA_DIR / "tower_dump"
TOWER_CDR_DUMP_DATA_DIR = TOWER_DUMP_DATA_DIR / "cdr"
TOWER_GPRS_DUMP_DATA_DIR = TOWER_DUMP_DATA_DIR / "gprs"
TOWER_IPDR_DUMP_DATA_DIR = TOWER_DUMP_DATA_DIR / "ipdr"

# Backward-compatible alias. New code should use TOWER_GPRS_DUMP_DATA_DIR.
GPRS_DUMP_DATA_DIR = TOWER_GPRS_DUMP_DATA_DIR

DATABASE_DIR = PROJECT_ROOT / "database"
DATABASE_FILE = DATABASE_DIR / "telecom_forensics.db"
DATABASE_BACKUP_DIR = DATABASE_DIR / "backups"
DATABASE_IMPORT_LOG_DIR = DATABASE_DIR / "import_logs"

OUTPUT_DIR = PROJECT_ROOT / "output"
LOG_DIR = OUTPUT_DIR / "logs"
REPORT_DIR = OUTPUT_DIR / "reports"

CDR_SINGLE_REPORT_DIR = REPORT_DIR / "single"
CDR_MULTIPLE_REPORT_DIR = REPORT_DIR / "multiple"
TOWER_DUMP_REPORT_DIR = REPORT_DIR / "tower_dump"
TOWER_CDR_DUMP_REPORT_DIR = TOWER_DUMP_REPORT_DIR / "cdr"
TOWER_GPRS_DUMP_REPORT_DIR = TOWER_DUMP_REPORT_DIR / "gprs"
TOWER_IPDR_DUMP_REPORT_DIR = TOWER_DUMP_REPORT_DIR / "ipdr"
IPDR_REPORT_DIR = REPORT_DIR / "ipdr"

# Backward-compatible alias.
GPRS_DUMP_REPORT_DIR = TOWER_GPRS_DUMP_REPORT_DIR


def ensure_runtime_directories() -> None:
    """Create only canonical runtime directories."""

    directories = (
        CASES_DIR,
        ACTIVE_CASES_DIR,
        ARCHIVED_CASES_DIR,
        DATABASE_DIR,
        DATABASE_BACKUP_DIR,
        DATABASE_IMPORT_LOG_DIR,
        OUTPUT_DIR,
        LOG_DIR,
        REPORT_DIR,
        CDR_SINGLE_REPORT_DIR,
        CDR_MULTIPLE_REPORT_DIR,
        TOWER_DUMP_REPORT_DIR,
        TOWER_CDR_DUMP_REPORT_DIR,
        TOWER_GPRS_DUMP_REPORT_DIR,
        TOWER_IPDR_DUMP_REPORT_DIR,
        IPDR_REPORT_DIR,
        IPDR_DATA_DIR / "single",
        IPDR_DATA_DIR / "multiple",
        IPDR_DATA_DIR / "rejected",
        IPDR_REPORT_DIR / "single",
        IPDR_REPORT_DIR / "multiple",
        TOWER_CDR_DUMP_DATA_DIR / "input",
        TOWER_CDR_DUMP_DATA_DIR / "processed",
        TOWER_CDR_DUMP_DATA_DIR / "rejected",
        TOWER_GPRS_DUMP_DATA_DIR / "input",
        TOWER_GPRS_DUMP_DATA_DIR / "processed",
        TOWER_GPRS_DUMP_DATA_DIR / "rejected",
        TOWER_IPDR_DUMP_DATA_DIR / "input",
        TOWER_IPDR_DUMP_DATA_DIR / "processed",
        TOWER_IPDR_DUMP_DATA_DIR / "rejected",
    )

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
