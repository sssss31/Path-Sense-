"use client";
import {QueryClient,QueryClientProvider} from "@tanstack/react-query";
import {useEffect,useState} from "react";
import {apiBase} from "@/lib/api-base";
export function Providers({children}:{children:React.ReactNode}){const [client]=useState(()=>new QueryClient());useEffect(()=>{fetch(`${apiBase()}/system/health`).catch(()=>{})},[]);return <QueryClientProvider client={client}>{children}</QueryClientProvider>}

