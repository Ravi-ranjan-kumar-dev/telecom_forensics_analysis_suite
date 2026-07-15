from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator

import duckdb
import pandas as pd


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class DuckDBStoreInfo:
    database_path: str
    table_count: int
    tables: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def validate_identifier(
    name: str,
    *,
    kind: str = "identifier",
) -> str:
    """Validate table/column/index names before using in SQL.

    Values such as file paths, phone numbers, or user input should never be
    passed here directly. This is only for internal table/column names.
    """

    value = str(name).strip()

    if not _IDENTIFIER_RE.match(value):
        raise ValueError(
            f"Invalid {kind}: {name!r}. "
            "Use letters, numbers and underscore only, "
            "and do not start with a number."
        )

    return value


def quote_identifier(name: str) -> str:
    value = validate_identifier(name)
    return f'"{value}"'


def ensure_database_folder(
    database_path: str | Path,
) -> Path:
    path = Path(database_path).expanduser().resolve()
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    return path


def connect_duckdb(
    database_path: str | Path,
    *,
    read_only: bool = False,
) -> duckdb.DuckDBPyConnection:
    path = ensure_database_folder(database_path)
    return duckdb.connect(
        str(path),
        read_only=read_only,
    )


@contextmanager
def duckdb_connection(
    database_path: str | Path,
    *,
    read_only: bool = False,
) -> Iterator[duckdb.DuckDBPyConnection]:
    connection = connect_duckdb(
        database_path,
        read_only=read_only,
    )

    try:
        yield connection
    finally:
        connection.close()


class DuckDBStore:
    """Small common wrapper around DuckDB.

    This keeps database access consistent across:
    - Multiple CDR
    - Tower CDR
    - Tower GPRS
    - Tower IPDR
    - Multiple IPDR
    """

    def __init__(
        self,
        database_path: str | Path,
    ) -> None:
        self.database_path = ensure_database_folder(database_path)

    def execute(
        self,
        sql: str,
        parameters: Iterable | None = None,
    ) -> None:
        with duckdb_connection(self.database_path) as connection:
            if parameters is None:
                connection.execute(sql)
            else:
                connection.execute(sql, parameters)

    def query_df(
        self,
        sql: str,
        parameters: Iterable | None = None,
    ) -> pd.DataFrame:
        with duckdb_connection(self.database_path, read_only=False) as connection:
            if parameters is None:
                return connection.execute(sql).fetchdf()

            return connection.execute(sql, parameters).fetchdf()

    def table_exists(
        self,
        table_name: str,
    ) -> bool:
        table = validate_identifier(
            table_name,
            kind="table name",
        )

        sql = """
            SELECT COUNT(*) AS count
            FROM information_schema.tables
            WHERE table_name = ?
        """

        result = self.query_df(
            sql,
            [table],
        )

        if result.empty:
            return False

        return int(result.loc[0, "count"]) > 0

    def list_tables(self) -> list[str]:
        sql = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
            ORDER BY table_name
        """

        result = self.query_df(sql)

        if result.empty:
            return []

        return [
            str(value)
            for value in result["table_name"].tolist()
        ]

    def row_count(
        self,
        table_name: str,
    ) -> int:
        table = quote_identifier(table_name)

        result = self.query_df(
            f"SELECT COUNT(*) AS count FROM {table}"
        )

        if result.empty:
            return 0

        return int(result.loc[0, "count"])

    def drop_table(
        self,
        table_name: str,
    ) -> None:
        table = quote_identifier(table_name)

        self.execute(
            f"DROP TABLE IF EXISTS {table}"
        )

    def write_dataframe(
        self,
        dataframe: pd.DataFrame,
        table_name: str,
        *,
        mode: str = "append",
    ) -> int:
        """Write a DataFrame to DuckDB.

        mode:
            append  = create table if missing, then append rows
            replace = drop table first, then create from DataFrame
        """

        if dataframe is None or dataframe.empty:
            return 0

        table = quote_identifier(table_name)

        if mode not in {"append", "replace"}:
            raise ValueError(
                "mode must be 'append' or 'replace'"
            )

        with duckdb_connection(self.database_path) as connection:
            connection.register(
                "_incoming_dataframe",
                dataframe,
            )

            if mode == "replace":
                connection.execute(
                    f"DROP TABLE IF EXISTS {table}"
                )
                connection.execute(
                    f"CREATE TABLE {table} AS "
                    "SELECT * FROM _incoming_dataframe"
                )

            else:
                exists = self.table_exists(table_name)

                if not exists:
                    connection.execute(
                        f"CREATE TABLE {table} AS "
                        "SELECT * FROM _incoming_dataframe"
                    )
                else:
                    connection.execute(
                        f"INSERT INTO {table} "
                        "SELECT * FROM _incoming_dataframe"
                    )

            connection.unregister(
                "_incoming_dataframe"
            )

        return len(dataframe)

    def create_index(
        self,
        table_name: str,
        columns: Iterable[str],
        *,
        index_name: str | None = None,
    ) -> None:
        table = validate_identifier(
            table_name,
            kind="table name",
        )

        column_list = [
            validate_identifier(
                column,
                kind="column name",
            )
            for column in columns
        ]

        if not column_list:
            return

        if index_name is None:
            index_name = (
                "idx_"
                + table
                + "_"
                + "_".join(column_list)
            )

        index = validate_identifier(
            index_name,
            kind="index name",
        )

        quoted_table = quote_identifier(table)
        quoted_columns = ", ".join(
            quote_identifier(column)
            for column in column_list
        )
        quoted_index = quote_identifier(index)

        try:
            self.execute(
                f"CREATE INDEX {quoted_index} "
                f"ON {quoted_table} ({quoted_columns})"
            )
        except Exception as error:
            message = str(error).lower()

            if "already exists" in message:
                return

            raise

    def export_table_to_csv(
        self,
        table_name: str,
        output_path: str | Path,
    ) -> Path:
        table = quote_identifier(table_name)
        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        safe_output = str(output).replace("'", "''")

        self.execute(
            f"COPY {table} TO '{safe_output}' "
            "(HEADER, DELIMITER ',')"
        )

        return output

    def info(self) -> DuckDBStoreInfo:
        tables = self.list_tables()

        return DuckDBStoreInfo(
            database_path=str(self.database_path),
            table_count=len(tables),
            tables=tables,
        )


def print_duckdb_store_info(
    store: DuckDBStore,
) -> None:
    info = store.info()

    print("\nDUCKDB STORE INFO")
    print("-" * 70)
    print(f"Database path : {info.database_path}")
    print(f"Table count   : {info.table_count}")

    if not info.tables:
        print("Tables        : none")
        return

    print("Tables:")
    for table in info.tables:
        try:
            count = store.row_count(table)
        except Exception:
            count = -1

        print(f"  - {table}: {count:,} row(s)")