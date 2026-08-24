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

                else:
                    from modules.controllers.app_controller import (
                        get_direct_analysis_workspace,
                    )
                    from modules.controllers.lookup_controller import (
                        run_cgi_lookup,
                        run_sdr_lookup,
                    )

                    case = get_direct_analysis_workspace()

                    if self.operation == "sdr":
                        result = run_sdr_lookup(case, self.value)
                    else:
                        result = run_cgi_lookup(case, self.value)

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
