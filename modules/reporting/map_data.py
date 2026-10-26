"""Coordinate extraction and bounded CGI hydration for generated map artifacts."""
from __future__ import annotations

import math
import re


def key(value):
    return re.sub(r'[^a-z0-9]', '', str(value).lower())


def coordinate_pair(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
    except (ValueError, TypeError):
        return None
    return (lat, lon) if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180 else None


def collect_map_points(frames):
    from modules.database.cgi_repository import normalize_cgi
    from modules.enrichment.cgi_address_enrichment import lookup_cgi_addresses
    from .forensic_intelligence_suite import _cell_text

    specifications = [
        ('latitude','longitude','first'),('lat','lon','first'),('lat','lng','first'),
        ('Most Used Latitude','Most Used Longitude','most'),
        ('Last Interaction Latitude','Last Interaction Longitude','interaction'),
    ]
    for prefix, kind in [('first_cell','first'),('last_cell','last'),('first_cgi','first'),('last_cgi','last'),
                         ('tower','first'),('cgi','first'),('cell','first'),('cell_id_cgi','first'),
                         ('searched_cell','searched'),('searched_tower','searched'),('First Tower','first'),('Last Tower','last')]:
        specifications.append((prefix+'_latitude',prefix+'_longitude',kind))
    aliases = {
        'first': ('first_cgi','first_cell_id','cgi','cell_id','Cell ID / CGI','Tower','Tower ID'),
        'last': ('last_cgi','last_cell_id'),
        'searched': ('searched_cell_id','Searched Cell ID','cgi','cell_id'),
        'most': ('Most Used Target CGI',), 'interaction': ('Last Interaction CGI',),
    }
    points=[]; seen=set(); missing=set(); requested=set(); errors=[]
    def add(lat,lon,cgi,target,sheet):
        signature=(lat,lon,cgi,target)
        if signature not in seen:
            seen.add(signature)
            points.append({'lat':lat,'lon':lon,'label':cgi or 'CGI unavailable','subscriber':target,'sheet':sheet})
    for sheet, frame in frames:
        colmap={key(c):c for c in frame.columns}
        def col(names):return next((colmap[key(n)] for n in names if key(n) in colmap),None)
        target_col=col(('target_number','a_party','Target','subscriber_number','Mobile / Subscriber No.'))
        pairs=[(col((a,)),col((b,)),kind) for a,b,kind in specifications if col((a,)) is not None and col((b,)) is not None]
        cgi_cols={kind:col(names) for kind,names in aliases.items()}
        # Scan only relevant columns; avoid copying unrelated evidence fields.
        columns=list(dict.fromkeys(c for c in [target_col,*cgi_cols.values(),*(v for a,b,_ in pairs for v in (a,b))] if c is not None))
        for values in frame[columns].itertuples(index=False,name=None):
            row=dict(zip(columns,values));target=_cell_text(row.get(target_col,''));located=set()
            for a,b,kind in pairs:
                pair=coordinate_pair(row.get(a),row.get(b))
                if pair is not None:
                    cgi=_cell_text(row.get(cgi_cols[kind],''))
                    add(*pair,cgi,target,sheet);located.add(kind)
            for kind,c in cgi_cols.items():
                if c is None or kind in located:continue
                cgi=normalize_cgi(row.get(c))
                if cgi:
                    missing.add((cgi,target,sheet));requested.add(cgi)
    locations={}
    ordered=sorted(requested)
    for offset in range(0,len(ordered),1000):
        try:
            found=lookup_cgi_addresses(ordered[offset:offset+1000])
            for record in found.to_dict(orient='records'):
                pair=coordinate_pair(record.get('latitude'),record.get('longitude'))
                if pair is not None:locations[normalize_cgi(record.get('cgi'))]=pair
        except Exception as error:
            errors.append(type(error).__name__)
            break
    for cgi,target,sheet in sorted(missing):
        if cgi in locations:add(*locations[cgi],cgi,target,sheet)
    message=f'{len(points)} coordinate points; {len(locations)} of {len(requested)} CGI keys resolved from master.'
    if errors:message+=' CGI lookup failed ('+errors[0]+'); check database access.'
    if not points:message+=' No usable coordinates were supplied or matched. Verify the input CGI format and master coverage.'
    return points,{'message':message,'lookup_candidates':len(requested),'lookup_matches':len(locations),'lookup_errors':errors}
