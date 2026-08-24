"""Generate investigator-facing CDR movement route maps."""

from __future__ import annotations

import html
import json
import math
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

    for column in columns:
        if column not in row.index:
            continue

        value = row[
            column
        ]

        if _text(
            value
        ):
            return value

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

    dates = (
        frame[
            "call_date"
        ].map(
            _text
        )
        if "call_date" in frame.columns
        else pd.Series(
            "",
            index=frame.index,
            dtype="object",
        )
    )
    times = (
        frame[
            "call_time"
        ].map(
            _text
        )
        if "call_time" in frame.columns
        else pd.Series(
            "",
            index=frame.index,
            dtype="object",
        )
    )

    return pd.to_datetime(
        (
            dates
            + " "
            + times
        ).str.strip(),
        errors="coerce",
        dayfirst=True,
        format="mixed",
    )


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


def render_movement_route_html(
    points: list[dict[str, Any]],
    *,
    target: str = "",
) -> str:
    """Render one standalone interactive movement-route map."""

    safe_payload = json.dumps(
        {
            "target": _text(
                target
            ),
            "points": points,
        },
        ensure_ascii=True,
    ).replace(
        "<",
        "\\u003c",
    ).replace(
        ">",
        "\\u003e",
    ).replace(
        "&",
        "\\u0026",
    )
    safe_target = html.escape(
        _text(
            target
        )
        or "Not provided"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CDR Movement Route — {safe_target}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #0f172a; color: #e5e7eb; font-family: system-ui, sans-serif; }}
header {{ padding: 14px 18px; background: #111827; border-bottom: 1px solid #334155; }}
h1 {{ margin: 0 0 4px; font-size: 21px; }}
.sub {{ color: #94a3b8; font-size: 13px; }}
.toolbar {{ display: flex; gap: 8px; align-items: center; padding: 10px 14px; flex-wrap: wrap; }}
button {{ background: #2563eb; color: white; border: 0; border-radius: 6px; padding: 8px 12px; cursor: pointer; }}
button:disabled {{ opacity: .45; cursor: default; }}
#position {{ color: #cbd5e1; min-width: 130px; }}
#map {{ height: 58vh; min-height: 390px; }}
.caution {{ margin: 10px 14px; padding: 10px 12px; border: 1px solid #92400e; border-radius: 7px; background: #451a03; color: #fde68a; font-size: 13px; }}
.route-marker {{ width: 28px; height: 28px; border-radius: 50%; color: white; background: #2563eb; border: 2px solid white; text-align: center; line-height: 24px; font-weight: 700; box-shadow: 0 1px 5px #000; }}
.route-marker.start {{ background: #16a34a; }}
.route-marker.end {{ background: #dc2626; }}
.table-wrap {{ max-height: 29vh; overflow: auto; border-top: 1px solid #334155; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
th, td {{ padding: 8px; border-bottom: 1px solid #263449; text-align: left; vertical-align: top; }}
th {{ position: sticky; top: 0; background: #1e293b; }}
tr.active {{ background: #1e3a5f; }}
.empty {{ padding: 30px; text-align: center; color: #fca5a5; }}
</style>
</head>
<body>
<header>
  <h1>Target Movement Route</h1>
  <div class="sub">Target: {safe_target} | Mapped chronological tower points: {len(points)}</div>
</header>
<div class="toolbar">
  <button id="previous">Previous</button>
  <button id="play">Play Route</button>
  <button id="next">Next</button>
  <button id="showAll">Show Full Route</button>
  <span id="position"></span>
</div>
<div id="map"></div>
<div class="caution">This route connects the target handset's serving towers in chronological order. Lines between towers do not prove the exact road travelled, exact handset location or continuous movement. Verify findings with source CDR, CGI records and independent case evidence.</div>
<div class="table-wrap"><table>
<thead><tr><th>Step</th><th>Date-Time</th><th>CGI</th><th>Site / Address</th><th>Contact</th><th>Call Type</th></tr></thead>
<tbody id="routeRows"></tbody>
</table></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const payload = {safe_payload};
const points = payload.points || [];
const mapElement = document.getElementById("map");
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[char]));

if (!window.L) {{
  mapElement.innerHTML = '<div class="empty">Interactive basemap resources could not be loaded. The route evidence table remains available below.</div>';
}}

const rows = document.getElementById("routeRows");
points.forEach((point, index) => {{
  const row = document.createElement("tr");
  row.id = `route-row-${{index}}`;
  row.innerHTML = `<td>${{point.sequence}}</td><td>${{esc(point.timestamp)}}</td><td>${{esc(point.cgi)}}</td><td>${{esc(point.site_name || point.address || point.district || "Not available")}}</td><td>${{esc(point.contact || "—")}}</td><td>${{esc(point.call_type || "—")}}</td>`;
  rows.appendChild(row);
}});

if (window.L && points.length) {{
  const map = L.map("map");
  L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
  }}).addTo(map);

  const coordinates = points.map((point) => [point.latitude, point.longitude]);
  const route = L.polyline(coordinates, {{color: "#38bdf8", weight: 4, opacity: .8}}).addTo(map);
  const markers = points.map((point, index) => {{
    let markerClass = "route-marker";
    if (index === 0) markerClass += " start";
    if (index === points.length - 1) markerClass += " end";
    const icon = L.divIcon({{className: "", html: `<div class="${{markerClass}}">${{point.sequence}}</div>`, iconSize: [28, 28], iconAnchor: [14, 14]}});
    const marker = L.marker([point.latitude, point.longitude], {{icon}}).addTo(map);
    marker.bindPopup(`<b>Step ${{point.sequence}}</b><br>${{esc(point.timestamp)}}<br><b>CGI:</b> ${{esc(point.cgi)}}<br>${{esc(point.site_name || "")}}<br>${{esc(point.address || "")}}`);
    return marker;
  }});

  if (coordinates.length === 1) map.setView(coordinates[0], 14);
  else map.fitBounds(route.getBounds(), {{padding: [25, 25]}});

  let current = 0;
  let timer = null;
  const position = document.getElementById("position");
  const play = document.getElementById("play");
  const focus = (index) => {{
    current = Math.max(0, Math.min(points.length - 1, index));
    map.setView(coordinates[current], Math.max(map.getZoom(), 13));
    markers[current].openPopup();
    document.querySelectorAll("tr.active").forEach((row) => row.classList.remove("active"));
    const row = document.getElementById(`route-row-${{current}}`);
    if (row) {{ row.classList.add("active"); row.scrollIntoView({{block: "nearest"}}); }}
    position.textContent = `Step ${{current + 1}} of ${{points.length}}`;
  }};
  document.getElementById("previous").onclick = () => focus(current - 1);
  document.getElementById("next").onclick = () => focus(current + 1);
  document.getElementById("showAll").onclick = () => coordinates.length === 1 ? map.setView(coordinates[0], 14) : map.fitBounds(route.getBounds(), {{padding: [25, 25]}});
  play.onclick = () => {{
    if (timer) {{ clearInterval(timer); timer = null; play.textContent = "Play Route"; return; }}
    focus(current >= points.length - 1 ? 0 : current);
    play.textContent = "Pause";
    timer = setInterval(() => {{
      if (current >= points.length - 1) {{ clearInterval(timer); timer = null; play.textContent = "Play Route"; return; }}
      focus(current + 1);
    }}, 1200);
  }};
  focus(0);
}} else if (!points.length) {{
  mapElement.innerHTML = '<div class="empty">No movement points with valid CGI coordinates were available.</div>';
  document.querySelectorAll("button").forEach((button) => button.disabled = true);
}}
</script>
</body>
</html>
"""


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
        return None

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
        or "Target" not in movement.columns
    ):
        return []

    points: list[dict[str, Any]] = []

    for target, frame in movement.groupby(
        "Target",
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


def render_multi_movement_route_html(
    points: list[dict[str, Any]],
) -> str:
    """Render multiple target routes without joining different targets."""

    safe_payload = json.dumps(
        {
            "points": points,
        },
        ensure_ascii=True,
    ).replace(
        "<",
        "\\u003c",
    ).replace(
        ">",
        "\\u003e",
    ).replace(
        "&",
        "\\u0026",
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Multiple CDR Movement Routes</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #0f172a; color: #e5e7eb; font-family: system-ui, sans-serif; }}
header {{ padding: 14px 18px; background: #111827; border-bottom: 1px solid #334155; }}
h1 {{ margin: 0 0 4px; font-size: 21px; }}
.sub {{ color: #94a3b8; font-size: 13px; }}
.toolbar {{ display: flex; gap: 10px; align-items: center; padding: 10px 14px; flex-wrap: wrap; }}
select, button {{ min-height: 36px; border-radius: 6px; padding: 7px 10px; }}
select {{ min-width: 230px; color: #f8fafc; background: #111827; border: 1px solid #475569; }}
button {{ color: white; background: #2563eb; border: 0; cursor: pointer; }}
#summary {{ color: #bfdbfe; font-size: 13px; }}
#map {{ height: 58vh; min-height: 390px; }}
.caution {{ margin: 10px 14px; padding: 10px 12px; border: 1px solid #92400e; border-radius: 7px; background: #451a03; color: #fde68a; font-size: 13px; }}
.table-wrap {{ max-height: 31vh; overflow: auto; border-top: 1px solid #334155; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
th, td {{ padding: 8px; border-bottom: 1px solid #263449; text-align: left; vertical-align: top; }}
th {{ position: sticky; top: 0; color: white; background: #1e3a5f; }}
.empty {{ padding: 30px; text-align: center; color: #fca5a5; }}
</style>
</head>
<body>
<header>
  <h1>Multiple CDR Movement Routes</h1>
  <div class="sub">Each target route is drawn separately. Different targets are never joined by one route line.</div>
</header>
<div class="toolbar">
  <label for="targetFilter">Target</label>
  <select id="targetFilter"><option value="">All Targets</option></select>
  <button id="reset" type="button">Reset View</button>
  <span id="summary"></span>
</div>
<div id="map"></div>
<div class="caution">Routes connect chronological serving towers and do not prove an exact road, exact handset position, continuous movement or co-location. Verify important points with source CDR, CGI coverage and independent evidence.</div>
<div class="table-wrap"><table>
<thead><tr><th>Target</th><th>Step</th><th>Date-Time</th><th>CGI</th><th>Site / Address</th><th>Contact</th><th>Call Type</th></tr></thead>
<tbody id="routeRows"></tbody>
</table></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
"use strict";
const payload = {safe_payload};
const allPoints = Array.isArray(payload.points) ? payload.points : [];
const palette = ["#38bdf8", "#f97316", "#22c55e", "#e879f9", "#facc15", "#a78bfa", "#fb7185", "#2dd4bf"];
const targets = [...new Set(allPoints.map((point) => String(point.target || "")).filter(Boolean))].sort();
const filter = document.getElementById("targetFilter");
for (const target of targets) {{
  const option = document.createElement("option");
  option.value = target;
  option.textContent = target;
  filter.appendChild(option);
}}

const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[char]));
const mapElement = document.getElementById("map");
let map = null;
let layers = [];

function selectedPoints() {{
  const target = filter.value;
  return target ? allPoints.filter((point) => String(point.target || "") === target) : allPoints;
}}

function clearLayers() {{
  if (!map) return;
  for (const layer of layers) map.removeLayer(layer);
  layers = [];
}}

function renderTable(points) {{
  const body = document.getElementById("routeRows");
  body.replaceChildren();
  if (!points.length) {{
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 7;
    cell.textContent = "No mapped route points are available for this selection.";
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }}
  for (const point of points) {{
    const row = document.createElement("tr");
    const values = [
      point.target || "",
      point.sequence || "",
      point.timestamp || "",
      point.cgi || "",
      point.site_name || point.address || point.district || "",
      point.contact || "",
      point.call_type || "",
    ];
    for (const value of values) {{
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    }}
    body.appendChild(row);
  }}
}}

function render() {{
  const points = selectedPoints();
  renderTable(points);
  const visibleTargets = [...new Set(points.map((point) => String(point.target || "")))];
  document.getElementById("summary").textContent = `Targets: ${{visibleTargets.length}} | Mapped points: ${{points.length}}`;
  if (!map) return;
  clearLayers();
  const bounds = [];
  for (const [targetIndex, target] of visibleTargets.sort().entries()) {{
    const routePoints = points.filter((point) => String(point.target || "") === target);
    const color = palette[targetIndex % palette.length];
    const coordinates = routePoints.map((point) => [point.latitude, point.longitude]);
    if (coordinates.length > 1) {{
      const line = L.polyline(coordinates, {{color, weight: 4, opacity: 0.82}}).addTo(map);
      line.bindTooltip(`Target ${{esc(target)}} | ${{coordinates.length}} route points`);
      layers.push(line);
    }}
    routePoints.forEach((point) => {{
      const marker = L.circleMarker([point.latitude, point.longitude], {{radius: 7, color, fillColor: color, fillOpacity: 0.82, weight: 2}}).addTo(map);
      marker.bindPopup(`<b>Target:</b> ${{esc(target)}}<br><b>Step:</b> ${{esc(point.sequence)}}<br>${{esc(point.timestamp)}}<br><b>CGI:</b> ${{esc(point.cgi)}}<br>${{esc(point.site_name || point.address || "")}}`);
      layers.push(marker);
      bounds.push([point.latitude, point.longitude]);
    }});
  }}
  if (bounds.length === 1) map.setView(bounds[0], 14);
  else if (bounds.length > 1) map.fitBounds(bounds, {{padding: [25, 25], maxZoom: 15}});
}}

if (window.L) {{
  map = L.map("map");
  L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{maxZoom: 19, attribution: "&copy; OpenStreetMap contributors"}}).addTo(map);
}} else {{
  mapElement.innerHTML = '<div class="empty">Interactive basemap resources could not be loaded. The route evidence table remains available below.</div>';
}}

filter.addEventListener("change", render);
document.getElementById("reset").addEventListener("click", () => {{ filter.value = ""; render(); }});
render();
</script>
</body>
</html>
"""


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
        return None

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
