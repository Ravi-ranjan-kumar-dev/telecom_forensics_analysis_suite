"""Self-contained SVG previews: no CDN scripts, tiles or network access."""
from __future__ import annotations

import html
import json
from pathlib import Path


def render_offline_view(kind: str, payload: dict) -> str:
    title = "Tower coordinate explorer" if kind == "map" else "Communication link explorer"
    data = json.dumps({"kind": kind, **payload}, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    document = _TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__DATA__", data)
    if kind == "map":
        assets = Path(__file__).with_name("assets")
        document = document.replace("/*__MAP_CSS__*/", (assets / "leaflet.css").read_text(encoding="utf-8"))
        document = document.replace("/*__MAP_JS__*/", (assets / "leaflet.js").read_text(encoding="utf-8"))
    return document


_TEMPLATE = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: https://*.tile.openstreetmap.org; connect-src 'none'">
<title>EthicalArmor — __TITLE__</title><style>
/*__MAP_CSS__*/
[hidden]{display:none!important}:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#101827;color:#e7edf6;font:14px system-ui,sans-serif}
header{padding:22px 28px;border-bottom:1px solid #30405a;display:flex;justify-content:space-between;align-items:center}h1{font-size:23px;margin:4px 0}small,.muted{color:#9cacbf}.brand{color:#53dfbf;letter-spacing:2px;font-size:11px;font-weight:700}
.controls{display:flex;flex-wrap:wrap;gap:10px;padding:16px 28px;background:#172237;align-items:center}input,select,button{border:1px solid #3a4d69;border-radius:7px;background:#20314c;color:#fff;padding:9px;font:inherit}input{min-width:240px;flex:1}button{cursor:pointer}button:hover{border-color:#53dfbf}label{display:flex;gap:7px;align-items:center}
main{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:1px;background:#30405a}#viewport{position:relative;height:68vh;min-height:450px;background:#101827;overflow:hidden}#scene{width:100%;height:100%;touch-action:none;cursor:grab}aside{background:#172237;padding:18px;overflow:auto;max-height:68vh}#items button{display:block;width:100%;text-align:left;margin:7px 0}#summary,.note{padding:12px 28px}#summary{color:#53dfbf}.note{color:#b5c3d5;line-height:1.6}#detail{white-space:pre-wrap;line-height:1.7;margin-bottom:18px}#geo{height:100%;background-color:#152239;background-image:linear-gradient(#22334c 1px,transparent 1px),linear-gradient(90deg,#22334c 1px,transparent 1px);background-size:40px 40px}.leaflet-tooltip{color:#172237}.leaflet-control-attribution{font-size:10px}#scene text{fill:#e7edf6;font:12px system-ui;pointer-events:none}#scene .grid{stroke:#29374b;stroke-width:1}#scene .edge{stroke:#4e7196;opacity:.55;cursor:pointer}#scene .edge:hover{stroke:#53dfbf;opacity:1}#scene circle{cursor:pointer}h2{font-size:16px}#mapStatus{position:absolute;top:12px;left:12px;right:12px;z-index:1000;padding:12px;background:#20314c;border:1px solid #eabf66;border-radius:6px;line-height:1.5}#empty{padding:60px;text-align:center;color:#eabf66}@media(max-width:850px){main{grid-template-columns:1fr}aside{max-height:300px}header{padding:16px}#viewport{position:relative;height:55vh}}
</style></head><body><header><div><div class="brand">ETHICALARMOR / ANALYSIS WORKSPACE</div><h1>__TITLE__</h1><small>Self-contained preview · works offline · drag to pan, scroll to zoom</small></div><button onclick="window.print()">Print</button></header>
<div class="controls"><input id="query" type="search" placeholder="Search identifier, CGI or source sheet" aria-label="Search">
<label id="sourceLabel">Target <select id="source"></select></label><label id="limitLabel">Top links <select id="limit"><option>10</option><option selected>20</option><option>50</option><option>100</option></select></label>
<label id="minLabel">Min events <input id="minimum" type="number" min="1" value="1" style="min-width:70px;width:80px;flex:none"></label>
<button id="basemap" hidden>Load street basemap (internet)</button><button id="zoomIn">Zoom +</button><button id="zoomOut">Zoom −</button><button id="fit">Fit view</button></div><div id="summary"></div>
<main><section id="viewport"><div id="mapStatus" role="status">Preparing visualization. If this message remains, JavaScript did not start; use a current browser and regenerate this report.</div><svg id="scene" role="img" aria-label="Interactive analysis visualization"></svg></section><aside><h2>Selection details</h2><div id="detail">Select a point or link.</div><h2>Visible results</h2><div id="items"></div></aside></main>
<div class="note" id="note"></div><script id="data" type="application/json">__DATA__</script><script>/*__MAP_JS__*/</script><script>
"use strict";
const D=JSON.parse(document.getElementById('data').textContent),S=document.getElementById('scene'),NS='http://www.w3.org/2000/svg';
const $=id=>document.getElementById(id);let geo=null,layer=null,markers=[],routes=[],mapFailure="",base=[0,0,1000,600],box=base.slice(),drag=null;
function node(tag,attrs,text){let n=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(attrs||{}))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;S.append(n);return n}
function view(){S.setAttribute('viewBox',box.join(' '))}function zoom(f){box=[box[0]+box[2]*(1-f)/2,box[1]+box[3]*(1-f)/2,box[2]*f,box[3]*f];view()}
$('zoomIn').onclick=()=>geo?geo.zoomIn():zoom(.8);$('zoomOut').onclick=()=>geo?geo.zoomOut():zoom(1.25);$('fit').onclick=()=>{if(geo&&markers.length){geo.fitBounds(L.featureGroup(markers).getBounds().pad(.2),{maxZoom:15})}else{box=base.slice();view()}};
S.onwheel=e=>{e.preventDefault();zoom(e.deltaY>0?1.15:.87)};
S.onpointerdown=e=>{drag=[e.clientX,e.clientY,...box];S.setPointerCapture(e.pointerId)};S.onpointerup=()=>drag=null;
S.onpointermove=e=>{if(drag){const r=S.getBoundingClientRect();box=[drag[2]-(e.clientX-drag[0])*drag[4]/r.width,drag[3]-(e.clientY-drag[1])*drag[5]/r.height,drag[4],drag[5]];view()}};
function detail(text){$('detail').textContent=text}function item(label,action){let b=document.createElement('button');b.textContent=label;b.onclick=action;$('items').append(b)}
function empty(message){node('text',{x:40,y:100},message)}
const sources=[...new Set(D.kind==='map'?(D.points||[]).map(p=>p.subscriber).filter(Boolean):(D.edges||[]).map(e=>e.source))].sort();if(D.kind==='map'){let all=document.createElement('option');all.value='';all.textContent='All targets';$('source').append(all)}for(const v of sources){let o=document.createElement('option');o.value=v;o.textContent=v;$('source').append(o)}
if(D.kind==='map'){for(const id of ['limitLabel','minLabel'])$(id).hidden=true;$('sourceLabel').hidden=sources.length<2;}
if(D.kind==='map'){
try{
if(typeof L==='undefined')throw Error('Bundled map engine unavailable');
let div=document.createElement('div');div.id='geo';$('viewport').append(div);
geo=L.map(div,{zoomControl:false}).setView([20,78],4);S.style.display='none';$('basemap').hidden=false;
$('basemap').onclick=()=>{if(layer){geo.removeLayer(layer);layer=null;$('basemap').textContent='Load street basemap (internet)';return}layer=L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(geo);let warned=false;layer.on('tileerror',()=>{if(!warned){warned=true;$('summary').textContent+=' · Street tiles unavailable; tower coordinates remain visible.'}});$('basemap').textContent='Hide street basemap'};
}catch(error){mapFailure=String(error.message||error);if(geo){geo.remove();geo=null}const div=$('geo');if(div)div.remove();S.style.display='';$('basemap').hidden=true}
}
function status(message){$('mapStatus').textContent=message;$('mapStatus').hidden=!message}
function routeGroups(points){const groups=new Map();for(const p of points){if(!p.route||p.sequence===undefined)continue;let key=p.subscriber||'Single target';if(!groups.has(key))groups.set(key,[]);groups.get(key).push(p)}for(const group of groups.values())group.sort((a,b)=>a.sequence-b.sequence);return [...groups.values()]}
function fallback(points,allPoints){
const lats=points.map(p=>p.lat),lons=points.map(p=>p.lon),minLat=Math.min(...lats),maxLat=Math.max(...lats),minLon=Math.min(...lons),maxLon=Math.max(...lons);
const dx=Math.max(maxLon-minLon,.002),dy=Math.max(maxLat-minLat,.002),cx=(maxLon+minLon)/2,cy=(maxLat+minLat)/2;
const xy=p=>[500+(p.lon-cx)*820/dx,300-(p.lat-cy)*430/dy];
for(let x=80;x<1000;x+=100)node('path',{d:`M${x} 50 V550`,class:'grid'});for(let y=50;y<=550;y+=100)node('path',{d:`M80 ${y} H920`,class:'grid'});
const visible=new Set(points);for(const group of routeGroups(allPoints)){for(let i=1;i<group.length;i++){const a=group[i-1],b=group[i];if(visible.has(a)&&visible.has(b)&&b.sequence===a.sequence+1)node('polyline',{points:[a,b].map(p=>xy(p).join(',')).join(' '),fill:'none',stroke:'#eda96e','stroke-width':3,'stroke-dasharray':'8 5'})}}
points.forEach((p,i)=>{let[x,y]=xy(p),show=()=>detail(pointDetail(p));let circle=node('circle',{cx:x,cy:y,r:8,fill:'#4ed9bf',stroke:'#fff','stroke-width':2});circle.onclick=show;node('text',{x:x+12,y:y-10},p.label||String(i+1));item(`${i+1}. ${p.label||'Tower'}`,show)});
}
function pointDetail(p){return `CGI / event: ${p.label||'Unavailable'}\nLatitude: ${p.lat}\nLongitude: ${p.lon}\nTarget: ${p.subscriber||''}\nSource: ${p.sheet||''}\n${p.description||''}`}
window.addEventListener('error',event=>{status('Visualization error: '+event.message+'. Regenerate this report or use the current desktop update.')});

function render(){S.replaceChildren();$('items').replaceChildren();detail('Select a point or link.');const q=$('query').value.toLowerCase().trim();
if(D.kind==='graph'){
status('');
let edges=(D.edges||[]).filter(e=>(!$('source').value||e.source===$('source').value)&&e.events>=Number($('minimum').value||1)&&(!q||[e.source,e.contact].join(' ').toLowerCase().includes(q))).slice(0,Number($('limit').value));
base=[0,0,1000,Math.max(600,edges.length*36+100)];
const targets=[...new Set(edges.map(e=>e.source))],ys=new Map(targets.map((t,i)=>[t,base[3]*(i+1)/(targets.length+1)]));
for(const[t,y]of ys){node('circle',{cx:160,cy:y,r:19,fill:'#4ed9bf'});node('text',{x:35,y:y-30},'Target / served subscriber');node('text',{x:35,y:y+40},t)}
edges.forEach((e,i)=>{const y=55+i*36,sy=ys.get(e.source);let l=node('path',{d:`M180 ${sy} C410 ${sy},480 ${y},680 ${y}`,fill:'none',class:'edge','stroke-width':Math.min(8,1+Math.log2(e.events+1))});const show=()=>detail(`Target: ${e.source}\\nCounterparty: ${e.contact}\\nEvents: ${e.events}\\nSource table: ${D.source_sheet}\\nAssociation only; call direction is not inferred.`);l.onclick=show;let c=node('circle',{cx:690,cy:y,r:7,fill:'#eda96e'});c.onclick=show;node('text',{x:710,y:y+4},`${e.contact} · ${e.events}`);item(`${e.contact} · ${e.events} events`,show)});
$('summary').textContent=`Showing ${edges.length} of ${D.total_links||0} aggregated links · ${D.source_rows||0} source rows · ${D.skipped_rows||0} rows without usable endpoints`;
$('note').textContent='Links are associations between the served subscriber and counterparty. Width indicates event count. Select a target, raise the minimum count or search to reduce clutter. Counts use one identified source table, never overlapping summary tables. Source: '+(D.source_sheet||'No row-level CDR table found.');
if(!edges.length)empty('No links match these filters. A row-level CDR table with both parties is required.');
}else{
const valid=(D.points||[]).filter(p=>Number.isFinite(p.lat)&&Number.isFinite(p.lon)&&Math.abs(p.lat)<=90&&Math.abs(p.lon)<=180);
const matched=valid.filter(p=>(!$('source').value||p.subscriber===$('source').value)&&(!q||JSON.stringify(p).toLowerCase().includes(q))),pts=matched.slice(0,1000);base=[0,0,1000,600];
status(!valid.length?'No usable tower coordinates. '+(D.diagnostics?.message||'Check CGI matching and latitude/longitude in the master database.'):!pts.length?'No points match this search.':mapFailure?'Map engine unavailable; showing an offline coordinate plot. '+mapFailure:'');
if(geo){try{
markers.concat(routes).forEach(m=>geo.removeLayer(m));markers=[];routes=[];
pts.forEach((p,i)=>{const show=()=>{detail(pointDetail(p));geo.panTo([p.lat,p.lon])};let label=document.createElement('span');label.textContent=p.label||'Tower';let m=L.circleMarker([p.lat,p.lon],{radius:7,color:'#101827',weight:2,fillColor:'#4ed9bf',fillOpacity:.9}).addTo(geo).bindTooltip(label);m.on('click',show);markers.push(m);item(`${i+1}. ${p.label||'Tower'}`,show)});
// Connect only consecutive chronological observations belonging to the same target.
// Search/caps must not fabricate a new adjacency across omitted observations.
const visible=new Set(pts);
for(const group of routeGroups(valid)){for(let i=1;i<group.length;i++){const a=group[i-1],b=group[i];if(visible.has(a)&&visible.has(b)&&b.sequence===a.sequence+1)routes.push(L.polyline([[a.lat,a.lon],[b.lat,b.lon]],{color:'#eda96e',weight:3,dashArray:'8 5'}).addTo(geo))}}
geo.invalidateSize();if(markers.length)geo.fitBounds(L.featureGroup(markers).getBounds().pad(.2),{maxZoom:15});requestAnimationFrame(()=>geo.invalidateSize());
}catch(error){mapFailure=String(error.message||error);try{geo.remove()}catch(ignored){}geo=null;const div=$('geo');if(div)div.remove();S.style.display='';$('basemap').hidden=true;S.replaceChildren();$('items').replaceChildren();fallback(pts,valid);status('Map rendering unavailable; showing an offline coordinate plot. '+mapFailure)}}else if(pts.length){fallback(pts,valid)}else{empty('No usable coordinates to display.')}
$('summary').textContent=`Showing ${pts.length} of ${matched.length} matching points (${valid.length} total) · offline tower layer; search to refine`;
if(D.diagnostics)$('summary').textContent+=' · '+(D.diagnostics.message||'');
$('note').textContent='Tower points work offline. Street basemap is optional and requests internet tiles only when enabled; blocked tiles do not remove your tower layer. Locations are network tower coordinates, not exact handset positions or the exact road travelled. Dashed links, where present, connect chronological tower observations of one target; they are not road routes. Different targets are never joined.';

}box=base.slice();view()}
for(const id of ['query','source','limit','minimum'])$(id).addEventListener('input',render);render();
</script></body></html>'''
