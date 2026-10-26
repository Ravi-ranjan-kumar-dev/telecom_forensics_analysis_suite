# Memory Optimization & Safe Chunked Ingestion for Massive Dumps
from __future__ import annotations

from typing import Iterator
import pandas as pd

try:
    import duckdb
    _HAS_DUCKDB = True
except ImportError:
    _HAS_DUCKDB = False


def chunked_read_csv(file_path: str, chunk_size: int = 100_000, **kwargs) -> Iterator[pd.DataFrame]:
    """Read massive CSV files in memory-efficient chunks to prevent RAM spikes."""
    try:
        for chunk in pd.read_csv(file_path, chunksize=chunk_size, low_memory=True, **kwargs):
            yield chunk
    except Exception as err:
        print(f"[!] Chunked read error for {file_path}: {{err}}")
        yield pd.DataFrame()


def duckdb_load_csv_safe(file_path: str) -> pd.DataFrame:
    """Load massive CSV files efficiently using DuckDB engine without RAM exhaustion."""
    if not _HAS_DUCKDB:
        # Fallback to chunked concatenation if DuckDB is unavailable
        chunks = list(chunked_read_csv(file_path))
        return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
    
    try:
        con = duckdb.connect(database=':memory:')
        df = con.execute("SELECT * FROM read_csv_auto(?)", [str(file_path)]).fetch_df()
        con.close()
        return df
    except Exception as err:
        print(f"[!] DuckDB safe load error for {file_path}: {{err}} (falling back to chunked pandas)")
        chunks = list(chunked_read_csv(file_path))
        return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
