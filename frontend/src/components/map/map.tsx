"use client";
import dynamic from "next/dynamic";
import {useCallback,useState} from "react";
import type {Analysis} from "@/lib/types";
import {useAppStore} from "@/store/app";

const GOOGLE_KEY=process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY||"";
const Loading=()=><div className="map"><div className="mapStatus">Loading map…</div></div>;
const OsmMap=dynamic(()=>import("./analysis-map").then(m=>m.AnalysisMap),{ssr:false,loading:Loading});
const GoogleMap=dynamic(()=>import("./google-analysis-map").then(m=>m.GoogleAnalysisMap),{ssr:false,loading:Loading});

/** Map provider selection: Google Maps when NEXT_PUBLIC_GOOGLE_MAPS_API_KEY is set (and chosen), OpenStreetMap/Leaflet otherwise or on failure. */
export function LogisticsMap({analysis}:{analysis:Analysis}){
  const {mapProvider,setMapProvider}=useAppStore();const[fallbackReason,setFallbackReason]=useState<string|null>(null);
  const onFallback=useCallback((reason:string)=>{setFallbackReason(reason);setMapProvider("osm")},[setMapProvider]);
  const useGoogle=!!GOOGLE_KEY&&mapProvider==="google"&&!fallbackReason;
  return <>{useGoogle?<GoogleMap analysis={analysis} onFallback={onFallback}/>:<OsmMap analysis={analysis} googleAvailable={!!GOOGLE_KEY&&!fallbackReason}/>}{fallbackReason&&<div className="routeOptionsHint" style={{padding:"6px 2px 0"}}>Google Maps unavailable ({fallbackReason}); showing OpenStreetMap.</div>}{!GOOGLE_KEY&&<div className="routeOptionsHint" style={{padding:"6px 2px 0"}}>Google base map available once <code>NEXT_PUBLIC_GOOGLE_MAPS_API_KEY</code> is set; routing and hazards are identical on both maps.</div>}</>;
}
