"use client";
import {useEffect} from "react";
import {CircleMarker,MapContainer,Polyline,Popup,TileLayer,GeoJSON,useMap} from "react-leaflet";
import type {FeatureCollection} from "geojson";
import type {Coordinate} from "@/lib/types";

const COLORS:Record<string,string>={low:"#2f8f5b",moderate:"#c98a1c",high:"#c94b3f",critical:"#7d2727"};
const SEVERITY=["#4e9b70","#6ea574","#d39a36","#d35f4f","#7d2727"];

function FitBounds({points}:{points:Coordinate[]}){const map=useMap();useEffect(()=>{if(points.length<2)return;const id=window.requestAnimationFrame(()=>{map.invalidateSize();map.fitBounds(points.map(p=>[p.lat,p.lng] as [number,number]),{padding:[28,28],maxZoom:12})});return()=>window.cancelAnimationFrame(id)},[map,points]);return null}

export type DeliveryMapProps={geometry:Coordinate[];source:Coordinate|null;destination:Coordinate|null;sourceName:string;destinationName:string;riskLevel?:string|null;hazards?:FeatureCollection|null;intersectingIds?:string[];nearbyIds?:string[]};

/** Renders the saved recommended geometry only. Nothing is re-routed for a historical delivery. */
export function DeliveryMap({geometry,source,destination,sourceName,destinationName,riskLevel,hazards,intersectingIds=[],nearbyIds=[]}:DeliveryMapProps){
  const points=geometry.length?geometry:[source,destination].filter(Boolean) as Coordinate[];
  const center:[number,number]=points.length?[points[Math.floor(points.length/2)].lat,points[Math.floor(points.length/2)].lng]:[25.8,91.8];
  return <MapContainer center={center} zoom={9} className="leafletMap" scrollWheelZoom={false}>
    <TileLayer attribution="© OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>
    <FitBounds points={points}/>
    {hazards&&<GeoJSON data={hazards} style={f=>{const id=String(f?.id??"");const crosses=intersectingIds.includes(id);const near=nearbyIds.includes(id);const severity=Number(f?.properties?.severity||1);return {color:crosses?"#b3261e":SEVERITY[severity-1],fillColor:SEVERITY[severity-1],fillOpacity:crosses?.3:near?.18:.08,weight:crosses?2.5:1,dashArray:near?"4 3":undefined}}} onEachFeature={(f,layer)=>{const id=String(f.id??"");const relation=intersectingIds.includes(id)?"Delivery route intersects this zone":nearbyIds.includes(id)?"Near the delivery route (within 2 km)":"Not related to this route by backend analysis";layer.bindPopup(`<strong>${f.properties?.label||f.properties?.category||"Hazard zone"}</strong><br/>Severity: ${f.properties?.severity??"Unknown"}<br/>Dataset: ${f.properties?.dataset||f.properties?.source||"Unknown"}<br/>Provenance: ${f.properties?.provenance||"historical"}<br/><em>${relation}</em>`)}}/>}
    {geometry.length>1&&<Polyline positions={geometry.map(p=>[p.lat,p.lng] as [number,number])} pathOptions={{color:COLORS[riskLevel||"moderate"]||"#2b6cb0",weight:5,opacity:.9}}/>}
    {source&&<CircleMarker center={[source.lat,source.lng]} radius={8} pathOptions={{color:"#fff",fillColor:"#1f66ed",fillOpacity:1,weight:2}}><Popup><strong>Source</strong><br/>{sourceName}</Popup></CircleMarker>}
    {destination&&<CircleMarker center={[destination.lat,destination.lng]} radius={8} pathOptions={{color:"#fff",fillColor:"#1b2a3a",fillOpacity:1,weight:2}}><Popup><strong>Destination</strong><br/>{destinationName}</Popup></CircleMarker>}
  </MapContainer>;
}
