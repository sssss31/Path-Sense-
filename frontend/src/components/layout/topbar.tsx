"use client";
import {useEffect,useRef,useState} from "react";
import Link from "next/link";
import {useRouter} from "next/navigation";
import {useQuery} from "@tanstack/react-query";
import {Bell,CloudRain,Menu,Search} from "lucide-react";
import {useOptionalUser} from "@/features/auth/optional-user";
import {platformApi} from "@/lib/platform-api";
import {dateTime} from "@/lib/format";
import type {Coordinate} from "@/lib/types";
import {useAppStore} from "@/store/app";

/** Live topbar: real weather at the destination via the configured provider, notifications from persisted records, working search. */
export function Topbar({destination}:{destination?:{name:string;coordinate:Coordinate}}){
  const {toggleSidebar}=useAppStore();const router=useRouter();const {user}=useOptionalUser();
  const[query,setQuery]=useState("");const[open,setOpen]=useState(false);const wrap=useRef<HTMLDivElement>(null);
  const lat=destination?.coordinate.lat??25.5788,lon=destination?.coordinate.lng??91.8933,name=destination?.name.split(",")[0]??"Shillong";
  const weather=useQuery({queryKey:["weather",lat.toFixed(3),lon.toFixed(3)],queryFn:()=>platformApi.weather(lat,lon,name),staleTime:900000,retry:0});
  const notifications=useQuery({queryKey:["notifications"],queryFn:platformApi.notifications,staleTime:60000,retry:0,enabled:!!user});
  useEffect(()=>{const onDoc=(e:MouseEvent)=>{if(wrap.current&&!wrap.current.contains(e.target as Node))setOpen(false)};document.addEventListener("mousedown",onDoc);return()=>document.removeEventListener("mousedown",onDoc)},[]);
  const w=weather.data;const count=notifications.data?.count||0;
  return <header className="topbar">
    <button className="iconBtn mobile" onClick={toggleSidebar} aria-label="Menu"><Menu size={19}/></button>
    <div><span className="eyebrow">OPERATIONS / ROUTE ANALYSIS</span><h1>Route Intelligence</h1></div>
    <div className="topActions">
      <form className="search" onSubmit={e=>{e.preventDefault();if(query.trim())router.push(`/deliveries?search=${encodeURIComponent(query.trim())}`)}}><Search size={17}/><input placeholder="Search deliveries…" value={query} onChange={e=>setQuery(e.target.value)} aria-label="Search deliveries"/></form>
      <div className="weather" title={w?`${w.provider} · ${w.status} · ${dateTime(w.updated_at)}`:"Weather loading"}><CloudRain size={18}/><span>{weather.isLoading?<><strong>…</strong><small>Weather loading</small></>:!w||w.status==="unavailable"?<><strong>—</strong><small>Weather unavailable</small></>:<><strong>{Math.round(w.temperature_c??0)}°C</strong><small>{w.condition} in {name} · {w.status==="live"?"live":"demo"}</small></>}</span></div>
      <div className="notifWrap" ref={wrap}><button className="iconBtn" aria-label="Notifications" onClick={()=>setOpen(o=>!o)}><Bell size={19}/>{count>0&&<i/>}</button>
        {open&&<div className="notifPanel">{!user?<div className="notifEmpty"><Link href="/login">Sign in</Link> to see operational alerts.</div>:notifications.isLoading?<div className="notifEmpty">Loading…</div>:!notifications.data?.items.length?<div className="notifEmpty">No active alerts. Delayed deliveries, imminent departures and high-risk corridors appear here.</div>:notifications.data.items.map((n,i)=><Link key={i} href={n.href} onClick={()=>setOpen(false)}><span><i className={`sev ${n.severity}`}/><strong>{n.title}</strong></span><small>{n.detail}{n.at?` · ${dateTime(n.at)}`:""}</small></Link>)}</div>}
      </div>
    </div>
  </header>;
}
