"""Core SQL result tables for Tower IPDR complete analysis.

Only SQL statements from the controller are moved here. The caller
supplies its existing read_sql and SQL expression builders; no database
connection or filesystem action occurs in this module.
"""

from __future__ import annotations


def build_tower_ipdr_core_tables(
    read_sql,
    count_distinct,
    event_ts,
    searched_cell,
    subscriber,
    imei,
    imsi,
    spot_id,
):
    """Return the original six result tables in their original order."""
    summary = read_sql(f"\n            SELECT 'Total Events' AS metric, CAST(COUNT(*) AS VARCHAR) AS value FROM tower_ipdr_events\n            UNION ALL SELECT 'Unique Subscribers', CAST({count_distinct('subscriber_number')} AS VARCHAR) FROM tower_ipdr_events\n            UNION ALL SELECT 'Unique IMEI', CAST({count_distinct('imei')} AS VARCHAR) FROM tower_ipdr_events\n            UNION ALL SELECT 'Unique IMSI', CAST({count_distinct('imsi')} AS VARCHAR) FROM tower_ipdr_events\n            UNION ALL SELECT 'Unique Searched Cells', CAST({count_distinct('searched_cell_id')} AS VARCHAR) FROM tower_ipdr_events\n            UNION ALL SELECT 'Unique Source Files', CAST({count_distinct('source_file')} AS VARCHAR) FROM tower_ipdr_events\n            UNION ALL SELECT 'First Event Time', CAST(MIN({event_ts}) AS VARCHAR) FROM tower_ipdr_events\n            UNION ALL SELECT 'Last Event Time', CAST(MAX({event_ts}) AS VARCHAR) FROM tower_ipdr_events\n            ")
    cell_summary = read_sql(f'\n            SELECT\n                {searched_cell} AS searched_cell_id,\n                COUNT(*) AS event_count,\n                COUNT(DISTINCT {subscriber}) AS subscriber_count,\n                COUNT(DISTINCT {imei}) AS imei_count,\n                COUNT(DISTINCT {imsi}) AS imsi_count,\n                MIN({event_ts}) AS first_seen,\n                MAX({event_ts}) AS last_seen\n            FROM tower_ipdr_events\n            WHERE {searched_cell} IS NOT NULL\n            GROUP BY 1\n            ORDER BY event_count DESC\n            LIMIT 500\n            ')
    top_subscribers = read_sql(f"\n            SELECT\n                {subscriber} AS subscriber_number,\n                COUNT(*) AS event_count,\n                COUNT(\n                    DISTINCT {spot_id}\n                ) AS spots_seen,\n                STRING_AGG(\n                    DISTINCT CAST(\n                        {spot_id} AS VARCHAR\n                    ),\n                    ', '\n                    ORDER BY CAST(\n                        {spot_id} AS VARCHAR\n                    )\n                ) AS spots,\n                COUNT(\n                    DISTINCT {searched_cell}\n                ) AS cells_seen,\n                COUNT(\n                    DISTINCT {imei}\n                ) AS imei_count,\n                COUNT(\n                    DISTINCT {imsi}\n                ) AS imsi_count,\n                MIN({event_ts}) AS first_seen,\n                MAX({event_ts}) AS last_seen\n            FROM tower_ipdr_events\n            WHERE {subscriber} IS NOT NULL\n            GROUP BY 1\n            ORDER BY event_count DESC\n            LIMIT 1000\n            ")
    repeat_presence = top_subscribers.query('event_count >= 2').head(500).copy()
    rare_presence = read_sql(f'\n            SELECT\n                {subscriber} AS subscriber_number,\n                COUNT(*) AS event_count,\n                COUNT(DISTINCT {searched_cell}) AS cells_seen,\n                COUNT(DISTINCT {imei}) AS imei_count,\n                COUNT(DISTINCT {imsi}) AS imsi_count,\n                MIN({event_ts}) AS first_seen,\n                MAX({event_ts}) AS last_seen\n            FROM tower_ipdr_events\n            WHERE {subscriber} IS NOT NULL\n            GROUP BY 1\n            HAVING COUNT(*) <= 2\n            ORDER BY event_count ASC, first_seen ASC\n            LIMIT 500\n            ')
    multi_cell_presence = read_sql(f"\n            SELECT\n                {subscriber} AS subscriber_number,\n                COUNT(*) AS event_count,\n                COUNT(DISTINCT {searched_cell}) AS cells_seen,\n                STRING_AGG(DISTINCT CAST({searched_cell} AS VARCHAR), ', ') AS searched_cells,\n                COUNT(DISTINCT {imei}) AS imei_count,\n                COUNT(DISTINCT {imsi}) AS imsi_count,\n                MIN({event_ts}) AS first_seen,\n                MAX({event_ts}) AS last_seen\n            FROM tower_ipdr_events\n            WHERE {subscriber} IS NOT NULL\n              AND {searched_cell} IS NOT NULL\n            GROUP BY 1\n            HAVING COUNT(DISTINCT {searched_cell}) >= 2\n            ORDER BY cells_seen DESC, event_count DESC\n            LIMIT 500\n            ")

    return (
        summary,
        cell_summary,
        top_subscribers,
        repeat_presence,
        rare_presence,
        multi_cell_presence,
    )
