# gui/workers/lookup_worker.py
"""Background lookup and master-data import worker using API."""

from __future__ import annotations

import contextlib
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from gui.workers.text_stream import SignalTextStream
from gui.api_client import (
    ApiClient,
    ApiError,
    RecordNotFoundError,
    ServiceUnavailableError,
)
from modules.controllers import lookup_controller  # Fallback when API unavailable

LOOKUP_OPERATIONS = {
    "sdr",
    "cgi",
    "import",
    "import_folder",
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

    @Slot()
    def run(self) -> None:
        output_stream = SignalTextStream(self.log.emit)

        try:
            with (
                contextlib.redirect_stdout(output_stream),
                contextlib.redirect_stderr(output_stream),
            ):
                if self.operation == "import":
                    if self.api_client is None:
                        raise ServiceUnavailableError("API client not available")
                    result = self.api_client.import_master_file(self.value)

                elif self.operation == "import_folder":
                    if self.api_client is None:
                        raise ServiceUnavailableError("API client not available")
                    folder = Path(self.value)
                    if not folder.is_dir():
                        raise FileNotFoundError(f"Folder not found: {folder}")
                    files = [
                        p for p in folder.iterdir()
                        if p.is_file() and p.suffix.lower() in (".csv", ".txt", ".tsv", ".xlsx", ".xls")
                    ]
                    total_rows = 0
                    for f in files:
                        resp = self.api_client.import_master_file(str(f))
                        total_rows += resp.get("rows", 0)
                    result = {
                        "status": "SUCCESS",
                        "message": f"Imported {len(files)} files, total rows: {total_rows}",
                        "inserted_rows": total_rows,
                    }

                elif self.operation in ("sdr", "cgi"):
                    if self.api_client is None:
                        # Fallback to local controller (for tests and offline use)
                        if self.operation == "sdr":
                            numbers = [n.strip() for n in self.value.split(",") if n.strip()]
                            records = []
                            for num in numbers:
                                res = lookup_controller.run_sdr_lookup(None, num)
                                # Check both 'found' and 'status' for correctness
                                if res.get("found") or res.get("status") == "MATCHED":
                                    records.append({**res.get("record", {}), "__status": "FOUND"})
                                else:
                                    records.append({"mobile_number": num, "__status": "NOT_FOUND"})
                            result = {
                                "status": "MATCHED" if any(r.get("__status") == "FOUND" for r in records) else "NOT_FOUND",
                                "records": records,
                            }
                        else:  # cgi
                            cgis = [c.strip() for c in self.value.split(",") if c.strip()]
                            records = []
                            for cgi in cgis:
                                res = lookup_controller.run_cgi_lookup(None, cgi)
                                if res.get("found") or res.get("status") == "MATCHED":
                                    records.append({**res.get("record", {}), "__status": "FOUND"})
                                else:
                                    records.append({"cgi": cgi, "__status": "NOT_FOUND"})
                            result = {
                                "status": "MATCHED" if any(r.get("__status") == "FOUND" for r in records) else "NOT_FOUND",
                                "records": records,
                            }
                    else:
                        # Use API client
                        if self.operation == "sdr":
                            numbers = [n.strip() for n in self.value.split(",") if n.strip()]
                            records = []
                            for num in numbers:
                                try:
                                    record = self.api_client.lookup_sdr(num)
                                    if record:
                                        mapped = {
                                            "mobile_number": record.get("mobile_number", num),
                                            "subscriber_name": record.get("subscriber_name", ""),
                                            "father_name": record.get("father_name", ""),
                                            "clean_address": clean_display_address(record.get("address", "")),
                                            "id_number": record.get("id_number", ""),
                                            "operator_or_source_category": record.get("operator", ""),
                                            "circle": record.get("circle", ""),
                                            "activation_date": record.get("activation_date", ""),
                                            "source_file": record.get("source_file", ""),
                                            "__status": "FOUND",
                                        }
                                        records.append(mapped)
                                    else:
                                        records.append({"mobile_number": num, "__status": "NOT_FOUND"})
                                except RecordNotFoundError:
                                    records.append({"mobile_number": num, "__status": "NOT_FOUND"})
                                except ServiceUnavailableError:
                                    self.failed.emit("Backend service is unavailable. Please try again later.")
                                    return
                                except ApiError as e:
                                    self.failed.emit(str(e))
                                    return
                            result = {
                                "status": "MATCHED" if any(r.get("__status") == "FOUND" for r in records) else "NOT_FOUND",
                                "records": records,
                            }
                        else:  # cgi
                            cgis = [c.strip() for c in self.value.split(",") if c.strip()]
                            records = []
                            for cgi in cgis:
                                try:
                                    record = self.api_client.lookup_cgi(cgi)
                                    if record:
                                        record["__status"] = "FOUND"
                                        records.append(record)
                                    else:
                                        records.append({"cgi": cgi, "__status": "NOT_FOUND"})
                                except RecordNotFoundError:
                                    records.append({"cgi": cgi, "__status": "NOT_FOUND"})
                                except ServiceUnavailableError:
                                    self.failed.emit("Backend service is unavailable. Please try again later.")
                                    return
                                except ApiError as e:
                                    self.failed.emit(str(e))
                                    return
                            result = {
                                "status": "MATCHED" if any(r.get("__status") == "FOUND" for r in records) else "NOT_FOUND",
                                "records": records,
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


def clean_display_address(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("!", ", ").replace("|", ", ").replace("^", ", ")
    text = " ".join(text.split())
    return text.strip(", ")