"""GUI worker helper: request in-memory GUI analysis when supported."""
from __future__ import annotations
import inspect

def supports_gui_only(function) -> bool:
    try:
        params = inspect.signature(function).parameters
    except (TypeError, ValueError):
        return False
    return (
        "gui_only" in params
        or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    )
