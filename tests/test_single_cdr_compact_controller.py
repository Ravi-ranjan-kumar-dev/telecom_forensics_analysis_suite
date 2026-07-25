"""Controller tests for the compact Single CDR report."""

from modules.controllers import app_controller
from modules.reporting.cdr_compact_excel import (
    generate_single_cdr_compact_report,
)
from modules.reporting.single_cdr_excel import (
    generate_single_cdr_report,
)


def test_reporting_functions_select_compact_renderer(
    monkeypatch,
):
    """The controller must select the compact investigator report."""

    imports = []

    def fake_safe_import(
        module_path: str,
        function_name: str,
    ):
        imports.append(
            (
                module_path,
                function_name,
            )
        )

        return (
            module_path,
            function_name,
        )

    monkeypatch.setattr(
        app_controller,
        "safe_import",
        fake_safe_import,
    )

    reporting = app_controller._reporting_functions()

    assert reporting["single_excel"] == (
        "modules.reporting.cdr_compact_excel",
        "generate_single_cdr_compact_report",
    )

    assert (
        "modules.reporting",
        "generate_single_cdr_report",
    ) not in imports


def test_detailed_renderer_remains_available():
    """The detailed renderer remains available for a future annex."""

    assert callable(
        generate_single_cdr_compact_report
    )

    assert callable(
        generate_single_cdr_report
    )

    assert (
        generate_single_cdr_compact_report
        is not generate_single_cdr_report
    )
