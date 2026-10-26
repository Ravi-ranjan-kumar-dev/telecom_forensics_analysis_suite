"""Check container catalog, API readiness and shared lock without changing rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modules.database.master_access import master_access
from tools.configure_shared_master import selected_master

CATALOG = """
import json, time
from urllib.request import urlopen
from modules.database.db_paths import master_duckdb_path
from modules.database.duckdb_core import duckdb_connection
for attempt in range(20):
    try:
        with urlopen('http://127.0.0.1:8000/api/health',timeout=2) as response:
            ready=json.loads(response.read())['status']=='ok'
        break
    except Exception:
        if attempt==19:raise
        time.sleep(1)
path=master_duckdb_path()
with duckdb_connection(path,read_only=True) as con:
    tables=sorted(row[0] for row in con.execute('SHOW TABLES').fetchall())
    for table,key in [('sdr_subscribers','mobile_number'),('cgi_addresses','cgi')]:
        row=con.execute(f'SELECT {key} FROM {table} LIMIT 1').fetchone()
        if row is None:raise ValueError('Lookup table has no sample records: '+table)
        if con.execute(f'SELECT {key} FROM {table} WHERE {key}=? LIMIT 1',[row[0]]).fetchone() is None:
            raise ValueError('Sample key lookup failed: '+table)
print(json.dumps({'api_ready':ready,'path':str(path),'size_bytes':path.stat().st_size,'tables':tables,'sample_key_lookups':'PASS'}))
"""

LOCK_CHECK = """
from modules.database.master_access import master_access
try:
    with master_access(timeout=.3):
        print('UNCOORDINATED')
except TimeoutError:
    print('BLOCKED_BY_HOST')
"""


def verify(project):
    project = Path(project).expanduser().resolve(strict=True)
    database = selected_master(project)
    base = [
        "docker",
        "compose",
        "-f",
        str(project / "backend/docker-compose.yml"),
        "-f",
        str(project / "backend/docker-compose.shared-master.json"),
    ]

    def execute(script):
        result = subprocess.run(
            base + ["exec", "-T", "api", "python", "-"],
            input=script,
            text=True,
            capture_output=True,
            timeout=70,
            cwd=project,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "Container check failed")
        return result.stdout.strip()

    before = database.stat()
    catalog = json.loads(execute(CATALOG))
    if not catalog.get("api_ready"):
        raise ValueError("API health check did not report ready")
    if catalog["path"] != "/master/" + database.name or catalog["size_bytes"] != before.st_size:
        raise ValueError("Container did not select the expected master file")
    with master_access(database):
        if execute(LOCK_CHECK) != "BLOCKED_BY_HOST":
            raise ValueError(
                "Host and container do not coordinate the same lock; keep GUI/API closed until mount setup is corrected"
            )
    after = database.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Master changed during verification; close writers and rerun")
    print(
        json.dumps(
            {
                "status": "VERIFIED",
                "host_master": str(database),
                "container": catalog,
                "cross_process_lock": "PASS",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    try:
        verify(parser.parse_args().project)
    except Exception as error:
        print(f"STOPPED: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
