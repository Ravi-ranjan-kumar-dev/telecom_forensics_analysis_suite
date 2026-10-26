"""Small, privacy-conscious local diagnostic events for handled GUI exceptions.

Does not inspect original evidence, record values, SQL parameters, or full exception
messages. The traceback's code locations are enough for module/function triage.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import traceback
from typing import Any
import uuid

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DIAG_DIR = PROJECT_ROOT / "diagnostics"
LAST_FILE = DIAG_DIR / "last_handled_error.json"
HISTORY_FILE = DIAG_DIR / "handled_errors.jsonl"
MAX_HISTORY_BYTES = 1024 * 1024


def _project_frame(filename: str) -> str | None:
    try:
        p = Path(filename).resolve()
        return p.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except (ValueError, OSError):
        return None


def record_handled_exception() -> str:
    """Record current except block's traceback without sensitive evidence values.

    Returns error ID, never raises. Call only inside an except handler.
    """
    try:
        exc_type, exc_value, tb = sys.exc_info()
        if exc_type is None:
            return ""
        frames = traceback.extract_tb(tb) if tb is not None else []
        project_frames = []
        for frame in frames:
            local = _project_frame(frame.filename)
            if local is not None:
                project_frames.append({
                    "module": local[:-3].replace("/", ".") if local.endswith(".py") else local,
                    "file": local,
                    "function": frame.name,
                    "line": frame.lineno,
                })
        # The last project frame is the deepest project code that failed.
        origin: dict[str, Any] | None = project_frames[-1] if project_frames else None
        # Site of the *catch* is useful when an exception crosses GUI boundaries.
        caught = sys._getframe(1)
        catch_file = _project_frame(caught.f_code.co_filename)
        handler = ({
            "module": catch_file[:-3].replace("/", ".") if catch_file and catch_file.endswith(".py") else catch_file,
            "file": catch_file,
            "function": caught.f_code.co_name,
            "line": caught.f_lineno,
        } if catch_file else None)
        event = {
            "id": uuid.uuid4().hex[:10].upper(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "type": exc_type.__name__,
            "origin": origin,
            "caught_at": handler,
            "project_trace": project_frames[-12:],
            "privacy": "No exception message, source-line contents, or evidence values logged.",
        }
        DIAG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        if HISTORY_FILE.exists() and HISTORY_FILE.stat().st_size > MAX_HISTORY_BYTES:
            rotated = HISTORY_FILE.with_suffix(".jsonl.old")
            HISTORY_FILE.replace(rotated)
        with HISTORY_FILE.open("a", encoding="utf-8") as out:
            out.write(json.dumps(event, ensure_ascii=False) + "\n")
        try:
            HISTORY_FILE.chmod(0o600)
        except OSError:
            pass
        tmp = LAST_FILE.with_name("last_handled_error_" + event["id"] + ".tmp")
        with tmp.open("w", encoding="utf-8") as out:
            json.dump(event, out, ensure_ascii=False, indent=2)
        tmp.replace(LAST_FILE)
        try:
            LAST_FILE.chmod(0o600)
        except OSError:
            pass
        where = origin or handler or {}
        print(
            f"[EA-DIAG {event['id']}] {event['type']} in "
            f"{where.get('file', '?')}:{where.get('line', '?')} "
            f"{where.get('function', '?')}()",
            file=sys.stderr,
        )
        return event["id"]
    except Exception:
        # Tracking must never interrupt the original GUI error handling.
        return ""
