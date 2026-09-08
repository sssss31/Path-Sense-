"use client";
import "../platform.css";import "../charts.css";
import {useState} from "react";
import {useQuery} from "@tanstack/react-query";
import {PageShell} from "@/components/layout/page-shell";
import {AccessibilityTrendChart,CargoDistributionChart,DataAvailabilityChart,DeliveryStatusChart,RiskDistributionChart,RiskFactorChart} from "@/components/charts/charts";
import {platformApi} from "@/lib/platform-api";
import {dateOnly} from "@/lib/format";

const RANGES:[string,string][]=[["7d","Last 7 days"],["30d","Last 30 days"],["90d","Last 90 days"],["365d","Last year"]];
export default function Reports(){
  const[range,setRange]=useState("30d");const[from,setFrom]=useState("");const[to,setTo]=useState("");
  const custom=!!from;
  const q=useQuery({queryKey:["reports",{range,from,to}],queryFn:()=>platformApi.reports(custom?undefined:range,custom?new Date(from).toISOString():undefined,custom&&to?new Date(to+"T23:59:59").toISOString():undefined),staleTime:60000,placeholderData:prev=>prev});
  const d=q.data;
  const card=(title:string,subtitle:string,body:React.ReactNode)=><section className="dataCard" key={title}><h2>{title}<small>{subtitle}</small></h2>{q.isLoading?<div className="empty">Loading…</div>:q.isError?<div className="empty">Report data unavailable.</div>:body}</section>;
  return <PageShell title="Reports" subtitle="Aggregated from persisted operational records">
    <div className="filterRow"><div className="segmented">{RANGES.map(([k,l])=><button key={k} className={!custom&&range===k?"on":""} onClick={()=>{setRange(k);setFrom("");setTo("")}}>{l}</button>)}</div><label>From<input type="date" value={from} onChange={e=>setFrom(e.target.value)}/></label><label>To<input type="date" value={to} min={from||undefined} onChange={e=>setTo(e.target.value)}/></label>{d&&<span className="rangeNote">{dateOnly(d.range.from)} – {dateOnly(d.range.to)}{q.isFetching?" · updating…":""}</span>}</div>
    <div className="contentGrid">
      {card("Accessibility Trend","daily average of recommended routes",<AccessibilityTrendChart data={d?.accessibility_trend||[]}/>)}
      {card("Risk Distribution","recommended routes by risk level",<RiskDistributionChart data={d?.risk_distribution||[]}/>)}
    </div>
    <div className="contentGrid three">
      {card("Top Risk Factors","from persisted normalized risk factors",<RiskFactorChart data={d?.risk_factors||[]}/>)}
      {card("Cargo Distribution","analyses by cargo type",<CargoDistributionChart data={d?.cargo_distribution||[]}/>)}
      {card("Delivery Status","deliveries created in range",<DeliveryStatusChart data={d?.delivery_status||[]}/>)}
    </div>
    <div className="contentGrid">
      {card("Data Availability","analyses by evidence coverage · unavailable never means safe",<DataAvailabilityChart data={d?.data_availability||[]}/>)}
      <section className="dataCard"><h2>Reading this report</h2><p style={{fontSize:11,color:"#4b5963",lineHeight:1.6,margin:0}}>Risk and accessibility come from persisted analyses. <strong>Hazard data unavailable</strong> means the route was evaluated without a covering hazard dataset, so exposure is unknown rather than zero. Historical landslide and flood datasets are evidence of past events or susceptibility, never live alerts.</p></section>
    </div>
  </PageShell>;
}
