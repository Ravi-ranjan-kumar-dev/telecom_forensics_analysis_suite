from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

import duckdb
import pandas as pd

from .db_paths import master_duckdb_path


@contextmanager
def duckdb_connection(database_path: Optional[Path] = None) -> Iterator[duckdb.DuckDBPyConnection]:
    db_path = Path(database_path) if database_path else master_duckdb_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = duckdb.connect(str(db_path), read_only=False)
    try:
        yield connection
    finally:
        connection.close()


def execute_sql(sql: str, parameters: Optional[list] = None) -> None:
    with duckdb_connection() as connection:
        if parameters:
            connection.execute(sql, parameters)
        else:
            connection.execute(sql)


def query_dataframe(sql: str, parameters: Optional[list] = None) -> pd.DataFrame:
    with duckdb_connection() as connection:
        if parameters:
            return connection.execute(sql, parameters).df()
        return connection.execute(sql).df()


def table_exists(table_name: str) -> bool:
    result = query_dataframe(
        """
        SELECT COUNT(*) AS total
        FROM information_schema.tables
        WHERE table_name = ?
        """,
        [table_name],
    )
    return int(result.iloc[0]["total"]) > 0


def table_count(table_name: str) -> int:
    if not table_exists(table_name):
        return 0

    result = query_dataframe(f"SELECT COUNT(*) AS total FROM {table_name}")
    return int(result.iloc[0]["total"])
