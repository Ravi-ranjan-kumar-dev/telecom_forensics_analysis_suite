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


def render_contact_map_html(points: list[dict[str, Any]], *, target: str = "") -> str:
    """Bundle Leaflet locally; the tower layer does not require street tiles."""
    from .offline_views import render_offline_view
    mapped = []
    for p in points:
        mapped.append({
            "lat": p["latitude"], "lon": p["longitude"], "label": p.get("cgi", ""),
            "sheet": p.get("type", "Contact towers"), "subscriber": target,
            "description": str(p.get("contacts", [])),
        })
    return render_offline_view("map", {"points": mapped, "target": target})


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
    if not points:
        # A report may contain CGI identifiers without coordinates. Resolve them
        # from the selected master rather than saving an unexplained empty map.
        from .map_data import collect_map_points
        from .offline_views import render_offline_view
        mapped, diagnostics = collect_map_points([('Contact summary', contact_summary)])
        output.write_text(render_offline_view('map', {
            'points': mapped, 'target': target, 'diagnostics': diagnostics,
        }), encoding='utf-8')
        return output
    output.write_text(
        render_contact_map_html(
            points,
            target=target,
        ),
        encoding="utf-8",
    )

    return output


# EA_CONTACT_NUMBERS_PANEL_V2: Investigator contact numbers next to serving CGI.
# The panel is rendered from the same verified points already used by the map.
# It does NOT assume the contact's own location equals the target's serving tower.
import html as _ea_contact_html

_ea_original_contact_map_renderer = render_contact_map_html


def _ea_build_contact_number_panel(points):
    def esc(value):
        if value is None:
            return ""
        return _ea_contact_html.escape(str(value), quote=True)

    rows = []
    for point in (points or []):
        if not isinstance(point, dict):
            continue
        raw_contacts = point.get("contacts", [])
        seen = set()
        numbers = []
        for item in raw_contacts if isinstance(raw_contacts, (tuple, list)) else []:
            if not isinstance(item, dict):
                continue
            number = str(item.get("contact") or "").strip()
            if not number or number in seen:
                continue
            seen.add(number)
            name = str(item.get("name") or "").strip()
            numbers.append((number, name))

        if not numbers:
            contact_html = '<span class="ea-muted">Not available in source CDR</span>'
        else:
            visible = []
            for number, name in numbers[:6]:
                label = "{}{}".format(esc(number), " — " + esc(name) if name else "")
                visible.append('<span class="ea-number">{}</span>'.format(label))
            contact_html = " ".join(visible)
            if len(numbers) > 6:
                remaining = []
                for number, name in numbers[6:]:
                    label = "{}{}".format(esc(number), " — " + esc(name) if name else "")
                    remaining.append('<span class="ea-number">{}</span>'.format(label))
                contact_html += (
                    '<details><summary>Show {} more contact(s)</summary><div>{}</div></details>'
                    .format(len(numbers) - 6, " ".join(remaining))
                )
        cgi = esc(point.get("cgi") or "Not available")
        address = esc(point.get("address") or point.get("site_name") or "Not available")
        kind = esc(point.get("type") or "Tower")
        rows.append(
            '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
                kind, cgi, contact_html, address
            )
        )

    if not rows:
        body = '<tr><td colspan="4">No verified tower-contact points available.</td></tr>'
    else:
        body = "".join(rows)

    return """
<section id="ea-contact-numbers" aria-label="Contact Numbers by CGI">
<style>
#ea-contact-numbers{margin:16px;padding:15px;background:#101c2d;color:#e5e7eb;border:1px solid #334155;border-radius:10px;font:13px system-ui,Arial,sans-serif}
#ea-contact-numbers h2{font-size:17px;margin:0 0 7px;color:#e8f2ff}
#ea-contact-numbers p{margin:6px 0 12px;color:#b6c6d9}
#ea-contact-numbers .ea-table-wrap{overflow:auto;max-height:44vh}
#ea-contact-numbers table{width:100%;min-width:650px;border-collapse:collapse;background:transparent}
#ea-contact-numbers th,#ea-contact-numbers td{padding:9px 11px;border-bottom:1px solid #344055;text-align:left;vertical-align:top}
#ea-contact-numbers th{background:#1d3659;color:#fff;position:sticky;top:0}
#ea-contact-numbers td:nth-child(3){min-width:230px;max-width:520px;overflow-wrap:anywhere}
#ea-contact-numbers .ea-number{display:inline-block;background:#183859;color:#eff6ff;padding:4px 8px;border-radius:5px;margin:2px}
#ea-contact-numbers details{margin-top:7px}
#ea-contact-numbers summary{color:#93c5fd;cursor:pointer}
#ea-contact-numbers .ea-muted{color:#fbbf24}
</style>
<h2>Contact Numbers by CGI / Tower</h2>
<p>These contact numbers are from the CDR Other Party field. The tower address belongs to the <strong>target handset's serving network</strong>, not the contact's exact location.</p>
<div class="ea-table-wrap"><table>
<thead><tr><th>Interaction / Tower Type</th><th>CGI</th><th>Contact Number(s)</th><th>Tower / CGI Address</th></tr></thead>
<tbody>__EA_ROWS__</tbody></table></div></section>
""".replace("__EA_ROWS__", body)


def render_contact_map_html(points, *, target=""):
    """Preserve the existing map, adding a static contact-by-CGI panel."""
    original = _ea_original_contact_map_renderer(points, target=target)
    if not isinstance(original, str):
        return original
    panel = _ea_build_contact_number_panel(points)
    # Place it at the end of the page without relying on any table, JS or CSS.
    lower = original.lower()
    position = lower.rfind("</body>")
    if position >= 0:
        return original[:position] + panel + "\n" + original[position:]
    position = lower.rfind("</html>")
    if position >= 0:
        return original[:position] + panel + "\n" + original[position:]
    return original + "\n" + panel

