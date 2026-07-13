from __future__ import annotations

import pandas as pd

from modules.controllers import app_controller
from modules.reporting.single_cdr_excel import _fclc


def test_default_startup_opens_direct_analysis_workspace(monkeypatch):
    monkeypatch.delenv(app_controller.CASE_MANAGEMENT_ENV, raising=False)
    case = {"case_id": "DEV-WORKSPACE", "case_name": "Development Analysis Workspace"}
    observed = {}

    monkeypatch.setattr(app_controller, "_direct_analysis_workspace", lambda: case)

    def fake_workspace(selected_case, *, direct_mode=False):
        observed["case"] = selected_case
        observed["direct_mode"] = direct_mode

    monkeypatch.setattr(app_controller, "case_workspace", fake_workspace)
    app_controller.run_application()

    assert observed == {"case": case, "direct_mode": True}


def test_direct_menu_hides_case_creation_and_active_case(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _prompt: "0")
    choice = app_controller._workspace_menu(
        {"case_id": "DEV-WORKSPACE", "case_name": "Development Analysis Workspace"},
        direct_mode=True,
    )
    output = capsys.readouterr().out

    assert choice == "0"
    assert "1. CDR Analysis" in output
    assert "2. Tower Dump Analysis" in output
    assert "3. IPDR Analysis" in output
    assert "Create New Case" not in output
    assert "ACTIVE CASE" not in output


def test_fclc_handles_dataframe_valued_attrs_without_concat_failure():
    data = pd.DataFrame(
        {
            "datetime": pd.to_datetime(
                ["2025-09-13 18:25:22", "2025-09-13 19:25:22"]
            ),
            "call_type": ["incoming", "outgoing"],
            "call_direction": ["INCOMING", "OUTGOING"],
            "other_party": ["9000000001", "9000000002"],
            "level_code": ["Missing", "Missing"],
            "call_duration": [10, 20],
            "first_cell_id": ["405-51-1", "405-51-2"],
            "tower_address": ["Tower A", "Tower B"],
        }
    )
    data.attrs["rejected_rows"] = pd.DataFrame(
        {"source_row_number": [99], "rejection_reason": ["footer"]}
    )

    result = _fclc(data)

    assert len(result) == 2
    assert result["Description"].tolist() == ["first call", "last call"]
