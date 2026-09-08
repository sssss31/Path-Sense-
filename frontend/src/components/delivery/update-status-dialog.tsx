"use client";
import {useState} from "react";
import {useMutation,useQueryClient} from "@tanstack/react-query";
import {AlertTriangle,ArrowRight,Loader2,ShieldAlert} from "lucide-react";
import {Modal} from "@/components/ui/modal";
import {ApiError,platformApi} from "@/lib/platform-api";
import {STATUS_LABELS} from "@/lib/format";
import type {DeliveryDetail,DeliveryStatus} from "@/lib/types";

/** Controlled status change. Allowed targets come from the backend (`allowed_transitions`); sensitive targets need explicit confirmation. */
export function UpdateStatusDialog({delivery,onClose}:{delivery:DeliveryDetail;onClose:()=>void}){
  const queryClient=useQueryClient();
  const allowed=delivery.allowed_transitions;
  const[target,setTarget]=useState<DeliveryStatus|"">(allowed[0]||"");
  const[note,setNote]=useState("");
  const[confirmed,setConfirmed]=useState(false);
  const sensitive=!!target&&delivery.sensitive_transitions.includes(target);
  const mutation=useMutation({
    mutationFn:()=>platformApi.updateDelivery(delivery.id,{status:target as DeliveryStatus,status_note:note.trim()||null}),
    onSuccess:(detail)=>{queryClient.setQueryData(["delivery",delivery.id],detail);queryClient.invalidateQueries({queryKey:["deliveries"]});queryClient.invalidateQueries({queryKey:["dashboard"]});queryClient.invalidateQueries({queryKey:["reports"]});onClose()},
  });
  const error=mutation.error as ApiError|Error|null;
  return <Modal title="Update status" eyebrow={delivery.identifier} onClose={onClose} width={460}>
    <form className="modalBody" onSubmit={e=>{e.preventDefault();if(!target)return;if(sensitive&&!confirmed){setConfirmed(true);return}mutation.mutate()}}>
      {allowed.length===0?<div className="formAlert"><ShieldAlert size={15}/><span>{STATUS_LABELS[delivery.status]} is a terminal status. No further transitions are allowed.</span></div>:<>
        <div className="transitionRow"><span className={`statusPill ${delivery.status}`}>{STATUS_LABELS[delivery.status]}</span><ArrowRight size={15}/><select value={target} onChange={e=>{setTarget(e.target.value as DeliveryStatus);setConfirmed(false)}}>{allowed.map(s=><option key={s} value={s}>{STATUS_LABELS[s]}</option>)}</select></div>
        <label>Note (optional)<textarea rows={3} maxLength={500} placeholder="Reason, driver update, incident reference…" value={note} onChange={e=>setNote(e.target.value)}/></label>
        {sensitive&&<div className={`formAlert ${confirmed?"warn":""}`} role="alert"><ShieldAlert size={15}/><span>{confirmed?`Confirm marking this delivery as ${STATUS_LABELS[target].toLowerCase()}. This cannot be reverted.`:`Marking a delivery ${STATUS_LABELS[target].toLowerCase()} is final and will require confirmation.`}</span></div>}
        {error&&<div className="formAlert" role="alert"><AlertTriangle size={15}/><span>{error instanceof ApiError&&error.status===409?`Transition rejected by server: ${error.message}`:error.message}</span></div>}
        <div className="modalActions"><button type="button" className="secondaryBtn" onClick={onClose} disabled={mutation.isPending}>Cancel</button><button type="submit" className={`primaryBtn ${sensitive?"danger":""}`} disabled={mutation.isPending||!target}>{mutation.isPending?<><Loader2 className="spin" size={15}/>Updating…</>:sensitive&&confirmed?`Confirm ${STATUS_LABELS[target]}`:sensitive?"Review change":"Update status"}</button></div>
      </>}
    </form>
  </Modal>;
}
