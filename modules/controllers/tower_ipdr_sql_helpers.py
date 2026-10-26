"""Pure SQL column-name expression helpers for Tower IPDR complete reports.

These builders do not open a database, inspect evidence, or write reports.
Extracted without changing the four original function bodies.
"""

from __future__ import annotations


def make_tower_ipdr_column_helpers(columns):
    """Return the original has, q, text_column, count_distinct closures."""
    def has(column: str) -> bool:
        return column in columns

    def q(column: str) -> str:
        return '"' + column.replace('"', '""') + '"'

    def text_column(column: str) -> str:
        if has(column):
            return f"NULLIF(TRIM(CAST({q(column)} AS VARCHAR)), '')"
        return "NULL"

    def count_distinct(column: str) -> str:
        return f"COUNT(DISTINCT {text_column(column)})" if has(column) else "0"

    return has, q, text_column, count_distinct
