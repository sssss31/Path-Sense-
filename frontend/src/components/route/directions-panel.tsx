"use client";
import {Navigation} from "lucide-react";
import type {Route} from "@/lib/types";
import {useAppStore} from "@/store/app";
const fmt=(m:number)=>m>=1000?`${(m/1000).toFixed(1)} km`:`${m} m`;
/** Turn-by-turn directions stored with the analysis (OSRM steps); clicking a step pans the map to it. */
export function DirectionsPanel({route}:{route:Route}){
  const focusOn=useAppStore(s=>s.focusOn);const steps=route.directions||[];
  return <div className="directions"><header><span><Navigation size={13} style={{verticalAlign:-2}}/> Directions · {route.name}</span><small>{steps.length?`${steps.length} steps · ${route.distance_km} km`:"no step data"}</small></header>
    {steps.length?<ol>{steps.map((s,i)=><li key={i} onClick={()=>s.location&&focusOn(s.location.lat,s.location.lng)} title={s.location?"Show on map":""}><b>{i+1}</b><span>{s.instruction}{s.road&&!s.instruction.includes(s.road)?<span style={{color:"#7d8992"}}> · {s.road}</span>:null}</span><small>{s.distance_m?fmt(s.distance_m):""}</small></li>)}</ol>:<div className="empty">The routing provider returned no step-by-step directions for this route.</div>}
  </div>;
}
