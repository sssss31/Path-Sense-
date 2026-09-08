import type {Analysis} from "./types";
import {token} from "./platform-api";
const BASE=process.env.NEXT_PUBLIC_API_BASE_URL||"http://localhost:8000/api/v1";
// Route analysis works anonymously, but sends the bearer token when present so the
// analysis is persisted under the operator and can be turned into a delivery.
export async function analyzeRoute(payload:object):Promise<Analysis>{
  const auth=token();
  const response=await fetch(`${BASE}/analysis/route`,{method:"POST",headers:{"Content-Type":"application/json",...(auth?{Authorization:`Bearer ${auth}`}:{})},body:JSON.stringify(payload)});
  if(!response.ok){const body=await response.json().catch(()=>null);throw new Error(typeof body?.detail==="string"?body.detail:"Analysis service is temporarily unavailable")}
  return response.json();
}
