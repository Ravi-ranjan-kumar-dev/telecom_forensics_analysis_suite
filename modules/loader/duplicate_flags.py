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

    # Grouping the complete signature is implemented inside pandas instead of
    # joining and hashing every row in Python.  Large multi-target cases often
    # contain millions of unique events; computing SHA-256 for every unique
    # event added substantial CPU time even though only duplicate groups need
    # a persistent review identifier.
    group_codes = signature_frame.groupby(
        list(
            signature_frame.columns
        ),
        sort=False,
        dropna=False,
        observed=True,
    ).ngroup()

    group_sizes = group_codes.value_counts(
        sort=False
    )
    counts = group_codes.map(
        group_sizes
    ).astype(
        "Int64"
    )
    duplicate_mask = (
        counts.gt(
            1
        )
        .fillna(
            False
        )
        .astype(
            bool
        )
    )

    # Preserve the existing deterministic SHA-256 group label, but calculate
    # it once per actual duplicate signature rather than once per source row.
    duplicate_group_ids: dict[int, str] = {}
    representatives = group_codes.loc[
        duplicate_mask
    ].drop_duplicates()

    for row_index, group_code in representatives.items():
        signature_text = "\x1f".join(
            signature_frame.loc[
                row_index,
                :,
            ].astype(
                str
            )
        )
        digest = hashlib.sha256(
            signature_text.encode(
                "utf-8"
            )
        ).hexdigest()
        duplicate_group_ids[
            int(
                group_code
            )
        ] = f"DUP-{digest[:16]}"

    data["is_potential_duplicate"] = duplicate_mask
    data["potential_duplicate_count"] = counts
    data["potential_duplicate_group"] = (
        group_codes.map(
            duplicate_group_ids
        )
        .where(
            duplicate_mask,
            "",
        )
        .fillna(
            ""
        )
    )
    data["potential_duplicate_signature_columns"] = ", ".join(
        columns
    )

    return data
