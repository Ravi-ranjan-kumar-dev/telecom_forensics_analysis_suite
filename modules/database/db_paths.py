"""Master-store location shared by imports, lookups and desktop diagnostics."""
from pathlib import Path
import os
import json
from modules.core.paths import DATABASE_DIR, PROJECT_ROOT

MASTER_DUCKDB_PATH = DATABASE_DIR / "telecom_forensics.duckdb"


def ensure_database_dir() -> Path:
    path = master_duckdb_path().parent
    path.mkdir(parents=True, exist_ok=True)
    return path


def master_duckdb_path() -> Path:
    configured = os.getenv("ETHICALARMOR_MASTER_DB", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    pointer = DATABASE_DIR / "master_database.json"
    if pointer.exists():
        try:
            data = json.loads(pointer.read_text(encoding="utf-8"))
            if data.get("format") != "ethicalarmor/master-database-pointer/v1":
                raise ValueError("Unsupported master database pointer format")
            path = Path(data["database_path"]).expanduser()
            if not path.is_absolute():
                path = DATABASE_DIR / path
            path = path.resolve()
            if not path.is_file():
                raise FileNotFoundError(f"Selected master database is missing: {path}")
            return path
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError(f"Invalid master database pointer: {pointer}") from error
    return MASTER_DUCKDB_PATH
