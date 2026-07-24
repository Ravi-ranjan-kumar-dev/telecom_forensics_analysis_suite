from __future__ import annotations

from typing import Iterable

import pandas as pd
from modules.loader.identity import normalize_msisdn

from modules.database.duckdb_core import query_dataframe


def normalize_mobile_number(value) -> str:
    """Normalize SDR lookup values using the canonical MSISDN rule."""

    return normalize_msisdn(value) or ""


def _chunks(values: list[str], size: int = 1000):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _empty_lookup_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "lookup_mobile",
            "subscriber_name",
            "father_name",
            "subscriber_address",
            "id_type",
            "id_number",
            "operator",
            "circle",
            "activation_date",
            "caf_number",
            "source_file",
            "sdr_found",
        ]
    )


def _table_exists(table_name: str) -> bool:
    try:
        result = query_dataframe(
            """
            SELECT COUNT(*) AS total
            FROM information_schema.tables
            WHERE table_name = ?
            """,
            [table_name],
        )

        return result is not None and not result.empty and int(result.iloc[0]["total"]) > 0

    except Exception:
        return False


def _lookup_from_large_table(numbers: list[str]) -> pd.DataFrame:
    if not numbers or not _table_exists("sdr_subscribers_large"):
        return _empty_lookup_frame()

    frames = []

    for batch in _chunks(numbers):
        placeholders = ",".join(["?"] * len(batch))

        result = query_dataframe(
            f"""
            WITH ranked AS (
                SELECT
                    mobile_number AS lookup_mobile,
                    subscriber_name,
                    father_name,
                    address AS subscriber_address,
                    id_type,
                    id_number,
                    replace(operator, ' - Copy', '') AS operator,
                    CASE
                        WHEN circle IS NULL THEN NULL
                        WHEN circle = chr(0) THEN NULL
                        WHEN trim(circle) = '' THEN NULL
                        WHEN upper(trim(circle)) IN ('NONE', 'NULL') THEN NULL
                        ELSE circle
                    END AS circle,
                    activation_date,
                    caf_number,
                    source_file,
                    ROW_NUMBER() OVER (
                        PARTITION BY mobile_number
                        ORDER BY
                            TRY_CAST(activation_date AS DATE) DESC NULLS LAST,
                            TRY_CAST(caf_number AS BIGINT) DESC NULLS LAST
                    ) AS rn
                FROM sdr_subscribers_large
                WHERE mobile_number IN ({placeholders})
            )
            SELECT
                lookup_mobile,
                subscriber_name,
                father_name,
                subscriber_address,
                id_type,
                id_number,
                operator,
                circle,
                activation_date,
                caf_number,
                source_file,
                'Yes' AS sdr_found
            FROM ranked
            WHERE rn = 1
            """,
            batch,
        )

        if result is not None and not result.empty:
            frames.append(result)

    if not frames:
        return _empty_lookup_frame()

    return pd.concat(frames, ignore_index=True)


def _lookup_from_primary_table(numbers: list[str]) -> pd.DataFrame:
    if not numbers:
        return _empty_lookup_frame()

    frames = []

    for batch in _chunks(numbers):
        placeholders = ",".join(["?"] * len(batch))

        result = query_dataframe(
            f"""
            SELECT
                mobile_number AS lookup_mobile,
                subscriber_name,
                father_name,
                address AS subscriber_address,
                id_type,
                id_number,
                operator,
                circle,
                activation_date,
                caf_number,
                source_file,
                'Yes' AS sdr_found
            FROM sdr_subscribers
            WHERE mobile_number IN ({placeholders})
            """,
            batch,
        )

        if result is not None and not result.empty:
            frames.append(result)

    if not frames:
        return _empty_lookup_frame()

    return pd.concat(frames, ignore_index=True)


def lookup_sdr_subscribers(
    numbers: Iterable,
) -> pd.DataFrame:
    """
    Lookup SDR profiles with new delta records taking priority.

    The small primary table stores verified updates and corrections.
    The historical large table is used only for numbers not found in
    the primary table.
    """

    normalized_numbers = sorted(
        {
            normalize_mobile_number(
                number
            )
            for number in numbers
            if normalize_mobile_number(
                number
            )
        }
    )

    if not normalized_numbers:
        return _empty_lookup_frame()

    primary_result = (
        _lookup_from_primary_table(
            normalized_numbers
        )
    )

    primary_numbers: set[str] = set()

    if (
        primary_result is not None
        and not primary_result.empty
    ):
        primary_numbers = set(
            primary_result[
                "lookup_mobile"
            ].astype(
                str
            )
        )

    missing_numbers = [
        number
        for number in normalized_numbers
        if number not in primary_numbers
    ]

    large_result = (
        _lookup_from_large_table(
            missing_numbers
        )
    )

    frames = []

    if (
        primary_result is not None
        and not primary_result.empty
    ):
        frames.append(
            primary_result
        )

    if (
        large_result is not None
        and not large_result.empty
    ):
        frames.append(
            large_result
        )

    if not frames:
        output = pd.DataFrame(
            {
                "lookup_mobile": (
                    normalized_numbers
                )
            }
        )
        output["sdr_found"] = "No"
        return output

    return pd.concat(
        frames,
        ignore_index=True,
    )




def enrich_dataframe_with_sdr(
    dataframe: pd.DataFrame,
    number_column: str = "b_party",
    prefix: str = "other_party_",
) -> pd.DataFrame:
    if dataframe is None or not isinstance(dataframe, pd.DataFrame):
        return dataframe

    if dataframe.empty or number_column not in dataframe.columns:
        return dataframe

    output = dataframe.copy()
    output[f"{prefix}lookup_mobile"] = output[number_column].apply(normalize_mobile_number)

    lookup = lookup_sdr_subscribers(output[f"{prefix}lookup_mobile"].dropna().unique())

    if lookup.empty:
        output[f"{prefix}sdr_found"] = "No"
        return output

    renamed = lookup.rename(
        columns={
            "lookup_mobile": f"{prefix}lookup_mobile",
            "subscriber_name": f"{prefix}subscriber_name",
            "father_name": f"{prefix}father_name",
            "subscriber_address": f"{prefix}subscriber_address",
            "id_type": f"{prefix}id_type",
            "id_number": f"{prefix}id_number",
            "operator": f"{prefix}operator",
            "circle": f"{prefix}circle",
            "activation_date": f"{prefix}activation_date",
            "caf_number": f"{prefix}caf_number",
            "source_file": f"{prefix}source_file",
            "sdr_found": f"{prefix}sdr_found",
        }
    )

    output = output.merge(
        renamed,
        on=f"{prefix}lookup_mobile",
        how="left",
    )

    output[f"{prefix}sdr_found"] = output[f"{prefix}sdr_found"].fillna("No")

    return output
