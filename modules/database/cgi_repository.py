"""Fast and safe CGI lookup and CDR enrichment."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from functools import lru_cache
from typing import Any, Iterable

from .connection import database_connection, get_db_path
from .normalization import digits_only
from .schema import initialize_database

LOGGER = logging.getLogger(__name__)

PUBLIC_COLUMNS = (
    "cgi", "cgi_key", "mcc", "mnc", "lac", "tac", "cell_id",
    "enodeb_id", "local_cell_id", "technology", "site_id", "site_name",
    "cell_name", "latitude", "longitude", "azimuth", "address", "town",
    "block", "district", "state", "circle", "ssa", "pin_code", "operator",
    "vendor", "source_file", "source_sheet", "source_row", "updated_at",
)


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


@lru_cache(maxsize=50000)
def _cached_exact_lookup(db_path: str, cgi_key: str) -> dict[str, Any] | None:
    if not cgi_key:
        return None
    if not Path(db_path).is_file():
        return None
    with database_connection(read_only=True) as conn:
        row = conn.execute(
            f"SELECT {', '.join(PUBLIC_COLUMNS)} FROM cgi_towers WHERE cgi_key = ?",
            (cgi_key,),
        ).fetchone()
        if row is not None:
            return _row_to_dict(row)

        rows = conn.execute(
            f"SELECT {', '.join('t.' + col for col in PUBLIC_COLUMNS)} "
            "FROM cgi_aliases a JOIN cgi_towers t ON t.id=a.tower_id "
            "WHERE a.alias_key=? LIMIT 2",
            (cgi_key,),
        ).fetchall()
        return _row_to_dict(rows[0]) if len(rows) == 1 else None


def clear_lookup_cache() -> None:
    _cached_exact_lookup.cache_clear()


def lookup_cgi(value: Any) -> dict[str, Any] | None:
    """Return an exact CGI match; database failures are not disguised as not-found."""

    key = digits_only(value)
    if not key or not get_db_path().is_file():
        return None
    return _cached_exact_lookup(str(get_db_path()), key)


def get_tower_candidates(value: Any, limit: int = 20) -> list[dict[str, Any]]:
    key = digits_only(value)
    if not key or not get_db_path().is_file():
        return []
    exact = lookup_cgi(key)
    if exact:
        return [exact]
    with database_connection(read_only=True) as conn:
        rows = conn.execute(
            f"SELECT {', '.join(PUBLIC_COLUMNS)} FROM cgi_towers "
            "WHERE cell_id=? ORDER BY updated_at DESC LIMIT ?",
            (key, max(1, min(int(limit), 100))),
        ).fetchall()
    return [dict(row) for row in rows]


def bulk_lookup_cgi(values: Iterable[Any]) -> dict[str, dict[str, Any]]:
    keys = {digits_only(value) for value in values}
    keys.discard("")
    if not keys or not get_db_path().is_file():
        return {}

    results: dict[str, dict[str, Any]] = {}
    key_list = list(keys)
    with database_connection(read_only=True) as conn:
        for start in range(0, len(key_list), 800):
            chunk = key_list[start:start + 800]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"SELECT {', '.join(PUBLIC_COLUMNS)} FROM cgi_towers "
                f"WHERE cgi_key IN ({placeholders})",
                chunk,
            ).fetchall()
            for row in rows:
                item = dict(row)
                results[item["cgi_key"]] = item

        missing = [key for key in key_list if key not in results]
        for start in range(0, len(missing), 800):
            chunk = missing[start:start + 800]
            if not chunk:
                continue
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"SELECT a.alias_key, {', '.join('t.' + col for col in PUBLIC_COLUMNS)} "
                "FROM cgi_aliases a JOIN cgi_towers t ON t.id=a.tower_id "
                f"WHERE a.alias_key IN ({placeholders})",
                chunk,
            ).fetchall()
            seen: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                item = dict(row)
                alias = item.pop("alias_key")
                seen.setdefault(alias, []).append(item)
            for alias, matches in seen.items():
                if len(matches) == 1:
                    results[alias] = matches[0]
    return results


def enrich_cdr_dataframe(df: Any, *, inplace: bool = False) -> Any:
    """Add tower details to first_cell_id/last_cell_id without crashing CDR analysis."""
    try:
        if df is None or not hasattr(df, "columns") or getattr(df, "empty", True):
            return df

        output = df if inplace else df.copy()
        specs = [
            ("first_cell_id", "first"),
            ("last_cell_id", "last"),
        ]
        available = [(column, prefix) for column, prefix in specs if column in output.columns]
        if not available:
            output.attrs["cgi_enrichment"] = {"status": "SKIPPED", "reason": "No cell-ID columns"}
            return output

        all_values: list[Any] = []
        for column, _ in available:
            all_values.extend(output[column].dropna().unique().tolist())
        lookup = bulk_lookup_cgi(all_values)

        field_map = {
            "tower_cgi": "cgi",
            "tower_site_id": "site_id",
            "tower_site_name": "site_name",
            "tower_cell_name": "cell_name",
            "tower_address": "address",
            "tower_latitude": "latitude",
            "tower_longitude": "longitude",
            "tower_district": "district",
            "tower_state": "state",
            "tower_circle": "circle",
            "tower_operator": "operator",
            "tower_technology": "technology",
            "tower_azimuth": "azimuth",
        }

        matched_keys: set[str] = set()
        for column, prefix in available:
            normalized = output[column].map(digits_only)
            for new_suffix, db_field in field_map.items():
                output[f"{prefix}_{new_suffix}"] = normalized.map(
                    lambda key, field=db_field: (lookup.get(key) or {}).get(field)
                )
            matched_keys.update(key for key in normalized if key and key in lookup)

        unique_keys = {digits_only(value) for value in all_values if digits_only(value)}
        output.attrs["cgi_enrichment"] = {
            "status": "COMPLETED",
            "unique_cell_ids": len(unique_keys),
            "matched": len(matched_keys),
            "not_found": max(0, len(unique_keys) - len(matched_keys)),
        }
        return output
    except Exception as exc:
        LOGGER.exception("CGI enrichment failed")
        try:
            df.attrs["cgi_enrichment"] = {
                "status": "FAILED_SAFE",
                "error": f"{type(exc).__name__}: {exc}",
            }
        except Exception:
            pass
        return df


def database_status() -> dict[str, Any]:
    try:
        initialize_database()
        with database_connection(read_only=True) as conn:
            towers = conn.execute("SELECT COUNT(*) FROM cgi_towers").fetchone()[0]
            aliases = conn.execute("SELECT COUNT(*) FROM cgi_aliases").fetchone()[0]
            last_run = conn.execute(
                "SELECT id, completed_at, status, inserted, updated, rejected "
                "FROM cgi_import_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return {
            "status": "READY",
            "database": str(get_db_path()),
            "tower_records": towers,
            "aliases": aliases,
            "last_import": dict(last_run) if last_run else None,
        }
    except Exception as exc:
        return {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
