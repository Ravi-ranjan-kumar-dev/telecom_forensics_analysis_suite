"""Canonical CDR timestamp helpers.

All CDR analytics must consume the loader-created ``datetime`` column when it
is available.  Presentation columns such as ``call_date`` and ``call_time``
are only a controlled fallback and are always parsed day-first.
"""

from __future__ import annotations

import pandas as pd


def canonical_datetime(df: pd.DataFrame) -> pd.Series:
    """Return one validated timestamp Series aligned to ``df.index``."""

    if not isinstance(df, pd.DataFrame):
        return pd.Series(dtype="datetime64[ns]")

    if "datetime" in df.columns:
        values = df["datetime"]
        if pd.api.types.is_datetime64_any_dtype(values):
            return values.copy()
        try:
            return pd.to_datetime(
                values,
                errors="coerce",
                dayfirst=True,
                format="mixed",
            )
        except (TypeError, ValueError):
            return pd.to_datetime(values, errors="coerce", dayfirst=True)

    if "call_datetime" in df.columns:
        values = df["call_datetime"]
        try:
            return pd.to_datetime(
                values,
                errors="coerce",
                dayfirst=True,
                format="mixed",
            )
        except (TypeError, ValueError):
            return pd.to_datetime(values, errors="coerce", dayfirst=True)

    if "call_date" not in df.columns:
        return pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")

    call_time = (
        df["call_time"]
        if "call_time" in df.columns
        else pd.Series("00:00:00", index=df.index)
    )
    combined = (
        df["call_date"].fillna("").astype(str).str.strip()
        + " "
        + call_time.fillna("").astype(str).str.strip()
    ).str.strip()

    try:
        return pd.to_datetime(
            combined,
            errors="coerce",
            dayfirst=True,
            format="mixed",
        )
    except (TypeError, ValueError):
        return pd.to_datetime(combined, errors="coerce", dayfirst=True)


def with_canonical_datetime(
    df: pd.DataFrame,
    *,
    column: str = "_event_datetime",
) -> pd.DataFrame:
    """Copy ``df`` and attach the canonical timestamp in ``column``."""

    data = df.copy()
    data[column] = canonical_datetime(data)
    return data
