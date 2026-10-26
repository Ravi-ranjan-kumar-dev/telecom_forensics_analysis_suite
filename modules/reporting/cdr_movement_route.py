"""Generate investigator-facing CDR movement route maps."""

from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd


ROUTE_SUFFIX = "_movement_route.html"


def movement_route_path(
    report_path: str | Path,
) -> Path:
    """Return the deterministic movement-route sidecar path."""

    report = Path(
        report_path
    ).expanduser().resolve(
        strict=False
    )

    return report.with_name(
        f"{report.stem}{ROUTE_SUFFIX}"
    )


def _text(
    value: Any,
) -> str:
    """Return one clean display value."""

    if value is None:
        return ""

    try:
        if pd.isna(
            value
        ):
            return ""
    except (
        TypeError,
        ValueError,
    ):
        pass

    text = str(
        value
    ).strip()

    if text.endswith(
        ".0"
    ) and text[:-2].isdigit():
        return text[:-2]

    return text


def _first_value(
    row: pd.Series,
    columns: tuple[str, ...],
) -> Any:
    """Return the first non-blank value from candidate columns."""

    normalized = {re.sub(r'[^a-z0-9]', '', str(name).lower()): name for name in row.index}
    for column in columns:
        actual = normalized.get(re.sub(r'[^a-z0-9]', '', column.lower()))
        if actual is not None and _text(row[actual]):
            return row[actual]

    return None


def _coordinate(
    value: Any,
    *,
    minimum: float,
    maximum: float,
) -> float | None:
    """Return one valid bounded coordinate."""

    try:
        coordinate = float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if (
        not math.isfinite(
            coordinate
        )
        or not minimum
        <= coordinate
        <= maximum
    ):
        return None

    return round(
        coordinate,
        7,
    )


def _event_datetimes(
    frame: pd.DataFrame,
) -> pd.Series:
    """Return canonical route timestamps without changing source rows."""

    # Canonical parser supports call_date/time, date/time and event datetime aliases.
    from modules.analysis.cdr.datetime_utils import canonical_datetime
    renamed = frame.rename(columns={c: re.sub(r"[^a-z0-9]+", "_", str(c).lower()).strip("_") for c in frame.columns})
    for source, dest in (("date", "call_date"), ("time", "call_time"), ("event_datetime", "datetime"), ("event_time", "datetime"), ("date_time", "datetime"), ("event_date_time", "datetime"), ("timestamp", "datetime")):
        if dest not in renamed and source in renamed:
            renamed = renamed.rename(columns={source: dest})
    timestamps = canonical_datetime(renamed)
    if 'datetime' not in renamed and 'call_datetime' not in renamed:
        # A date alone does not establish a chronological tower-event sequence.
        if 'call_time' not in renamed:
            return pd.Series(pd.NaT, index=frame.index, dtype='datetime64[ns]')
        timestamps = timestamps.where(renamed['call_time'].map(_text).ne(''))
    return timestamps


def build_movement_route_points(
    movement: pd.DataFrame,
    *,
    target: str = "",
) -> list[dict[str, Any]]:
    """Build chronological mapped route points from enriched movement data."""

    if (
        movement is None
        or not isinstance(
            movement,
            pd.DataFrame,
        )
        or movement.empty
    ):
        return []

    frame = movement.copy()
    frame[
        "_route_datetime"
    ] = _event_datetimes(
        frame
    )
    frame[
        "_route_order"
    ] = range(
        len(
            frame
        )
    )
    frame = frame.sort_values(
        [
            "_route_datetime",
            "_route_order",
        ],
        kind="stable",
        na_position="last",
    )

    points: list[dict[str, Any]] = []
    previous_cgi = ""

    for _, row in frame.iterrows():
        cgi = _text(
            _first_value(
                row,
                (
                    "first_cell_id",
                    "first_cgi",
                    "cell_id",
                    "First Cell ID",
                    "Cell ID",
                    "CGI",
                ),
            )
        )

        if (
            not cgi
            or cgi == previous_cgi
        ):
            continue

        latitude = _coordinate(
            _first_value(
                row,
                (
                    "first_cell_latitude",
                    "cell_id_cgi_latitude", "tower_latitude", "first_cgi_latitude", "latitude",
                    "First Tower Latitude",
                    "Tower Latitude",
                    "Latitude",
                ),
            ),
            minimum=-90.0,
            maximum=90.0,
        )
        longitude = _coordinate(
            _first_value(
                row,
                (
                    "first_cell_longitude",
                    "cell_id_cgi_longitude", "tower_longitude", "first_cgi_longitude", "longitude",
                    "First Tower Longitude",
                    "Tower Longitude",
                    "Longitude",
                ),
            ),
            minimum=-180.0,
            maximum=180.0,
        )

        if (
            latitude is None
            or longitude is None
        ):
            continue

        previous_cgi = cgi

        timestamp = row.get(
            "_route_datetime"
        )
        timestamp_text = (
            timestamp.strftime(
                "%d-%m-%Y %H:%M:%S"
            )
            if pd.notna(
                timestamp
            )
            else "Time unavailable"
        )

        points.append(
            {
                "sequence": len(
                    points
                )
                + 1,
                "target": _text(
                    target
                ),
                "timestamp": timestamp_text,
                "cgi": cgi,
                "latitude": latitude,
                "longitude": longitude,
                "site_name": _text(
                    _first_value(
                        row,
                        (
                            "first_cell_site_name",
                            "First Tower Site Name",
                            "Tower Site Name",
                            "Site Name",
                        ),
                    )
                ),
                "address": _text(
                    _first_value(
                        row,
                        (
                            "first_cell_address",
                            "First Tower Address",
                            "Tower Address",
                            "Address",
                        ),
                    )
                ),
                "district": _text(
                    _first_value(
                        row,
                        (
                            "first_cell_district",
                            "First Tower District",
                            "Tower District",
                            "District",
                        ),
                    )
                ),
                "call_type": _text(
                    row.get(
                        "call_type"
                    )
                ),
                "contact": _text(
                    row.get(
                        "b_party"
                    )
                ),
            }
        )

    return points


def render_movement_route_html(points: list[dict[str, Any]], *, target: str = "") -> str:
    """Offline tower-event explorer; points do not show an exact road travelled."""
    from .offline_views import render_offline_view
    mapped = []
    for i, p in enumerate(points):
        mapped.append({
            "lat": p["latitude"], "lon": p["longitude"],
            "label": str(i + 1) + ". " + str(p.get("cgi", p.get("cell_id", "Tower event"))),
            "sheet": "Chronological tower events", "subscriber": str(p.get("target", target)),
            "sequence": int(p.get("sequence", i+1)), "route": p.get("timestamp") != "Time unavailable",
            "description": str(p),
        })
    return render_offline_view("map", {"points": mapped, "interpretation": "Tower events do not establish the exact road travelled."})


def _hydrate_route(movement):
    """Resolve missing first-tower coordinates without altering event order."""
    from .map_data import collect_map_points
    from modules.database.cgi_repository import normalize_cgi
    if not isinstance(movement, pd.DataFrame) or movement.empty:
        return movement
    points, _ = collect_map_points([('Movement events', movement)])
    locations = {normalize_cgi(p['label']): (p['lat'], p['lon']) for p in points}
    result = movement.copy()
    cgis = result.apply(lambda row: normalize_cgi(_first_value(row, ('first_cell_id','first_cgi','CGI','cell_id'))), axis=1)
    for index, axis in enumerate(('latitude','longitude')):
        values = cgis.map(lambda c: locations.get(c, (None,None))[index])
        name = 'first_cell_' + axis
        if name in result:
            result[name] = result[name].where(pd.to_numeric(result[name], errors='coerce').notna(), values)
        else:
            result[name] = values
    return result


def generate_cdr_movement_route(
    movement: pd.DataFrame,
    *,
    target: str,
    report_path: str | Path,
) -> Path | None:
    """Generate one movement-route map when mapped points are available."""

    points = build_movement_route_points(
        movement,
        target=target,
    )

    if not points:
        points = build_movement_route_points(_hydrate_route(movement), target=target)

    output = movement_route_path(
        report_path
    )
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output.write_text(
        render_movement_route_html(
            points,
            target=target,
        ),
        encoding="utf-8",
    )

    return output


def build_multi_movement_route_points(
    movement: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Build separate chronological route points for every target."""

    if (
        not isinstance(movement, pd.DataFrame)
        or movement.empty
    ):
        return []

    target_column = next((c for c in movement.columns if re.sub(r'[^a-z0-9]', '', str(c).lower()) in {'target','targetnumber','aparty','subscribernumber'}), None)
    if target_column is None:
        return []

    points: list[dict[str, Any]] = []

    for target, frame in movement.groupby(
        target_column,
        sort=True,
        dropna=False,
    ):
        target_text = _text(
            target
        )

        if not target_text:
            continue

        points.extend(
            build_movement_route_points(
                frame,
                target=target_text,
            )
        )

    return points


def render_multi_movement_route_html(points: list[dict[str, Any]]) -> str:
    """Offline tower-event explorer; points do not show an exact road travelled."""
    from .offline_views import render_offline_view
    mapped = []
    for i, p in enumerate(points):
        mapped.append({
            "lat": p["latitude"], "lon": p["longitude"],
            "label": str(i + 1) + ". " + str(p.get("cgi", p.get("cell_id", "Tower event"))),
            "sheet": "Chronological tower events", "subscriber": str(p.get("target", "")),
            "sequence": int(p.get("sequence", i+1)), "route": p.get("timestamp") != "Time unavailable",
            "description": str(p),
        })
    return render_offline_view("map", {"points": mapped, "interpretation": "Tower events do not establish the exact road travelled."})


def generate_multi_cdr_movement_route(
    movement: pd.DataFrame,
    *,
    report_path: str | Path,
) -> Path | None:
    """Generate one combined sidecar with separate per-target routes."""

    points = build_multi_movement_route_points(
        movement
    )

    if not points:
        points = build_multi_movement_route_points(_hydrate_route(movement))

    output = movement_route_path(
        report_path
    )
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output.write_text(
        render_multi_movement_route_html(
            points
        ),
        encoding="utf-8",
    )
    return output


