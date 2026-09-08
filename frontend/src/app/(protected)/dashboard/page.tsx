"use client";
import "../platform.css";import "../charts.css";import "../deliveries/delivery.css";
import Link from "next/link";
import {useQuery} from "@tanstack/react-query";
import {PageShell} from "@/components/layout/page-shell";
import {AccessibilityTrendChart,DeliveryStatusChart,RiskDistributionChart} from "@/components/charts/charts";
import {platformApi} from "@/lib/platform-api";
import {STATUS_LABELS,dateOnly,label} from "@/lib/format";

export default function Dashboard(){
  const q=useQuery({queryKey:["dashboard"],queryFn:platformApi.dashboard,staleTime:30000,retry:1});const d=q.data;
  const state=(body:React.ReactNode)=>q.isLoading?<div className="empty">Loading…</div>:q.isError?<div className="empty">Dashboard data unavailable. Retry shortly.</div>:body;
  return <PageShell title="Operations Dashboard" subtitle="Overview from persisted route intelligence">
    <div className="metricGrid">{[["Total analyses",d?.metrics?.total_analyses],["Average accessibility",d?.metrics?.average_accessibility],["High-risk analyses",d?.metrics?.high_risk],["Active deliveries",d?.metrics?.active_deliveries],["Last 7 days",d?.metrics?.last_7_days]].map(([a,b])=><div className="metric" key={a}><span>{a}</span><strong>{b??"—"}</strong></div>)}</div>
    <div className="contentGrid equal">
      <section className="dataCard"><h2>Accessibility Trend<small>last 14 days</small></h2>{state(<AccessibilityTrendChart data={d?.accessibility_trend||[]} compact/>)}</section>
      <section className="dataCard"><h2>Risk Distribution</h2>{state(<RiskDistributionChart data={(d?.risk_distribution||[]).map(x=>({name:x.level,value:x.count}))}/>)}</section>
      <section className="dataCard"><h2>Delivery Status</h2>{state(<DeliveryStatusChart data={d?.delivery_status||[]}/>)}</section>
    </div>
    <div className="contentGrid">
      <section className="dataCard"><h2>Recent Route Analyses</h2>{state(!d?.recent_analyses?.length?<div className="empty">No saved analyses yet. Analyze a route to begin.</div>:<div style={{overflowX:"auto"}}><table className="dataTable recentTable"><thead><tr><th>Corridor</th><th>Cargo</th><th>Accessibility</th><th>Risk</th><th>Route</th><th>Date</th><th></th></tr></thead><tbody>{d.recent_analyses.map(x=><tr key={x.analysis_id}><td>{x.source} → {x.destination}</td><td>{label(x.cargo_type)}</td><td>{x.accessibility??"—"}</td><td>{x.risk_level?<span className={`risk ${x.risk_level}`}>{x.risk_level}</span>:"—"}</td><td>{x.recommended_route}</td><td>{dateOnly(x.created_at)}</td><td><Link href={`/risk-map?analysis=${x.analysis_id}`}>Map</Link></td></tr>)}</tbody></table></div>)}</section>
      <section className="dataCard"><h2>Active Deliveries</h2>{state(!d?.active_deliveries?.length?<div className="empty">No active deliveries.</div>:<table className="dataTable recentTable"><thead><tr><th>Delivery</th><th>Corridor</th><th>Status</th></tr></thead><tbody>{d.active_deliveries.map(x=><tr key={x.id}><td><Link href={`/deliveries/${x.id}`}>{x.identifier}</Link></td><td>{x.source} → {x.destination}</td><td><span className={`statusPill ${x.status}`}>{STATUS_LABELS[x.status]}</span></td></tr>)}</tbody></table>)}</section>
    </div>
  </PageShell>;
}
