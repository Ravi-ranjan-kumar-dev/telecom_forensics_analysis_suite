"""Spot SQL result tables for Tower IPDR complete analysis.

Only SQL statements from the controller are moved here. The caller
supplies its existing read_sql and SQL expression builders; no database
connection or filesystem action occurs in this module.
"""

from __future__ import annotations


def build_tower_ipdr_spot_tables(
    read_sql,
    spot_id,
    spot_name,
    spot_folder,
    subscriber,
    searched_cell,
    source_relative_path,
    event_ts,
    imei,
    imsi,
):
    """Return four Spot SQL result tables in their original order."""
    spot_summary = read_sql(f'\n            SELECT\n                {spot_id} AS spot_id,\n                {spot_name} AS spot_name,\n                {spot_folder} AS spot_folder,\n                COUNT(*) AS event_count,\n                COUNT(\n                    DISTINCT {subscriber}\n                ) AS subscriber_count,\n                COUNT(\n                    DISTINCT {searched_cell}\n                ) AS cell_count,\n                COUNT(\n                    DISTINCT\n                    {source_relative_path}\n                ) AS source_file_count,\n                MIN({event_ts}) AS first_seen,\n                MAX({event_ts}) AS last_seen\n            FROM tower_ipdr_events\n            WHERE {spot_id} IS NOT NULL\n            GROUP BY 1, 2, 3\n            ORDER BY 1\n            ')
    repeated_spot_cells = read_sql(f"\n            SELECT\n                {searched_cell}\n                    AS searched_cell_id,\n                COUNT(\n                    DISTINCT {spot_id}\n                ) AS spot_count,\n                STRING_AGG(\n                    DISTINCT CAST(\n                        {spot_id} AS VARCHAR\n                    ),\n                    ', '\n                    ORDER BY CAST(\n                        {spot_id} AS VARCHAR\n                    )\n                ) AS spots,\n                COUNT(*) AS event_count,\n                COUNT(\n                    DISTINCT {subscriber}\n                ) AS subscriber_count,\n                MIN({event_ts}) AS first_seen,\n                MAX({event_ts}) AS last_seen\n            FROM tower_ipdr_events\n            WHERE\n                {searched_cell} IS NOT NULL\n                AND {spot_id} IS NOT NULL\n            GROUP BY 1\n            HAVING\n                COUNT(\n                    DISTINCT {spot_id}\n                ) >= 2\n            ORDER BY\n                spot_count DESC,\n                event_count DESC\n            ")
    multi_spot_subscribers = read_sql(f"\n            SELECT\n                {subscriber}\n                    AS subscriber_number,\n                COUNT(*) AS event_count,\n                COUNT(\n                    DISTINCT {spot_id}\n                ) AS spots_seen,\n                STRING_AGG(\n                    DISTINCT CAST(\n                        {spot_id} AS VARCHAR\n                    ),\n                    ', '\n                    ORDER BY CAST(\n                        {spot_id} AS VARCHAR\n                    )\n                ) AS spots,\n                COUNT(\n                    DISTINCT {searched_cell}\n                ) AS cells_seen,\n                COUNT(\n                    DISTINCT {imei}\n                ) AS imei_count,\n                COUNT(\n                    DISTINCT {imsi}\n                ) AS imsi_count,\n                MIN({event_ts}) AS first_seen,\n                MAX({event_ts}) AS last_seen\n            FROM tower_ipdr_events\n            WHERE\n                {subscriber} IS NOT NULL\n                AND {spot_id} IS NOT NULL\n            GROUP BY 1\n            HAVING\n                COUNT(\n                    DISTINCT {spot_id}\n                ) >= 2\n            ORDER BY\n                spots_seen DESC,\n                cells_seen DESC,\n                event_count DESC\n            LIMIT 500\n            ")
    spot_exclusive_subscribers = read_sql(f'\n            SELECT\n                {subscriber}\n                    AS subscriber_number,\n                COUNT(*) AS event_count,\n                MIN({spot_id}) AS spot_id,\n                COUNT(\n                    DISTINCT {searched_cell}\n                ) AS cells_seen,\n                COUNT(\n                    DISTINCT {imei}\n                ) AS imei_count,\n                COUNT(\n                    DISTINCT {imsi}\n                ) AS imsi_count,\n                MIN({event_ts}) AS first_seen,\n                MAX({event_ts}) AS last_seen\n            FROM tower_ipdr_events\n            WHERE\n                {subscriber} IS NOT NULL\n                AND {spot_id} IS NOT NULL\n            GROUP BY 1\n            HAVING\n                COUNT(\n                    DISTINCT {spot_id}\n                ) = 1\n            ORDER BY\n                event_count DESC\n            LIMIT 500\n            ')

    return (
        spot_summary,
        repeated_spot_cells,
        multi_spot_subscribers,
        spot_exclusive_subscribers,
    )
