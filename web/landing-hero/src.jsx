import React from 'react';
import {createRoot} from 'react-dom/client';
import {ArrowRight,ArrowDown} from 'lucide-react';
import Brain from './Brain';
import './hero.css';
function Hero(){return <><Brain/><div className="sh-hero-copy"><p className="sh-eyebrow">Free forever</p><h1>Support that notices<br/>before you have to ask</h1><p className="sh-description">A private, on-device wellbeing companion for students, families, and school counselors.</p><a className="sh-cta" href="/app">Start free <ArrowRight size={18}/></a></div><div className="sh-hero-bottom"><a href="#demo">Scroll <ArrowDown size={14}/></a></div></>}
const root=document.getElementById('sh-hero-root');if(root)createRoot(root).render(<Hero/>);
