"""Investigator-facing desktop GUI pages."""

from gui.pages.case_details_page import CaseDetailsPage
from gui.pages.case_reports_page import CaseReportsPage
from gui.pages.cdr_page import CdrPage
from gui.pages.imei_page import ImeiPage
from gui.pages.ipdr_page import IpdrPage
from gui.pages.lookup_page import LookupPage
from gui.pages.tower_dump_page import TowerDumpPage

__all__ = [
    "CaseDetailsPage",
    "CaseReportsPage",
    "CdrPage",
    "ImeiPage",
    "IpdrPage",
    "LookupPage",
    "TowerDumpPage",
]
