"""Current-run event sources and HTML previews, independent of Excel export."""

from __future__ import annotations

from pathlib import Path
import re
import pandas as pd

from .forensic_intelligence_suite import _frames


def event_frames(sheets):
    candidates = []
    for name, frame in _frames(sheets):
        if frame.empty or frame.attrs.get("source_truncated"):
            continue
        low = name.casefold()
        if frame.attrs.get("row_level_source") or (
            "full" in low and ("cdr" in low or "loaded data" in low)
        ):
            candidates.append((name, frame))
    # A combined full-data sheet supersedes its per-target copies.
    combined = [(n, f) for n, f in candidates if "full loaded data" in n.casefold()]
    return [max(combined, key=lambda item: len(item[1]))] if combined else candidates


def canonical_events(frame):
    aliases = {
        "mobile_subscriber_no": "target_number",
        "subscriber_no": "target_number",
        "other_party_b_party": "b_party",
        "other_party": "b_party",
        "event_date_time": "datetime",
        "date_time": "datetime",
        "first_tower_latitude": "first_cell_latitude",
        "first_tower_longitude": "first_cell_longitude",
        "cell_id_cgi": "first_cell_id",
    }
    names = {}
    for c in frame.columns:
        key = re.sub(r"[^a-z0-9]+", "_", str(c).lower()).strip("_")
        names[c] = aliases.get(key, key)
    result = frame.rename(columns=names)
    return result.loc[:, ~result.columns.duplicated()]


def generate_gui_maps(sheets, directory):
    """Always save diagnostic HTML, including when coordinates cannot be matched."""
    from .cdr_contact_map import generate_cdr_contact_map
    from .cdr_movement_route import generate_multi_cdr_movement_route

    sources = event_frames(sheets)
    if not sources:
        return [], []
    parts = []
    for name, frame in sources:
        part = canonical_events(frame)
        if "target_number" not in part and "a_party" in part:
            part = part.assign(target_number=part["a_party"])
        parts.append(part)
    events = pd.concat(parts, ignore_index=True)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    anchor = directory / "cdr_preview.xlsx"  # Naming anchor only; no workbook is written.
    summaries = [frame for _, frame in _frames(sheets) if "Most Used Target CGI" in frame.columns]
    contact = pd.concat(summaries, ignore_index=True) if summaries else events
    map_path = generate_cdr_contact_map(contact, target="", report_path=anchor)
    route_path = generate_multi_cdr_movement_route(events, report_path=anchor)
    return [str(map_path)], [str(route_path)] if route_path else []
