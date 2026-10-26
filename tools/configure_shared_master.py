"""Generate a local Linux Docker override for the currently selected master."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def selected_master(project):
    override = os.getenv("ETHICALARMOR_MASTER_DB", "").strip()
    directory = (
        Path(os.getenv("ETHICALARMOR_DATA_DIR", "").strip() or project).expanduser().resolve()
        / "database"
    )
    if override:
        path = Path(override).expanduser().resolve()
    elif (directory / "master_database.json").is_file():
        payload = json.loads((directory / "master_database.json").read_text(encoding="utf-8"))
        if payload.get("format") != "ethicalarmor/master-database-pointer/v1":
            raise ValueError("Unsupported master pointer format")
        path = Path(payload["database_path"]).expanduser()
        path = (path if path.is_absolute() else directory / path).resolve()
    else:
        path = directory / "telecom_forensics.duckdb"
    if not path.is_file():
        raise FileNotFoundError(f"Selected master is missing: {path}")
    return path


def configure(project):
    if sys.platform != "linux":
        raise RuntimeError(
            "This shared Docker setup is for local Linux; other Docker hosts need separate mount/lock validation"
        )
    project = Path(project).expanduser().resolve(strict=True)
    if not (project / "backend/docker-compose.yml").is_file():
        raise FileNotFoundError("Project must contain backend/docker-compose.yml")
    database = selected_master(project)
    if not os.access(database.parent, os.R_OK | os.W_OK | os.X_OK):
        raise PermissionError(
            "Master directory must be readable and writable for its lock/WAL files"
        )
    from modules.database.duckdb_core import duckdb_connection

    with duckdb_connection(database, read_only=True) as con:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
    if not {"sdr_subscribers", "cgi_addresses"} <= tables:
        raise ValueError("Selected master lacks the SDR/CGI lookup tables")
    runtime = project / "database/backend_runtime"
    if runtime.is_symlink():
        raise ValueError("Refusing a symlink as the backend runtime directory")
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    container_master = "/master/" + database.name
    # Compose interpolates dollar signs even in JSON strings.
    escaped = lambda path: str(path).replace("$", "$$")
    result = {
        "x-ethicalarmor-shared-master": {
            "format": "ethicalarmor/shared-master/v1",
            "host_master": escaped(database),
        },
        "services": {
            "api": {
                "user": f"{os.getuid()}:{os.getgid()}",
                "environment": {
                    "ETHICALARMOR_MASTER_DB": container_master,
                    "ETHICALARMOR_MASTER_AUTHORITATIVE": "1",
                    "ETHICALARMOR_DATA_DIR": "/runtime",
                },
                "volumes": [
                    {
                        "type": "bind",
                        "source": escaped(database.parent),
                        "target": "/master",
                        "bind": {"create_host_path": False},
                    },
                    {
                        "type": "bind",
                        "source": escaped(runtime),
                        "target": "/runtime",
                        "bind": {"create_host_path": False},
                    },
                ],
            }
        },
    }
    output = project / "backend/docker-compose.shared-master.json"
    content = json.dumps(result, indent=2) + "\n"
    if output.exists() and output.read_text(encoding="utf-8") != content:
        previous = json.loads(output.read_text(encoding="utf-8"))
        if (
            previous.get("x-ethicalarmor-shared-master", {}).get("format")
            != "ethicalarmor/shared-master/v1"
        ):
            raise ValueError(
                "Existing override was not created by this tool; review it before replacement"
            )
        shutil.copy2(
            output,
            output.with_name(
                output.name + ".previous-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            ),
        )
    temporary = output.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(content)
    os.chmod(temporary, 0o600)
    temporary.replace(output)
    print("Host master:", database)
    print("Container master:", container_master)
    print("Compose override:", output)
    print(
        "No master data was copied, migrated or rebuilt. Existing PostgreSQL volume configuration is retained."
    )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        configure(args.project)
    except Exception as error:
        print(f"STOPPED: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
