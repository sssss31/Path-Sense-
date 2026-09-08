"use client";
import {Bar,BarChart,CartesianGrid,Cell,Line,LineChart,ResponsiveContainer,Tooltip,XAxis,YAxis} from "recharts";
import type {NamedValue,TrendPoint} from "@/lib/types";
import {label} from "@/lib/format";

/* Palette validated with the dataviz validator (light surface). Status colors are reserved for risk levels;
   categorical slots are assigned in fixed order by entity, never by rank. */
export const RISK_COLORS:Record<string,string>={low:"#2f8f5b",moderate:"#eda100",high:"#e34948",critical:"#4a3aa7"};
export const STATUS_COLORS:Record<string,string>={planned:"#2a78d6",in_transit:"#1baf7a",delayed:"#eda100",completed:"#008300",cancelled:"#8a8f96"};
const CATEGORICAL=["#2a78d6","#eb6834","#1baf7a","#eda100","#e87ba4","#4a3aa7"];
const INK={primary:"#17212b",secondary:"#5b6771",grid:"#e8ecef"};
const RISK_ORDER=["low","moderate","high","critical"];

function EmptyState({text}:{text:string}){return <div className="chartEmpty">{text}</div>}
function ChartTip({active,payload,labelText,formatter}:{active?:boolean;payload?:{value:number;payload:Record<string,unknown>}[];labelText?:string;formatter?:(v:number,row:Record<string,unknown>)=>string}){
  if(!active||!payload?.length)return null;const row=payload[0];
  return <div className="chartTip"><strong>{labelText||label(String(row.payload.name??row.payload.date))}</strong><span>{formatter?formatter(row.value,row.payload):row.value}</span></div>;
}
function DataTable({rows,columns}:{rows:Record<string,unknown>[];columns:[string,string][]}){
  return <details className="chartTable"><summary>Table view</summary><table><thead><tr>{columns.map(([k,h])=><th key={k}>{h}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={i}>{columns.map(([k])=><td key={k}>{String(r[k]??"—")}</td>)}</tr>)}</tbody></table></details>;
}

/** Categorical bars with a fixed color per entity and always-visible direct labels. */
function CategoryBars({data,colorFor,valueLabel,emptyText,order}:{data:NamedValue[];colorFor:(name:string,index:number)=>string;valueLabel:string;emptyText:string;order?:string[]}){
  if(!data.length)return <EmptyState text={emptyText}/>;
  const rows=order?[...data].sort((a,b)=>order.indexOf(a.name)-order.indexOf(b.name)):data;
  const total=rows.reduce((s,r)=>s+r.value,0)||1;
  return <div className="chartBlock">
    <ResponsiveContainer width="100%" height={Math.max(150,rows.length*34+20)}>
      <BarChart data={rows} layout="vertical" margin={{top:4,right:44,bottom:4,left:4}} barCategoryGap={6}>
        <CartesianGrid horizontal={false} stroke={INK.grid}/>
        <XAxis type="number" hide/>
        <YAxis type="category" dataKey="name" width={118} tickLine={false} axisLine={false} tick={{fontSize:11,fill:INK.secondary}} tickFormatter={label}/>
        <Tooltip cursor={{fill:"#f2f4f6"}} content={<ChartTip formatter={(v)=>`${v} ${valueLabel} · ${Math.round(v/total*100)}%`}/>}/>
        <Bar dataKey="value" radius={[0,4,4,0]} barSize={16} label={{position:"right",fontSize:11,fill:INK.primary}}>{rows.map((r,i)=><Cell key={r.name} fill={colorFor(r.name,i)}/>)}</Bar>
      </BarChart>
    </ResponsiveContainer>
    <DataTable rows={rows} columns={[["name","Category"],["value",valueLabel]]}/>
  </div>;
}

export function RiskDistributionChart({data}:{data:NamedValue[]}){
  return <CategoryBars data={data.filter(d=>d.value>0||RISK_ORDER.slice(0,3).includes(d.name))} colorFor={n=>RISK_COLORS[n]||"#8a8f96"} valueLabel="analyses" emptyText="No analyses in this range." order={RISK_ORDER}/>;
}
export function RiskFactorChart({data}:{data:NamedValue[]}){
  return <CategoryBars data={data} colorFor={()=>"#2a78d6"} valueLabel="routes" emptyText="No risk factors recorded for recommended routes in this range."/>;
}
export function CargoDistributionChart({data}:{data:NamedValue[]}){
  return <CategoryBars data={data} colorFor={(_,i)=>CATEGORICAL[i%CATEGORICAL.length]} valueLabel="analyses" emptyText="No cargo data in this range."/>;
}
export function DeliveryStatusChart({data}:{data:NamedValue[]}){
  return <CategoryBars data={data} colorFor={n=>STATUS_COLORS[n]||"#8a8f96"} valueLabel="deliveries" emptyText="No deliveries in this range." order={Object.keys(STATUS_COLORS)}/>;
}

const AVAILABILITY_COLORS:Record<string,string>={"Full data coverage":"#2f8f5b","Partial hazard coverage":"#eda100","Hazard data unavailable":"#e34948","Simulated demo data":"#4a3aa7","Weather unavailable":"#8a8f96"};
/** Analyses by evidence state (from persisted data_quality). One chart only; detail lives in Settings/Data Sources. */
export function DataAvailabilityChart({data}:{data:NamedValue[]}){
  return <CategoryBars data={data} colorFor={n=>AVAILABILITY_COLORS[n]||"#8a8f96"} valueLabel="analyses" emptyText="No analyses in this range." order={Object.keys(AVAILABILITY_COLORS)}/>;
}

/** Aggregated daily average; plots the returned aggregation only. */
export function AccessibilityTrendChart({data,compact=false}:{data:TrendPoint[];compact?:boolean}){
  if(!data.length)return <EmptyState text="No analyses in this range."/>;
  const rows=data.map(d=>({...d,short:new Date(d.date).toLocaleDateString(undefined,{month:"short",day:"numeric"})}));
  return <div className="chartBlock">
    <ResponsiveContainer width="100%" height={compact?150:230}>
      <LineChart data={rows} margin={{top:12,right:16,bottom:4,left:-14}}>
        <CartesianGrid vertical={false} stroke={INK.grid}/>
        <XAxis dataKey="short" tickLine={false} axisLine={false} tick={{fontSize:10,fill:INK.secondary}} interval="preserveStartEnd"/>
        <YAxis domain={[0,100]} ticks={[0,25,50,75,100]} tickLine={false} axisLine={false} tick={{fontSize:10,fill:INK.secondary}}/>
        <Tooltip cursor={{stroke:INK.secondary,strokeDasharray:"3 3"}} content={<ChartTip formatter={(v,row)=>`${v}/100 avg · ${row.analyses} analyses`}/>}/>
        <Line type="monotone" dataKey="average_accessibility" name="Average accessibility" stroke="#2a78d6" strokeWidth={2} dot={{r:4,strokeWidth:2,stroke:"#fff",fill:"#2a78d6"}} activeDot={{r:6}} isAnimationActive={false}/>
      </LineChart>
    </ResponsiveContainer>
    {!compact&&<DataTable rows={rows} columns={[["date","Date"],["average_accessibility","Avg accessibility"],["analyses","Analyses"]]}/>}
  </div>;
}
