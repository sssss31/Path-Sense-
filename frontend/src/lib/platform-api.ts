import type {Analysis,AnalysisMap,AssistantReply,Dataset,DashboardSummary,Delivery,DeliveryCreatePayload,DeliveryDetail,DeliveryUpdatePayload,ExternalLayer,Health,HistoryPage,Notification,Readiness,ReportsSummary,SpatialRiskSummary,SystemConfig,TransitionRules,WeatherNow} from "./types";

// Single place for API routes so paths stay editable centrally.
export const ROUTES={
  analysis:"/analysis",analysisDetail:(id:string)=>`/analysis/${id}`,analysisMap:(id:string,alternatives=false)=>`/analysis/${id}/map${alternatives?"?alternatives=true":""}`,
  spatialRisk:(id:string)=>`/analysis/${id}/spatial-risk-summary`,dashboard:"/dashboard/summary",reports:"/reports/summary",datasets:"/datasets",health:"/system/health",
  deliveries:"/deliveries",delivery:(id:string)=>`/deliveries/${id}`,deliveryTransitions:(id:string)=>`/deliveries/${id}/transitions`,deliveryExplain:(id:string)=>`/deliveries/${id}/explain`,transitionRules:"/deliveries/transitions",
  riskZones:"/risk-zones",incidents:"/incidents",assistant:"/assistant/chat",mapLayers:"/map-layers",readiness:"/system/readiness",userReports:"/user-reports",weather:"/system/weather",notifications:"/notifications",config:"/system/config",suggest:"/geocode/suggest",
};
import {apiBase} from "./api-base";

export function token(){return typeof window==="undefined"?null:localStorage.getItem("pathsense_token")}

export class ApiError extends Error{status:number;detail:unknown;constructor(status:number,detail:unknown,message:string){super(message);this.status=status;this.detail=detail}}
function describe(detail:unknown,status:number):string{
  if(typeof detail==="string")return detail;
  if(Array.isArray(detail))return detail.map((d:{loc?:unknown[];msg?:string})=>`${(d.loc||[]).filter(x=>x!=="body").join(".")}: ${d.msg}`).join("; ");
  return status===401?"Your session has expired. Sign in again.":status===404?"Not found.":status===409?"That change is not allowed.":status>=500?"Server error. Try again shortly.":"Request failed.";
}
export async function api<T>(path:string,options:RequestInit={}):Promise<T>{
  const auth=token();
  const response=await fetch(`${apiBase()}${path}`,{...options,headers:{"Content-Type":"application/json",...(auth?{Authorization:`Bearer ${auth}`}:{}),...options.headers}});
  if(response.status===204)return undefined as T;
  const body=await response.json().catch(()=>null);
  if(!response.ok){const detail=body?.detail??body;throw new ApiError(response.status,detail,describe(detail,response.status))}
  return body as T;
}
const qs=(params:Record<string,string|number|undefined|null>)=>{const p=new URLSearchParams();Object.entries(params).forEach(([k,v])=>{if(v!==undefined&&v!==null&&v!=="")p.set(k,String(v))});const s=p.toString();return s?`?${s}`:""};

export const platformApi={
  history:(page=1,pageSize=20)=>api<HistoryPage>(`${ROUTES.analysis}${qs({page,page_size:pageSize})}`),
  analysis:(id:string)=>api<Analysis>(ROUTES.analysisDetail(id)),
  analysisMap:(id:string,alternatives=false)=>api<AnalysisMap>(ROUTES.analysisMap(id,alternatives)),
  spatialRisk:(id:string)=>api<SpatialRiskSummary>(ROUTES.spatialRisk(id)),
  dashboard:()=>api<DashboardSummary>(ROUTES.dashboard),
  reports:(range?:string,dateFrom?:string,dateTo?:string)=>api<ReportsSummary>(`${ROUTES.reports}${qs({range,date_from:dateFrom,date_to:dateTo})}`),
  datasets:()=>api<{items:Dataset[];total:number}>(ROUTES.datasets),
  health:()=>api<Health>(ROUTES.health),
  readiness:()=>api<Readiness>(ROUTES.readiness),
  suggest:(q:string)=>api<{items:{name:string;short:string;lat:number;lon:number;type:string;state:string|null}[];provider:string}>(`${ROUTES.suggest}${qs({q})}`),
  weather:(lat:number,lon:number,name?:string)=>api<WeatherNow>(`${ROUTES.weather}${qs({lat,lon,name})}`),
  notifications:()=>api<{items:Notification[];count:number;generated_at:string}>(ROUTES.notifications),
  config:()=>api<SystemConfig>(ROUTES.config),
  mapLayers:()=>api<{items:ExternalLayer[];total:number;note:string}>(ROUTES.mapLayers),
  deliveries:(params:{page?:number;status?:string;search?:string}={})=>api<{items:Delivery[];page:number;page_size:number;total:number}>(`${ROUTES.deliveries}${qs(params)}`),
  delivery:(id:string)=>api<DeliveryDetail>(ROUTES.delivery(id)),
  createDelivery:(payload:DeliveryCreatePayload)=>api<Delivery>(ROUTES.deliveries,{method:"POST",body:JSON.stringify(payload)}),
  updateDelivery:(id:string,payload:DeliveryUpdatePayload)=>api<DeliveryDetail>(ROUTES.delivery(id),{method:"PATCH",body:JSON.stringify(payload)}),
  deleteDelivery:(id:string)=>api<void>(ROUTES.delivery(id),{method:"DELETE"}),
  transitionRules:()=>api<TransitionRules>(ROUTES.transitionRules),
  explainDelivery:(id:string,message?:string)=>api<AssistantReply>(ROUTES.deliveryExplain(id),{method:"POST",body:JSON.stringify({message})}),
  assistant:(message:string,context:object)=>api<AssistantReply>(ROUTES.assistant,{method:"POST",body:JSON.stringify({message,context})}),
};
