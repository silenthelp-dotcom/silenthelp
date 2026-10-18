import {describe,it,expect} from 'vitest';
import {summarize} from '../backend/functions/snapshot';
const c=(m:string)=>({sha:'a',message:m,author:'x',date:'',url:''});
const ai={url:'https://provider.example',key:'k',model:'m'};
const reply=(content:unknown)=>async()=>new Response(JSON.stringify({choices:[{message:{content:JSON.stringify(content)}}]}));
describe('weekly code summary',()=>{
 it('uses the model summary when valid',async()=>{const r=await summarize([c('HQ: add video uploads')],['hq/x.ts'],ai,reply({headline:'HQ got video uploads.',summary:['Videos up to 50 MB.']}));expect(r).toEqual({headline:'HQ got video uploads.',summary:['Videos up to 50 MB.']})});
 it('falls back to commit titles on provider error or bad output',async()=>{const commits=[c('Fix login\n\nbody'),c('Add photo')];expect((await summarize(commits,[],ai,async()=>new Response('x',{status:503}))).summary).toEqual(['Fix login','Add photo']);expect((await summarize(commits,[],ai,reply({nope:1}))).headline).toBe('2 changes this week')});
 it('reports a quiet week without calling the model',async()=>{let called=false;const r=await summarize([],[],ai,async()=>{called=true;return new Response('')});expect(called).toBe(false);expect(r.headline).toBe('No code changes this week')});
});
