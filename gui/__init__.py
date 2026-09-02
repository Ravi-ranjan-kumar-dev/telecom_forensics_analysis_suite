"""Desktop GUI package for the Telecom Forensics Analysis Suite."""

from __future__ import annotations


def main() -> int:
    """Load and start the Qt application only when requested."""

    from gui.app import main as run_application

    return run_application()

__all__ = [
    "main",
]
