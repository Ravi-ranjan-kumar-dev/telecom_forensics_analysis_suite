"""Create repaired copies of existing EthicalArmor map HTML; originals stay unchanged."""
from __future__ import annotations

import argparse
import ast
from html.parser import HTMLParser
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class MapPayload(HTMLParser):
    def __init__(self):
        super().__init__(); self.active=False; self.parts=[]

    def handle_starttag(self, tag, attrs):
        if tag=='script' and dict(attrs).get('id')=='data':self.active=True

    def handle_endtag(self, tag):
        if tag=='script':self.active=False

    def handle_data(self, data):
        if self.active:self.parts.append(data)


def repair(path):
    from modules.reporting.offline_views import render_offline_view
    parser=MapPayload();parser.feed(path.read_text(encoding='utf-8'))
    if not parser.parts:return None
    payload=json.loads(''.join(parser.parts))
    if not isinstance(payload,dict) or payload.get('kind')!='map':return None
    points=payload.get('points',[])
    if not isinstance(points,list):raise ValueError('Map points must be a list')
    for point in points:
        if not isinstance(point,dict):raise ValueError('Malformed point record')
        if point.get('sheet')=='Chronological tower events' and 'sequence' not in point:
            try:
                detail=ast.literal_eval(str(point.get('description',''))[:10000])
                if isinstance(detail,dict):
                    point['subscriber']=str(detail.get('target',''))
                    point['sequence']=int(detail.get('sequence',0))
                    point['route']=bool(detail.get('timestamp')) and detail['timestamp']!='Time unavailable'
            except (ValueError,TypeError,SyntaxError,RecursionError):
                point['route']=False
    if not points:
        payload['diagnostics']={'message':'This saved HTML contains zero coordinates. Generate a fresh analysis to resolve CGI locations from the selected master.'}
    output=path.with_name(path.stem+'.repaired.html')
    if output.exists():return ('EXISTS',str(output),len(points))
    document=render_offline_view('map',payload)
    with output.open('x',encoding='utf-8') as handle:
        handle.write(document)
    return ('REPAIRED',str(output),len(points))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--input',type=Path,help='Repair one HTML instead of scanning project output and cases')
    args=parser.parse_args();project=args.project.expanduser().resolve()
    candidates=[args.input.expanduser().resolve()] if args.input else sorted({p for folder in (project/'output',project/'cases') if folder.is_dir() for p in folder.rglob('*.html') if not p.name.endswith('.repaired.html')})
    count=0;errors=0
    for path in candidates:
        try:
            result=repair(path)
            if result:print(json.dumps({'status':result[0],'path':result[1],'embedded_points':result[2]}));count+=1
        except (OSError,ValueError,TypeError) as error:
            errors+=1;print(f'SKIPPED {path}: {type(error).__name__}',file=sys.stderr)
    print(f'{count} map copies available; {errors} errors. Original HTML files were not changed.')
    return 1 if errors else 0


if __name__=='__main__':raise SystemExit(main())
