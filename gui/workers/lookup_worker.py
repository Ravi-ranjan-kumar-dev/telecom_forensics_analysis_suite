# gui/workers/lookup_worker.py
"""Background lookup and master-data import worker using API."""

from __future__ import annotations

import contextlib
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from gui.workers.text_stream import SignalTextStream

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
        api_client=None,
    ) -> None:
        super().__init__()
        self.operation = str(operation).strip().casefold()
        self.value = str(value).strip()
        self.api_client = api_client

        if self.operation not in LOOKUP_OPERATIONS:
            raise ValueError(f"Unsupported lookup operation: {operation}")

    @Slot()
    def run(self) -> None:
        """Execute one selected lookup operation."""
        output_stream = SignalTextStream(self.log.emit)

        try:
            with (
                contextlib.redirect_stdout(output_stream),
                contextlib.redirect_stderr(output_stream),
            ):
                if self.operation == "import":
                    from modules.database.master_import_service import import_master_data_file
                    result = import_master_data_file(self.value, create_backup=True)

                elif self.operation == "import_folder":
                    from modules.database.master_import_service import import_master_folder
                    total_rows = import_master_folder(self.value, import_type="auto")
                    result = {
                        "status": "SUCCESS",
                        "message": f"Folder import completed. Total rows: {total_rows}",
                        "inserted_rows": total_rows,
                        "source_file": self.value,
                    }

                else:
                    # API-based lookup
                    if self.api_client is None:
                        raise ValueError("API client not available for lookup.")

                    if self.operation == "sdr":
                        numbers = [n.strip() for n in self.value.split(",") if n.strip()]
                        records = []
                        for num in numbers:
                            record = self.api_client.lookup_sdr(num)
                            if record:
                                # API response has 'address' and 'operator', but GUI expects 'clean_address' and 'operator_or_source_category'
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
                                records.append({
                                    "mobile_number": num,
                                    "__status": "NOT_FOUND",
                                })
                        result = {"status": "MATCHED" if any(r.get("__status") == "FOUND" for r in records) else "NOT_FOUND", "records": records}

                    else:  # cgi
                        cgis = [c.strip() for c in self.value.split(",") if c.strip()]
                        records = []
                        for cgi in cgis:
                            record = self.api_client.lookup_cgi(cgi)
                            if record:
                                record["__status"] = "FOUND"
                                records.append(record)
                            else:
                                records.append({"cgi": cgi, "__status": "NOT_FOUND"})
                        result = {"status": "MATCHED" if any(r.get("__status") == "FOUND" for r in records) else "NOT_FOUND", "records": records}

            output_stream.flush()

            if not isinstance(result, dict):
                raise TypeError("Lookup operation did not return a valid result.")

            self.completed.emit({
                "operation": self.operation,
                "value": self.value,
                "result": result,
            })

        except Exception as error:  # noqa: BLE001 - worker failure boundary.
            output_stream.flush()
            self.failed.emit(f"{type(error).__name__}: {error}")

        finally:
            self.finished.emit()


def clean_display_address(value: object) -> str:
    """Simple address cleaner to remove separators."""
    if value is None:
        return ""
    text = str(value).replace("!", ", ").replace("|", ", ").replace("^", ", ")
    text = " ".join(text.split())
    return text.strip(", ")