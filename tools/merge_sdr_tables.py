"""Copy-and-validate SDR consolidation. The input DuckDB is never modified.

Run --plan first; --build writes a new output bundle. --activate changes only a
small reversible application pointer after validation. No input tables are dropped.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from uuid import uuid4

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from modules.database.db_paths import master_duckdb_path
from modules.core.paths import DATABASE_DIR

FIELDS = ["mobile_number", "subscriber_name", "father_name", "address", "id_type", "id_number", "operator", "circle", "activation_date", "caf_number", "source_file", "imported_at"]
TEXT_FIELDS = FIELDS[1:-1]
SOURCES = ("sdr_subscribers", "sdr_subscribers_large")
FORMAT = "ethicalarmor/sdr-consolidation/v1"


def qi(value):
    return '"' + str(value).replace('"', '""') + '"'


def write_json(path, value):
    temp = path.with_name(path.name + ".tmp-" + uuid4().hex)
    with temp.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


@contextmanager
def pointer_lock(pointer):
    pointer.parent.mkdir(parents=True, exist_ok=True)
    lock = pointer.with_name(pointer.name + ".lock")
    descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, str(os.getpid()).encode())
        yield
    finally:
        os.close(descriptor)
        lock.unlink()


def inspect_source(connection):
    tables = [r[0] for r in connection.execute("SELECT table_name FROM duckdb_tables() WHERE database_name=current_database() AND schema_name='main' AND NOT internal ORDER BY table_name").fetchall()]
    if {"ea_sdr_ranked", "ea_sdr_unified"} & set(tables):
        raise ValueError("Reserved migration table names already exist; review before proceeding.")
    missing = set(SOURCES) - set(tables)
    if missing:
        raise ValueError("Both source tables are required; missing: " + ", ".join(sorted(missing)) + ". This database may already be consolidated.")
    views = connection.execute("SELECT view_name FROM duckdb_views() WHERE database_name=current_database() AND NOT internal").fetchall()
    macros = connection.execute("SELECT function_name FROM duckdb_functions() WHERE database_name=current_database() AND function_type IN ('macro','table_macro') AND NOT internal").fetchall()
    if views or macros:
        raise ValueError("Custom views/macros require dependency review before consolidation; no files changed.")
    for table in SOURCES:
        columns = [r[0] for r in connection.execute("DESCRIBE " + qi(table)).fetchall()]
        if set(columns) != set(FIELDS):
            raise ValueError(f"Unsupported columns in {table}; expected the supplied 12-column schema. Extra/missing columns need an explicit migration mapping.")
    return {t: int(connection.execute("SELECT count(*) FROM " + qi(t)).fetchone()[0]) for t in tables}


def plan(source, output_dir):
    source = source.expanduser().resolve(strict=True)
    if Path(str(source) + ".wal").exists():
        raise ValueError("A WAL file exists. Close all database users cleanly and checkpoint through your normal database workflow; do not delete the WAL.")
    with duckdb.connect(str(source), read_only=True) as connection:
        counts = inspect_source(connection)
    ancestor = output_dir.expanduser().resolve()
    while not ancestor.exists():
        ancestor = ancestor.parent
    free = shutil.disk_usage(ancestor).free
    required = source.stat().st_size * 4 + 256 * 1024**2
    return {"source": str(source), "source_size_bytes": source.stat().st_size, "table_counts": counts, "output_directory": str(output_dir.expanduser().resolve()), "free_bytes": free, "minimum_free_bytes": required, "space_note": "Conservative preflight: four times the input file plus 256 MiB. This is not a guarantee of peak usage; normalization, sorting, index creation and audit output may need more."}


def copy_hashed(source, target):
    digest = hashlib.sha256()
    total = 0
    next_message = 1024**3
    with source.open("rb") as inp, target.open("xb") as out:
        while block := inp.read(8 * 1024**2):
            out.write(block)
            digest.update(block)
            total += len(block)
            if total >= next_message:
                print(f"Copied {total / 1024**3:.1f} GiB", flush=True)
                next_message += 1024**3
        out.flush()
        os.fsync(out.fileno())
    return digest.hexdigest()


def build(source, output_dir, *, memory_limit="4GB", threads=2, minimum_free_bytes=None):
    source = source.expanduser().resolve(strict=True)
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"Output directory already exists; refusing to overwrite: {output_dir}")
    if not re.fullmatch(r"[1-9][0-9]*(MB|GB)", memory_limit.upper()):
        raise ValueError("Memory limit must be a positive integer followed by MB or GB")
    if threads < 1:
        raise ValueError("Threads must be positive")
    info = plan(source, output_dir)
    required = info["minimum_free_bytes"] if minimum_free_bytes is None else minimum_free_bytes
    if info["free_bytes"] < required:
        raise OSError(f"Insufficient free space: {info['free_bytes']/1024**3:.1f} GiB free; preflight needs {required/1024**3:.1f} GiB. Choose a larger output drive.")
    output_dir.mkdir(parents=True, exist_ok=False)
    try:
        os.chmod(output_dir, 0o700)
    except OSError:
        pass
    write_json(output_dir / "INCOMPLETE.json", {"format": FORMAT, "source": str(source), "status": "INCOMPLETE"})
    working = output_dir / "working.duckdb"
    # The read-only connection holds the source against other-process writers
    # while the checkpointed bytes are copied. Recheck WAL under that lock.
    with duckdb.connect(str(source), read_only=True) as locked_source:
        if Path(str(source) + ".wal").exists():
            raise ValueError("Source has a WAL; stop and checkpoint it before copying.")
        before = inspect_source(locked_source)
        stat_before = source.stat()
        if stat_before.st_size != info["source_size_bytes"]:
            raise RuntimeError("Source changed after preflight; rerun with all database users closed.")
        print("Copying original into a separate output bundle…", flush=True)
        digest = copy_hashed(source, working)
        stat_after = source.stat()
        if (stat_before.st_size, stat_before.st_mtime_ns) != (stat_after.st_size, stat_after.st_mtime_ns):
            raise RuntimeError("Source file changed during copy; output is incomplete and cannot be activated.")
    temp = output_dir / "spill"
    temp.mkdir()
    connection = duckdb.connect(str(working))
    try:
        connection.execute("SET TimeZone='UTC'")
        connection.execute("SET memory_limit = ?", [memory_limit.upper()])
        connection.execute("SET threads = ?", [threads])
        connection.execute("SET temp_directory = ?", [str(temp)])
        connection.execute("SET preserve_insertion_order=false")
        connection.execute("PRAGMA enable_progress_bar")
        connection.execute("BEGIN TRANSACTION")
        selects = []
        for priority, table in enumerate(SOURCES):
            texts = ", ".join("CAST(" + qi(c) + " AS VARCHAR) AS " + qi(c) for c in TEXT_FIELDS)
            selects.append(f"SELECT CAST(mobile_number AS VARCHAR) AS raw_mobile_number, {texts}, TRY_CAST(imported_at AS TIMESTAMPTZ) AS imported_at, '{table}' AS source_table, {priority} AS source_priority, rowid AS source_rowid FROM {qi(table)}")
        print("Normalizing and ranking complete subscriber records…", flush=True)
        connection.execute("""
            CREATE TEMP TABLE ea_sdr_ranked AS
            WITH raw AS (""" + " UNION ALL ".join(selects) + """),
            digits AS (
                SELECT *, regexp_replace(
                    CASE WHEN regexp_full_match(trim(raw_mobile_number), '[0-9]+[.]0')
                         THEN left(trim(raw_mobile_number), length(trim(raw_mobile_number))-2)
                         ELSE raw_mobile_number END,
                    '[^0-9]', '', 'g') AS raw_digits FROM raw
            ), candidates AS (
                SELECT *, CASE
                    WHEN length(raw_digits)=12 AND starts_with(raw_digits,'91') THEN right(raw_digits,10)
                    WHEN length(raw_digits)=11 AND starts_with(raw_digits,'0') THEN right(raw_digits,10)
                    WHEN length(raw_digits)=10 THEN raw_digits ELSE NULL END AS candidate_mobile
                FROM digits
            ), normalized AS (
                SELECT *, CASE WHEN regexp_full_match(candidate_mobile,'[6-9][0-9]{9}')
                    THEN candidate_mobile ELSE NULL END AS mobile_number FROM candidates
            )
            SELECT *, row_number() OVER (
                PARTITION BY mobile_number
                ORDER BY source_priority ASC,
                    TRY_CAST(activation_date AS DATE) DESC NULLS LAST,
                    imported_at DESC NULLS LAST,
                    ((nullif(trim(subscriber_name),'') IS NOT NULL)::INT +
                     (nullif(trim(address),'') IS NOT NULL)::INT +
                     (nullif(trim(id_number),'') IS NOT NULL)::INT) DESC,
                    TRY_CAST(caf_number AS HUGEINT) DESC NULLS LAST,
                    source_rowid ASC
            ) AS selection_rank FROM normalized
        """)
        all_rows, valid_rows, invalid_rows, distinct_numbers = connection.execute("""
            SELECT count(*), count(mobile_number), count(*)-count(mobile_number), count(DISTINCT mobile_number)
            FROM ea_sdr_ranked
        """).fetchone()
        if all_rows != sum(before[t] for t in SOURCES):
            raise RuntimeError("Source-row reconciliation failed")
        if all_rows and not distinct_numbers:
            raise ValueError("No valid normalized Indian mobile numbers found; review source data. No active database was changed.")
        duplicate_rows = valid_rows - distinct_numbers
        audit_path = output_dir / "sdr_review.parquet"
        connection.execute("""
            COPY (SELECT raw_mobile_number, mobile_number,
                subscriber_name, father_name, address, id_type, id_number, operator,
                circle, activation_date, caf_number, source_file, imported_at,
                source_table, source_rowid,
                CASE WHEN mobile_number IS NULL THEN 'INVALID_MOBILE'
                     ELSE 'ALTERNATE_OR_DUPLICATE_RECORD' END AS review_reason
                FROM ea_sdr_ranked WHERE mobile_number IS NULL OR selection_rank > 1)
            TO ? (FORMAT PARQUET, COMPRESSION ZSTD)
        """, [str(audit_path)])
        # Exact source records remain in the untouched original database. Each
        # winning row is kept whole; fields from different subscribers are not mixed.
        connection.execute("""CREATE TABLE ea_sdr_unified (
            mobile_number VARCHAR PRIMARY KEY, subscriber_name VARCHAR,
            father_name VARCHAR, address VARCHAR, id_type VARCHAR, id_number VARCHAR,
            operator VARCHAR, circle VARCHAR, activation_date VARCHAR, caf_number VARCHAR,
            source_file VARCHAR, imported_at TIMESTAMPTZ DEFAULT current_timestamp)
        """)
        column_csv = ", ".join(qi(c) for c in FIELDS)
        connection.execute(f"INSERT INTO ea_sdr_unified ({column_csv}) SELECT {column_csv} FROM ea_sdr_ranked WHERE mobile_number IS NOT NULL AND selection_rank=1")
        stored = int(connection.execute("SELECT count(*) FROM ea_sdr_unified").fetchone()[0])
        mismatch = " OR ".join(f"r.{qi(c)} IS DISTINCT FROM t.{qi(c)}" for c in FIELDS[1:])
        mismatches = connection.execute(f"""SELECT count(*) FROM ea_sdr_ranked r
            LEFT JOIN ea_sdr_unified t ON r.mobile_number=t.mobile_number
            WHERE r.mobile_number IS NOT NULL AND r.selection_rank=1
              AND (t.mobile_number IS NULL OR {mismatch})""").fetchone()[0]
        audit_count = int(connection.execute("SELECT count(*) FROM read_parquet(?)", [str(audit_path)]).fetchone()[0])
        if stored != distinct_numbers or mismatches or stored + audit_count != all_rows or audit_count != invalid_rows + duplicate_rows:
            raise RuntimeError("Canonical/audit/winner reconciliation failed; output cannot be activated")
        print(f"Validated: {stored:,} canonical records; {audit_count:,} review records.", flush=True)
        # Destructive DDL is confined to the separate working COPY, inside this transaction.
        for table in SOURCES:
            connection.execute("DROP TABLE " + qi(table))
        connection.execute("ALTER TABLE ea_sdr_unified RENAME TO sdr_subscribers")
        after = {t: int(connection.execute("SELECT count(*) FROM " + qi(t)).fetchone()[0]) for t in before if t not in SOURCES}
        if any(before[t] != count for t, count in after.items()):
            raise RuntimeError("Non-SDR table counts changed")
        connection.execute("COMMIT")
        connection.execute("CHECKPOINT")
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        connection.close()
    final = output_dir / "telecom_forensics.duckdb"
    working.rename(final)
    try:
        temp.rmdir()
    except OSError:
        pass
    current_source = source.stat()
    if (current_source.st_size, current_source.st_mtime_ns) != (stat_after.st_size, stat_after.st_mtime_ns):
        raise RuntimeError("Source database changed while building the merged copy. This output remains incomplete; stop other writers and rebuild.")
    report = {
        "format": FORMAT, "status": "VALIDATED", "generated_at": datetime.now(timezone.utc).isoformat(),
        **info, "source_sha256": digest, "source_mtime_ns": stat_after.st_mtime_ns, "source_table_counts": before,
        "canonical_records": stored, "input_sdr_records": all_rows,
        "invalid_mobile_records": invalid_rows, "alternate_or_duplicate_records": duplicate_rows,
        "review_records": audit_count, "unchanged_non_sdr_table_counts": after,
        "database_path": str(final), "database_size_bytes": final.stat().st_size,
        "database_mtime_ns": final.stat().st_mtime_ns,
        "selection_rule": "Whole-row winner: original primary table first, then parsed ISO activation date, imported_at, name/address/id completeness, numeric CAF and source rowid. No cross-record field coalescing.",
        "time_rule": "Naive imported_at timestamps interpreted as UTC for ordering; original source values remain in the input database.",
        "review_path": str(audit_path), "primary_key": "mobile_number",
        "activation": None,
        "migration_progress_note": "Old PostgreSQL migration progress tables are preserved. Do not resume an old offset-based migration against this changed SDR table without a new migration plan.",
    }
    write_json(output_dir / "migration-report.json", report)
    (output_dir / "INCOMPLETE.json").unlink()
    return report


def activate(output_dir, pointer=None):
    pointer = Path(pointer) if pointer else DATABASE_DIR / "master_database.json"
    report_path = Path(output_dir) / "migration-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("format") != FORMAT or report.get("status") != "VALIDATED" or (Path(output_dir) / "INCOMPLETE.json").exists():
        raise ValueError("Only a fully validated output can be activated")
    database = Path(report["database_path"]).resolve(strict=True)
    if database.parent != Path(output_dir).resolve():
        raise ValueError("Output bundle was moved; rebuild/review its report paths before activation")
    stat = database.stat()
    if (stat.st_size, stat.st_mtime_ns) != (report["database_size_bytes"], report["database_mtime_ns"]):
        raise ValueError("Output database changed after validation; refusing automatic activation")
    env = os.getenv("ETHICALARMOR_MASTER_DB", "").strip()
    if env:
        raise ValueError("ETHICALARMOR_MASTER_DB overrides the pointer. Unset it before activating this output.")
    source_stat = Path(report["source"]).stat()
    if (source_stat.st_size, source_stat.st_mtime_ns) != (report["source_size_bytes"], report["source_mtime_ns"]):
        raise ValueError("Original database changed since the copy was taken; stop its writers and build a fresh output before activating.")
    with duckdb.connect(str(database), read_only=True) as con:
        tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        if "sdr_subscribers_large" in tables or "sdr_subscribers" not in tables:
            raise ValueError("Output is not a single canonical SDR store")
        if int(con.execute("SELECT count(*) FROM sdr_subscribers").fetchone()[0]) != report["canonical_records"]:
            raise ValueError("Output record count changed")
    pointer.parent.mkdir(parents=True, exist_ok=True)
    with pointer_lock(pointer):
        if report.get("activation") is not None:
            raise ValueError("This bundle already has an activation record; use its rollback before reactivating")
        previous = pointer.read_text(encoding="utf-8") if pointer.exists() else None
        if previous is not None:
            old = json.loads(previous)
            if old.get("format") != "ethicalarmor/master-database-pointer/v1":
                raise ValueError("Existing pointer has an unsupported format; review it before activation")
        activation = {"pointer": str(pointer.resolve()), "previous_text": previous, "selected_database": str(database)}
        # Persist rollback metadata before touching the application pointer.
        report["activation"] = activation
        write_json(report_path, report)
        try:
            write_json(pointer, {"format": "ethicalarmor/master-database-pointer/v1", "database_path": str(database), "migration_report": str(report_path.resolve())})
        except Exception:
            report["activation"] = None
            write_json(report_path, report)
            raise
    return report


def rollback(output_dir):
    if os.getenv("ETHICALARMOR_MASTER_DB", "").strip():
        raise ValueError("Unset ETHICALARMOR_MASTER_DB before pointer rollback; it overrides the selected database.")
    report_path = Path(output_dir) / "migration-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("format") != FORMAT:
        raise ValueError("Unsupported migration report format")
    record = report.get("activation")
    if not record:
        raise ValueError("No activation record to roll back")
    pointer = Path(record["pointer"])
    with pointer_lock(pointer):
        current = json.loads(pointer.read_text())
        if current.get("database_path") != record["selected_database"]:
            raise ValueError("Current pointer has changed since this activation; refusing to overwrite it")
        if record["previous_text"] is None:
            pointer.unlink()
        else:
            previous = json.loads(record["previous_text"])
            write_json(pointer, previous)
        report["activation"] = None
        report["rolled_back_at"] = datetime.now(timezone.utc).isoformat()
        write_json(report_path, report)
    print("Master database pointer restored. Neither database was deleted.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--memory-limit", default="4GB")
    parser.add_argument("--threads", type=int, default=2)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan", action="store_true")
    group.add_argument("--build", action="store_true")
    group.add_argument("--activate-dir", type=Path)
    group.add_argument("--rollback-dir", type=Path)
    parser.add_argument("--activate", action="store_true", help="After build validation, select the new database through a reversible pointer")
    args = parser.parse_args(argv)
    try:
        if args.rollback_dir:
            rollback(args.rollback_dir)
            return 0
        if args.activate_dir:
            report = activate(args.activate_dir)
        else:
            source = args.source or master_duckdb_path()
            output = args.output_dir or DATABASE_DIR / ("unified-sdr-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
            if args.plan:
                print(json.dumps(plan(source, output), indent=2))
                return 0
            report = build(source, output, memory_limit=args.memory_limit, threads=args.threads)
            if args.activate:
                report = activate(output)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("Done. Restart EthicalArmor and its backend after activation. The original database remains untouched.")
        return 0
    except Exception as error:
        print(f"Migration stopped: {type(error).__name__}: {error}", file=sys.stderr)
        print("The input database was not changed. An output with INCOMPLETE.json must not be activated.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
