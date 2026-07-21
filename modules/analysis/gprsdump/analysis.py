"""Core Airtel GPRS session analyses and CCTV-window partitioning."""

from __future__ import annotations

from typing import Any

import pandas as pd

from modules.analysis.spot_partition_scope import (
    resolve_partition_spot_scope,
)

from modules.analysis.partition_scope import (
    cell_mask,
    loaded_cell_map,
    resolve_sighting_scope,
)

from modules.analysis.gprsdump.uncommon_presence import (
    build_tower_gprs_presence_intelligence,
)


def _clean_text(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .replace({"nan": "", "None": "", "<NA>": ""})
    )


def _joined_unique(series: pd.Series) -> str:
    values = sorted(
        {
            value
            for value in _clean_text(series)
            if value
        }
    )
    return ", ".join(values)


def _metric_table(rows: list[tuple[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["Metric", "Value"])


def _summary(df: pd.DataFrame) -> pd.DataFrame:
    valid_duration = pd.to_numeric(
        df.get("session_duration_seconds"),
        errors="coerce",
    )
    total_volume = pd.to_numeric(
        df.get("total_volume"),
        errors="coerce",
    )

    return _metric_table(
        [
            ("Total Sessions", len(df)),
            (
                "Unique Subscribers",
                _clean_text(df["subscriber_number"]).replace("", pd.NA).nunique(),
            ),
            (
                "Unique IMEI",
                _clean_text(df["imei"]).replace("", pd.NA).nunique(),
            ),
            (
                "Unique IMSI",
                _clean_text(df["imsi"]).replace("", pd.NA).nunique(),
            ),
            (
                "Unique IPv4",
                _clean_text(df["ipv4_address"]).replace("", pd.NA).nunique(),
            ),
            (
                "Unique IPv6",
                _clean_text(df["ipv6_address"]).replace("", pd.NA).nunique(),
            ),
            (
                "Unique CGI",
                _clean_text(df["searched_cell_id"]).replace("", pd.NA).nunique(),
            ),
            (
                "Total Data Volume",
                float(total_volume.fillna(0).sum()),
            ),
            (
                "Average Session Seconds",
                float(valid_duration.dropna().mean())
                if valid_duration.notna().any()
                else 0.0,
            ),
            (
                "Longest Session Seconds",
                float(valid_duration.dropna().max())
                if valid_duration.notna().any()
                else 0.0,
            ),
            (
                "Invalid Session Time Rows",
                int((~df["session_time_valid"].fillna(False)).sum()),
            ),
            (
                "Missing Volume Rows",
                int((~df["volume_fields_present"].fillna(False)).sum()),
            ),
            (
                "Volume Mismatch Rows",
                int(df["volume_mismatch"].fillna(False).sum()),
            ),
            (
                "Non-standard Subscriber Rows",
                int(df["identifier_type"].ne("MSISDN").sum()),
            ),
            (
                "Zero-volume Sessions",
                int(df["is_zero_volume"].fillna(False).sum()),
            ),
        ]
    )


def _simple_count(
    df: pd.DataFrame,
    column: str,
    output_name: str,
) -> pd.DataFrame:
    values = _clean_text(df[column]).replace("", "UNKNOWN")
    return (
        values.value_counts(dropna=False)
        .rename_axis(output_name)
        .reset_index(name="Sessions")
    )


def _subscriber_summary(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["_subscriber"] = _clean_text(work["subscriber_number"])
    work = work.loc[work["_subscriber"].ne("")].copy()

    if work.empty:
        return pd.DataFrame()

    grouped = work.groupby("_subscriber", sort=False)

    summary = grouped.agg(
        Sessions=("subscriber_number", "size"),
        First_Seen=("session_start", "min"),
        Last_Seen=("session_end", "max"),
        Total_Downlink=("downlink_volume", "sum"),
        Total_Uplink=("uplink_volume", "sum"),
        Total_Volume=("total_volume", "sum"),
        Average_Duration_Seconds=("session_duration_seconds", "mean"),
        Max_Duration_Seconds=("session_duration_seconds", "max"),
        IMEI_Count=("imei", lambda x: _clean_text(x).replace("", pd.NA).nunique()),
        IMSI_Count=("imsi", lambda x: _clean_text(x).replace("", pd.NA).nunique()),
        IPv4_Count=("ipv4_address", lambda x: _clean_text(x).replace("", pd.NA).nunique()),
        IPv6_Count=("ipv6_address", lambda x: _clean_text(x).replace("", pd.NA).nunique()),
        CGI_Count=("searched_cell_id", lambda x: _clean_text(x).replace("", pd.NA).nunique()),
        Identifier_Type=("identifier_type", _joined_unique),
        Technology=("technology", _joined_unique),
        Pre_Post=("pre_post", _joined_unique),
        Operator=("operator", _joined_unique),
    ).reset_index().rename(columns={"_subscriber": "subscriber_number"})

    return summary.sort_values(
        ["Sessions", "Total_Volume", "subscriber_number"],
        ascending=[False, False, True],
        ignore_index=True,
    )


def _identity_summary(
    df: pd.DataFrame,
    identity_column: str,
) -> pd.DataFrame:
    work = df.copy()
    work["_identity"] = _clean_text(work[identity_column])
    work = work.loc[work["_identity"].ne("")].copy()

    if work.empty:
        return pd.DataFrame()

    grouped = work.groupby("_identity", sort=False)
    output = grouped.agg(
        Sessions=(identity_column, "size"),
        Subscriber_Count=(
            "subscriber_number",
            lambda x: _clean_text(x).replace("", pd.NA).nunique(),
        ),
        Subscribers=("subscriber_number", _joined_unique),
        First_Seen=("session_start", "min"),
        Last_Seen=("session_end", "max"),
        Total_Volume=("total_volume", "sum"),
        Technology=("technology", _joined_unique),
    ).reset_index().rename(columns={"_identity": identity_column})

    return output.sort_values(
        ["Subscriber_Count", "Sessions", identity_column],
        ascending=[False, False, True],
        ignore_index=True,
    )


def _ip_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []

    for column, version in (
        ("ipv4_address", "IPv4"),
        ("ipv6_address", "IPv6"),
    ):
        work = df.copy()
        work["_ip"] = _clean_text(work[column])
        work = work.loc[work["_ip"].ne("")].copy()

        if work.empty:
            continue

        grouped = work.groupby("_ip", sort=False)
        part = grouped.agg(
            Sessions=(column, "size"),
            Subscriber_Count=(
                "subscriber_number",
                lambda x: _clean_text(x).replace("", pd.NA).nunique(),
            ),
            Subscribers=("subscriber_number", _joined_unique),
            First_Seen=("session_start", "min"),
            Last_Seen=("session_end", "max"),
            Total_Volume=("total_volume", "sum"),
        ).reset_index().rename(columns={"_ip": "ip_address"})
        part.insert(0, "ip_version", version)
        rows.append(part)

    if not rows:
        return pd.DataFrame()

    return pd.concat(rows, ignore_index=True).sort_values(
        ["Subscriber_Count", "Sessions", "ip_address"],
        ascending=[False, False, True],
        ignore_index=True,
    )


def _duration_buckets(df: pd.DataFrame) -> pd.DataFrame:
    seconds = pd.to_numeric(
        df["session_duration_seconds"],
        errors="coerce",
    )
    buckets = pd.cut(
        seconds,
        bins=[-0.001, 60, 300, 900, 1800, 3600, 7200, float("inf")],
        labels=[
            "0-1 minute",
            "1-5 minutes",
            "5-15 minutes",
            "15-30 minutes",
            "30-60 minutes",
            "1-2 hours",
            "More than 2 hours",
        ],
        include_lowest=True,
    )

    return (
        buckets.value_counts(sort=False, dropna=False)
        .rename_axis("Duration_Bucket")
        .reset_index(name="Sessions")
    )


def _hourly_activity(df: pd.DataFrame) -> pd.DataFrame:
    starts = pd.to_datetime(df["session_start"], errors="coerce")
    output = (
        starts.dt.hour.value_counts()
        .sort_index()
        .rename_axis("Hour")
        .reset_index(name="Sessions_Started")
    )
    return output


def _quality_table(df: pd.DataFrame) -> pd.DataFrame:
    checks = [
        ("Invalid session timestamp/duration", ~df["session_time_valid"].fillna(False)),
        ("Missing volume fields", ~df["volume_fields_present"].fillna(False)),
        ("Downlink + Uplink != Total", df["volume_mismatch"].fillna(False)),
        ("Non-standard subscriber identifier", df["identifier_type"].ne("MSISDN")),
        ("Zero total volume", df["is_zero_volume"].fillna(False)),
        ("Missing IPv4", _clean_text(df["ipv4_address"]).eq("")),
        ("Missing IPv6", _clean_text(df["ipv6_address"]).eq("")),
        ("Missing IMEI", _clean_text(df["imei"]).eq("")),
        ("Missing IMSI", _clean_text(df["imsi"]).eq("")),
    ]

    return pd.DataFrame(
        [
            {
                "Check": label,
                "Rows": int(mask.sum()),
                "Percentage": round(
                    (int(mask.sum()) / len(df) * 100) if len(df) else 0,
                    4,
                ),
            }
            for label, mask in checks
        ]
    )


def run_gprs_analysis(
    df: pd.DataFrame,
    *,
    file_summary: pd.DataFrame | None = None,
) -> dict[str, Any]:
    if not isinstance(df, pd.DataFrame):
        raise TypeError("GPRS pandas DataFrame required hai.")

    if df.empty:
        raise ValueError("GPRS DataFrame empty hai.")

    subscriber_summary = _subscriber_summary(df)
    imei_summary = _identity_summary(df, "imei")
    imsi_summary = _identity_summary(df, "imsi")
    presence = build_tower_gprs_presence_intelligence(df)

    return {
        "summary": _summary(df),
        "file_summary": (
            file_summary.copy()
            if isinstance(file_summary, pd.DataFrame)
            else pd.DataFrame()
        ),
        "technology_summary": _simple_count(
            df, "technology", "Technology"
        ),
        "pre_post_summary": _simple_count(
            df, "pre_post", "Connection_Type"
        ),
        "roaming_summary": _simple_count(
            df, "roaming_circle", "Roaming_Circle"
        ),
        "subscriber_summary": subscriber_summary,
        "repeat_subscribers": subscriber_summary.loc[
            subscriber_summary["Sessions"] >= 2
        ].reset_index(drop=True)
        if not subscriber_summary.empty
        else subscriber_summary,
        "gprs_common_numbers": presence.get("common_numbers", pd.DataFrame()),
        "gprs_uncommon_numbers": presence.get("uncommon_numbers", pd.DataFrame()),
        "gprs_multi_cell_presence": presence.get("multi_cell_presence", pd.DataFrame()),
        "gprs_device_consistency": presence.get("device_consistency", pd.DataFrame()),
        "gprs_suspicious_timing": presence.get("suspicious_timing", pd.DataFrame()),
        "gprs_priority_leads": presence.get("priority_leads", pd.DataFrame()),
        "imei_summary": imei_summary,
        "shared_imei": imei_summary.loc[
            imei_summary["Subscriber_Count"] >= 2
        ].reset_index(drop=True)
        if not imei_summary.empty
        else imei_summary,
        "imsi_summary": imsi_summary,
        "shared_imsi": imsi_summary.loc[
            imsi_summary["Subscriber_Count"] >= 2
        ].reset_index(drop=True)
        if not imsi_summary.empty
        else imsi_summary,
        "ip_summary": _ip_summary(df),
        "duration_buckets": _duration_buckets(df),
        "hourly_activity": _hourly_activity(df),
        "long_sessions": df.sort_values(
            "session_duration_seconds",
            ascending=False,
            na_position="last",
        ).head(200).reset_index(drop=True),
        "zero_volume_sessions": df.loc[
            df["is_zero_volume"].fillna(False)
        ].reset_index(drop=True),
        "non_standard_identifiers": df.loc[
            df["identifier_type"].ne("MSISDN")
        ].reset_index(drop=True),
        "data_quality": _quality_table(df),
        "record_count": len(df),
    }


def _presence_table(
    partitions: dict[str, pd.DataFrame],
    identity_column: str,
) -> pd.DataFrame:
    partition_ids = list(partitions)
    aggregate: dict[str, dict[str, Any]] = {}

    for partition_id, dataframe in partitions.items():
        if dataframe.empty or identity_column not in dataframe.columns:
            continue

        work = dataframe.copy()
        work["_identity"] = _clean_text(work[identity_column])
        work = work.loc[work["_identity"].ne("")]

        for identity, group in work.groupby("_identity", sort=False):
            item = aggregate.setdefault(
                identity,
                {
                    identity_column: identity,
                    "match_count": 0,
                    "matched_partitions": [],
                    "session_count": 0,
                    "total_overlap_seconds": 0.0,
                    "total_volume": 0.0,
                    "operators": set(),
                },
            )
            item["match_count"] += 1
            item["matched_partitions"].append(partition_id)
            item["session_count"] += len(group)
            item["total_overlap_seconds"] += float(
                pd.to_numeric(
                    group["partition_overlap_seconds"],
                    errors="coerce",
                ).fillna(0).sum()
            )
            item["total_volume"] += float(
                pd.to_numeric(
                    group["total_volume"],
                    errors="coerce",
                ).fillna(0).sum()
            )
            item["operators"].update(
                value
                for value in _clean_text(group["operator"]).unique()
                if value
            )

    rows: list[dict[str, Any]] = []

    for item in aggregate.values():
        matched = set(item["matched_partitions"])
        row = {
            identity_column: item[identity_column],
            "match_count": item["match_count"],
            "total_partitions": len(partition_ids),
            "match_ratio": f"{item['match_count']}/{len(partition_ids)}",
            "matched_partitions": ", ".join(item["matched_partitions"]),
            "session_count": item["session_count"],
            "total_overlap_seconds": item["total_overlap_seconds"],
            "total_volume": item["total_volume"],
            "operators": ", ".join(sorted(item["operators"])),
        }

        for partition_id in partition_ids:
            row[partition_id] = 1 if partition_id in matched else 0

        rows.append(row)

    if not rows:
        return pd.DataFrame(
            columns=[
                identity_column,
                "match_count",
                "total_partitions",
                "match_ratio",
                "matched_partitions",
                "session_count",
                "total_overlap_seconds",
                "total_volume",
                "operators",
                *partition_ids,
            ]
        )

    return pd.DataFrame(rows).sort_values(
        ["match_count", "session_count", identity_column],
        ascending=[False, False, True],
        ignore_index=True,
    )


def create_gprs_partitions(
    df: pd.DataFrame,
    *,
    sightings: list[dict[str, Any]],
    cgi_groups: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create time-and-CGI scoped GPRS partitions.

    Session rule:
        session_start <= window_end AND session_end >= window_start

    For an explicit CGI group, the session must also match the sighting's
    resolved ``searched_cell_id``. ``AUTO_ALL`` remains available as an
    explicitly labelled time-only exploratory mode.
    """

    if not isinstance(df, pd.DataFrame) or df.empty:
        raise ValueError("Valid GPRS DataFrame required hai.")

    ordered = sorted(
        [item for item in sightings if isinstance(item, dict)],
        key=lambda item: (
            str(item.get("cctv_timestamp", "")),
            str(item.get("sighting_id", "")),
        ),
    )

    partitions: dict[str, pd.DataFrame] = {}
    window_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    excluded_hits: list[pd.DataFrame] = []
    warnings: list[str] = []

    session_start = pd.to_datetime(df["session_start"], errors="coerce")
    session_end = pd.to_datetime(df["session_end"], errors="coerce")

    for index, sighting in enumerate(ordered, start=1):
        partition_id = f"P{index}"
        sighting_id = str(sighting.get("sighting_id", "")).strip()
        window_start = pd.to_datetime(sighting.get("window_start"), errors="coerce")
        window_end = pd.to_datetime(sighting.get("window_end"), errors="coerce")

        status: dict[str, Any] = {
            "partition_id": partition_id,
            "sighting_id": sighting_id,
            "location_name": sighting.get("location_name", ""),
            "cctv_timestamp": sighting.get("cctv_timestamp", ""),
            "window_start": window_start,
            "window_end": window_end,
            "cgi_group_id": str(sighting.get("cgi_group_id", "")),
            "spot_id": str(
                sighting.get(
                    "spot_id",
                    "",
                )
            ),
            "spot_name": str(
                sighting.get(
                    "spot_name",
                    "",
                )
            ),
            "spot_scope_mode": str(
                sighting.get(
                    "spot_scope_mode",
                    "",
                )
            ),
        }

        if not sighting_id:
            status.update(
                status="INVALID_SIGHTING_ID",
                scope_mode="INVALID",
                message="Sighting ID missing hai.",
                included=False,
            )
            status_rows.append(status)
            continue

        if pd.isna(window_start) or pd.isna(window_end) or window_start >= window_end:
            status.update(
                status="INVALID_TIME_WINDOW",
                scope_mode="INVALID",
                message="Window start/end invalid hai.",
                included=False,
            )
            status_rows.append(status)
            continue

        spot_scope = resolve_partition_spot_scope(
            df,
            sighting,
        )

        status.update(
            spot_id=spot_scope.get(
                "spot_id",
                "",
            ),
            spot_name=spot_scope.get(
                "spot_name",
                "",
            ),
            spot_folder=spot_scope.get(
                "spot_folder",
                "",
            ),
            spot_scope_mode=spot_scope.get(
                "spot_scope_mode",
                "",
            ),
            spot_scope_status=spot_scope.get(
                "status",
                "",
            ),
        )

        if not spot_scope.get("valid"):
            status.update(
                status=spot_scope.get(
                    "status",
                    "INVALID_SPOT_SCOPE",
                ),
                scope_mode="INVALID",
                message=spot_scope.get(
                    "message",
                    "Selected Spot resolve नहीं हुआ।",
                ),
                included=False,
            )
            status_rows.append(status)
            continue

        spot_dataframe = spot_scope[
            "dataframe"
        ]

        spot_mask = spot_scope[
            "mask"
        ]

        loaded_cells = loaded_cell_map(
            spot_dataframe
        )

        scope = resolve_sighting_scope(
            sighting,
            cgi_groups=cgi_groups,
            loaded_cells=loaded_cells,
            source_type="GPRS",
        )
        status.update(
            status=scope["status"],
            scope_mode=scope["scope_mode"],
            cgi_group_id=scope["group_id"],
            resolved_cgi_count=len(scope["cell_keys"]),
            resolved_cgi_values=", ".join(scope["cell_values"]),
            message=scope["message"],
            included=bool(scope["valid"]),
        )
        status_rows.append(status)

        if not scope["valid"]:
            continue

        if scope["scope_mode"] == "TIME_ONLY_ALL_CELLS":
            location_mask = spot_mask.copy()
            warnings.append(
                f"{partition_id}: "
                f"{scope['message']}"
            )
        else:
            location_mask = (
                spot_mask
                & cell_mask(
                    df,
                    scope["cell_keys"],
                )
            )

        time_mask = (
            session_start.lt(window_end)
            & session_end.ge(window_start)
            & session_start.notna()
            & session_end.notna()
        )

        include_mask = (
            time_mask
            & location_mask
        )
        part = df.loc[include_mask].copy()

        excluded = df.loc[
            time_mask
            & spot_mask
            & ~location_mask
        ].copy()
        if not excluded.empty:
            excluded.insert(0, "partition_id", partition_id)
            excluded.insert(1, "sighting_id", sighting_id)
            excluded.insert(2, "exclusion_reason", "TIME_MATCH_LOCATION_MISMATCH")
            excluded_hits.append(excluded)

        if not part.empty:
            overlap_start = pd.concat(
                [
                    pd.to_datetime(part["session_start"], errors="coerce"),
                    pd.Series(window_start, index=part.index),
                ],
                axis=1,
            ).max(axis=1)
            overlap_end = pd.concat(
                [
                    pd.to_datetime(part["session_end"], errors="coerce"),
                    pd.Series(window_end, index=part.index),
                ],
                axis=1,
            ).min(axis=1)

            part.insert(
                0,
                "partition_id",
                partition_id,
            )
            part.insert(
                1,
                "partition_sighting_id",
                sighting_id,
            )
            part.insert(
                2,
                "partition_spot_id",
                spot_scope.get(
                    "spot_id",
                    "",
                ),
            )
            part.insert(
                3,
                "partition_spot_name",
                spot_scope.get(
                    "spot_name",
                    "",
                ),
            )
            part.insert(
                4,
                "partition_spot_scope_mode",
                spot_scope.get(
                    "spot_scope_mode",
                    "",
                ),
            )
            part.insert(
                5,
                "partition_location",
                sighting.get(
                    "location_name",
                    "",
                ),
            )
            part.insert(
                6,
                "partition_cgi_group_id",
                scope["group_id"],
            )
            part.insert(
                7,
                "partition_scope_mode",
                scope["scope_mode"],
            )
            part.insert(
                8,
                "partition_window_start",
                window_start,
            )
            part.insert(
                9,
                "partition_window_end",
                window_end,
            )
            part.insert(
                10,
                "partition_overlap_seconds",
                (overlap_end - overlap_start).dt.total_seconds().clip(lower=0),
            )
            part = part.reset_index(drop=True)

        partitions[partition_id] = part
        window_rows.append(
            {
                "partition_id": partition_id,
                "source_sighting_id": sighting_id,
                "spot_id": spot_scope.get(
                    "spot_id",
                    "",
                ),
                "spot_name": spot_scope.get(
                    "spot_name",
                    "",
                ),
                "spot_folder": spot_scope.get(
                    "spot_folder",
                    "",
                ),
                "spot_scope_mode": spot_scope.get(
                    "spot_scope_mode",
                    "",
                ),
                "spot_scope_status": spot_scope.get(
                    "status",
                    "",
                ),
                "location_name": sighting.get("location_name", ""),
                "cctv_timestamp": sighting.get("cctv_timestamp", ""),
                "window_start": window_start,
                "window_end": window_end,
                "minutes_before": sighting.get("minutes_before", 10),
                "minutes_after": sighting.get("minutes_after", 10),
                "cgi_group_id": scope["group_id"],
                "scope_mode": scope["scope_mode"],
                "resolved_cgi_values": ", ".join(scope["cell_values"]),
            }
        )
        summary_rows.append(
            {
                "partition_id": partition_id,
                "sighting_id": sighting_id,
                "spot_id": spot_scope.get(
                    "spot_id",
                    "",
                ),
                "spot_name": spot_scope.get(
                    "spot_name",
                    "",
                ),
                "spot_folder": spot_scope.get(
                    "spot_folder",
                    "",
                ),
                "spot_scope_mode": spot_scope.get(
                    "spot_scope_mode",
                    "",
                ),
                "spot_scope_status": spot_scope.get(
                    "status",
                    "",
                ),
                "location_name": sighting.get("location_name", ""),
                "cctv_timestamp": sighting.get("cctv_timestamp", ""),
                "window_start": window_start,
                "window_end": window_end,
                "cgi_group_id": scope["group_id"],
                "scope_mode": scope["scope_mode"],
                "resolved_cgi_count": len(scope["cell_keys"]),
                "sessions": len(part),
                "time_only_location_exclusions": int((time_mask & ~location_mask).sum()),
                "unique_subscribers": _clean_text(part["subscriber_number"]).replace("", pd.NA).nunique() if not part.empty else 0,
                "unique_imei": _clean_text(part["imei"]).replace("", pd.NA).nunique() if not part.empty else 0,
                "unique_imsi": _clean_text(part["imsi"]).replace("", pd.NA).nunique() if not part.empty else 0,
                "unique_ipv4": _clean_text(part["ipv4_address"]).replace("", pd.NA).nunique() if not part.empty else 0,
                "unique_ipv6": _clean_text(part["ipv6_address"]).replace("", pd.NA).nunique() if not part.empty else 0,
                "total_overlap_seconds": float(pd.to_numeric(part["partition_overlap_seconds"], errors="coerce").fillna(0).sum()) if not part.empty else 0.0,
            }
        )

    subscriber_presence = _presence_table(partitions, "subscriber_number")
    imei_presence = _presence_table(partitions, "imei")
    imsi_presence = _presence_table(partitions, "imsi")
    ipv4_presence = _presence_table(partitions, "ipv4_address")
    ipv6_presence = _presence_table(partitions, "ipv6_address")

    total = len(partitions)
    minimum = 1 if total <= 1 else 2
    n_of_m = (
        subscriber_presence.loc[subscriber_presence["match_count"] >= minimum].reset_index(drop=True)
        if not subscriber_presence.empty
        else subscriber_presence
    )
    strict = (
        subscriber_presence.loc[subscriber_presence["match_count"] == total].reset_index(drop=True)
        if total and not subscriber_presence.empty
        else subscriber_presence.head(0)
    )

    return {
        "partition_windows": pd.DataFrame(window_rows),
        "partition_summary": pd.DataFrame(summary_rows),
        "partition_status": pd.DataFrame(status_rows),
        "time_only_excluded_by_location": pd.concat(excluded_hits, ignore_index=True) if excluded_hits else pd.DataFrame(),
        "partitions": partitions,
        "subscriber_presence": subscriber_presence,
        "n_of_m_candidates": n_of_m,
        "strict_common_candidates": strict,
        "imei_presence": imei_presence,
        "imsi_presence": imsi_presence,
        "ipv4_presence": ipv4_presence,
        "ipv6_presence": ipv6_presence,
        "total_partitions": total,
        "total_configured_sightings": len(ordered),
        "total_input_records": len(df),
        "warnings": list(dict.fromkeys(warnings)),
        "overlap_rule": (
            "session_start < window_end "
            "AND session_end >= window_start"
        ),
        "spot_rule": (
            "selected Spot is applied before "
            "CGI and session-overlap filtering"
        ),
        "location_rule": (
            "searched_cell_id matches resolved "
            "CGI group inside selected Spot"
        ),
    }
