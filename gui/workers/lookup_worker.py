"""Background lookup and master-data import worker."""

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
    ) -> None:
        super().__init__()

        normalized_operation = str(operation).strip().casefold()

        if normalized_operation not in LOOKUP_OPERATIONS:
            raise ValueError(f"Unsupported lookup operation: {operation}")

        self.operation = normalized_operation
        self.value = str(value).strip()

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
                    from modules.database.master_import_service import (
                        import_master_data_file,
                    )

                    result = import_master_data_file(
                        self.value,
                        create_backup=True,
                    )

                elif self.operation == "import_folder":
                    from modules.database.master_import_service import (
                        import_master_folder,
                    )

                    total_rows = import_master_folder(
                        self.value,
                        import_type="auto",
                    )
                    result = {
                        "status": "SUCCESS",
                        "message": f"Folder import completed. Total rows: {total_rows}",
                        "inserted_rows": total_rows,
                        "source_file": self.value,
                    }

                else:
                    from modules.database.lookup_service import (
                        lookup_sdr_profiles,
                        lookup_cgi_profiles,
                    )

                    if self.operation == "sdr":
                        profiles = lookup_sdr_profiles(self.value)
                        flat_records = []
                        for profile in profiles:
                            if profile.get("found"):
                                rec = profile.get("record", {})
                                rec["__status"] = "FOUND"
                            else:
                                rec = {
                                    "mobile_number": profile.get("entered_number", ""),
                                    "subscriber_name": "",
                                    "father_name": "",
                                    "clean_address": "",
                                    "id_number": "",
                                    "operator_or_source_category": "",
                                    "circle": "",
                                    "activation_date": "",
                                    "source_file": "",
                                    "__status": profile.get("status", "NOT_FOUND"),
                                }
                            flat_records.append(rec)
                        result = {
                            "status": "MATCHED" if any(r["__status"]=="FOUND" for r in flat_records) else "NOT_FOUND",
                            "records": flat_records,
                        }
                    else:  # cgi
                        profiles = lookup_cgi_profiles(self.value)
                        flat_records = []
                        for profile in profiles:
                            if profile.get("found"):
                                rec = profile.get("record", {})
                                rec["__status"] = "FOUND"
                            else:
                                rec = {
                                    "cgi": profile.get("entered_cgi", ""),
                                    "operator": "",
                                    "technology": "",
                                    "circle": "",
                                    "state": "",
                                    "district": "",
                                    "police_station": "",
                                    "address": "",
                                    "town": "",
                                    "landmark": "",
                                    "site_name": "",
                                    "latitude": "",
                                    "longitude": "",
                                    "azimuth": "",
                                    "status": "",
                                    "status_change_date": "",
                                    "mcc_mnc": "",
                                    "lac": "",
                                    "cid": "",
                                    "tac_id": "",
                                    "site_id": "",
                                    "gnb_id": "",
                                    "cell_id": "",
                                    "source_file": "",
                                    "__status": profile.get("status", "NOT_FOUND"),
                                }
                            flat_records.append(rec)
                        result = {
                            "status": "MATCHED" if any(r["__status"]=="FOUND" for r in flat_records) else "NOT_FOUND",
                            "records": flat_records,
                        }

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

        except Exception as error:  # noqa: BLE001 - worker failure boundary.
            output_stream.flush()
            self.failed.emit(f"{type(error).__name__}: {error}")

        finally:
            self.finished.emit()