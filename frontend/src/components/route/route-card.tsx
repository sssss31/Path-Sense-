"use client";
import type {Route} from "@/lib/types";
import {Clock3,Mountain,Route as RouteIcon} from "lucide-react";
import {useAppStore} from "@/store/app";
export function RouteCard({route}:{route:Route}){const {selectedRoute,setRoute}=useAppStore();return <button onClick={()=>setRoute(route.id)} className={`routeCard ${selectedRoute===route.id?"selected":""}`}><div className="routeHead"><span className={`risk ${route.risk.level}`}>{route.risk.level} risk</span>{route.recommended&&<span className="recommended">Recommended</span>}</div><strong>{route.name}</strong><div className="routeMeta"><span><RouteIcon size={15}/>{route.distance_km} km</span><span><Clock3 size={15}/>{Math.floor(route.eta_minutes/60)}h {route.eta_minutes%60}m</span><span><Mountain size={15}/>{route.terrain.average_slope}°</span></div><div className="miniScore"><span>Accessibility</span><div><i style={{width:`${route.accessibility.score}%`}}/></div><b>{route.accessibility.score}</b></div></button>}

