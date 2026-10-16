"""Background lookup and master-data import worker with API + DuckDB support."""

from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from gui.api_client import (
    ApiClient,
    ApiError,
    RecordNotFoundError,
    ServiceUnavailableError,
)
from gui.workers.text_stream import SignalTextStream
from modules.controllers import lookup_controller
from modules.database.lookup_service import clear_all_lookup_caches
from modules.database.master_import_service import (
    SUPPORTED_MASTER_SUFFIXES,
    import_master_data_file,
)

LOOKUP_OPERATIONS = {
    "sdr",
    "cgi",
    "import",
    "import_folder",
}


def clean_display_address(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("!", ", ").replace("|", ", ").replace("^", ", ")
    text = " ".join(text.split())
    return text.strip(", ")


def _normalize_api_import_response(
    resp: dict[str, Any],
    source_path: str,
) -> dict[str, Any]:
    """Ensure API import responses populate all GUI summary fields."""
    status = str(resp.get("status", "SUCCESS")).strip().upper()
    import_type = str(resp.get("import_type") or resp.get("type") or "").strip().upper()
    rows = int(resp.get("rows", resp.get("valid_rows", 0)) or 0)
    inserted = int(resp.get("inserted_rows", rows) or 0)
    updated = int(resp.get("updated_rows", 0) or 0)
    target_table = str(
        resp.get("target_table")
        or ("sdr_subscribers" if import_type == "SDR" else "cgi_addresses" if import_type == "CGI" else "")
    )
    return {
        "status": status,
        "import_type": import_type,
        "target_table": target_table,
        "source_file": str(resp.get("source_file") or Path(source_path).name),
        "rows_read": int(resp.get("rows_read", rows) or 0),
        "valid_rows": int(resp.get("valid_rows", rows) or 0),
        "invalid_rows": int(resp.get("invalid_rows", 0) or 0),
        "duplicate_rows": int(resp.get("duplicate_rows", 0) or 0),
        "inserted_rows": inserted,
        "updated_rows": updated,
        "skipped_rows": int(resp.get("skipped_rows", 0) or 0),
        "before_count": int(resp.get("before_count", 0) or 0),
        "after_count": int(resp.get("after_count", inserted + updated) or 0),
        "duration_seconds": resp.get("duration_seconds", "-"),
        "backup_path": resp.get("backup_path", "-"),
        "log_path": resp.get("log_path", "-"),
        "message": str(resp.get("message") or f"Imported {rows:,} rows."),
    }


class LookupWorker(QObject):
    """Run a lookup or master-data import outside the GUI thread."""

    log = Signal(str)
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        *,
        operation: str,
        value: str | Path,
        api_client: ApiClient | None = None,
    ) -> None:
        super().__init__()
        self.operation = str(operation).strip().casefold()
        self.value = str(value).strip()
        self.api_client = api_client

        if self.operation not in LOOKUP_OPERATIONS:
            raise ValueError(f"Unsupported lookup operation: {operation}")

    def _lookup_sdr_local(self, num: str) -> list[dict[str, Any]]:
        res = lookup_controller.run_sdr_lookup(None, num)
        if res.get("found") or res.get("status") == "MATCHED":
            records = res.get("records")
            if isinstance(records, list) and records:
                return [{**r, "__status": "FOUND"} for r in records if isinstance(r, dict)]
            record = res.get("record")
            if isinstance(record, dict) and record:
                return [{**record, "__status": "FOUND"}]
        return [{"mobile_number": num, "__status": "NOT_FOUND"}]

    def _lookup_cgi_local(self, cgi: str) -> list[dict[str, Any]]:
        res = lookup_controller.run_cgi_lookup(None, cgi)
        if res.get("found") or res.get("status") == "MATCHED":
            record = res.get("record")
            if isinstance(record, dict) and record:
                return [{**record, "__status": "FOUND"}]
        return [{"cgi": cgi, "__status": "NOT_FOUND"}]

    @Slot()
    def run(self) -> None:
        output_stream = SignalTextStream(self.log.emit)

        try:
            with (
                contextlib.redirect_stdout(output_stream),
                contextlib.redirect_stderr(output_stream),
            ):
                if self.operation == "import":
                    if self.api_client is not None:
                        try:
                            resp = self.api_client.import_master_file(self.value)
                            result = _normalize_api_import_response(resp, self.value)
                        except ServiceUnavailableError:
                            print("[!] API backend unavailable; importing directly into local DuckDB master database.")
                            result = import_master_data_file(self.value, create_backup=True)
                    else:
                        result = import_master_data_file(self.value, create_backup=True)
                    clear_all_lookup_caches()

                elif self.operation == "import_folder":
                    folder = Path(self.value)
                    if not folder.is_dir():
                        raise FileNotFoundError(f"Folder not found: {folder}")
                    files = sorted(
                        p
                        for p in folder.iterdir()
                        if p.is_file() and p.suffix.lower() in SUPPORTED_MASTER_SUFFIXES
                    )
                    if not files:
                        raise ValueError(f"No supported master files found in {folder}")

                    total_rows = 0
                    total_inserted = 0
                    total_updated = 0
                    skipped_files = 0
                    for f in files:
                        if self.api_client is not None:
                            try:
                                resp = self.api_client.import_master_file(str(f))
                                norm = _normalize_api_import_response(resp, str(f))
                            except ServiceUnavailableError:
                                norm = import_master_data_file(f, create_backup=False)
                        else:
                            norm = import_master_data_file(f, create_backup=False)

                        st = str(norm.get("status", "")).upper()
                        if st == "SUCCESS":
                            ins = int(norm.get("inserted_rows", 0) or 0)
                            upd = int(norm.get("updated_rows", 0) or 0)
                            val = int(norm.get("valid_rows", ins + upd) or 0)
                            total_rows += val
                            total_inserted += ins
                            total_updated += upd
                            print(f"[+] Imported {f.name}: {val:,} valid rows")
                        elif st.startswith("SKIPPED"):
                            skipped_files += 1
                            print(f"[=] Skipped {f.name}: {norm.get('message', '')}")
                        else:
                            print(f"[-] Failed {f.name}: {norm.get('message', '')}")

                    clear_all_lookup_caches()
                    result = {
                        "status": "SUCCESS",
                        "import_type": "FOLDER_BATCH",
                        "target_table": "sdr_subscribers / cgi_addresses",
                        "source_file": str(folder),
                        "rows_read": total_rows,
                        "valid_rows": total_rows,
                        "inserted_rows": total_inserted or total_rows,
                        "updated_rows": total_updated,
                        "skipped_rows": skipped_files,
                        "message": f"Imported {len(files)} file(s), total valid rows: {total_rows:,}",
                    }

                elif self.operation == "sdr":
                    numbers = [
                        n.strip()
                        for n in re.split(r"[,;\s]+", self.value)
                        if n.strip()
                    ]
                    records: list[dict[str, Any]] = []
                    for num in numbers:
                        if self.api_client is None:
                            records.extend(self._lookup_sdr_local(num))
                        else:
                            try:
                                record = self.api_client.lookup_sdr(num)
                                if record:
                                    mapped = {
                                        "mobile_number": record.get("mobile_number", num),
                                        "subscriber_name": record.get("subscriber_name", ""),
                                        "father_name": record.get("father_name", ""),
                                        "clean_address": clean_display_address(
                                            record.get("address", "")
                                        ),
                                        "id_number": record.get("id_number", ""),
                                        "operator_or_source_category": record.get(
                                            "operator", ""
                                        ),
                                        "circle": record.get("circle", ""),
                                        "activation_date": record.get(
                                            "activation_date", ""
                                        ),
                                        "source_file": record.get("source_file", ""),
                                        "__status": "FOUND",
                                    }
                                    records.append(mapped)
                                else:
                                    records.extend(self._lookup_sdr_local(num))
                            except RecordNotFoundError:
                                records.extend(self._lookup_sdr_local(num))
                            except ServiceUnavailableError:
                                records.extend(self._lookup_sdr_local(num))
                            except ApiError as error:
                                self.failed.emit(str(error))
                                return

                    found_any = any(r.get("__status") == "FOUND" for r in records)
                    result = {
                        "status": "MATCHED" if found_any else "NOT_FOUND",
                        "records": records,
                        "message": (
                            "SDR profile matched."
                            if found_any
                            else "SDR profile database mein nahi mila."
                        ),
                    }

                elif self.operation == "cgi":
                    cgis = [
                        c.strip()
                        for c in re.split(r"[,;]+", self.value)
                        if c.strip()
                    ]
                    records = []
                    for cgi in cgis:
                        if self.api_client is None:
                            records.extend(self._lookup_cgi_local(cgi))
                        else:
                            try:
                                record = self.api_client.lookup_cgi(cgi)
                                if record:
                                    record["__status"] = "FOUND"
                                    records.append(record)
                                else:
                                    records.extend(self._lookup_cgi_local(cgi))
                            except RecordNotFoundError:
                                records.extend(self._lookup_cgi_local(cgi))
                            except ServiceUnavailableError:
                                records.extend(self._lookup_cgi_local(cgi))
                            except ApiError as error:
                                self.failed.emit(str(error))
                                return

                    found_any = any(r.get("__status") == "FOUND" for r in records)
                    result = {
                        "status": "MATCHED" if found_any else "NOT_FOUND",
                        "records": records,
                        "message": (
                            "CGI / Cell record matched."
                            if found_any
                            else "CGI / Cell database mein nahi mila."
                        ),
                    }

                else:
                    raise ValueError(f"Unsupported operation: {self.operation}")

            output_stream.flush()

            if not isinstance(result, dict):
                raise TypeError("Lookup operation did not return a valid result.")

            self.completed.emit(
                {
                    "operation": self.operation,
                    "value": self.value,
                    "result": result,
                }
            )

        except Exception as error:
            output_stream.flush()
            self.failed.emit(f"{type(error).__name__}: {error}")

        finally:
            self.finished.emit()
