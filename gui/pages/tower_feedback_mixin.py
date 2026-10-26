"""Tower Dump run status, progress log, and completed/failed feedback.

Phase 3: original method implementations retained without changes.
Do not import TowerDumpPage here (avoids circular imports).
"""

from __future__ import annotations

from modules.controllers.tower_dump_controller import TOWER_DUMP_SOURCE_TYPES


class TowerFeedbackMixin:
    """Page supplies widgets, report slots, and running-state attributes."""

    def _set_running_state(
        self,
        running: bool,
    ) -> None:
        self._mode_box.setEnabled(
            not running
        )
        self._browse_button.setEnabled(
            not running
        )
        self._spot_list.setEnabled(
            not running
        )
        self._select_all_spots_button.setEnabled(
            not running
        )
        self._clear_spots_button.setEnabled(
            not running
        )
        self._run_button.setEnabled(
            not running
        )
        self._manage_parts_button.setEnabled(
            not running
        )
        self._run_parts_button.setEnabled(
            not running
        )
        self._progress.setVisible(
            running
        )

        if running:
            self._status_label.setText(
                "Analysis is running. Keep this window open."
            )

    def _append_log(
        self,
        message: str,
    ) -> None:
        text = str(
            message
        ).strip()

        if text:
            self._log.appendPlainText(
                text
            )

    def _analysis_completed(
        self,
        payload: object,
    ) -> None:
        result = (
            payload
            if isinstance(
                payload,
                dict,
            )
            else {}
        )
        gui_sheets = result.get("gui_sheets")
        if isinstance(gui_sheets, dict) and gui_sheets:
            self._data_viewer_panel.load_dataframe(gui_sheets)
            if hasattr(self, '_workspace_tabs'):
                self._workspace_tabs.setCurrentIndex(1)
            self._append_log(f"[+] Loaded {len(gui_sheets)} analyzed table(s) into Interactive GUI Viewer.")
        source_type = str(
            result.get(
                "source_type",
                self.selected_mode,
            )
        )

        if source_type not in TOWER_DUMP_SOURCE_TYPES:
            source_type = self.selected_mode

        analysis_mode = str(
            result.get(
                "analysis_mode",
                self._running_analysis_mode,
            )
            or self._running_analysis_mode
        )

        paths = [
            str(
                path
            )
            for path in result.get(
                "report_paths",
                [],
            )
            if str(
                path
            ).strip()
        ]
        self._report_paths_by_source[
            source_type
        ] = paths
        self._open_report_button.setEnabled(
            bool(
                self.report_paths
            )
        )
        self._open_viewer_button.setEnabled(
            bool(
                self.report_paths
            )
        )

        if paths:
            self._status_label.setText(
                (
                    "Part-wise analysis completed. "
                    "The investigator report is ready."
                    if analysis_mode == "partition"
                    else (
                        "Analysis completed. The investigator report "
                        "is ready."
                    )
                )
            )
            self._append_log(
                (
                    "[+] Part-wise analysis completed successfully."
                    if analysis_mode == "partition"
                    else "[+] Analysis completed successfully."
                )
            )

            for report_path in paths:
                self._append_log(
                    f"[+] Report: {report_path}"
                )
        else:
            self._status_label.setText(
                "Analysis completed, but no report path was returned."
            )
            self._append_log(
                "[!] No generated report path was returned."
            )

    def _analysis_failed(
        self,
        message: str,
    ) -> None:
        text = str(
            message
        ).strip()
        self._status_label.setText(
            "Analysis failed. Review the progress log."
        )
        self._append_log(
            f"[-] {text}"
        )

    def _thread_finished(
        self,
    ) -> None:
        self._thread = None
        self._worker = None
        self._running_analysis_mode = ""
        self._set_running_state(
            False
        )
