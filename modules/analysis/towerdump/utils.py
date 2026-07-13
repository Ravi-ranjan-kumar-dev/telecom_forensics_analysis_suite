from __future__ import annotations

from typing import Iterable

import pandas as pd


def ensure_dataframe(df: pd.DataFrame | None) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    return df.copy()


def text_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series([""] * len(df), index=df.index, dtype="object")
    return (
        df[column]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace({"nan": "", "None": "", "<NA>": ""})
    )


def datetime_series(df: pd.DataFrame) -> pd.Series:
    if "call_datetime" not in df.columns:
        return pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    return pd.to_datetime(df["call_datetime"], errors="coerce")


def numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series([0] * len(df), index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce").fillna(0)


def valid_rows(df: pd.DataFrame, column: str) -> pd.DataFrame:
    values = text_series(df, column)
    return df.loc[values.ne("")].copy()


def safe_nunique(df: pd.DataFrame, column: str) -> int:
    return int(text_series(df, column).replace("", pd.NA).nunique(dropna=True))


def count_types(group: pd.DataFrame, values: Iterable[str]) -> int:
    call_types = text_series(group, "call_type")
    return int(call_types.isin(set(values)).sum())


def join_unique(series: pd.Series, limit: int = 50) -> str:
    values = sorted(
        {
            str(value).strip()
            for value in series.dropna()
            if str(value).strip() not in {"", "nan", "None", "<NA>"}
        }
    )
    if len(values) > limit:
        return ", ".join(values[:limit]) + f" ... (+{len(values) - limit})"
    return ", ".join(values)
