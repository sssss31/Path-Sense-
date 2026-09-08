"use client";
import {useEffect,useState} from "react";
import {token} from "@/lib/platform-api";
export type SessionUser={id:string;email:string;role:string};
const BASE=process.env.NEXT_PUBLIC_API_BASE_URL||"http://localhost:8000/api/v1";
/** Non-blocking session lookup for pages that work anonymously (route analysis) but unlock actions when signed in. */
export function useOptionalUser(){
  const[user,setUser]=useState<SessionUser|null>(null);const[checked,setChecked]=useState(false);
  useEffect(()=>{const value=token();if(!value){setChecked(true);return}fetch(`${BASE}/auth/me`,{headers:{Authorization:`Bearer ${value}`}}).then(r=>r.ok?r.json():Promise.reject()).then(setUser).catch(()=>setUser(null)).finally(()=>setChecked(true))},[]);
  return {user,checked};
}
