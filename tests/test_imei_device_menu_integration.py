
from __future__ import annotations

import pandas as pd

from modules.controllers import (
    app_controller,
    imei_device_controller,
)
from modules.controllers import (
    lookup_controller,
)


def test_workspace_menu_has_final_contract(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": "0",
    )

    choice = app_controller._workspace_menu(
        {
            "case_id": "CASE-001",
            "case_name": "Menu Test",
        },
        direct_mode=True,
    )

    output = capsys.readouterr().out

    assert choice == "0"

    expected_options = (
        "1. CDR Analysis",
        "2. Tower Dump Analysis",
        "3. IPDR Analysis",
        "4. IMEI / Device Analysis",
        "5. Lookup Services",
        "6. View Case Details",
        "7. View Case Reports",
        "0. Close Case",
    )

    for option in expected_options:
        assert option in output


def test_imei_handler_uses_safe_import(
    monkeypatch,
):
    calls = []

    def fake_handler(
        case,
    ):
        calls.append(
            case
        )

    def fake_safe_import(
        module_path,
        function_name,
    ):
        assert module_path == (
            "modules.controllers."
            "imei_device_controller"
        )

        assert function_name == (
            "handle_imei_device_workspace"
        )

        return fake_handler

    monkeypatch.setattr(
        app_controller,
        "safe_import",
        fake_safe_import,
    )

    case = {
        "case_id": "CASE-001",
    }

    app_controller.handle_imei_device_analysis(
        case
    )

    assert calls == [
        case
    ]


def test_choice_four_routes_to_imei_workspace(
    monkeypatch,
):
    choices = iter(
        [
            "4",
            "0",
        ]
    )

    monkeypatch.setattr(
        app_controller,
        "_workspace_menu",
        lambda case, direct_mode=False: next(
            choices
        ),
    )

    calls = []

    monkeypatch.setattr(
        app_controller,
        "handle_imei_device_analysis",
        lambda case: calls.append(
            (
                "imei",
                case[
                    "case_id"
                ],
            )
        ),
    )

    monkeypatch.setattr(
        app_controller,
        "log_case_event",
        lambda *args, **kwargs: None,
    )

    app_controller.case_workspace(
        {
            "case_id": "CASE-001",
            "case_name": "Routing Test",
        },
        direct_mode=True,
    )

    assert calls == [
        (
            "imei",
            "CASE-001",
        )
    ]


def test_shifted_workspace_options_are_routed(
    monkeypatch,
):
    choices = iter(
        [
            "5",
            "6",
            "7",
            "0",
        ]
    )

    monkeypatch.setattr(
        app_controller,
        "_workspace_menu",
        lambda case, direct_mode=False: next(
            choices
        ),
    )

    calls = []

    monkeypatch.setattr(
        lookup_controller,
        "run_lookup_services",
        lambda case: calls.append(
            "lookup"
        ),
    )

    monkeypatch.setattr(
        app_controller,
        "print_case_details",
        lambda case: calls.append(
            "details"
        ),
    )

    monkeypatch.setattr(
        app_controller,
        "show_case_reports",
        lambda case_id: calls.append(
            "reports"
        ),
    )

    monkeypatch.setattr(
        app_controller,
        "log_case_event",
        lambda *args, **kwargs: None,
    )

    app_controller.case_workspace(
        {
            "case_id": "CASE-001",
            "case_name": "Routing Test",
        }
    )

    assert calls == [
        "lookup",
        "details",
        "reports",
    ]


def test_source_summary_prints_real_values(
    capsys,
):
    imei_device_controller._print_source_summary(
        {
            "requested_imei": (
                "354079831251890"
            ),
            "overall_status": "FOUND",
            "source_summary": pd.DataFrame(
                [
                    {
                        "Evidence Source": "CDR",
                        "Status": "FOUND",
                        "Matched Count": 3528,
                        "Evidence Unit": (
                            "CDR records"
                        ),
                    },
                    {
                        "Evidence Source": "IPDR",
                        "Status": "NO_INPUT",
                        "Matched Count": 0,
                        "Evidence Unit": (
                            "IPDR records"
                        ),
                    },
                    {
                        "Evidence Source": "GPRS",
                        "Status": "NO_INPUT",
                        "Matched Count": 0,
                        "Evidence Unit": (
                            "GPRS sessions"
                        ),
                    },
                ]
            ),
        }
    )

    output = capsys.readouterr().out

    assert (
        "CDR    | FOUND"
        in output
    )

    assert (
        "3528"
        in output
    )

    assert (
        "CDR records"
        in output
    )

    assert (
        "IPDR records"
        in output
    )

    assert (
        "GPRS sessions"
        in output
    )
