"""Durable SDR consolidation with narrow ranking and bounded, checkpointed inserts.

The original input is read-only. Only a new output directory is written. --resume
supports this v2 builder's checkpoints; the old v1 TEMP ranking cannot be resumed.
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
import sys
import time
from uuid import uuid4

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.merge_sdr_tables import (
    FIELDS, TEXT_FIELDS, SOURCES, FORMAT, qi, write_json, inspect_source,
    plan, copy_hashed, activate, rollback,
)
from modules.database.db_paths import master_duckdb_path
from modules.core.paths import DATABASE_DIR

STATE_FORMAT = "ethicalarmor/sdr-resume/v2"
KEYS = "ea_sdr_keys_v2"
KEY_META = "ea_sdr_key_meta_v2"
CURSOR = "ea_sdr_ingest_v2"
RANK_RULE = "whole-row-primary-first-iso-date-imported-completeness-caf-rowid/v1"
COLUMNS = ", ".join(qi(c) for c in FIELDS)


@contextmanager
def run_lock(root):
    lock = root / "run.lock"
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        os.close(fd)
        lock.unlink()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while block := file.read(8 * 1024**2):
            digest.update(block)
    return digest.hexdigest()


def save(root, state):
    write_json(root / "resume.json", state)


def unchanged_source(state):
    source = Path(state["source"])
    stat = source.stat()
    if (stat.st_size, stat.st_mtime_ns) != (state["source_size_bytes"], state["source_mtime_ns"]):
        raise ValueError("Original database changed since preflight/copy. Stop other writers; this checkpoint cannot be reused against changed input.")
    if Path(str(source) + ".wal").exists():
        raise ValueError("Original database has a WAL. Do not delete it; close/checkpoint its writers before proceeding.")


def connection(root, memory, threads):
    con = duckdb.connect(str(root / "telecom_forensics.duckdb"))
    try:
        con.execute("SET TimeZone='UTC'")
        con.execute("SET memory_limit=?", [memory])
        con.execute("SET threads=?", [threads])
        con.execute("SET temp_directory=?", [str(root / "spill")])
        con.execute("SET preserve_insertion_order=false")
        # Keep scans/validation from pinning unrelated ART buffers. Inserts still
        # enforce the canonical primary key. Reopening each batch releases caches.
        con.execute("SET index_scan_percentage=0")
        con.execute("SET index_scan_max_count=0")
        con.execute("PRAGMA enable_progress_bar")
        return con
    except Exception:
        con.close()
        raise


def exists(con, table):
    return bool(con.execute("SELECT count(*) FROM duckdb_tables() WHERE database_name=current_database() AND table_name=? AND NOT internal", [table]).fetchone()[0])


def artifact(root, path):
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError("Artifact outside output directory")
    metadata = pq.ParquetFile(path).metadata
    return {"path": str(path.relative_to(root)), "bytes": path.stat().st_size,
            "rows": metadata.num_rows, "sha256": sha256(path)}


def verify_artifact(root, item):
    path = root / item["path"]
    if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError(f"Checkpoint artifact missing/unsafe: {item['path']}")
    if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"] or pq.ParquetFile(path).metadata.num_rows != item["rows"]:
        raise ValueError(f"Checkpoint artifact changed or is corrupt: {item['path']}")
    return path


def create_keys(root, state, memory, threads):
    print("[2/7] Ranking narrow keys (whole subscriber rows are not materialized in the window).", flush=True)
    con = connection(root, memory, threads)
    try:
        if exists(con, KEYS) or exists(con, KEY_META):
            if not (exists(con, KEYS) and exists(con, KEY_META)):
                raise ValueError("Incomplete key checkpoint schema")
            if con.execute(f"SELECT token FROM {KEY_META}").fetchone()[0] != state["token"]:
                raise ValueError("Key checkpoint belongs to another migration")
        else:
            branches = []
            for priority, table in enumerate(SOURCES):
                branches.append(f"""SELECT CAST(mobile_number AS VARCHAR) AS raw_mobile,
                    {priority}::TINYINT AS source_priority, rowid AS source_rowid,
                    TRY_CAST(activation_date AS DATE) AS activation_order,
                    TRY_CAST(imported_at AS TIMESTAMPTZ) AS imported_order,
                    ((nullif(trim(subscriber_name),'') IS NOT NULL)::INT +
                     (nullif(trim(address),'') IS NOT NULL)::INT +
                     (nullif(trim(id_number),'') IS NOT NULL)::INT) AS completeness,
                    TRY_CAST(caf_number AS HUGEINT) AS caf_order FROM {qi(table)}""")
            con.execute("BEGIN")
            try:
                con.execute(f"""CREATE TABLE {KEYS} AS
                    WITH raw AS ({' UNION ALL '.join(branches)}), digits AS (
                        SELECT *, regexp_replace(CASE
                          WHEN regexp_full_match(trim(raw_mobile),'[0-9]+[.]0')
                          THEN left(trim(raw_mobile),length(trim(raw_mobile))-2)
                          ELSE raw_mobile END,'[^0-9]','','g') AS raw_digits FROM raw
                    ), candidates AS (
                        SELECT *, CASE
                          WHEN length(raw_digits)=12 AND starts_with(raw_digits,'91') THEN right(raw_digits,10)
                          WHEN length(raw_digits)=11 AND starts_with(raw_digits,'0') THEN right(raw_digits,10)
                          WHEN length(raw_digits)=10 THEN raw_digits ELSE NULL END AS candidate_mobile FROM digits
                    ), normalized AS (
                        SELECT *, CASE WHEN regexp_full_match(candidate_mobile,'[6-9][0-9]{{9}}')
                          THEN candidate_mobile ELSE NULL END AS mobile_number FROM candidates
                    )
                    SELECT mobile_number, source_priority, source_rowid,
                        row_number() OVER (PARTITION BY mobile_number ORDER BY
                            source_priority, activation_order DESC NULLS LAST,
                            imported_order DESC NULLS LAST, completeness DESC,
                            caf_order DESC NULLS LAST, source_rowid) AS selection_rank
                    FROM normalized
                """)
                con.execute(f"CREATE TABLE {KEY_META}(token VARCHAR)")
                con.execute(f"INSERT INTO {KEY_META} VALUES (?)", [state["token"]])
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
            con.execute("CHECKPOINT")
        count, valid, invalid, winners = con.execute(f"""SELECT count(*),count(mobile_number),
            count(*)-count(mobile_number),count(*) FILTER (WHERE mobile_number IS NOT NULL AND selection_rank=1)
            FROM {KEYS}""").fetchone()
        if count != sum(state["source_table_counts"][t] for t in SOURCES) or (count and not winners):
            raise ValueError("Ranked source counts/valid-number reconciliation failed")
        state["stats"] = {"input": count, "valid": valid, "invalid": invalid,
                          "winners": winners, "duplicates": valid - winners}
    finally:
        con.close()
    state["phase"] = "KEYS_READY"
    save(root, state)


def selected_rows_sql(review=False):
    branches = []
    condition = "(k.mobile_number IS NULL OR k.selection_rank>1)" if review else "k.mobile_number IS NOT NULL AND k.selection_rank=1"
    for priority, table in enumerate(SOURCES):
        fields = ",".join(f"CAST(t.{qi(c)} AS VARCHAR) AS {qi(c)}" for c in TEXT_FIELDS)
        extras = f""", CAST(t.mobile_number AS VARCHAR) AS raw_mobile_number,
            '{table}' AS source_table, k.source_priority, k.source_rowid,
            CASE WHEN k.mobile_number IS NULL THEN 'INVALID_MOBILE'
                 ELSE 'ALTERNATE_OR_DUPLICATE_RECORD' END AS review_reason""" if review else ""
        branches.append(f"""SELECT k.mobile_number,{fields},
            TRY_CAST(t.imported_at AS TIMESTAMPTZ) AS imported_at {extras}
            FROM {qi(table)} t JOIN {KEYS} k ON t.rowid=k.source_rowid
            WHERE k.source_priority={priority} AND {condition}""")
    return " UNION ALL ".join(branches)


def export_data(root, state, memory, threads):
    print("[3/7] Exporting auditable records and partitioned winners to durable Parquet.", flush=True)
    con = connection(root, memory, threads)
    try:
        if "audit" not in state:
            partial = root / "sdr_review.partial.parquet"
            if partial.exists():
                partial.unlink()  # This builder's own uncommitted export only.
            con.execute("COPY (" + selected_rows_sql(True) + ") TO ? (FORMAT PARQUET,COMPRESSION ZSTD,ROW_GROUP_SIZE 32768)", [str(partial)])
            expected = state["stats"]["invalid"] + state["stats"]["duplicates"]
            if pq.ParquetFile(partial).metadata.num_rows != expected:
                raise ValueError("Audit export count mismatch")
            final = root / "sdr_review.parquet"
            partial.replace(final)
            state["audit"] = artifact(root, final)
            save(root, state)
        if "raw_partitions" not in state:
            partial = root / "winners_raw.partial"
            if partial.exists():
                # Only the bounded, tool-owned partial directory is reset on retry.
                import shutil
                shutil.rmtree(partial)
            sql = "SELECT *, substr(mobile_number,1,2) AS phone_prefix FROM (" + selected_rows_sql(False) + ")"
            con.execute("COPY (" + sql + ") TO ? (FORMAT PARQUET,COMPRESSION ZSTD,PARTITION_BY(phone_prefix),ROW_GROUP_SIZE 32768)", [str(partial)])
            entries = []
            for path in sorted(partial.rglob("*.parquet")):
                prefix = path.parent.name.removeprefix("phone_prefix=")
                if not re.fullmatch(r"[6-9][0-9]", prefix):
                    raise ValueError("Unexpected winner partition")
                info = artifact(root, path)
                info["prefix"] = prefix
                entries.append(info)
            if sum(e["rows"] for e in entries) != state["stats"]["winners"]:
                raise ValueError("Winner export count mismatch")
            # Keep the directory's stable name; its files are now checkpointed.
            state["raw_partitions"] = entries
            save(root, state)
    finally:
        con.close()
    state["phase"] = "EXPORTS_READY"
    save(root, state)


def sort_partitions(root, state, memory, threads):
    print("[4/7] Sorting one phone-prefix partition at a time.", flush=True)
    state.setdefault("sorted", {})
    prefixes = sorted({e["prefix"] for e in state["raw_partitions"]})
    sorted_dir = root / "winners_sorted"
    sorted_dir.mkdir(exist_ok=True)
    for prefix in prefixes:
        if prefix in state["sorted"]:
            continue
        entries = [e for e in state["raw_partitions"] if e["prefix"] == prefix]
        paths = [str(verify_artifact(root, e)) for e in entries]
        con = connection(root, memory, threads)
        partial = sorted_dir / (prefix + ".partial.parquet")
        try:
            if partial.exists():
                partial.unlink()
            con.execute(f"COPY (SELECT {COLUMNS} FROM read_parquet($input_paths,hive_partitioning=false) ORDER BY mobile_number) TO $output_file (FORMAT PARQUET,COMPRESSION ZSTD,ROW_GROUP_SIZE 32768)", {"input_paths":paths,"output_file":str(partial)})
        finally:
            con.close()
        if pq.ParquetFile(partial).metadata.num_rows != sum(e["rows"] for e in entries):
            raise ValueError("Sorted partition count mismatch")
        final = sorted_dir / (prefix + ".parquet")
        partial.replace(final)
        state["sorted"][prefix] = artifact(root, final)
        save(root, state)
        # The verified sorted file replaces this raw staging partition. Audit,
        # input database and already-loaded data are never deleted here.
        for e in entries:
            (root / e["path"]).unlink()
        print(f"  Sorted prefix partition {len(state['sorted'])}/{len(prefixes)}", flush=True)
    state["phase"] = "SORTED_READY"
    save(root, state)


def prepare_target(root, state, memory, threads):
    print("[5/7] Preparing the canonical indexed table in the output copy.", flush=True)
    con = connection(root, memory, threads)
    try:
        if exists(con, CURSOR):
            if con.execute(f"SELECT token FROM {CURSOR}").fetchone()[0] != state["token"]:
                raise ValueError("Load checkpoint belongs to another migration")
        else:
            con.execute("BEGIN")
            try:
                for t in SOURCES:
                    con.execute("DROP TABLE " + qi(t))
                con.execute(f"DROP TABLE {KEYS}")
                con.execute(f"DROP TABLE {KEY_META}")
                con.execute("""CREATE TABLE sdr_subscribers (
                    mobile_number VARCHAR PRIMARY KEY,subscriber_name VARCHAR,
                    father_name VARCHAR,address VARCHAR,id_type VARCHAR,id_number VARCHAR,
                    operator VARCHAR,circle VARCHAR,activation_date VARCHAR,caf_number VARCHAR,
                    source_file VARCHAR,imported_at TIMESTAMPTZ DEFAULT current_timestamp)""")
                con.execute(f"CREATE TABLE {CURSOR}(token VARCHAR,file_index INTEGER,row_offset BIGINT,loaded_rows BIGINT)")
                con.execute(f"INSERT INTO {CURSOR} VALUES (?,0,0,0)", [state["token"]])
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
            con.execute("CHECKPOINT")
    finally:
        con.close()
    state["phase"] = "LOADING"
    save(root, state)


def load_batches(root, state, memory, threads, batch_rows, stop_after_batches=None):
    print("[6/7] Loading bounded batches; every commit/checkpoint reopens DuckDB to release index caches.", flush=True)
    files = [state["sorted"][p] for p in sorted(state["sorted"])]
    con = connection(root, memory, threads)
    try:
        token, file_index, row_offset, loaded = con.execute(f"SELECT * FROM {CURSOR}").fetchone()
        if token != state["token"] or con.execute("SELECT count(*) FROM sdr_subscribers").fetchone()[0] != loaded:
            raise ValueError("Load cursor and canonical row count disagree")
    finally:
        con.close()
    print(f"  Resuming at {loaded:,}/{state['stats']['winners']:,} committed rows.", flush=True)
    commits = 0
    started = time.monotonic()
    for index in range(file_index, len(files)):
        file = pq.ParquetFile(root / files[index]["path"])
        offset = row_offset if index == file_index else 0
        position = 0
        for record_batch in file.iter_batches(batch_size=batch_rows, use_threads=False):
            end = position + record_batch.num_rows
            if end <= offset:
                position = end
                continue
            if position < offset:
                record_batch = record_batch.slice(offset - position)
            position = end
            batch = pa.Table.from_batches([record_batch])
            if batch.column_names != FIELDS:
                raise ValueError("Unexpected canonical Parquet columns")
            new_offset = offset + batch.num_rows
            next_index = index + 1 if new_offset == files[index]["rows"] else index
            next_offset = 0 if next_index != index else new_offset
            lower = batch["mobile_number"][0].as_py()
            upper = batch["mobile_number"][-1].as_py()
            con = connection(root, memory, threads)
            try:
                con.register("ea_batch", batch)
                con.execute("BEGIN")
                try:
                    con.execute(f"INSERT INTO sdr_subscribers({COLUMNS}) SELECT {COLUMNS} FROM ea_batch")
                    different = " OR ".join(f"a.{qi(c)} IS DISTINCT FROM t.{qi(c)}" for c in FIELDS[1:])
                    count = con.execute(f"""SELECT count(*) FROM ea_batch a
                        LEFT JOIN (SELECT * FROM sdr_subscribers WHERE mobile_number BETWEEN ? AND ?) t
                        ON a.mobile_number=t.mobile_number
                        WHERE t.mobile_number IS NULL OR {different}""", [lower, upper]).fetchone()[0]
                    if count:
                        raise ValueError("Inserted batch differs from its winner records")
                    con.execute(f"UPDATE {CURSOR} SET file_index=?,row_offset=?,loaded_rows=?", [next_index,next_offset,loaded+batch.num_rows])
                    con.execute("COMMIT")
                except Exception:
                    con.execute("ROLLBACK")
                    raise
                con.execute("CHECKPOINT")
            finally:
                con.close()
            loaded += batch.num_rows
            offset = new_offset
            commits += 1
            if commits == 1 or commits % 10 == 0 or loaded == state["stats"]["winners"]:
                print(f"  Checkpoint: {loaded:,}/{state['stats']['winners']:,} rows; {time.monotonic()-started:.1f}s in this session.", flush=True)
            if stop_after_batches is not None and commits >= stop_after_batches:
                raise InterruptedError("Test interruption after a committed batch")
    if loaded != state["stats"]["winners"]:
        raise ValueError("Loaded count does not match expected distinct numbers")
    state["phase"] = "FINALIZING"
    save(root, state)


def finalize(root, state, memory, threads):
    print("[7/7] Final counts, source consistency and activation eligibility.", flush=True)
    unchanged_source(state)
    con = connection(root, memory, threads)
    try:
        stored = int(con.execute("SELECT count(*) FROM sdr_subscribers").fetchone()[0])
        if stored != state["stats"]["winners"] or stored + state["audit"]["rows"] != state["stats"]["input"]:
            raise ValueError("Final canonical/audit reconciliation failed")
        others = {t: int(con.execute("SELECT count(*) FROM " + qi(t)).fetchone()[0]) for t in state["source_table_counts"] if t not in SOURCES}
        if any(state["source_table_counts"][t] != count for t,count in others.items()):
            raise ValueError("Non-SDR counts changed")
        if exists(con, CURSOR):
            con.execute(f"DROP TABLE {CURSOR}")
        con.execute("CHECKPOINT")
    finally:
        con.close()
    database = root / "telecom_forensics.duckdb"
    stat = database.stat()
    report = {"format":FORMAT,"builder":"resumable-v2","status":"VALIDATED",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "source":state["source"],"source_size_bytes":state["source_size_bytes"],
        "source_mtime_ns":state["source_mtime_ns"],"source_sha256":state["source_sha256"],
        "source_table_counts":state["source_table_counts"],"canonical_records":stored,
        "input_sdr_records":state["stats"]["input"],"invalid_mobile_records":state["stats"]["invalid"],
        "alternate_or_duplicate_records":state["stats"]["duplicates"],"review_records":state["audit"]["rows"],
        "review_path":str(root/state["audit"]["path"]),"unchanged_non_sdr_table_counts":others,
        "database_path":str(database),"database_size_bytes":stat.st_size,"database_mtime_ns":stat.st_mtime_ns,
        "primary_key":"mobile_number","selection_rule":RANK_RULE,"activation":None,
        "checkpoint_manifest":str(root/"resume.json"),
        "note":"Input remains untouched; old PostgreSQL migration offsets must not be resumed blindly against changed SDR rows."}
    write_json(root/"migration-report.json",report)
    (root/"INCOMPLETE.json").unlink(missing_ok=True)
    state["phase"]="VALIDATED"
    save(root,state)
    return report


def build(source, root, *, resume=False, memory_limit="4GB", threads=1, batch_rows=250000, stop_after_batches=None):
    root=Path(root).expanduser().resolve()
    memory_limit=memory_limit.upper()
    if not re.fullmatch(r"[1-9][0-9]*(MB|GB)",memory_limit) or threads<1 or batch_rows<1:
        raise ValueError("Use a positive memory budget (e.g. 4GB), threads and batch-rows")
    if resume:
        if not (root/"resume.json").is_file():
            raise ValueError("No v2 resume checkpoint. The old v1 TEMP ranking was rolled back and cannot be resumed by this builder.")
        state=json.loads((root/"resume.json").read_text())
        if state.get("format")!=STATE_FORMAT or state.get("output_directory")!=str(root) or state.get("rank_rule")!=RANK_RULE:
            raise ValueError("Unsupported or moved resume checkpoint")
    else:
        source=Path(source).expanduser().resolve(strict=True)
        if root.exists():
            raise FileExistsError("Choose a NEW output directory; existing failed runs are not overwritten.")
        info=plan(source,root)
        if info["free_bytes"]<info["minimum_free_bytes"]:
            raise OSError("Insufficient space for conservative preflight. Free more space or choose a larger output volume.")
        root.mkdir(parents=True)
        try:os.chmod(root,0o700)
        except OSError:pass
        state={"format":STATE_FORMAT,"token":uuid4().hex,"rank_rule":RANK_RULE,
            "source":str(source),"source_size_bytes":source.stat().st_size,"source_mtime_ns":source.stat().st_mtime_ns,
            "source_table_counts":info["table_counts"],"output_directory":str(root),"phase":"NEW"}
        save(root,state)
        write_json(root/"INCOMPLETE.json",{"format":STATE_FORMAT,"source":str(source),"status":"INCOMPLETE"})
    with run_lock(root):
        if state["phase"]=="VALIDATED":
            return json.loads((root/"migration-report.json").read_text())
        unchanged_source(state)
        (root/"spill").mkdir(exist_ok=True)
        if state["phase"]=="NEW":
            print("[1/7] Copying checkpointed original into a separate output database.",flush=True)
            target=root/"telecom_forensics.duckdb"
            if target.exists():target.unlink()
            with duckdb.connect(state["source"],read_only=True) as source_con:
                unchanged_source(state)
                if inspect_source(source_con)!=state["source_table_counts"]:
                    raise ValueError("Source counts changed after planning")
                state["source_sha256"]=copy_hashed(Path(state["source"]),target)
                unchanged_source(state)
            state["phase"]="COPY_READY";save(root,state)
        # Verify durable exports before reusing them. Raw files for a completed
        # sort partition were deliberately replaced by its verified sorted file.
        if "audit" in state or state.get("sorted"):
            print("Verifying saved artifact hashes before reusing checkpoints…",flush=True)
        if "audit" in state:verify_artifact(root,state["audit"])
        for item in state.get("sorted",{}).values():verify_artifact(root,item)
        for item in state.get("raw_partitions",[]):
            if item["prefix"] not in state.get("sorted",{}):verify_artifact(root,item)
        if state["phase"]=="COPY_READY":create_keys(root,state,memory_limit,threads)
        if state["phase"]=="KEYS_READY":export_data(root,state,memory_limit,threads)
        if state["phase"]=="EXPORTS_READY":sort_partitions(root,state,memory_limit,threads)
        if state["phase"]=="SORTED_READY":prepare_target(root,state,memory_limit,threads)
        if state["phase"]=="LOADING":load_batches(root,state,memory_limit,threads,batch_rows,stop_after_batches)
        return finalize(root,state,memory_limit,threads)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan",action="store_true")
    group.add_argument("--build",action="store_true")
    group.add_argument("--resume",type=Path,metavar="OUTPUT_DIR")
    parser.add_argument("--source",type=Path)
    parser.add_argument("--output-dir",type=Path)
    parser.add_argument("--memory-limit",default="4GB")
    parser.add_argument("--threads",type=int,default=1)
    parser.add_argument("--batch-rows",type=int,default=250000)
    parser.add_argument("--activate",action="store_true")
    args=parser.parse_args(argv)
    try:
        source=args.source or (Path(".") if args.resume else master_duckdb_path())
        output=args.resume or args.output_dir or DATABASE_DIR/"unified_sdr_v2"
        if args.plan:
            print(json.dumps(plan(source,output),indent=2));return 0
        report=build(source,output,resume=bool(args.resume),memory_limit=args.memory_limit,threads=args.threads,batch_rows=args.batch_rows)
        if args.activate and not report.get("activation"):
            report=activate(output)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        print("Validated. Restart GUI/backend after activation. Keep the original database until real lookups are verified.")
        return 0
    except Exception as error:
        print(f"Stopped: {type(error).__name__}: {error}",file=sys.stderr)
        print("Original input is unchanged. Keep this v2 output; --resume reuses completed v2 stages and committed batches.",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
