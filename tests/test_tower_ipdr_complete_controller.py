from __future__ import annotations

import inspect

from modules.controllers import (
    tower_ipdr_controller,
)


def test_complete_controller_uses_canonical_renderer():
    source = inspect.getsource(
        tower_ipdr_controller
        ._run_complete_tower_ipdr_analysis
    )

    assert (
        "generate_tower_ipdr_complete_excel_report"
        in source
    )

    assert "pd.ExcelWriter" not in source

    for token in (
        "spot_summary",
        "multi_spot_subscribers",
        "spot_exclusive_subscribers",
        "repeated_spot_cells",
        "priority_review_queue",
        "source_relative_path",
        "methodology_limits",
    ):
        assert token in source


def test_complete_controller_avoids_absolute_source_export():
    source = inspect.getsource(
        tower_ipdr_controller
        ._run_complete_tower_ipdr_analysis
    )

    assert (
        "FROM tower_ipdr_file_summary"
        in source
    )

    assert (
        "source_relative_path"
        in source
    )

    assert (
        '"source_path"'
        not in source
    )
