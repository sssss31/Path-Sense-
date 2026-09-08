"use client";
import "../platform.css";import "../deliveries/delivery.css";
import {useEffect,useRef,useState} from "react";
import {useMutation,useQuery} from "@tanstack/react-query";
import {Send,Sparkles} from "lucide-react";
import {PageShell} from "@/components/layout/page-shell";
import {DataSourcesPanel} from "@/components/route/data-sources-panel";
import {platformApi} from "@/lib/platform-api";
import {dateOnly} from "@/lib/format";
import type {AssistantReply} from "@/lib/types";

type Msg={role:"user"|"bot";text:string;source?:string;status?:string};
const SUGGESTIONS=["Why was this route recommended?","What hazard data was used and what is unavailable?","Is the weather data live?","Which vehicle should I dispatch and why?"];

/** AI Assistant over persisted analyses or deliveries. Every answer is grounded in a server-controlled context; provenance is always shown. */
export default function AssistantPage(){
  const history=useQuery({queryKey:["history-selector"],queryFn:()=>platformApi.history(1,50),staleTime:60000,retry:0});
  const deliveries=useQuery({queryKey:["deliveries",{page:1}],queryFn:()=>platformApi.deliveries({page:1}),staleTime:60000,retry:0});
  const health=useQuery({queryKey:["health"],queryFn:platformApi.health,staleTime:60000,retry:0});
  const[subject,setSubject]=useState<string>("");
  const[messages,setMessages]=useState<Msg[]>([]);const[question,setQuestion]=useState("");const end=useRef<HTMLDivElement>(null);
  useEffect(()=>{if(!subject&&history.data?.items.length)setSubject(`analysis:${history.data.items[0].analysis_id}`)},[history.data,subject]);
  const [kind,id]=subject.split(":");
  const analysis=useQuery({queryKey:["analysis",id],queryFn:()=>platformApi.analysis(id),enabled:kind==="analysis"&&!!id,staleTime:300000,retry:0});
  const delivery=useQuery({queryKey:["delivery",id],queryFn:()=>platformApi.delivery(id),enabled:kind==="delivery"&&!!id,staleTime:60000,retry:0});
  useEffect(()=>{setMessages([])},[subject]);
  useEffect(()=>{end.current?.scrollIntoView({behavior:"smooth"})},[messages]);
  const ask=useMutation({mutationFn:(q:string)=>kind==="delivery"?platformApi.explainDelivery(id,q):platformApi.assistant(q,{analysis_id:id,selected_route_id:analysis.data?.recommended_route_id,mode:analysis.data?.mode,routes:analysis.data?.routes,data_quality:analysis.data?.data_quality,data_sources:analysis.data?.data_sources,explanation:analysis.data?.explanation}),onSuccess:(r:AssistantReply)=>setMessages(m=>[...m,{role:"bot",text:r.message,source:r.source,status:r.status}])});
  const send=(q:string)=>{if(!q.trim()||!id)return;setMessages(m=>[...m,{role:"user",text:q}]);setQuestion("");ask.mutate(q)};
  const gemini=health.data?.services?.gemini;
  const sources=analysis.data?.data_sources;
  return <PageShell title="AI Assistant" subtitle="Grounded explanations over your saved analyses and deliveries · never invents hazard facts">
    <div className="contentGrid">
      <section className="dataCard" style={{display:"flex",flexDirection:"column",minHeight:520}}>
        <div className="toolbar"><select value={subject} onChange={e=>setSubject(e.target.value)} style={{minWidth:320}}><option value="">— Choose an analysis or delivery —</option><optgroup label="Saved analyses">{history.data?.items.map(h=><option key={h.analysis_id} value={`analysis:${h.analysis_id}`}>{h.source} → {h.destination} · {dateOnly(h.created_at)} · A{h.accessibility??"—"}</option>)}</optgroup><optgroup label="Deliveries">{deliveries.data?.items.map(d=><option key={d.id} value={`delivery:${d.id}`}>{d.identifier} · {d.source} → {d.destination} · {d.status}</option>)}</optgroup></select><span className={`badge ${gemini==="configured"?"live":"estimated"}`}>{gemini==="configured"?"Gemini live":"Deterministic fallback"}</span></div>
        <div className="chatBody" style={{flex:1,border:"1px solid #edf0f2",borderRadius:9}}>{!id?<div className="chatMsg bot">Select a saved analysis or a delivery to start. {history.data&&!history.data.items.length?"You have no saved analyses yet; run one from Route Analysis.":""}</div>:messages.length===0?<div className="chatMsg bot">Context loaded{analysis.data?` for ${analysis.data.source.name.split(",")[0]} → ${analysis.data.destination.name.split(",")[0]} (${analysis.data.mode} mode, ${analysis.data.routes.length} route(s))`:delivery.data?` for ${delivery.data.identifier} (${delivery.data.status})`:"…"}. Try a suggestion below.</div>:messages.map((m,i)=><div key={i} className={`chatMsg ${m.role}`}>{m.text}{m.source&&<span className="src">{m.source} · {m.status}</span>}</div>)}{ask.isPending&&<div className="chatMsg bot">Thinking…</div>}{ask.isError&&<div className="chatMsg bot">Assistant unavailable right now.</div>}<div ref={end}/></div>
        <div style={{display:"flex",gap:6,flexWrap:"wrap",margin:"10px 0 4px"}}>{SUGGESTIONS.map(s=><button key={s} type="button" className="secondaryBtn" style={{height:30,fontSize:10,padding:"0 10px"}} disabled={!id||ask.isPending} onClick={()=>send(s)}>{s}</button>)}</div>
        <form className="chatForm" style={{padding:"8px 0 0",borderTop:0}} onSubmit={e=>{e.preventDefault();send(question)}}><input value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Ask about hazards, weather, data provenance or the recommendation…" disabled={!id}/><button type="submit" disabled={!id||ask.isPending||!question.trim()}><Send size={14}/></button></form>
      </section>
      <section className="dataCard"><h2><Sparkles size={15} style={{verticalAlign:-2}}/> Grounding</h2><p style={{fontSize:11,color:"#4b5963",lineHeight:1.55}}>The assistant only receives normalized backend facts for the selected subject: route scores, risk factors, sampled weather, terrain, hazard features with their data state, and the data-source list. Unavailable feeds are stated as unknown, never as safe. Historical datasets are never presented as live alerts.</p>{sources?<DataSourcesPanel sources={sources} compact/>:delivery.data?<p style={{fontSize:11,color:"#4b5963"}}>Delivery context: {delivery.data.route?.name} · accessibility {delivery.data.accessibility} · hazard state {delivery.data.hazards?.summary?.hazard_status||delivery.data.hazards?.status||"unavailable"}.</p>:null}</section>
    </div>
  </PageShell>;
}
