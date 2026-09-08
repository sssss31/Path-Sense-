"use client";
import "leaflet/dist/leaflet.css";
import {useEffect,useMemo,useState} from "react";
import {useQuery} from "@tanstack/react-query";
import L from "leaflet";
import {CircleMarker,GeoJSON,MapContainer,Marker,Polyline,Popup,TileLayer,useMap} from "react-leaflet";
import type {Feature,FeatureCollection} from "geojson";
import {Layers3} from "lucide-react";
import {useOptionalUser} from "@/features/auth/optional-user";
import {api} from "@/lib/platform-api";
import type {Analysis,Coordinate} from "@/lib/types";
import {useAppStore} from "@/store/app";

const ROUTE_COLORS:Record<string,string>={low:"#2f8f5b",moderate:"#c98a1c",high:"#c94b3f",critical:"#4a3aa7"};
const SEVERITY=["#4e9b70","#6ea574","#d39a36","#d35f4f","#7d2727"];

function FitAll({points}:{points:Coordinate[]}){const map=useMap();useEffect(()=>{if(points.length<2)return;const id=window.requestAnimationFrame(()=>{map.invalidateSize();map.fitBounds(points.map(p=>[p.lat,p.lng] as [number,number]),{padding:[30,30],maxZoom:12})});return()=>window.cancelAnimationFrame(id)},[map,points]);return null}
function FocusPoint(){const map=useMap();const focus=useAppStore(s=>s.focusPoint);useEffect(()=>{if(focus)map.flyTo([focus.lat,focus.lng],Math.max(map.getZoom(),13),{duration:.6})},[map,focus]);return null}
function bbox(points:Coordinate[]){const lats=points.map(p=>p.lat),lngs=points.map(p=>p.lng);const pad=.08;return {min_lat:(Math.min(...lats)-pad).toFixed(4),min_lon:(Math.min(...lngs)-pad).toFixed(4),max_lat:(Math.max(...lats)+pad).toFixed(4),max_lon:(Math.max(...lngs)+pad).toFixed(4)}}
/** Direction arrows: rotated markers sampled along the selected route so travel direction is visible. */
type Arrow={pos:[number,number];angle:number;color:string};
function arrows(points:Coordinate[],color:string,count=12):Arrow[]{if(points.length<2)return [];const step=Math.max(1,Math.floor(points.length/count));const out:Arrow[]=[];for(let i=step;i<points.length-1;i+=step){const a=points[i-1],b=points[i];const angle=Math.atan2(b.lng-a.lng,b.lat-a.lat)*180/Math.PI;out.push({pos:[b.lat,b.lng],angle,color})}return out}
const arrowIcon=(angle:number,color:string)=>L.divIcon({className:"",html:`<div style="width:16px;height:16px;transform:rotate(${angle}deg);display:grid;place-items:center"><svg width="16" height="16" viewBox="0 0 16 16"><path d="M8 1 L14 13 L8 10 L2 13 Z" fill="${color}" stroke="#fff" stroke-width="1"/></svg></div>`,iconSize:[16,16],iconAnchor:[8,8]});

/** OpenStreetMap/Leaflet renderer: route geometries with direction arrows, hazard layers, step markers, clickable alternatives. */
export function AnalysisMap({analysis,googleAvailable}:{analysis:Analysis;googleAvailable:boolean}){
  const {selectedRoute,setRoute,setMapProvider}=useAppStore();const {user}=useOptionalUser();
  const[showHazards,setShowHazards]=useState(true);
  const selected=analysis.routes.find(r=>r.id===selectedRoute)||analysis.routes[0];
  const all=useMemo(()=>analysis.routes.flatMap(r=>r.geometry),[analysis]);
  const color=ROUTE_COLORS[selected.risk.level]||"#2b6cb0";
  const arrowMarks=useMemo(()=>arrows(selected.geometry,color),[selected.geometry,color]);
  const zones=useQuery({queryKey:["analysis-hazards",analysis.analysis_id],queryFn:()=>api<FeatureCollection>(`/risk-zones?${new URLSearchParams(bbox(all))}`),enabled:!!user&&all.length>1&&showHazards,staleTime:120000,retry:0});
  const incidents=useQuery({queryKey:["analysis-incidents",analysis.analysis_id],queryFn:()=>api<FeatureCollection>(`/incidents?${new URLSearchParams(bbox(all))}`),enabled:!!user&&all.length>1&&showHazards,staleTime:120000,retry:0});
  const center:[number,number]=[analysis.source.coordinate.lat,analysis.source.coordinate.lng];
  const hazardCount=(zones.data?.features.length||0)+(incidents.data?.features.length||0);
  const status=!user?"Sign in to overlay hazard datasets":zones.isLoading||incidents.isLoading?"Loading hazard layers…":zones.isError||incidents.isError?"Hazard layers unavailable":`${hazardCount} hazard feature(s) in corridor · OpenStreetMap`;
  const steps=(selected.directions||[]).filter(s=>s.location&&!s.maneuver.startsWith("depart")&&!s.maneuver.startsWith("arrive"));
  const every=Math.max(1,Math.ceil(steps.length/12));
  return <div className="map">
    <MapContainer center={center} zoom={9} className="leafletMap" scrollWheelZoom={false}>
      <TileLayer attribution="© OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>
      <FitAll points={all}/><FocusPoint/>
      {showHazards&&zones.data&&<GeoJSON key={analysis.analysis_id} data={zones.data} style={(f?:Feature)=>{const sev=Number(f?.properties?.severity||1);const flood=String(f?.properties?.layer_type||"").startsWith("flood");return {color:flood?"#2b6cb0":SEVERITY[sev-1],fillColor:flood?"#2b6cb0":SEVERITY[sev-1],fillOpacity:.14,weight:1.2,dashArray:f?.properties?.layer_type==="landslide_susceptibility"?"2 3":undefined}}} onEachFeature={(f,layer)=>{const p=f.properties||{};layer.bindPopup(`<strong>${p.label||p.category}</strong><br/>${p.layer_label||""}<br/>Severity: ${p.severity} · ${p.provenance}<br/>Dataset: ${p.dataset||p.source||""}`)}}/>}
      {showHazards&&incidents.data?.features.map(f=>{const [lng,lat]=(f.geometry as {coordinates:number[]}).coordinates;const p=f.properties||{};return <CircleMarker key={String(f.id)} center={[lat,lng]} radius={4} pathOptions={{color:SEVERITY[Math.max(0,(p.severity||1)-1)],fillOpacity:.8,weight:1}}><Popup><strong>{p.layer_label||"Historical incident"}</strong><br/>{p.category} · severity {p.severity}<br/>{p.dataset||p.source}<br/><em>{p.provenance} observed event</em></Popup></CircleMarker>})}
      {analysis.routes.filter(r=>r.id!==selected.id).map(r=><Polyline key={r.id} positions={r.geometry.map(p=>[p.lat,p.lng] as [number,number])} pathOptions={{color:"#6b7a88",weight:4,opacity:.55,dashArray:"6 5"}} eventHandlers={{click:()=>setRoute(r.id)}}><Popup><strong>{r.name}</strong><br/>Accessibility {r.accessibility.score} · {r.risk.level} risk · {r.distance_km} km<br/><em>Click to select</em></Popup></Polyline>)}
      <Polyline key={`sel-${selected.id}`} positions={selected.geometry.map(p=>[p.lat,p.lng] as [number,number])} pathOptions={{color,weight:6,opacity:.95}}><Popup><strong>{selected.name}</strong><br/>Accessibility {selected.accessibility.score} · {selected.risk.level} risk · {selected.distance_km} km</Popup></Polyline>
      {arrowMarks.map((a,i)=><Marker key={`arrow-${selected.id}-${i}`} position={a.pos} icon={arrowIcon(a.angle,a.color)} interactive={false}/>)}
      {steps.map((s,i)=>i%every===0&&s.location?<CircleMarker key={`step-${selected.id}-${i}`} center={[s.location.lat,s.location.lng]} radius={4} pathOptions={{color,fillColor:"#fff",fillOpacity:1,weight:2}}><Popup><strong>Step</strong><br/>{s.instruction}</Popup></CircleMarker>:null)}
      <CircleMarker center={[analysis.source.coordinate.lat,analysis.source.coordinate.lng]} radius={8} pathOptions={{color:"#fff",fillColor:"#1f66ed",fillOpacity:1,weight:2}}><Popup><strong>Origin</strong><br/>{analysis.source.name}</Popup></CircleMarker>
      <CircleMarker center={[analysis.destination.coordinate.lat,analysis.destination.coordinate.lng]} radius={8} pathOptions={{color:"#fff",fillColor:"#1b2a3a",fillOpacity:1,weight:2}}><Popup><strong>Destination</strong><br/>{analysis.destination.name}</Popup></CircleMarker>
    </MapContainer>
    <div className="mapStatus">{status}</div>
    <div className="mapProvider"><button type="button" onClick={()=>setMapProvider("google")} disabled={!googleAvailable} title={googleAvailable?"Switch to Google Maps":"Set NEXT_PUBLIC_GOOGLE_MAPS_API_KEY to enable Google Maps"}>Google</button><button type="button" className="on">OpenStreetMap</button></div>
    <button className="layers" onClick={()=>setShowHazards(v=>!v)}><Layers3 size={16}/> Hazard layers <b>{showHazards?"on":"off"}</b></button>
    <div className="mapLegend"><span><i className="safe"/>Selected (arrows = direction)</span><span><i className="alternative"/>Alternative</span><span><i className="danger"/>Hazard zone</span></div>
  </div>;
}
