"use client";
import type {DataSource} from "@/lib/types";
import {PROVENANCE_TEXT,dateTime,label} from "@/lib/format";

/** Per-source transparency: organisation, provenance, coverage and age. Source badges stay authoritative even in live mode. */
export function DataSourcesPanel({sources,compact=false}:{sources:DataSource[];compact?:boolean}){
  if(!sources?.length)return null;
  return <div className="sourcesPanel">
    <div className="panelTop"><span className="eyebrow">DATA SOURCES</span><small>{sources.filter(s=>s.status==="live").length} live · {sources.filter(s=>s.status==="historical").length} historical · {sources.filter(s=>s.status==="unavailable").length} unavailable</small></div>
    <table className="provenanceTable"><tbody>{sources.map(s=><tr key={s.key}>
      <td><strong>{s.name}</strong>{!compact&&s.note&&<div className="sourceNote">{s.note}</div>}</td>
      <td>{s.organization}</td>
      <td><span className={`badge ${s.status}`}>{PROVENANCE_TEXT[s.status]||label(s.status)}</span>{s.coverage&&s.coverage!=="full"&&<span className="badge partial" style={{marginLeft:4}}>{label(s.coverage)} coverage</span>}</td>
      <td className="sourceAge">{s.period?`Period ${s.period}`:s.updated_at?(s.status==="live"?`Updated ${dateTime(s.updated_at)}`:`Imported ${dateTime(s.updated_at)}`):"—"}</td>
    </tr>)}</tbody></table>
  </div>;
}
