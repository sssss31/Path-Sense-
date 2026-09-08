"use client";
import Link from "next/link";
import {usePathname,useRouter} from "next/navigation";
import {useQuery} from "@tanstack/react-query";
import {ChartNoAxesCombined,ChevronLeft,LayoutDashboard,Map,MessageSquareText,Route,Settings,ShieldCheck,Truck} from "lucide-react";
import {useOptionalUser} from "@/features/auth/optional-user";
import {platformApi} from "@/lib/platform-api";
import {useAppStore} from "@/store/app";

const nav=[["/dashboard",LayoutDashboard,"Dashboard"],["/",Route,"Route Analysis"],["/risk-map",Map,"Risk Map"],["/deliveries",Truck,"Deliveries"],["/assistant",MessageSquareText,"AI Assistant"],["/reports",ChartNoAxesCombined,"Reports"],["/settings",Settings,"Settings"]] as const;

/** Workspace sidebar: real navigation, signed-in operator from the API, live active-delivery badge. */
export function Sidebar(){
  const {sidebar,toggleSidebar}=useAppStore();const path=usePathname();const router=useRouter();const {user}=useOptionalUser();
  const dashboard=useQuery({queryKey:["dashboard"],queryFn:platformApi.dashboard,staleTime:30000,retry:0,enabled:!!user});
  const active=dashboard.data?.metrics.active_deliveries||0;
  const initials=user?user.email.slice(0,2).toUpperCase():"—";
  const signOut=()=>{localStorage.removeItem("pathsense_token");router.push("/login")};
  return <aside className={`sidebar ${sidebar?"":"collapsed"}`}>
    <div className="brand"><div className="brandmark"><ShieldCheck size={21}/></div>{sidebar&&<div><strong>PathSense</strong><span>LOGISTICS INTELLIGENCE</span></div>}</div>
    <nav>{nav.map(([href,Icon,label])=><Link href={href} key={href} className={path===href?"active":""} title={label}><Icon size={19}/>{sidebar&&<span>{label}</span>}{href==="/deliveries"&&sidebar&&active>0&&<i title="active deliveries">{active}</i>}</Link>)}</nav>
    <div className="sidebarFoot">{sidebar&&<div className="user"><div>{initials}</div><span><strong>{user?user.email.split("@")[0]:"Not signed in"}</strong>{user?<button className="signout" onClick={signOut}>{user.role} · Sign out</button>:<Link className="signout" href="/login">Sign in</Link>}</span></div>}<button className="collapse" onClick={toggleSidebar} aria-label="Toggle sidebar"><ChevronLeft size={18}/></button></div>
  </aside>;
}
