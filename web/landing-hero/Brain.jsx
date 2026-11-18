import React,{useRef,useEffect} from 'react';
import {createNetwork} from './network.js';
export default function Brain(){const ref=useRef(null);useEffect(()=>{
 const canvas=ref.current,ctx=canvas.getContext('2d'),host=canvas.parentElement;if(!ctx)return;
 const art=new Image();let nodes=[],edges=[],artReady=false;
 let width=0,height=0,scale=1,dx=0,dy=0,frame=0,time=0,last=0,inView=true,disposed=false;
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');
 art.onload=()=>{
  if(disposed)return;
  const sample=document.createElement('canvas');sample.width=600;sample.height=400;
  const sampleCtx=sample.getContext('2d',{willReadFrequently:true});if(!sampleCtx)return;
  sampleCtx.drawImage(art,0,0,600,400);const pixels=sampleCtx.getImageData(0,0,600,400).data;
  const network=createNetwork((x,y)=>{
   if(y>=400)return false;const i=(Math.floor(y)*600+Math.floor(x))*4;
   return pixels[i+3]>140&&pixels[i]+pixels[i+1]+pixels[i+2]>240;
  },220);
  nodes=network.nodes;edges=network.edges;artReady=true;host.classList.add('sh-brain-ready');restart();
 };
 art.src='/static/cinematic/img/sh-brain-engraving.png';
 function draw(now){
  if(disposed||!inView||document.hidden)return;
  const dt=Math.min(now-last,40)||16;last=now;if(!reduced.matches)time+=dt/1000;
  ctx.clearRect(0,0,width,height);ctx.save();ctx.translate(dx,dy);ctx.scale(scale,scale);
  if(artReady){
   ctx.globalAlpha=.34;ctx.drawImage(art,0,0,600,400);ctx.globalAlpha=1;
   // Source-atop embeds muted activity in the engraving's existing alpha.
   // No cursor tracking, floating branches, halos, or bright particles.
   ctx.globalCompositeOperation='source-atop';
   edges.forEach(e=>{
    const a=nodes[e.a],b=nodes[e.b],pulse=(Math.sin(time*.35+e.phase*Math.PI*2)+1)/2;
    ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.quadraticCurveTo((a.x+b.x)/2+8,(a.y+b.y)/2-8,b.x,b.y);
    ctx.strokeStyle=`rgba(${e.a%2?'100,112,143':'148,105,111'},${.07+pulse*.12})`;ctx.lineWidth=.65;ctx.stroke();
   });
   ctx.globalCompositeOperation='source-over';
  }
  ctx.restore();if(!reduced.matches)frame=requestAnimationFrame(draw);
 }
 function restart(){cancelAnimationFrame(frame);last=0;if(inView&&!document.hidden)frame=requestAnimationFrame(draw)}
 function resize(){const r=host.getBoundingClientRect();width=r.width;height=r.height;const dpr=Math.min(devicePixelRatio||1,2);canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);scale=Math.min(width/620,height/414);dx=(width-600*scale)/2;dy=(height-400*scale)/2;restart()}
 const resizer=new ResizeObserver(resize);resizer.observe(host);const observer=new IntersectionObserver(([entry])=>{inView=entry.isIntersecting;restart()});observer.observe(host);
 document.addEventListener('visibilitychange',restart);reduced.addEventListener('change',restart);resize();
 return()=>{disposed=true;art.onload=null;cancelAnimationFrame(frame);resizer.disconnect();observer.disconnect();document.removeEventListener('visibilitychange',restart);reduced.removeEventListener('change',restart)};
},[]);return <figure className="sh-brain" role="img" aria-label="Anatomical brain engraving with SH woven into its folds"><img className="sh-brain-fallback" src="/static/cinematic/img/sh-brain-engraving.png" alt=""/><canvas ref={ref} aria-hidden="true"/></figure>}
