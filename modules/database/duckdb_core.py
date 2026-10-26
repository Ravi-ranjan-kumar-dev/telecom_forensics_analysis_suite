from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

import duckdb
import pandas as pd

from .db_paths import master_duckdb_path
from .master_access import master_access


@contextmanager
def duckdb_connection(database_path: Optional[Path] = None, *, read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    db_path = Path(database_path) if database_path else master_duckdb_path()
    if read_only and not db_path.is_file():
        raise FileNotFoundError(f'Selected master database does not exist: {db_path}')
    with master_access(db_path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = duckdb.connect(str(db_path), read_only=read_only)
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
    with duckdb_connection(read_only=True) as connection:
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


