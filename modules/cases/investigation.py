"""Case-scoped saved leads and a derived number index; never edits evidence."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3

import pandas as pd
from modules.core.time_utils import utc_now_iso
from . import service
from .repository import read_json, safe_descendant


def text(value):
    if value is None or (pd.api.types.is_scalar(value) and pd.isna(value)):
        return ""
    return str(value)


def bookmark_id(source_id, sheet, row, source_row=""):
    payload = [
        str(source_id),
        str(sheet),
        str(source_row),
        sorted((str(k), text(v)) for k, v in row.items()),
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


@contextmanager
def _connection(case_id, *, write=False):
    directory = service.case_directory(case_id)
    path = safe_descendant(directory, "configuration", "investigation.sqlite3")
    if not write and not path.is_file():
        yield None
        return
    if write:
        service.ensure_case_writable(case_id)
        path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(
        str(path) if write else path.resolve().as_uri() + "?mode=ro", uri=not write, timeout=30
    )
    con.row_factory = sqlite3.Row
    try:
        if write:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS bookmarks (
                    bookmark_id TEXT PRIMARY KEY, source_id TEXT NOT NULL,
                    sheet TEXT NOT NULL, source_row TEXT NOT NULL,
                    row_json TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS number_runs (run_id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS numbers (
                    run_id TEXT NOT NULL, number TEXT NOT NULL, role TEXT NOT NULL,
                    observations INTEGER NOT NULL, PRIMARY KEY(run_id, number, role));
            """)
        yield con
        if write:
            con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def list_bookmarks(case_id):
    with _connection(case_id) as con:
        rows = (
            con.execute("SELECT * FROM bookmarks ORDER BY created_at, bookmark_id").fetchall()
            if con
            else []
        )
    return [{**dict(row), "row_data": json.loads(row["row_json"])} for row in rows]


def add_bookmarks(case_id, entries):
    added = duplicate = 0
    with _connection(case_id, write=True) as con:
        for entry in entries:
            key = entry["bookmark_id"]
            result = con.execute(
                "INSERT OR IGNORE INTO bookmarks VALUES (?,?,?,?,?,?)",
                (
                    key,
                    entry["source_id"],
                    entry["sheet"],
                    str(entry.get("source_row", "")),
                    json.dumps(
                        {str(k): text(v) for k, v in entry["row_data"].items()}, ensure_ascii=False
                    ),
                    utc_now_iso(),
                ),
            )
            added += result.rowcount
            duplicate += 1 - result.rowcount
    return added, duplicate


def remove_bookmarks(case_id, identifiers):
    with _connection(case_id, write=True) as con:
        con.executemany(
            "DELETE FROM bookmarks WHERE bookmark_id=?", [(str(key),) for key in identifiers]
        )


def bookmarks_frame(case_id):
    output = []
    for entry in list_bookmarks(case_id):
        output.append(
            {
                **entry["row_data"],
                "Case ID": case_id,
                "Source Sheet": entry["sheet"],
                "Source Run": entry["source_id"],
                "Source Row": entry["source_row"],
                "Bookmarked At": entry["created_at"],
                "Bookmark ID": entry["bookmark_id"],
            }
        )
    return pd.DataFrame(output)


_NUMBER_COLUMNS = {
    "targetnumber": "Target",
    "aparty": "Subscriber / A-party",
    "subscriber_number": "Subscriber / A-party",
    "subscribernumber": "Subscriber / A-party",
    "mobilesubscriberno": "Subscriber / A-party",
    "subscriberno": "Subscriber / A-party",
    "msisdn": "Subscriber / A-party",
    "bparty": "Counterparty",
    "otherparty": "Counterparty",
    "otherpartybparty": "Counterparty",
    "callingnumber": "Caller",
    "callednumber": "Called party",
    "mobilenumber": "Subscriber / A-party",
}


def number_columns(columns):
    return [
        (c, _NUMBER_COLUMNS[key])
        for c in columns
        if (key := re.sub(r"[^a-z0-9]", "", str(c).lower())) in _NUMBER_COLUMNS
    ]


def number_text(value):
    value = text(value).strip()
    if value.endswith(".0") and value[:-2].isdigit():
        value = value[:-2]
    # Indian 10-digit numbers may arrive with the country prefix.
    digits = re.sub(r"[\s()+-]", "", value)
    if re.fullmatch(r"(?:0091|91)[6-9]\d{9}", digits):
        return digits[-10:]
    return digits if digits.isdigit() and 3 <= len(digits) <= 15 else ""


def index_case_numbers(case_id, run_id, frames):
    """Replace one run's derived counts; repeated indexing never doubles them."""
    counts = {}
    for _, frame in frames:
        for column, role in number_columns(frame.columns):
            values = frame[column].map(number_text)
            for number, count in values[values.ne("")].value_counts().items():
                counts[(str(number), role)] = counts.get((str(number), role), 0) + int(count)
    with _connection(case_id, write=True) as con:
        con.execute("DELETE FROM numbers WHERE run_id=?", (str(run_id),))
        con.executemany(
            "INSERT INTO numbers VALUES (?,?,?,?)",
            [(str(run_id), n, r, count) for (n, r), count in counts.items()],
        )
        con.execute("INSERT OR IGNORE INTO number_runs VALUES (?)", (str(run_id),))


def indexed_runs(case_id):
    with _connection(case_id) as con:
        return {r[0] for r in con.execute("SELECT run_id FROM number_runs")} if con else set()


def numbers_frame(case_id):
    with _connection(case_id) as con:
        rows = (
            con.execute("""SELECT number AS "Number", GROUP_CONCAT(DISTINCT role) AS "Observed Roles",
            SUM(observations) AS "Analyzed Appearances", COUNT(DISTINCT run_id) AS "Analysis Runs"
            FROM numbers GROUP BY number ORDER BY number""").fetchall()
            if con
            else []
        )
    result = {row["Number"]: dict(row) for row in rows}
    targets = read_json(
        safe_descendant(service.case_directory(case_id), "configuration", "targets.json"),
        default=[],
    )
    for target in targets:
        if str(target.get("target_type", "")).upper() not in {"MSISDN", "MOBILE", "PHONE"}:
            continue
        number = number_text(target.get("target_value"))
        if not number:
            continue
        item = result.setdefault(
            number,
            {
                "Number": number,
                "Observed Roles": "Registered target",
                "Analyzed Appearances": 0,
                "Analysis Runs": 0,
            },
        )
        if "Registered target" not in item["Observed Roles"]:
            item["Observed Roles"] += ",Registered target"
    return pd.DataFrame(
        result.values(),
        columns=["Number", "Observed Roles", "Analyzed Appearances", "Analysis Runs"],
    )


def backfill_saved_numbers(case_id):
    """Project phone columns from older case-local saved CDR runs on demand."""
    import duckdb
    from modules.reporting.cdr_report_source import _resolve_portable_path

    root = service.case_directory(case_id).resolve()
    done = indexed_runs(case_id)
    errors = []
    for manifest in sorted((root / "staging/cdr_report_runs").glob("*/manifest.json")):
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            run_id = str(payload["analysis_run_id"])
            if payload.get("case_id") != case_id or run_id in done:
                continue
            frames = []
            with duckdb.connect(":memory:") as con:
                con.execute("SET memory_limit='256MB'")
                con.execute("SET threads=1")
                for dataset in payload.get("datasets", []):
                    path = _resolve_portable_path(dataset["path"]).resolve(strict=True)
                    if not path.is_relative_to(root):
                        raise ValueError("Saved dataset is outside this case")
                    columns = [
                        r[0]
                        for r in con.execute(
                            "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]
                        ).fetchall()
                    ]
                    names = [c for c, _ in number_columns(columns)]
                    if names:
                        projection = ",".join('"' + c.replace('"', '""') + '"' for c in names)
                        frame = con.execute(
                            "SELECT " + projection + " FROM read_parquet(?)", [str(path)]
                        ).df()
                        frames.append((str(path.name), frame))
            index_case_numbers(case_id, run_id, frames)
            done.add(run_id)
        except Exception as error:
            errors.append(f"{manifest.parent.name}: {type(error).__name__}: {error}")
    return errors


def all_case_numbers_frame():
    """Read registered targets and existing number indexes across saved cases."""
    frames, errors = [], []
    for archived in (False, True):
        for metadata in service.list_cases(archived=archived):
            case_id = str(metadata["case_id"])
            try:
                frame = numbers_frame(case_id)
                if not frame.empty:
                    frame.insert(0, "Case ID", case_id)
                    frame.insert(1, "Case Name", str(metadata.get("case_name", "")))
                    frame.insert(2, "Case Status", "Archived" if archived else "Active")
                    frames.append(frame)
            except Exception as error:
                errors.append(f"{case_id}: {type(error).__name__}: {error}")
    columns = [
        "Case ID",
        "Case Name",
        "Case Status",
        "Number",
        "Observed Roles",
        "Analyzed Appearances",
        "Analysis Runs",
    ]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns), errors
