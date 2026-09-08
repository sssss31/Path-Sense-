"use client";
import {useEffect,useMemo,useRef,useState} from "react";
import {useQuery} from "@tanstack/react-query";
import {CircleMarker,GeoJSON,MapContainer,Polyline,Popup,TileLayer,WMSTileLayer,useMap,useMapEvents} from "react-leaflet";
import type {Feature,FeatureCollection} from "geojson";
import {AlertTriangle,ShieldAlert,X} from "lucide-react";
import {ApiError,api,platformApi} from "@/lib/platform-api";
import {HAZARD_STATUS_TEXT,PROVENANCE_TEXT,dateOnly,label} from "@/lib/format";
import type {Coordinate,ExternalLayer,SpatialRiskSummary} from "@/lib/types";

type Bounds={min_lat:number;min_lon:number;max_lat:number;max_lon:number};
const colors=["#4e9b70","#6ea574","#d39a36","#d35f4f","#7d2727"];
const ROUTE_COLORS:Record<string,string>={low:"#2f8f5b",moderate:"#c98a1c",high:"#c94b3f",critical:"#4a3aa7"};
const url=(path:string,b:Bounds,extra:Record<string,string>={})=>`${path}?${new URLSearchParams({...Object.fromEntries(Object.entries(b).map(([k,v])=>[k,String(v)])),...extra})}`;

function BoundsWatcher({onChange}:{onChange:(value:Bounds)=>void}){
  const timer=useRef(0);
  const map=useMapEvents({moveend(){window.clearTimeout(timer.current);timer.current=window.setTimeout(()=>{const b=map.getBounds();onChange({min_lat:+b.getSouth().toFixed(4),min_lon:+b.getWest().toFixed(4),max_lat:+b.getNorth().toFixed(4),max_lon:+b.getEast().toFixed(4)})},450)}});
  useEffect(()=>{map.fire("moveend")},[map]);return null;
}
function FitRoute({points}:{points:Coordinate[]}){const map=useMap();useEffect(()=>{if(points.length<2)return;const id=window.requestAnimationFrame(()=>{map.invalidateSize();map.fitBounds(points.map(p=>[p.lat,p.lng] as [number,number]),{padding:[40,40],maxZoom:12})});return()=>window.cancelAnimationFrame(id)},[map,points]);return null}

/** Popup text states a relationship only when the backend spatial summary confirms it. */
function relationText(feature:Feature,summary:SpatialRiskSummary|undefined,kind:"zone"|"incident"){
  if(!summary||summary.hazard_status==="unavailable")return "";
  const id=String(feature.id??"");
  if(kind==="zone"){if(summary.intersecting_zone_ids.includes(id))return "<br/><strong style='color:#b3261e'>Selected route intersects this zone</strong>";if(summary.nearby_zone_ids.includes(id))return "<br/><strong style='color:#875910'>Near selected route (within 2 km)</strong>";return "<br/><em>Not related to the selected route</em>"}
  return summary.nearby_incident_ids.includes(id)?"<br/><strong style='color:#875910'>Within 2 km of selected route</strong>":"<br/><em>Not near the selected route</em>";
}
const esc=(v:unknown)=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c] as string));

export function RiskMapView({initialAnalysisId}:{initialAnalysisId?:string}){
  const[bounds,setBounds]=useState<Bounds>({min_lat:24.9,min_lon:90,max_lat:26.7,max_lon:92.5});
  const[layers,setLayers]=useState({zones:true,incidents:true,alternatives:false,reports:false});
  const[source,setSource]=useState("all");
  const[externalOn,setExternalOn]=useState<Record<string,boolean>>({});
  const[selectedId,setSelectedId]=useState<string>(initialAnalysisId||"");
  useEffect(()=>{if(initialAnalysisId)setSelectedId(initialAnalysisId)},[initialAnalysisId]);
  const readiness=useQuery({queryKey:["readiness"],queryFn:platformApi.readiness,staleTime:60000,retry:0});
  const live=readiness.data?.mode==="live";
  const datasets=useQuery({queryKey:["datasets"],queryFn:platformApi.datasets,staleTime:120000,retry:0});
  const external=useQuery({queryKey:["map-layers"],queryFn:platformApi.mapLayers,staleTime:600000,retry:0});
  const filter:Record<string,string>=source==="all"?{}:{dataset:source};
  const zones=useQuery({queryKey:["risk-zones",bounds,source],queryFn:()=>api<FeatureCollection>(url("/risk-zones",bounds,filter)),staleTime:60000,enabled:layers.zones,retry:0});
  const incidents=useQuery({queryKey:["incidents",bounds,source],queryFn:()=>api<FeatureCollection>(url("/incidents",bounds,filter)),staleTime:60000,enabled:layers.incidents,retry:0});
  const reports=useQuery({queryKey:["user-reports",bounds],queryFn:()=>api<FeatureCollection>(url("/user-reports",bounds)),staleTime:60000,enabled:layers.reports,retry:0});
  const history=useQuery({queryKey:["history-selector"],queryFn:()=>platformApi.history(1,50),staleTime:60000,retry:0});
  const route=useQuery({queryKey:["analysis-map",selectedId,layers.alternatives],queryFn:()=>platformApi.analysisMap(selectedId,layers.alternatives),enabled:!!selectedId,staleTime:300000,retry:0});
  const summary=useQuery({queryKey:["spatial-risk",selectedId],queryFn:()=>platformApi.spatialRisk(selectedId),enabled:!!selectedId,staleTime:120000,retry:0});
  const s=summary.data;const rec=route.data?.recommended_route;
  const points=useMemo(()=>rec?.geometry||[],[rec]);
  const routeGone=route.error instanceof ApiError&&route.error.status===404;
  const zoneStyle=(feature?:Feature)=>{const severity=Number(feature?.properties?.severity||1);const id=String(feature?.id??"");const crosses=!!s&&s.intersecting_zone_ids.includes(id);const near=!!s&&s.nearby_zone_ids.includes(id);const sus=feature?.properties?.layer_type==="landslide_susceptibility";const flood=String(feature?.properties?.layer_type||"").startsWith("flood");const base=flood?"#2b6cb0":colors[severity-1];return {color:crosses?"#b3261e":base,fillColor:base,fillOpacity:selectedId?(crosses?.32:near?.2:.08):sus?.14:.18,weight:crosses?2.5:near?2:1.5,dashArray:near?"4 3":sus?"2 3":undefined}};
  const datasetOptions=(datasets.data?.items||[]).filter(d=>d.status==="imported"&&(!live||d.provenance!=="simulated"));
  const externalLayers:ExternalLayer[]=external.data?.items||[];
  const attribution="© OpenStreetMap contributors"; // official WMS layers carry their own attribution via WMSTileLayer
  return <div className="riskMapWrap">
    <div className="riskControls">
      <strong>Saved route overlay</strong>
      <select value={selectedId} onChange={e=>setSelectedId(e.target.value)} disabled={history.isLoading}><option value="">— No route selected —</option>{history.data?.items.map(h=><option key={h.analysis_id} value={h.analysis_id}>{h.source} → {h.destination} · {dateOnly(h.created_at)} · A{h.accessibility??"—"} · {h.risk_level??"—"}</option>)}</select>
      {history.isError&&<small className="warn">Route history unavailable.</small>}
      {selectedId&&<button type="button" className="clearBtn" onClick={()=>setSelectedId("")}><X size={12}/> Clear route</button>}
      <strong>Dataset source</strong>
      <select value={source} onChange={e=>setSource(e.target.value)}><option value="all">All {live?"authoritative":"imported"} datasets</option>{datasetOptions.map(d=><option key={d.slug} value={d.slug}>{d.layer_label||label(d.layer_type)} · {d.organization}{d.provenance==="simulated"?" (simulated demo)":""}</option>)}{!live&&<option value="simulated">Simulated demo only</option>}<option value="authoritative">Authoritative only</option></select>
      <strong>Local layers (PostGIS)</strong>
      <label><input type="checkbox" checked={layers.zones} onChange={()=>setLayers(x=>({...x,zones:!x.zones}))}/>Hazard &amp; susceptibility zones</label>
      <label><input type="checkbox" checked={layers.incidents} onChange={()=>setLayers(x=>({...x,incidents:!x.incidents}))}/>Historical landslide inventory / incidents</label>
      <label><input type="checkbox" checked={layers.reports} onChange={()=>setLayers(x=>({...x,reports:!x.reports}))}/>Reported road issues (unverified)</label>
      <label><input type="checkbox" checked={layers.alternatives} disabled={!selectedId} onChange={()=>setLayers(x=>({...x,alternatives:!x.alternatives}))}/>Alternative routes</label>
      {externalLayers.length>0&&<><strong>Official remote layers (WMS)</strong>{externalLayers.slice(0,6).map(l=><label key={l.id} title={l.note||""}><input type="checkbox" checked={!!externalOn[l.id]} onChange={()=>setExternalOn(x=>({...x,[l.id]:!x[l.id]}))}/>{l.name} <span className="badge historical" style={{marginLeft:4}}>{PROVENANCE_TEXT[l.provenance]||l.provenance}</span></label>)}<small>{externalLayers[0].organization} · rendered remotely, never a current flood alert</small></>}
      {external.isError&&<small className="warn">Official remote layers unavailable; local layers remain usable.</small>}
      <small>{zones.isFetching||incidents.isFetching?"Updating viewport…":zones.data&&incidents.data&&!zones.data.features.length&&!incidents.data.features.length?"No hazard features in this viewport":"Viewport data current"}</small>
    </div>
    <MapContainer center={[25.65,91.35]} zoom={8} className="leafletMap"><TileLayer attribution={attribution} url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/><BoundsWatcher onChange={setBounds}/>
      {externalLayers.filter(l=>externalOn[l.id]&&l.kind==="wms").map(l=><WMSTileLayer key={l.id} url={l.url} layers={l.layers} format={l.format} transparent={l.transparent} version={l.version} opacity={l.opacity} attribution={l.attribution}/>)}
      {layers.zones&&zones.data&&<GeoJSON key={`${JSON.stringify(bounds)}-${selectedId}-${s?.route_id??""}-${source}`} data={zones.data} style={zoneStyle} onEachFeature={(feature,layer)=>{const p=feature.properties||{};layer.bindPopup(`<strong>${esc(p.label||p.category||"Hazard zone")}</strong><br/>${esc(p.layer_label||"")}${p.original_class?`<br/>Source class: ${esc(p.original_class)}`:""}<br/>Severity: ${esc(p.severity??"Unknown")}<br/>Dataset: ${esc(p.dataset||p.source||"Unknown")}<br/>Provenance: ${esc(p.provenance||"historical")}${p.attribution?`<br/><small>${esc(p.attribution)}</small>`:""}${relationText(feature,s,"zone")}`)}}/>}
      {layers.incidents&&incidents.data?.features.map((feature)=>{const id=String(feature.id);const near=!!s&&s.nearby_incident_ids.includes(id);const p=feature.properties||{};const [lng,lat]=(feature.geometry as {coordinates:number[]}).coordinates;return <CircleMarker key={id} center={[lat,lng]} radius={near?7:5} pathOptions={{color:near?"#875910":colors[Math.max(0,(p.severity||1)-1)],fillColor:colors[Math.max(0,(p.severity||1)-1)],fillOpacity:selectedId&&!near?.45:.85,weight:near?2:1}}><Popup><strong>{p.layer_label||"Historical incident"} · {label(p.category)}</strong><br/>{p.severity_known?`Severity: ${p.severity}`:"Severity: not published (default)"}<br/>Occurred: {dateOnly(p.occurred_at)}<br/>Dataset: {p.dataset||p.source}{p.external_id&&<><br/>Source ID: {p.external_id}</>}<br/><em>{PROVENANCE_TEXT[p.provenance]||"Historical"} observed event · not a live alert</em>{p.attribution&&<><br/><small>{p.attribution}</small></>}<span dangerouslySetInnerHTML={{__html:relationText(feature,s,"incident")}}/></Popup></CircleMarker>})}
      {layers.reports&&reports.data?.features.map((feature)=>{const p=feature.properties||{};const [lng,lat]=(feature.geometry as {coordinates:number[]}).coordinates;return <CircleMarker key={String(feature.id)} center={[lat,lng]} radius={6} pathOptions={{color:"#6b3fa0",fillColor:"#c9b3ea",fillOpacity:.9,weight:1.5}}><Popup><strong>{p.label||"Reported Road Issue"}</strong><br/>{label(p.category)} · {p.verification_status}<br/>{p.description}<br/>Reported: {dateOnly(p.reported_at)}<br/><em>Operator report · not a verified closure</em></Popup></CircleMarker>})}
      {rec&&<FitRoute points={points}/>}
      {layers.alternatives&&route.data?.alternatives.map(a=><Polyline key={a.id} positions={a.geometry.map(p=>[p.lat,p.lng] as [number,number])} pathOptions={{color:"#6b7a88",weight:3,opacity:.6,dashArray:"6 5"}}><Popup><strong>{a.name}</strong><br/>Alternative · accessibility {a.accessibility??"—"} · {a.risk_level} risk</Popup></Polyline>)}
      {rec&&<Polyline positions={points.map(p=>[p.lat,p.lng] as [number,number])} pathOptions={{color:ROUTE_COLORS[rec.risk_level||"moderate"]||"#2b6cb0",weight:6,opacity:.95}}><Popup><strong>{rec.name}</strong><br/>Recommended · accessibility {rec.accessibility} · {rec.risk_level} risk<br/>{rec.distance_km} km</Popup></Polyline>}
      {route.data?.source&&<CircleMarker center={[route.data.source.coordinate.lat,route.data.source.coordinate.lng]} radius={8} pathOptions={{color:"#fff",fillColor:"#1f66ed",fillOpacity:1,weight:2}}><Popup><strong>Source</strong><br/>{route.data.source.name}</Popup></CircleMarker>}
      {route.data?.destination&&<CircleMarker center={[route.data.destination.coordinate.lat,route.data.destination.coordinate.lng]} radius={8} pathOptions={{color:"#fff",fillColor:"#1b2a3a",fillOpacity:1,weight:2}}><Popup><strong>Destination</strong><br/>{route.data.destination.name}</Popup></CircleMarker>}
    </MapContainer>
    <div className="riskLegend">{[["Low",colors[0]],["Moderate",colors[2]],["High",colors[3]],["Critical",colors[4]]].map(([name,color])=><span key={name}><i style={{background:color}}/>{name}</span>)}<span><i style={{background:"#2b6cb0"}}/>Flood hazard</span>{selectedId&&<span><i style={{background:"#b3261e"}}/>Intersects route</span>}</div>
    {selectedId&&<aside className="routePanel">
      <div className="routePanelHead"><span className="eyebrow">SELECTED ROUTE</span>{route.data?<strong>{route.data.source.name} → {route.data.destination.name}</strong>:<strong>{routeGone?"Route unavailable":"Loading route…"}</strong>}</div>
      {routeGone?<div className="panelAlert"><AlertTriangle size={14}/><span>This saved analysis has been deleted. Choose another route.</span></div>:route.isError?<div className="panelAlert"><AlertTriangle size={14}/><span>Route geometry could not be loaded.</span></div>:rec&&<p className="routeMeta">{rec.name} · {rec.distance_km} km · accessibility {rec.accessibility} · <span className={`risk ${rec.risk_level}`}>{rec.risk_level} risk</span></p>}
      <div className="routePanelHead"><span className="eyebrow">SPATIAL RISK SUMMARY</span></div>
      {summary.isLoading?<small>Evaluating route against hazard datasets…</small>:summary.isError?<div className="panelAlert"><AlertTriangle size={14}/><span>{summary.error instanceof ApiError&&summary.error.status===404?"Spatial summary unavailable for a deleted route.":"Route spatial summary unavailable. Hazard layers remain usable."}</span></div>:s&&<>
        <div className={`hazardState ${s.hazard_status}`}><ShieldAlert size={14}/><span>{HAZARD_STATUS_TEXT[s.hazard_status]||label(s.hazard_status)}</span></div>
        <dl className="panelStats">
          <div><dt>Hazard zones crossed</dt><dd>{s.zones_crossed??"—"}</dd></div>
          <div><dt>Landslide exposure</dt><dd>{s.landslide_exposure_km==null?"—":`${s.landslide_exposure_km} km`}</dd></div>
          <div><dt>Flood exposure</dt><dd>{s.flood_exposure_km==null?"—":`${s.flood_exposure_km} km`}</dd></div>
          <div><dt>Affected distance</dt><dd>{s.affected_distance_km==null?"—":`${s.affected_distance_km} km`}</dd></div>
          <div><dt>Highest severity</dt><dd>{label(s.highest_severity)}</dd></div>
          <div><dt>Historical incidents nearby</dt><dd>{s.historical_incidents_nearby??"—"}</dd></div>
          <div><dt>Confidence</dt><dd>{Math.round(s.confidence*100)}%</dd></div>
          <div><dt>Coverage</dt><dd>{s.coverage_ratio==null?"unknown":`${Math.round(s.coverage_ratio*100)}%`}</dd></div>
        </dl>
        {s.datasets.length>0&&<small>Datasets: {s.datasets.join(", ")} · {PROVENANCE_TEXT[s.provenance]||s.provenance}</small>}
        {[...s.reasons,...s.confidence_reasons].filter((r,i,a)=>a.indexOf(r)===i).map(r=><small key={r} className="reason">{r}</small>)}
      </>}
    </aside>}
    {(zones.isError||incidents.isError||reports.isError)&&<div className="mapError">{[zones.isError&&"hazard zones",incidents.isError&&"incidents",reports.isError&&"reported issues"].filter(Boolean).join(", ")} layer unavailable. The map remains usable.</div>}
  </div>;
}
