"use client";
import {useEffect, useRef, useState} from 'react';
import {OfficeEngine, WIDTH, HEIGHT, roles, type Role} from './engine';
export function OfficeCanvas({engine, onSelect}: {engine: OfficeEngine; onSelect: (role: Role) => void}) {
  const canvas=useRef<HTMLCanvasElement>(null), select=useRef(onSelect);
  const [loading,setLoading]=useState(true);
  useEffect(()=>{select.current=onSelect;},[onSelect]);
  useEffect(()=>{
    const element=canvas.current!, ctx=element.getContext('2d')!;let frame=0,last=0,disposed=false;
    const media=matchMedia('(prefers-reduced-motion: reduce)'); const motion=()=>{engine.motion(media.matches);};motion();media.addEventListener('change',motion);
    void engine.load().then(()=>{if(!disposed)setLoading(false);});
    const draw=(now:number)=>{if(disposed)return;engine.update(last?Math.min((now-last)/1000,.05):0);last=now;engine.draw(ctx);frame=requestAnimationFrame(draw);};frame=requestAnimationFrame(draw);
    const click=(event:MouseEvent)=>{const box=element.getBoundingClientRect(),role=engine.hit((event.clientX-box.left)*WIDTH/box.width,(event.clientY-box.top)*HEIGHT/box.height);if(role){engine.select(role);select.current(role);}};
    element.addEventListener('click',click);
    return()=>{disposed=true;cancelAnimationFrame(frame);element.removeEventListener('click',click);media.removeEventListener('change',motion);};
  },[engine]);
  return <><canvas ref={canvas} width={WIDTH} height={HEIGHT} aria-label="Interactive pixel office with seven operational characters" className="pixel-canvas" data-ready={!loading} /><div className="pixel-roster" aria-label="Select an operational character">{roles.map(r=><button key={r.id} style={{borderColor:r.color}} onClick={()=>{engine.select(r.id);onSelect(r.id);}}>{r.name}</button>)}</div></>;
}
