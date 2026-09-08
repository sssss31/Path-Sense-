"use client";import "../platform.css";import "./risk-map.css";import "leaflet/dist/leaflet.css";
import {Suspense} from "react";import dynamic from "next/dynamic";import {useSearchParams} from "next/navigation";
import {PageShell} from "@/components/layout/page-shell";
const RiskMap=dynamic(()=>import("@/components/map/risk-map-view").then(x=>x.RiskMapView),{ssr:false,loading:()=> <div className="empty">Loading geospatial workspace…</div>});
function MapWithParams(){const params=useSearchParams();return <RiskMap initialAnalysisId={params.get("analysis")||undefined}/>}
export default function RiskMapPage(){return <PageShell title="Risk Intelligence Map" subtitle="Viewport-filtered hazard layers with saved-route overlay and backend-confirmed spatial relationships"><Suspense fallback={<div className="empty">Loading geospatial workspace…</div>}><MapWithParams/></Suspense></PageShell>}
