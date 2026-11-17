import React,{useRef,useEffect} from 'react';
import paths from './logo-paths.json';
import {createNetwork,proximity} from './network.js';
export default function Brain(){const ref=useRef(null);useEffect(()=>{
 const canvas=ref.current,ctx=canvas.getContext('2d'),host=canvas.parentElement;if(!ctx)return;
 const logo=new Path2D();paths.forEach(d=>logo.addPath(new Path2D(d),new DOMMatrix().translate(-760*600/2840,-600*600/2840).scale(600/2840)));
 const {nodes,edges}=createNetwork((x,y)=>ctx.isPointInPath(logo,x,y));
 let width=0,height=0,scale=1,dx=0,dy=0,frame=0,time=0,last=0,inView=true,disposed=false;
 let pointer={x:-1000,y:-1000},active=false,touchUntil=0;
 const reduced=matchMedia('(prefers-reduced-motion: reduce)'),strengths=nodes.map(()=>0);
 function glow(x,y,r,color,a){const g=ctx.createRadialGradient(x,y,0,x,y,r);g.addColorStop(0,`rgba(${color},${a})`);g.addColorStop(.25,`rgba(${color},${a*.32})`);g.addColorStop(1,`rgba(${color},0)`);ctx.fillStyle=g;ctx.fillRect(x-r,y-r,r*2,r*2)}
 function line(a,b,color,alpha,w=1){ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.quadraticCurveTo((a.x+b.x)/2+10,(a.y+b.y)/2-10,b.x,b.y);ctx.strokeStyle=`rgba(${color},${alpha})`;ctx.lineWidth=w;ctx.stroke()}
 function draw(now){if(disposed||!inView||document.hidden)return;const dt=Math.min(now-last,40)||16;last=now;if(!reduced.matches)time+=dt/1000;if(touchUntil&&now>touchUntil){active=false;touchUntil=0}
  ctx.clearRect(0,0,width,height);ctx.save();ctx.translate(dx,dy);ctx.scale(scale,scale);
  ctx.fillStyle='rgba(220,220,220,.42)';ctx.fill(logo);
  nodes.forEach((n,i)=>{const target=active?proximity(n,pointer,150):0;strengths[i]=reduced.matches?target:strengths[i]+(target-strengths[i])*.12});
  edges.forEach(e=>{const a=nodes[e.a],b=nodes[e.b],s=Math.max(strengths[e.a],strengths[e.b]);line(a,b,a.color,.035+s*.7,.5+s*.8);if(s>.02&&!reduced.matches){const t=(time*(.18+s*.3)+e.phase)%1,c={x:(a.x+b.x)/2+10,y:(a.y+b.y)/2-10},x=(1-t)**2*a.x+2*(1-t)*t*c.x+t*t*b.x,y=(1-t)**2*a.y+2*(1-t)*t*c.y+t*t*b.y;glow(x,y,6+s*4,a.color,s)}});
  nodes.forEach((n,i)=>{const s=strengths[i];ctx.fillStyle=`rgba(215,215,215,${.12+s*.7})`;ctx.beginPath();ctx.arc(n.x,n.y,.8+s*1.7,0,Math.PI*2);ctx.fill();if(s<.015)return;ctx.save();ctx.translate(n.x,n.y);const pop=.5+s*.8;ctx.scale(pop,pop);n.branches.forEach(b=>{const tip={x:Math.cos(b.angle)*b.length,y:Math.sin(b.angle)*b.length};line({x:0,y:0},tip,n.color,s*.8,.7);for(const sign of [-1,1])line({x:tip.x*.65,y:tip.y*.65},{x:tip.x*.65+Math.cos(b.angle+sign*.8)*b.length*.45,y:tip.y*.65+Math.sin(b.angle+sign*.8)*b.length*.45},n.color,s*.5,.5)});glow(0,0,22,n.color,s*.8);glow(0,0,5,n.color,s);ctx.restore()});
  ctx.restore();if(!reduced.matches)frame=requestAnimationFrame(draw);
 }
 function restart(){cancelAnimationFrame(frame);last=0;if(inView&&!document.hidden)frame=requestAnimationFrame(draw)}
 function resize(){const r=host.getBoundingClientRect();width=r.width;height=r.height;const dpr=Math.min(devicePixelRatio||1,2);canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);scale=Math.min(width/660,height/540);dx=(width-600*scale)/2;dy=(height-486*scale)/2;restart()}
 function move(e){const r=host.getBoundingClientRect();pointer={x:(e.clientX-r.left-dx)/scale,y:(e.clientY-r.top-dy)/scale};active=true;touchUntil=e.pointerType==='touch'?performance.now()+1600:0;if(reduced.matches)restart()}
 function leave(){active=false;if(reduced.matches)restart()}
 function focus(){pointer={x:300,y:245};active=true;restart()}
 function visibility(){restart()}
 const resizer=new ResizeObserver(resize);resizer.observe(host);const observer=new IntersectionObserver(([entry])=>{inView=entry.isIntersecting;restart()});observer.observe(host);
 host.addEventListener('pointermove',move,{passive:true});host.addEventListener('pointerdown',move,{passive:true});host.addEventListener('pointerleave',leave);host.addEventListener('focus',focus);host.addEventListener('blur',leave);document.addEventListener('visibilitychange',visibility);reduced.addEventListener('change',restart);resize();host.classList.add('sh-brain-ready');
 return()=>{disposed=true;cancelAnimationFrame(frame);resizer.disconnect();observer.disconnect();host.removeEventListener('pointermove',move);host.removeEventListener('pointerdown',move);host.removeEventListener('pointerleave',leave);host.removeEventListener('focus',focus);host.removeEventListener('blur',leave);document.removeEventListener('visibilitychange',visibility);reduced.removeEventListener('change',restart)};
},[]);return <figure className="sh-brain" tabIndex={0} role="img" aria-label="SilentHelp SH brain logo. Move over the logo or tap it to reveal red and blue neurons."><img className="sh-brain-fallback" src="/static/cinematic/img/sh-brain.svg" alt=""/><canvas ref={ref} aria-hidden="true"/><figcaption><span/> MOVE TO CONNECT <span/></figcaption></figure>}
