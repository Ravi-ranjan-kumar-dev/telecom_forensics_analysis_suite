import importlib
import inspect

import pandas as pd


MODULE_NAME = 'modules.reporting.tower_dump_console'
FUNCTION_NAME = 'print_tower_dump_report'


def test_combined_record_count_prefers_loaded_dataframe():
    module = importlib.import_module(
        MODULE_NAME
    )

    helper = getattr(
        module,
        "_tower_combined_record_count",
    )

    result = {
        "df": pd.DataFrame(
            {
                "subscriber_number": [
                    "9000000001",
                    "9000000002",
                    "9000000003",
                ]
            }
        ),
        "metadata": {
            "records_after_deduplication": 0,
            "combined_records": 0,
        },
    }

    assert helper(result) == 3


def test_combined_record_count_uses_metadata_fallback():
    module = importlib.import_module(
        MODULE_NAME
    )

    helper = getattr(
        module,
        "_tower_combined_record_count",
    )

    result = {
        "df": None,
        "metadata": {
            "records_after_deduplication": 125,
        },
    }

    assert helper(result) == 125


def test_combined_record_count_uses_analysis_summary_fallback():
    module = importlib.import_module(
        MODULE_NAME
    )

    helper = getattr(
        module,
        "_tower_combined_record_count",
    )

    result = {
        "df": None,
        "metadata": {},
        "analysis": {
            "results": {
                "tower_dump_summary": {
                    "total_records": 456,
                }
            }
        },
    }

    assert helper(result) == 456


def test_console_report_uses_canonical_count_resolver():
    module = importlib.import_module(
        MODULE_NAME
    )

    printer = getattr(
        module,
        FUNCTION_NAME,
    )

    source = inspect.getsource(
        printer
    )

    assert (
        "_tower_combined_record_count("
        in source
    )
