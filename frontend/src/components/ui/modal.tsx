"use client";
import {useEffect} from "react";
import {X} from "lucide-react";
export function Modal({title,eyebrow,onClose,children,width=520}:{title:string;eyebrow?:string;onClose:()=>void;children:React.ReactNode;width?:number}){
  useEffect(()=>{const onKey=(e:KeyboardEvent)=>{if(e.key==="Escape")onClose()};window.addEventListener("keydown",onKey);return()=>window.removeEventListener("keydown",onKey)},[onClose]);
  return <div className="modalBackdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}>
    <div className="modal" role="dialog" aria-modal="true" aria-label={title} style={{maxWidth:width}}>
      <header className="modalHead"><div>{eyebrow&&<span className="eyebrow">{eyebrow}</span>}<h2>{title}</h2></div><button type="button" className="iconBtn" aria-label="Close" onClick={onClose}><X size={17}/></button></header>
      {children}
    </div>
  </div>;
}
