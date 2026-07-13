"""Non-destructive duplicate indicators for forensic telecom records."""

from __future__ import annotations

import hashlib
from typing import Iterable

import pandas as pd


DEFAULT_EVENT_SIGNATURE = (
    "datetime",
    "a_party",
    "b_party",
    "call_type",
    "call_duration",
    "imei",
    "imsi",
    "first_cell_id",
    "last_cell_id",
)


def flag_potential_duplicates(
    dataframe: pd.DataFrame,
    *,
    signature_columns: Iterable[str] = DEFAULT_EVENT_SIGNATURE,
) -> pd.DataFrame:
    """Retain every row and flag identical analytical signatures.

    Identical displayed attributes do not prove that source records are
    duplicates. The function therefore never deletes rows.

    Pandas DataFrame.attrs may contain another DataFrame (for example the
    rejected-row ledger). Pandas internally compares attrs during astype/concat,
    which can raise "truth value of a DataFrame is ambiguous". Internal working
    copies therefore intentionally use empty attrs. Callers may reattach
    provenance metadata after duplicate flags are calculated.
    """

    if not isinstance(dataframe, pd.DataFrame):
        return pd.DataFrame()

    # IMPORTANT: DataFrame.copy() also copies attrs. Clear them before any
    # pandas operation that may internally concat/compare DataFrames.
    data = dataframe.copy()
    data.attrs = {}

    if data.empty:
        return data

    columns = [
        column
        for column in signature_columns
        if column in data.columns
    ]

    if not columns:
        data["is_potential_duplicate"] = False
        data["potential_duplicate_count"] = 1
        data["potential_duplicate_group"] = ""
        data["potential_duplicate_signature_columns"] = ""
        return data

    signature_frame = data.loc[:, columns].copy()
    signature_frame.attrs = {}

    for column in columns:
        if pd.api.types.is_datetime64_any_dtype(
            signature_frame[column]
        ):
            signature_frame[column] = (
                signature_frame[column]
                .astype("string")
                .fillna("")
            )
        else:
            signature_frame[column] = (
                signature_frame[column]
                .fillna("")
                .astype(str)
                .str.strip()
            )

    signature_text = signature_frame.astype(str).agg(
        "\x1f".join,
        axis=1,
    )

    hashes = signature_text.map(
        lambda value: hashlib.sha256(
            value.encode("utf-8")
        ).hexdigest()
    )

    counts = hashes.map(hashes.value_counts())
    duplicate_mask = counts.gt(1)

    data["is_potential_duplicate"] = duplicate_mask
    data["potential_duplicate_count"] = counts.astype("Int64")
    data["potential_duplicate_group"] = hashes.where(
        duplicate_mask,
        "",
    ).map(
        lambda value: f"DUP-{value[:16]}" if value else ""
    )
    data["potential_duplicate_signature_columns"] = ", ".join(
        columns
    )

    return data
