"use client";
import {useEffect,useRef,useState} from "react";
import {useQuery} from "@tanstack/react-query";
import type {FeatureCollection} from "geojson";
import {Layers3} from "lucide-react";
import {useOptionalUser} from "@/features/auth/optional-user";
import {api} from "@/lib/platform-api";
import type {Analysis,Coordinate} from "@/lib/types";
import {useAppStore} from "@/store/app";

/* Google Maps JavaScript API renderer. The key is read from NEXT_PUBLIC_GOOGLE_MAPS_API_KEY; the loader is a plain
   script tag so no extra package is needed. Routing still comes from the backend (OSRM); Google only draws the base map. */
declare global{interface Window{google?:typeof google;__pathsenseGmaps?:Promise<void>;gm_authFailure?:()=>void}}
const ROUTE_COLORS:Record<string,string>={low:"#2f8f5b",moderate:"#c98a1c",high:"#c94b3f",critical:"#4a3aa7"};
const SEVERITY=["#4e9b70","#6ea574","#d39a36","#d35f4f","#7d2727"];
export const GOOGLE_KEY=process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY||"";

export function loadGoogleMaps(key:string):Promise<void>{
  if(typeof window==="undefined")return Promise.reject(new Error("no window"));
  if(window.google?.maps)return Promise.resolve();
  if(!window.__pathsenseGmaps){window.__pathsenseGmaps=new Promise((resolve,reject)=>{const s=document.createElement("script");s.src=`https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&v=weekly&libraries=geometry`;s.async=true;s.onload=()=>resolve();s.onerror=()=>reject(new Error("Google Maps failed to load"));document.head.appendChild(s)})}
  return window.__pathsenseGmaps;
}
function bbox(points:Coordinate[]){const lats=points.map(p=>p.lat),lngs=points.map(p=>p.lng);const pad=.08;return {min_lat:(Math.min(...lats)-pad).toFixed(4),min_lon:(Math.min(...lngs)-pad).toFixed(4),max_lat:(Math.max(...lats)+pad).toFixed(4),max_lon:(Math.max(...lngs)+pad).toFixed(4)}}

export function GoogleAnalysisMap({analysis,onFallback}:{analysis:Analysis;onFallback:(reason:string)=>void}){
  const {selectedRoute,setRoute,focusPoint,setMapProvider}=useAppStore();const {user}=useOptionalUser();
  const el=useRef<HTMLDivElement>(null);const mapRef=useRef<google.maps.Map|null>(null);const overlays=useRef<google.maps.MVCObject[]>([]);const dataRef=useRef<google.maps.Data|null>(null);
  const[ready,setReady]=useState(false);const[showHazards,setShowHazards]=useState(true);const[status,setStatus]=useState("Loading Google Maps…");
  const all=analysis.routes.flatMap(r=>r.geometry);
  const zones=useQuery({queryKey:["analysis-hazards",analysis.analysis_id],queryFn:()=>api<FeatureCollection>(`/risk-zones?${new URLSearchParams(bbox(all))}`),enabled:!!user&&all.length>1&&showHazards,staleTime:120000,retry:0});
  const incidents=useQuery({queryKey:["analysis-incidents",analysis.analysis_id],queryFn:()=>api<FeatureCollection>(`/incidents?${new URLSearchParams(bbox(all))}`),enabled:!!user&&all.length>1&&showHazards,staleTime:120000,retry:0});
  // 1. load API and create the map once
  useEffect(()=>{let cancelled=false;loadGoogleMaps(GOOGLE_KEY).then(()=>{if(cancelled||!el.current||mapRef.current)return;mapRef.current=new google.maps.Map(el.current,{center:{lat:analysis.source.coordinate.lat,lng:analysis.source.coordinate.lng},zoom:9,mapTypeControl:true,streetViewControl:false,fullscreenControl:true,gestureHandling:"greedy",mapTypeId:"roadmap"});google.maps.event.addListenerOnce(mapRef.current,"idle",()=>setReady(true));window.gm_authFailure=()=>onFallback("Google Maps rejected the API key")}).catch(()=>onFallback("Google Maps script failed to load"));return()=>{cancelled=true}},[analysis.source.coordinate.lat,analysis.source.coordinate.lng,onFallback]);
  // 2. draw routes + markers whenever the analysis/selection changes
  useEffect(()=>{const map=mapRef.current;if(!ready||!map)return;overlays.current.forEach(o=>(o as google.maps.Polyline).setMap(null));overlays.current=[];
    const selected=analysis.routes.find(r=>r.id===selectedRoute)||analysis.routes[0];const bounds=new google.maps.LatLngBounds();
    analysis.routes.filter(r=>r.id!==selected.id).forEach(r=>{const line=new google.maps.Polyline({path:r.geometry,strokeColor:"#6b7a88",strokeOpacity:0,strokeWeight:4,icons:[{icon:{path:"M 0,-1 0,1",strokeOpacity:.7,strokeWeight:4,scale:3},offset:"0",repeat:"14px"}],map,clickable:true,zIndex:2});line.addListener("click",()=>setRoute(r.id));overlays.current.push(line)});
    const arrow={path:google.maps.SymbolPath.FORWARD_CLOSED_ARROW,scale:2.6,strokeColor:"#ffffff",strokeWeight:1,fillColor:ROUTE_COLORS[selected.risk.level]||"#2b6cb0",fillOpacity:1};
    const main=new google.maps.Polyline({path:selected.geometry,strokeColor:ROUTE_COLORS[selected.risk.level]||"#2b6cb0",strokeOpacity:.95,strokeWeight:6,icons:[{icon:arrow,offset:"4%",repeat:"90px"}],map,zIndex:5});overlays.current.push(main);
    selected.geometry.forEach(p=>bounds.extend(p));
    const pin=(pos:Coordinate,title:string,color:string,label:string)=>{const m=new google.maps.Marker({position:pos,map,title,zIndex:10,icon:{path:google.maps.SymbolPath.CIRCLE,scale:9,fillColor:color,fillOpacity:1,strokeColor:"#fff",strokeWeight:2}});const info=new google.maps.InfoWindow({content:`<strong>${label}</strong><br/>${title}`});m.addListener("click",()=>info.open({map,anchor:m}));overlays.current.push(m as unknown as google.maps.MVCObject)};
    pin(analysis.source.coordinate,analysis.source.name,"#1f66ed","Origin");pin(analysis.destination.coordinate,analysis.destination.name,"#1b2a3a","Destination");
    (selected.directions||[]).forEach((s,i)=>{if(!s.location||s.maneuver.startsWith("depart")||s.maneuver.startsWith("arrive")||i%Math.ceil((selected.directions||[]).length/12||1)!==0)return;const m=new google.maps.Marker({position:s.location,map,zIndex:6,title:s.instruction,icon:{path:google.maps.SymbolPath.CIRCLE,scale:4,fillColor:"#fff",fillOpacity:1,strokeColor:ROUTE_COLORS[selected.risk.level]||"#2b6cb0",strokeWeight:2}});const info=new google.maps.InfoWindow({content:`<strong>Step ${i+1}</strong><br/>${s.instruction}`});m.addListener("click",()=>info.open({map,anchor:m}));overlays.current.push(m as unknown as google.maps.MVCObject)});
    map.fitBounds(bounds,60);
  },[ready,analysis,selectedRoute,setRoute]);
  // 3. hazard layers via the Data layer
  useEffect(()=>{const map=mapRef.current;if(!ready||!map)return;if(dataRef.current){dataRef.current.setMap(null);dataRef.current=null}
    if(!showHazards)return;const data=new google.maps.Data({map});dataRef.current=data;
    if(zones.data)data.addGeoJson(zones.data);if(incidents.data)data.addGeoJson(incidents.data);
    data.setStyle(f=>{const sev=Number(f.getProperty("severity")||1);const lt=String(f.getProperty("layer_type")||"");const flood=lt.startsWith("flood");const c=flood?"#2b6cb0":SEVERITY[sev-1];return f.getGeometry()?.getType()==="Point"?{icon:{path:google.maps.SymbolPath.CIRCLE,scale:4,fillColor:c,fillOpacity:.85,strokeColor:c,strokeWeight:1}}:{fillColor:c,fillOpacity:.14,strokeColor:c,strokeWeight:1.2,zIndex:1}});
    const info=new google.maps.InfoWindow();data.addListener("click",(e:google.maps.Data.MouseEvent)=>{const g=(k:string)=>e.feature.getProperty(k);info.setContent(`<strong>${g("label")||g("layer_label")||g("category")}</strong><br/>${g("layer_label")||""}<br/>Severity: ${g("severity")} · ${g("provenance")}<br/>Dataset: ${g("dataset")||g("source")||""}`);info.setPosition(e.latLng);info.open(map)});
  },[ready,showHazards,zones.data,incidents.data]);
  // 4. focus from the directions panel
  useEffect(()=>{if(!ready||!mapRef.current||!focusPoint)return;mapRef.current.panTo({lat:focusPoint.lat,lng:focusPoint.lng});if((mapRef.current.getZoom()||0)<13)mapRef.current.setZoom(13)},[ready,focusPoint]);
  useEffect(()=>{if(!ready)return;const n=(zones.data?.features.length||0)+(incidents.data?.features.length||0);setStatus(!user?"Sign in to overlay hazard datasets":zones.isLoading||incidents.isLoading?"Loading hazard layers…":zones.isError||incidents.isError?"Hazard layers unavailable":`${n} hazard feature(s) in corridor · Google Maps`)},[ready,user,zones.data,zones.isLoading,zones.isError,incidents.data,incidents.isLoading,incidents.isError]);
  return <div className="map"><div ref={el} className="googleMap"/><div className="mapStatus">{status}</div>
    <div className="mapProvider"><button type="button" className="on">Google</button><button type="button" onClick={()=>setMapProvider("osm")}>OpenStreetMap</button></div>
    <button className="layers" onClick={()=>setShowHazards(v=>!v)}><Layers3 size={16}/> Hazard layers <b>{showHazards?"on":"off"}</b></button>
    <div className="mapLegend"><span><i className="safe"/>Selected (arrows = direction)</span><span><i className="alternative"/>Alternative</span><span><i className="danger"/>Hazard zone</span></div></div>;
}
