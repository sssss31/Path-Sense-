export const label=(value:string|null|undefined)=>value?value.replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase()):"—";
export const minutes=(value:number|null|undefined)=>value==null?"—":`${Math.floor(value/60)}h ${value%60}m`;
export const dateTime=(value:string|null|undefined)=>value?new Date(value).toLocaleString(undefined,{dateStyle:"medium",timeStyle:"short"}):"—";
export const dateOnly=(value:string|null|undefined)=>value?new Date(value).toLocaleDateString(undefined,{dateStyle:"medium"}):"—";
export const shortId=(value:string|null|undefined)=>value?value.slice(0,8):"—";
/** ISO string → value usable by <input type="datetime-local">. */
export const toLocalInput=(value:string|null|undefined)=>{if(!value)return "";const d=new Date(value);const pad=(n:number)=>String(n).padStart(2,"0");return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`};
export const fromLocalInput=(value:string)=>value?new Date(value).toISOString():null;
export const STATUS_LABELS:Record<string,string>={planned:"Planned",in_transit:"In transit",delayed:"Delayed",completed:"Completed",cancelled:"Cancelled"};
export const HAZARD_STATUS_TEXT:Record<string,string>={intersections:"Hazard zones intersect this route",no_intersection:"No hazard intersection (coverage confirmed)",partial_coverage:"Partial dataset coverage",unavailable:"Hazard data unavailable",simulated:"Simulated demo hazard data"};
export const PROVENANCE_TEXT:Record<string,string>={live:"Live",historical:"Historical",estimated:"Estimated",simulated:"Simulated",cached:"Cached",unavailable:"Unavailable",partial:"Partial"};
