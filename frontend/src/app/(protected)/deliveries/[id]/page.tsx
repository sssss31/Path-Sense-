"use client";
import "../../platform.css";import "../delivery.css";import "leaflet/dist/leaflet.css";
import {useMemo,useState} from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import {useParams} from "next/navigation";
import {useMutation,useQuery} from "@tanstack/react-query";
import type {FeatureCollection} from "geojson";
import {AlertTriangle,ArrowRight,CloudRain,Info,Mountain,RefreshCw,ShieldAlert,Sparkles,Truck} from "lucide-react";
import {PageShell} from "@/components/layout/page-shell";
import {UpdateStatusDialog} from "@/components/delivery/update-status-dialog";
import {ApiError,api,platformApi} from "@/lib/platform-api";
import {HAZARD_STATUS_TEXT,PROVENANCE_TEXT,STATUS_LABELS,dateTime,label,minutes,shortId} from "@/lib/format";
import type {Coordinate} from "@/lib/types";

const DeliveryMap=dynamic(()=>import("@/components/delivery/delivery-map").then(m=>m.DeliveryMap),{ssr:false,loading:()=><div className="mapUnavailable">Loading map…</div>});

function bounds(points:Coordinate[]){const lats=points.map(p=>p.lat),lngs=points.map(p=>p.lng);const pad=.05;return {min_lat:(Math.min(...lats)-pad).toFixed(4),min_lon:(Math.min(...lngs)-pad).toFixed(4),max_lat:(Math.max(...lats)+pad).toFixed(4),max_lon:(Math.max(...lngs)+pad).toFixed(4)}}

export default function DeliveryDetailPage(){
  const {id}=useParams<{id:string}>();
  const q=useQuery({queryKey:["delivery",id],queryFn:()=>platformApi.delivery(id),retry:(count,error)=>!(error instanceof ApiError&&error.status===404)&&count<1});
  const d=q.data;
  const[statusOpen,setStatusOpen]=useState(false);
  const routePoints=useMemo(()=>d?.geometry?.length?d.geometry:[d?.source_coordinate,d?.destination_coordinate].filter(Boolean) as Coordinate[],[d]);
  const hazardLayer=useQuery({queryKey:["delivery-hazards",id,routePoints.length],queryFn:()=>api<FeatureCollection>(`/risk-zones?${new URLSearchParams(bounds(routePoints))}`),enabled:routePoints.length>1,staleTime:120000,retry:0});
  const explain=useMutation({mutationFn:()=>platformApi.explainDelivery(id,"Explain this delivery, its accessibility evidence and hazard data state.")});
  const summary=d?.hazards?.summary;const hazardStatus=summary?.hazard_status||d?.hazards?.status||"unavailable";

  if(q.isLoading)return <PageShell title="Delivery" subtitle="Loading delivery record…"><div className="empty">Loading delivery…</div></PageShell>;
  if(q.isError||!d){const notFound=q.error instanceof ApiError&&q.error.status===404;return <PageShell title="Delivery" subtitle={notFound?"This delivery does not exist or belongs to another operator":"Delivery could not be loaded"}><section className="dataCard"><div className="empty"><div><p>{notFound?"Delivery not found.":"The delivery service is unavailable. Retry shortly."}</p><Link className="tableLink" href="/deliveries">Back to deliveries</Link></div></div></section></PageShell>}

  const access=d.accessibility_detail;const factors=access?.factors||{};
  return <PageShell title={d.identifier} subtitle="Delivery record linked to its authoritative route analysis">
    <header className="detailHead">
      <div className="headTop">
        <div><span className="eyebrow">DELIVERY</span><h2>{d.source}<ArrowRight size={16}/>{d.destination}</h2><div className="pills"><span className={`statusPill ${d.status}`}>{STATUS_LABELS[d.status]}</span><span className={`priorityPill ${d.priority}`}>{label(d.priority)} priority</span>{d.risk_level&&<span className={`risk ${d.risk_level}`}>{d.risk_level} risk</span>}</div></div>
        <div className="headActions"><button type="button" className="secondaryBtn" onClick={()=>q.refetch()} title="Refresh"><RefreshCw size={14}/></button><button type="button" className="primaryBtn" onClick={()=>setStatusOpen(true)} disabled={d.allowed_transitions.length===0}>{d.allowed_transitions.length?"Update Status":`${STATUS_LABELS[d.status]} (final)`}</button></div>
      </div>
      <div className="headMeta"><span><small>Delivery ID</small>{d.identifier}</span><span><small>Created</small>{dateTime(d.created_at)}</span><span><small>Planned departure</small>{dateTime(d.planned_departure)}</span><span><small>ETA</small>{dateTime(d.estimated_arrival)}</span>{d.actual_arrival&&<span><small>Actual arrival</small>{dateTime(d.actual_arrival)}</span>}<span><small>Cargo</small>{label(d.cargo_type)}</span><span><small>Vehicle</small>{d.vehicle}</span></div>
    </header>

    <div className="detailGrid">
      <div>
        <section className="dataCard"><h2>Route Summary</h2>{d.route?<div className="statGrid"><div className="stat"><small>Route</small><strong>{d.route.name}</strong><em>{d.route.rationale||"Recommended by decision engine"}</em></div><div className="stat"><small>Distance</small><strong>{d.route.distance_km} km</strong></div><div className="stat"><small>Driving time</small><strong>{minutes(d.route.duration_minutes)}</strong></div><div className="stat"><small>Risk-adjusted ETA</small><strong>{minutes(d.route.eta_minutes)}</strong></div>{d.route.road_quality!=null&&<div className="stat"><small>Road quality</small><strong>{d.route.road_quality}/100</strong></div>}</div>:<div className="empty">No route snapshot is attached to this delivery.</div>}</section>

        <section className="dataCard"><h2>Accessibility Intelligence<small>from persisted analysis</small></h2>{access?<><div className="statGrid"><div className="stat"><small>Accessibility</small><strong>{access.score}/100</strong><em>{label(access.status)}</em></div><div className="stat"><small>Risk score</small><strong>{d.risk?.score??"—"}/100</strong><em>{label(d.risk?.level)}</em></div><div className="stat"><small>Confidence</small><strong>{access.confidence!=null?`${Math.round(access.confidence*100)}%`:"—"}</strong><em>evidence coverage, independent of score</em></div></div><div className="factorBars">{Object.entries(factors).map(([k,v])=><div key={k}><span>{label(k)}</span><i><b style={{width:`${v}%`}}/></i><span>{v}</span></div>)}</div>{!!access.confidence_reasons?.length&&<ul className="riskList" style={{marginTop:12}}>{access.confidence_reasons.map(r=><li key={r}><Info size={14} style={{color:"#6f7d88"}}/><span>{r}</span></li>)}</ul>}</>:<div className="empty">Accessibility snapshot unavailable.</div>}</section>

        <section className="dataCard mapCard"><div style={{padding:"16px 16px 0"}}><h2>Route Map</h2></div>{routePoints.length>1?<><DeliveryMap geometry={d.geometry} source={d.source_coordinate} destination={d.destination_coordinate} sourceName={d.source} destinationName={d.destination} riskLevel={d.risk_level} hazards={hazardLayer.data||null} intersectingIds={summary?.intersecting_zone_ids||[]} nearbyIds={summary?.nearby_zone_ids||[]}/><div className="mapCaption"><span>Saved recommended geometry · not re-routed</span><span>{hazardLayer.isError?"Hazard overlay unavailable":hazardLayer.data?`${hazardLayer.data.features.length} hazard zone(s) in view`:"Loading hazard overlay…"}</span></div></>:<div className="mapUnavailable">Route geometry is not available for this delivery.</div>}</section>

        <section className="dataCard"><h2>Risk Factors</h2>{d.risk?.main_risks?.length?<ul className="riskList">{d.risk.main_risks.map(r=><li key={r}><AlertTriangle size={14}/><span>{r}</span></li>)}</ul>:<div className="empty">No risk factors recorded.</div>}</section>
      </div>

      <div>
        <section className="dataCard"><h2>Delivery Status</h2><ul className="timeline">{[...d.status_history].reverse().map((e,i)=><li key={i}><span><strong>{e.from_status?`${STATUS_LABELS[e.from_status]} → `:""}{STATUS_LABELS[e.to_status]||e.to_status}</strong><small>{dateTime(e.at)}</small>{e.note&&<em>{e.note}</em>}</span></li>)}</ul><p style={{fontSize:10,color:"#7d8992",marginBottom:0}}>Allowed next: {d.allowed_transitions.length?d.allowed_transitions.map(s=>STATUS_LABELS[s]).join(", "):"none (terminal)"}</p></section>

        <section className="dataCard"><h2>Vehicle &amp; Cargo</h2><div className="statGrid"><div className="stat"><small>Assigned vehicle</small><strong><Truck size={14} style={{verticalAlign:-2}}/> {d.vehicle}</strong><em>{d.route?.recommended_vehicle&&d.route.recommended_vehicle!==d.vehicle?`Engine recommended ${d.route.recommended_vehicle}`:"Matches engine recommendation"}</em></div><div className="stat"><small>Cargo</small><strong>{label(d.cargo_type)}</strong></div><div className="stat"><small>Priority</small><strong>{label(d.priority)}</strong></div></div>{d.notes&&<p style={{fontSize:11,color:"#2b3742",marginBottom:0}}><strong>Notes:</strong> {d.notes}</p>}</section>

        <section className="dataCard"><h2>Timing</h2><div className="statGrid"><div className="stat"><small>Planned departure</small><strong style={{fontSize:12}}>{dateTime(d.planned_departure)}</strong></div><div className="stat"><small>ETA</small><strong style={{fontSize:12}}>{dateTime(d.estimated_arrival)}</strong></div><div className="stat"><small>Actual arrival</small><strong style={{fontSize:12}}>{dateTime(d.actual_arrival)}</strong></div><div className="stat"><small>Last updated</small><strong style={{fontSize:12}}>{dateTime(d.updated_at)}</strong></div></div></section>

        <section className="dataCard"><h2>Hazard Exposure</h2><div className={`hazardBanner ${hazardStatus}`}><ShieldAlert size={15}/><span><strong>{HAZARD_STATUS_TEXT[hazardStatus]||label(hazardStatus)}</strong>{summary?.reasons?.length?<><br/>{summary.reasons.join(" ")}</>:null}</span></div>{summary&&summary.hazard_status!=="unavailable"&&<div className="statGrid" style={{marginTop:10}}><div className="stat"><small>Zones crossed</small><strong>{summary.zones_crossed??"—"}</strong></div><div className="stat"><small>Landslide exposure</small><strong>{summary.landslide_exposure_km??0} km</strong></div><div className="stat"><small>Flood exposure</small><strong>{summary.flood_exposure_km??0} km</strong></div><div className="stat"><small>Highest severity</small><strong>{label(summary.highest_severity)}</strong></div><div className="stat"><small>Incidents nearby</small><strong>{summary.historical_incidents_nearby??"—"}</strong></div><div className="stat"><small>Confidence</small><strong>{Math.round(summary.confidence*100)}%</strong></div></div>}{summary?.datasets?.length?<p style={{fontSize:10,color:"#6f7d88",marginBottom:0}}>Datasets: {summary.datasets.join(", ")} <span className={`badge ${summary.provenance}`}>{PROVENANCE_TEXT[summary.provenance]||summary.provenance}</span></p>:null}</section>

        <section className="dataCard"><h2>Weather Snapshot<small>recorded at analysis time</small></h2>{d.weather?<div className="statGrid"><div className="stat"><small>Condition</small><strong><CloudRain size={14} style={{verticalAlign:-2}}/> {d.weather.condition}</strong><em><span className={`badge ${d.weather.data_status}`}>{PROVENANCE_TEXT[d.weather.data_status]||d.weather.data_status}</span></em></div><div className="stat"><small>Rainfall</small><strong>{d.weather.rainfall_mm} mm</strong><em>{d.weather.rainfall_probability}% probability</em></div><div className="stat"><small>Visibility</small><strong>{d.weather.visibility_km} km</strong></div><div className="stat"><small>Temperature</small><strong>{d.weather.temperature_c}°C</strong><em>{d.weather.humidity}% humidity</em></div>{d.terrain&&<div className="stat"><small>Terrain</small><strong><Mountain size={14} style={{verticalAlign:-2}}/> {d.terrain.classification}</strong><em>{d.terrain.average_slope}° slope · {d.terrain.elevation_m} m</em></div>}</div>:<div className="empty">Weather snapshot unavailable.</div>}</section>

        <section className="dataCard"><h2>Related Analysis</h2>{d.analysis?<div className="aiPanel"><div className="statGrid"><div className="stat"><small>Analysis ID</small><strong className="mono" style={{fontSize:12}}>{shortId(d.analysis.analysis_id)}</strong><em>{dateTime(d.analysis.created_at)}</em></div><div className="stat"><small>Routes compared</small><strong>{d.analysis.route_count}</strong><em>{d.analysis.emergency_mode?"Emergency mode":"Standard mode"}</em></div></div><p>{d.analysis.explanation}</p><div className="aiMeta"><Link className="tableLink" href={`/risk-map?analysis=${d.analysis.analysis_id}`}>Open on Risk Map</Link><button type="button" className="textLink" onClick={()=>explain.mutate()} disabled={explain.isPending}><Sparkles size={13}/>{explain.isPending?"Asking assistant…":"Explain this delivery"}</button></div>{explain.data&&<div className="hazardBanner simulated" style={{display:"grid",gap:5}}><span>{explain.data.message}</span><small>Source: {explain.data.source} · {explain.data.status}</small></div>}{explain.isError&&<div className="formAlert"><AlertTriangle size={14}/><span>Assistant unavailable.</span></div>}</div>:<div className="empty">The source analysis has been deleted. Snapshot values above remain from the delivery record.</div>}</section>

        <section className="dataCard"><h2>Data Provenance</h2><table className="provenanceTable"><tbody>{Object.entries(d.data_quality||{}).map(([k,v])=><tr key={k}><td>{label(k)}</td><td><span className={`badge ${v.status}`}>{PROVENANCE_TEXT[v.status]||v.status}</span></td><td>{v.provider}</td></tr>)}{summary&&<tr><td>Spatial hazard query</td><td><span className={`badge ${summary.hazard_status==="unavailable"?"unavailable":summary.provenance}`}>{label(summary.hazard_status)}</span></td><td>{summary.datasets.join(", ")||"no dataset"}</td></tr>}</tbody></table>{d.analysis?.data_disclaimer&&<p style={{fontSize:10,color:"#7d8992",marginBottom:0}}>{d.analysis.data_disclaimer}</p>}</section>
      </div>
    </div>
    {statusOpen&&<UpdateStatusDialog delivery={d} onClose={()=>setStatusOpen(false)}/>}
  </PageShell>;
}
