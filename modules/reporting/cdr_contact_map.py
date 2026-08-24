"""Generate investigator-facing CDR contact tower maps."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

import pandas as pd


MAP_SUFFIX = "_contact_map.html"


def contact_map_path(
    report_path: str | Path,
) -> Path:
    """Return the deterministic map sidecar path for one CDR report."""

    report = Path(
        report_path
    ).expanduser().resolve(
        strict=False
    )

    return report.with_name(
        f"{report.stem}{MAP_SUFFIX}"
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


def _number(
    value: Any,
    *,
    minimum: float,
    maximum: float,
) -> float | None:
    """Return one valid bounded number."""

    try:
        result = float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if not (
        minimum
        <= result
        <= maximum
    ):
        return None

    return round(
        result,
        7,
    )


def _count(
    value: Any,
    *,
    default: int,
) -> int:
    """Return one non-negative event count."""

    try:
        return max(
            int(
                float(
                    value
                )
            ),
            0,
        )
    except (
        TypeError,
        ValueError,
    ):
        return default


def build_contact_map_points(
    contact_summary: pd.DataFrame,
    *,
    target: str = "",
) -> list[dict[str, Any]]:
    """Build aggregated tower points from the canonical contact summary."""

    if (
        not isinstance(
            contact_summary,
            pd.DataFrame,
        )
        or contact_summary.empty
    ):
        return []

    specifications = (
        {
            "type": "Most Used Tower",
            "cgi": "Most Used Target CGI",
            "status": "Most Used CGI Lookup Status",
            "site": "Most Used Site Name",
            "address": "Most Used Tower Address",
            "latitude": "Most Used Latitude",
            "longitude": "Most Used Longitude",
            "events": "Most Used CGI Events",
        },
        {
            "type": "Last Interaction Tower",
            "cgi": "Last Interaction CGI",
            "status": "Last Interaction CGI Lookup Status",
            "site": "Last Interaction Site Name",
            "address": "Last Interaction Tower Address",
            "latitude": "Last Interaction Latitude",
            "longitude": "Last Interaction Longitude",
            "events": None,
        },
    )

    grouped: dict[
        tuple[str, float, float, str],
        dict[str, Any],
    ] = {}

    for record in contact_summary.to_dict(
        orient="records"
    ):
        source_target = _text(
            record.get(
                "Target"
            )
        )
        contact = _text(
            record.get(
                "Other Party"
            )
        )
        name = _text(
            record.get(
                "Name"
            )
        )

        for specification in specifications:
            latitude = _number(
                record.get(
                    specification[
                        "latitude"
                    ]
                ),
                minimum=-90,
                maximum=90,
            )
            longitude = _number(
                record.get(
                    specification[
                        "longitude"
                    ]
                ),
                minimum=-180,
                maximum=180,
            )

            if (
                latitude is None
                or longitude is None
            ):
                continue

            cgi = _text(
                record.get(
                    specification[
                        "cgi"
                    ]
                )
            )
            key = (
                str(
                    specification[
                        "type"
                    ]
                ),
                latitude,
                longitude,
                cgi,
            )

            point = grouped.setdefault(
                key,
                {
                    "target": _text(
                        target
                    ),
                    "type": specification[
                        "type"
                    ],
                    "cgi": cgi,
                    "lookup_status": _text(
                        record.get(
                            specification[
                                "status"
                            ]
                        )
                    ),
                    "site_name": _text(
                        record.get(
                            specification[
                                "site"
                            ]
                        )
                    ),
                    "address": _text(
                        record.get(
                            specification[
                                "address"
                            ]
                        )
                    ),
                    "latitude": latitude,
                    "longitude": longitude,
                    "contact_count": 0,
                    "event_count": 0,
                    "contacts": [],
                },
            )

            point[
                "contacts"
            ].append(
                {
                    "target": source_target,
                    "contact": contact,
                    "name": name,
                    "sdr_status": _text(
                        record.get(
                            "SDR Lookup Status"
                        )
                    ),
                    "events": (
                        _count(
                            record.get(
                                specification[
                                    "events"
                                ]
                            ),
                            default=0,
                        )
                        if specification[
                            "events"
                        ]
                        else 1
                    ),
                    "last_communication": _text(
                        record.get(
                            "Last Call Time"
                        )
                    ),
                }
            )

    points = []

    for point in grouped.values():
        contacts = sorted(
            point[
                "contacts"
            ],
            key=lambda item: (
                -int(
                    item.get(
                        "events",
                        0,
                    )
                ),
                str(
                    item.get(
                        "contact",
                        "",
                    )
                ),
            ),
        )

        point[
            "contacts"
        ] = contacts
        point[
            "contact_count"
        ] = len(
            {
                item.get(
                    "contact",
                    "",
                )
                for item in contacts
                if item.get(
                    "contact",
                    "",
                )
            }
        )
        point[
            "event_count"
        ] = sum(
            int(
                item.get(
                    "events",
                    0,
                )
            )
            for item in contacts
        )

        points.append(
            point
        )

    return sorted(
        points,
        key=lambda item: (
            str(
                item.get(
                    "type",
                    "",
                )
            ),
            -int(
                item.get(
                    "contact_count",
                    0,
                )
            ),
            str(
                item.get(
                    "cgi",
                    "",
                )
            ),
        ),
    )


def _safe_json(
    payload: dict[str, Any],
) -> str:
    """Return JSON safe for one HTML script element."""

    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
        )
        .replace(
            "&",
            "\\u0026",
        )
        .replace(
            "<",
            "\\u003c",
        )
        .replace(
            ">",
            "\\u003e",
        )
    )


def render_contact_map_html(
    points: list[dict[str, Any]],
    *,
    target: str = "",
) -> str:
    """Render an interactive Leaflet map with an offline table fallback."""

    title = "CDR Contact Tower Map"
    payload = _safe_json(
        {
            "target": _text(
                target
            ),
            "points": points,
        }
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' https://unpkg.com; style-src 'self' 'unsafe-inline' https://unpkg.com; img-src 'self' data: blob: https://*.tile.openstreetmap.org; connect-src https://*.tile.openstreetmap.org;">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
body {{ margin: 0; background: #0b1220; color: #e5e7eb; font-family: Arial, sans-serif; }}
header {{ padding: 16px 20px; background: #111827; border-bottom: 1px solid #263449; }}
h1 {{ margin: 0 0 5px; font-size: 21px; }}
#target {{ color: #93a4b8; font-size: 12px; }}
.controls {{ display: grid; grid-template-columns: 1fr auto auto auto; gap: 10px; padding: 11px 16px; background: #0f1a2b; align-items: center; }}
input[type="search"] {{ min-height: 38px; padding: 8px 10px; color: #f8fafc; background: #08101d; border: 1px solid #334155; border-radius: 7px; }}
label {{ font-size: 12px; white-space: nowrap; }}
button {{ min-height: 36px; padding: 8px 12px; color: #fff; background: #2563eb; border: 0; border-radius: 7px; font-weight: 700; }}
#summary {{ padding: 9px 16px; color: #bfdbfe; background: #111827; border-top: 1px solid #263449; border-bottom: 1px solid #263449; font-size: 12px; }}
#map {{ height: 58vh; min-height: 410px; background: #111827; }}
#fallback {{ display: none; min-height: 250px; padding: 26px; color: #facc15; background: #111827; }}
.caution {{ margin: 14px 16px; padding: 11px 13px; color: #fef3c7; background: #312e14; border: 1px solid #854d0e; border-radius: 8px; font-size: 12px; }}
.table-wrap {{ margin: 0 16px 20px; overflow: auto; border: 1px solid #263449; border-radius: 8px; }}
table {{ width: 100%; border-collapse: collapse; background: #0f1a2b; font-size: 12px; }}
th, td {{ padding: 9px; border-bottom: 1px solid #263449; text-align: left; vertical-align: top; }}
th {{ position: sticky; top: 0; color: #fff; background: #1d4ed8; }}
.leaflet-popup-content-wrapper, .leaflet-popup-tip {{ color: #e5e7eb; background: #111827; }}
.popup-contact {{ padding: 5px 0; border-top: 1px solid #334155; }}
@media (max-width: 850px) {{ .controls {{ grid-template-columns: 1fr 1fr; }} }}
</style>
</head>
<body>
<header>
<h1>{html.escape(title)}</h1>
<div id="target"></div>
</header>
<div class="controls">
<input id="search" type="search" placeholder="Search contact, name, CGI, site or address">
<label><input id="most" type="checkbox" checked> Most Used</label>
<label><input id="last" type="checkbox" checked> Last Interaction</label>
<button id="reset" type="button">Reset View</button>
</div>
<div id="summary"></div>
<div id="map"></div>
<div id="fallback">Interactive basemap resources could not be loaded. The verified coordinate table remains available below. Reopen this file when internet access is available.</div>
<div class="caution">Tower markers show the target handset's serving network location during communication. They do not establish the exact location of the contact person or handset. Verify important findings with source CDR, CGI records and independent case evidence.</div>
<div class="table-wrap">
<table>
<thead><tr><th>Type</th><th>CGI</th><th>Site / Address</th><th>Coordinates</th><th>Contacts</th><th>Events</th></tr></thead>
<tbody id="rows"></tbody>
</table>
</div>
<script id="payload" type="application/json">{payload}</script>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
"use strict";

const payload = JSON.parse(document.getElementById("payload").textContent);
const allPoints = Array.isArray(payload.points) ? payload.points : [];
document.getElementById("target").textContent = payload.target ? `Target: ${{payload.target}}` : "Target: Not provided";

function esc(value) {{
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}}

function filterPoints() {{
    const query = document.getElementById("search").value.trim().toLowerCase();
    const showMost = document.getElementById("most").checked;
    const showLast = document.getElementById("last").checked;

    return allPoints.filter((point) => {{
        if (point.type === "Most Used Tower" && !showMost) return false;
        if (point.type === "Last Interaction Tower" && !showLast) return false;

        const contacts = Array.isArray(point.contacts) ? point.contacts : [];
        const text = [
            point.type,
            point.cgi,
            point.site_name,
            point.address,
            ...contacts.map((item) => `${{item.target ?? ""}} ${{item.contact ?? ""}} ${{item.name ?? ""}}`),
        ].join(" ").toLowerCase();

        return !query || text.includes(query);
    }});
}}

function popup(point) {{
    const contacts = Array.isArray(point.contacts) ? point.contacts : [];
    const visible = contacts.slice(0, 25).map((item) => `
        <div class="popup-contact">
        ${{item.target ? `<strong>Target: ${{esc(item.target)}}</strong><br>` : ""}}
        <strong>${{esc(item.contact || "Contact not available")}}</strong>
        ${{item.name ? `<br>${{esc(item.name)}}` : ""}}
        <br>Events: ${{esc(item.events ?? 0)}}
        ${{item.last_communication ? `<br>Last: ${{esc(item.last_communication)}}` : ""}}
        </div>
    `).join("");

    return `
        <strong>${{esc(point.type)}}</strong><br>
        CGI: ${{esc(point.cgi || "Not available")}}<br>
        Site: ${{esc(point.site_name || "Not available")}}<br>
        Address: ${{esc(point.address || "Not available")}}<br>
        Coordinates: ${{esc(point.latitude)}}, ${{esc(point.longitude)}}<br>
        Lookup: ${{esc(point.lookup_status || "Not available")}}<br>
        Contacts: ${{esc(point.contact_count ?? 0)}} | Events: ${{esc(point.event_count ?? 0)}}
        ${{visible}}
        ${{contacts.length > 25 ? `<div>+ ${{contacts.length - 25}} more contact(s)</div>` : ""}}
    `;
}}

function renderTable(points) {{
    const body = document.getElementById("rows");
    body.replaceChildren();

    if (!points.length) {{
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 6;
        cell.textContent = "No mapped tower records match the current filter.";
        row.appendChild(cell);
        body.appendChild(row);
        return;
    }}

    for (const point of points) {{
        const row = document.createElement("tr");
        const values = [
            point.type || "",
            point.cgi || "",
            [point.site_name, point.address].filter(Boolean).join(" | "),
            `${{point.latitude}}, ${{point.longitude}}`,
            String(point.contact_count ?? 0),
            String(point.event_count ?? 0),
        ];

        for (const value of values) {{
            const cell = document.createElement("td");
            cell.textContent = value;
            row.appendChild(cell);
        }}

        body.appendChild(row);
    }}
}}

let map = null;
let markers = [];
let initialBounds = null;

function clearMarkers() {{
    if (!map) return;
    for (const marker of markers) map.removeLayer(marker);
    markers = [];
}}

function render(points, fitView = false) {{
    renderTable(points);

    const mostCount = points.filter((point) => point.type === "Most Used Tower").length;
    const lastCount = points.filter((point) => point.type === "Last Interaction Tower").length;
    document.getElementById("summary").textContent =
        `Mapped points: ${{points.length}} | Most Used: ${{mostCount}} | Last Interaction: ${{lastCount}}`;

    if (!map) return;

    clearMarkers();
    const bounds = [];

    for (const point of points) {{
        const mostUsed = point.type === "Most Used Tower";
        const marker = L.circleMarker(
            [point.latitude, point.longitude],
            {{
                radius: Math.min(8 + Math.log2(Number(point.contact_count || 1) + 1), 15),
                color: mostUsed ? "#2563eb" : "#f97316",
                fillColor: mostUsed ? "#60a5fa" : "#fb923c",
                fillOpacity: 0.82,
                weight: 2,
            }}
        );

        marker.bindPopup(popup(point), {{ maxWidth: 420 }});
        marker.bindTooltip(esc(`${{point.type}} | ${{point.cgi || "CGI not available"}}`));
        marker.addTo(map);
        markers.push(marker);
        bounds.push([point.latitude, point.longitude]);
    }}

    if (bounds.length) {{
        initialBounds = L.latLngBounds(bounds);
        if (fitView) map.fitBounds(initialBounds, {{ padding: [30, 30], maxZoom: 15 }});
    }}
}}

function start() {{
    if (typeof window.L === "undefined") {{
        document.getElementById("map").style.display = "none";
        document.getElementById("fallback").style.display = "block";
        render(filterPoints(), false);
        return;
    }}

    map = L.map("map", {{ preferCanvas: true }});
    L.tileLayer(
        "https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png",
        {{ maxZoom: 19, attribution: "&copy; OpenStreetMap contributors" }}
    ).addTo(map);
    render(filterPoints(), true);
}}

for (const id of ["search", "most", "last"]) {{
    document.getElementById(id).addEventListener("input", () => render(filterPoints(), false));
    document.getElementById(id).addEventListener("change", () => render(filterPoints(), false));
}}

document.getElementById("reset").addEventListener("click", () => {{
    document.getElementById("search").value = "";
    document.getElementById("most").checked = true;
    document.getElementById("last").checked = true;
    render(filterPoints(), false);
    if (map && initialBounds) map.fitBounds(initialBounds, {{ padding: [30, 30], maxZoom: 15 }});
}});

window.addEventListener("load", start);
</script>
</body>
</html>
"""


def generate_cdr_contact_map(
    contact_summary: pd.DataFrame,
    *,
    target: str,
    report_path: str | Path,
) -> Path:
    """Generate the map beside one Single CDR workbook."""

    output = contact_map_path(
        report_path
    )
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    points = build_contact_map_points(
        contact_summary,
        target=target,
    )
    output.write_text(
        render_contact_map_html(
            points,
            target=target,
        ),
        encoding="utf-8",
    )

    return output
