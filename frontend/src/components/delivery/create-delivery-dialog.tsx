"use client";
import {useState} from "react";
import Link from "next/link";
import {useRouter} from "next/navigation";
import {useMutation,useQuery,useQueryClient} from "@tanstack/react-query";
import {AlertTriangle,ArrowRight,CheckCircle2,Loader2} from "lucide-react";
import {Modal} from "@/components/ui/modal";
import {ApiError,platformApi} from "@/lib/platform-api";
import {fromLocalInput,label,minutes,toLocalInput} from "@/lib/format";
import type {Analysis,Delivery,Route} from "@/lib/types";

const FALLBACK_PRIORITIES=["low","medium","high","critical"];
const VEHICLE_OPTIONS=["Cargo Van","Emergency Cargo Van","Pickup Truck","4x4 Utility Vehicle","Light Truck"];

export type CreateDeliveryDialogProps={analysis:Analysis;route:Route;cargoType:string;priority:string;departureTime:string;onClose:()=>void};

/** Confirmation step between a successful analysis and POST /deliveries. Source/destination are fixed; only operational fields are editable. */
export function CreateDeliveryDialog({analysis,route,cargoType,priority,departureTime,onClose}:CreateDeliveryDialogProps){
  const router=useRouter();const queryClient=useQueryClient();
  const rules=useQuery({queryKey:["transition-rules"],queryFn:platformApi.transitionRules,staleTime:600000,retry:0});
  const priorities=rules.data?.priorities||FALLBACK_PRIORITIES;
  const[vehicle,setVehicle]=useState(route.recommended_vehicle);
  const[selectedPriority,setPriority]=useState(priorities.includes(priority)?priority:"high");
  const[departure,setDeparture]=useState(toLocalInput(departureTime));
  const[notes,setNotes]=useState("");
  const[created,setCreated]=useState<Delivery|null>(null);
  const eta=departure?new Date(new Date(departure).getTime()+route.eta_minutes*60000):null;
  const mutation=useMutation({
    mutationFn:()=>platformApi.createDelivery({analysis_id:analysis.analysis_id,vehicle,priority:selectedPriority,planned_departure:fromLocalInput(departure),notes:notes.trim()||null}),
    onSuccess:(delivery)=>{setCreated(delivery);queryClient.invalidateQueries({queryKey:["deliveries"]});queryClient.invalidateQueries({queryKey:["dashboard"]});queryClient.invalidateQueries({queryKey:["reports"]})},
  });
  const error=mutation.error as ApiError|Error|null;
  const validation=error instanceof ApiError&&error.status===422;
  const vehicles=VEHICLE_OPTIONS.includes(vehicle)?VEHICLE_OPTIONS:[vehicle,...VEHICLE_OPTIONS];
  return <Modal title={created?"Delivery created":"Confirm delivery"} eyebrow={created?"DISPATCH RECORDED":"CREATE DELIVERY FROM ANALYSIS"} onClose={onClose}>
    {created?<div className="modalBody">
      <div className="successBox"><CheckCircle2 size={20}/><div><strong>{created.identifier}</strong><span>{created.source} → {created.destination} · {label(created.status)} · {label(created.priority)} priority</span></div></div>
      <div className="modalActions"><button type="button" className="secondaryBtn" onClick={onClose}>Stay here</button><Link className="primaryBtn" href={`/deliveries/${created.id}`} onClick={()=>router.push(`/deliveries/${created.id}`)}>View Delivery <ArrowRight size={15}/></Link></div>
    </div>:<form className="modalBody" onSubmit={e=>{e.preventDefault();mutation.mutate()}}>
      <div className="corridor"><strong>{analysis.source.name}</strong><ArrowRight size={14}/><strong>{analysis.destination.name}</strong></div>
      <dl className="factGrid">
        <div><dt>Cargo</dt><dd>{label(cargoType)}</dd></div>
        <div><dt>Recommended route</dt><dd>{route.name}</dd></div>
        <div><dt>Accessibility</dt><dd>{route.accessibility.score}/100 · {label(route.accessibility.status)}</dd></div>
        <div><dt>Risk</dt><dd><span className={`risk ${route.risk.level}`}>{route.risk.level} risk</span> {route.risk.score}/100</dd></div>
        <div><dt>Route ETA</dt><dd>{minutes(route.eta_minutes)} · {route.distance_km} km</dd></div>
        <div><dt>Estimated arrival</dt><dd>{eta?eta.toLocaleString(undefined,{dateStyle:"medium",timeStyle:"short"}):"Set a departure"}</dd></div>
        <div><dt>Analysis</dt><dd className="mono">{analysis.analysis_id.slice(0,8)}</dd></div>
        <div><dt>Hazard data</dt><dd>{route.hazards?label(route.hazards.status):"Unavailable"}</dd></div>
      </dl>
      <div className="formRow">
        <label>Vehicle<select value={vehicle} onChange={e=>setVehicle(e.target.value)}>{vehicles.map(v=><option key={v} value={v}>{v}{v===route.recommended_vehicle?" (recommended)":""}</option>)}</select></label>
        <label>Priority<select value={selectedPriority} onChange={e=>setPriority(e.target.value)}>{priorities.map(p=><option key={p} value={p}>{label(p)}</option>)}</select></label>
      </div>
      <label>Planned departure<input type="datetime-local" value={departure} onChange={e=>setDeparture(e.target.value)}/></label>
      <label>Notes<textarea rows={3} maxLength={1000} placeholder="Handling instructions, consignee contact, cold-chain requirements…" value={notes} onChange={e=>setNotes(e.target.value)}/></label>
      {error&&<div className="formAlert" role="alert"><AlertTriangle size={15}/><span>{validation?`Validation error: ${error.message}`:error instanceof ApiError&&error.status===404?"This analysis is no longer available for delivery creation.":error.message}</span></div>}
      <div className="modalActions"><button type="button" className="secondaryBtn" onClick={onClose} disabled={mutation.isPending}>Cancel</button><button type="submit" className="primaryBtn" disabled={mutation.isPending}>{mutation.isPending?<><Loader2 className="spin" size={15}/>Creating…</>:<>Create delivery</>}</button></div>
    </form>}
  </Modal>;
}
