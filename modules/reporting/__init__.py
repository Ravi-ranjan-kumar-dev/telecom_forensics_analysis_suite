"""Reporting API for the Telecom Forensics Analysis Suite."""

from .analysis_bundle import (
    ANALYSIS_REGISTRY,
    analysis_completion_summary,
    build_single_analysis_bundle,
)
from .console_report import print_single_analysis_report
from .multi_cdr_excel import generate_multi_cdr_report
from .single_cdr_excel import generate_single_cdr_report
from .imei_device_excel import generate_imei_device_report

__all__ = [
    "ANALYSIS_REGISTRY",
    "analysis_completion_summary",
    "build_single_analysis_bundle",
    "print_single_analysis_report",
    "generate_single_cdr_report",
    "generate_multi_cdr_report",
    "generate_imei_device_report",
]

# Tower Dump Excel report export
try:
    from .tower_dump_excel import generate_tower_dump_excel_report
except Exception:
    generate_tower_dump_excel_report = None


from .imei_device_excel import generate_imei_common_report

if "generate_imei_common_report" not in __all__:
    __all__.append(
        "generate_imei_common_report"
    )
