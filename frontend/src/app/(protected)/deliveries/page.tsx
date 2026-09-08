"use client";
import "../platform.css";import "./delivery.css";
import {Suspense,useState} from "react";
import {useSearchParams} from "next/navigation";
import Link from "next/link";
import {useQuery} from "@tanstack/react-query";
import {PageShell} from "@/components/layout/page-shell";
import {platformApi} from "@/lib/platform-api";
import {STATUS_LABELS,dateTime,label} from "@/lib/format";

const STATUSES=["","planned","in_transit","delayed","completed","cancelled"];
export default function DeliveriesPage(){return <Suspense fallback={<PageShell title="Deliveries" subtitle="Dispatches linked to route intelligence"><div className="empty">Loading…</div></PageShell>}><Deliveries/></Suspense>}
function Deliveries(){
  const params=useSearchParams();
  const[status,setStatus]=useState("");const[search,setSearch]=useState(params.get("search")||"");const[page,setPage]=useState(1);
  const q=useQuery({queryKey:["deliveries",{status,search,page}],queryFn:()=>platformApi.deliveries({page,status:status||undefined,search:search||undefined}),staleTime:20000,placeholderData:prev=>prev});
  const rows=q.data?.items||[];const total=q.data?.total||0;const pages=Math.max(1,Math.ceil(total/(q.data?.page_size||20)));
  return <PageShell title="Deliveries" subtitle="Dispatches linked to route intelligence">
    <section className="dataCard">
      <div className="toolbar"><input placeholder="Search identifier or place…" value={search} onChange={e=>{setSearch(e.target.value);setPage(1)}}/><select value={status} onChange={e=>{setStatus(e.target.value);setPage(1)}}>{STATUSES.map(s=><option key={s} value={s}>{s?STATUS_LABELS[s]:"All statuses"}</option>)}</select><span style={{fontSize:10,color:"#7d8992"}}>{q.isFetching?"Updating…":`${total} deliver${total===1?"y":"ies"}`}</span></div>
      {q.isLoading?<div className="empty">Loading deliveries…</div>:q.isError?<div className="empty">Delivery data unavailable. Retry shortly.</div>:!rows.length?<div className="empty">No deliveries yet. Run a route analysis and use “Create Delivery” from the result.</div>:<div style={{overflowX:"auto"}}><table className="dataTable"><thead><tr><th>Delivery</th><th>Corridor</th><th>Status</th><th>Priority</th><th>Cargo</th><th>Vehicle</th><th>Accessibility</th><th>Risk</th><th>Departure</th><th>ETA</th></tr></thead><tbody>{rows.map(x=><tr key={x.id}><td><Link className="tableLink" href={`/deliveries/${x.id}`}>{x.identifier}</Link></td><td>{x.source} → {x.destination}</td><td><span className={`statusPill ${x.status}`}>{STATUS_LABELS[x.status]}</span></td><td><span className={`priorityPill ${x.priority}`}>{label(x.priority)}</span></td><td>{label(x.cargo_type)}</td><td>{x.vehicle}</td><td>{x.accessibility??"—"}</td><td>{x.risk_level?<span className={`risk ${x.risk_level}`}>{x.risk_level}</span>:"—"}</td><td>{dateTime(x.planned_departure)}</td><td>{dateTime(x.estimated_arrival)}</td></tr>)}</tbody></table></div>}
      {pages>1&&<div className="pager"><button disabled={page<=1} onClick={()=>setPage(p=>p-1)}>Previous</button><span>Page {page} of {pages}</span><button disabled={page>=pages} onClick={()=>setPage(p=>p+1)}>Next</button></div>}
    </section>
  </PageShell>;
}
