"""Shared Excel value sanitization for all report renderers.

The helper preserves forensic identifiers as literal text and prevents Excel
from treating untrusted source values as formulas when a workbook is opened.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE


_FORMULA_PREFIXES = ("=", "+", "-", "@")
_LEADING_FORMULA_WHITESPACE = " \t\r\n"


def excel_safe_value(value: Any) -> Any:
    """Return an OpenPyXL-compatible value safe for literal Excel display."""
    if value is None:
        return ""

    try:
        missing = pd.isna(value)
        if isinstance(missing, bool) and missing:
            return ""
    except (TypeError, ValueError):
        pass

    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()

    if isinstance(value, datetime):
        # Excel cannot store timezone-aware datetime objects. Preserve the
        # explicit offset as ISO text rather than silently dropping timezone.
        return value.isoformat() if value.tzinfo is not None else value
    if isinstance(value, date):
        return value

    if hasattr(value, "item"):
        try:
            value = value.item()
        except (TypeError, ValueError, AttributeError):
            pass

    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    elif isinstance(value, (list, tuple, set)):
        value = ", ".join(str(item) for item in value)
    elif isinstance(value, dict):
        value = "; ".join(f"{key}={item}" for key, item in value.items())

    if isinstance(value, str):
        value = ILLEGAL_CHARACTERS_RE.sub("", value)
        probe = value.lstrip(_LEADING_FORMULA_WHITESPACE)
        if probe.startswith(_FORMULA_PREFIXES):
            return "'" + value

    return value
