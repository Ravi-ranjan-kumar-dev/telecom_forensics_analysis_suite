from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_DIR = PROJECT_ROOT / "database"
MASTER_DUCKDB_PATH = DATABASE_DIR / "telecom_forensics.duckdb"


def ensure_database_dir() -> Path:
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    return DATABASE_DIR


def master_duckdb_path() -> Path:
    ensure_database_dir()
    return MASTER_DUCKDB_PATH
