// Team chat data layer. Production: Supabase tables (read under RLS), chat_* RPCs (writes),
// a private "chat" bucket for pictures and Realtime for live updates. Demo: the same API over localStorage.
import {supabase,demo} from './api';
import {readDemo} from './demo';

export type Channel={id:string;kind:'team'|'group'|'dm';name:string|null;description:string|null;project_id:string|null;dm_key:string|null;created_by:string|null;created_at:string};
export type Member={channel_id:string;user_id:string;last_read_at:string;joined_at?:string};
export type Message={id:string;channel_id:string;author_id:string;body:string;image_path:string|null;image_name:string|null;reply_to:string|null;created_at:string;edited_at:string|null;unsent_at:string|null};
export type Reaction={message_id:string;user_id:string;emoji:string};
export type Overview={channel_id:string;unread:number;last_at:string|null;last_body:string|null;last_author:string|null;last_unsent:boolean;last_image:boolean};
export type Person={id:string;full_name:string;avatar_path:string|null;role:string;bio:string|null};
export type ChatEvent={table:string;channel_id?:string};

export const PAGE=60;
export const IMAGE_TYPES=['image/png','image/jpeg','image/webp','image/gif'];
export function checkImage(f:File){if(!IMAGE_TYPES.includes(f.type))throw new Error('Pictures can be PNG, JPEG, WebP or GIF.');if(f.size>10*1024*1024)throw new Error('Pictures can be up to 10 MB.');}

export interface ChatApi{
 me():string;
 load():Promise<{channels:Channel[];members:Member[];overview:Overview[];people:Person[]}>;
 messages(ch:string,before?:string):Promise<{messages:Message[];reactions:Reaction[];hidden:string[]}>;
 send(ch:string,body:string,file?:File|null,replyTo?:string|null):Promise<void>;
 edit(id:string,body:string):Promise<void>;
 unsend(id:string):Promise<void>;
 hide(id:string):Promise<void>;
 react(id:string,emoji:string):Promise<void>;
 createGroup(name:string,members:string[],project?:string|null,description?:string):Promise<string>;
 addMembers(ch:string,members:string[]):Promise<void>;
 leave(ch:string):Promise<void>;
 rename(ch:string,name:string,description?:string):Promise<void>;
 openDm(other:string):Promise<string>;
 markRead(ch:string):Promise<void>;
 imageUrl(path:string):Promise<string>;
 subscribe(cb:(e:ChatEvent)=>void):()=>void;
}

const must=<T,>(r:{data:T;error:any}):T=>{if(r.error)throw new Error(r.error.message);return r.data;};
const ext=(f:File)=>({'image/png':'png','image/jpeg':'jpg','image/webp':'webp','image/gif':'gif'} as Record<string,string>)[f.type]||'img';

function supabaseChat(userId:string):ChatApi{
 const sb=supabase!;const urls=new Map<string,{url:string;until:number}>();
 return {
  me:()=>userId,
  async load(){const [channels,members,overview,people]=await Promise.all([sb.from('chat_channels').select('*'),sb.from('chat_members').select('channel_id,user_id,last_read_at,joined_at'),sb.rpc('chat_overview'),sb.rpc('team_directory')]);return {channels:must(channels) as Channel[],members:must(members) as Member[],overview:must(overview) as Overview[],people:must(people) as Person[]};},
  async messages(ch,before){let q=sb.from('chat_messages').select('*').eq('channel_id',ch).order('created_at',{ascending:false}).limit(PAGE);if(before)q=q.lt('created_at',before);const messages=(must(await q) as Message[]).reverse();const ids=messages.map(m=>m.id);if(!ids.length)return {messages,reactions:[],hidden:[]};const [r,h]=await Promise.all([sb.from('chat_reactions').select('message_id,user_id,emoji').in('message_id',ids),sb.from('chat_hidden').select('message_id').in('message_id',ids)]);return {messages,reactions:must(r) as Reaction[],hidden:(must(h) as {message_id:string}[]).map(x=>x.message_id)};},
  async send(ch,body,file,replyTo){let image_path:string|null=null,image_name:string|null=null;if(file){checkImage(file);image_path=`${ch}/${userId}/${crypto.randomUUID()}.${ext(file)}`;image_name=file.name.slice(0,240);must(await sb.storage.from('chat').upload(image_path,file,{contentType:file.type,upsert:false}));}
   const r=await sb.rpc('chat_send',{ch,body,image_path,image_name,reply_to:replyTo||null});if(r.error){if(image_path)await sb.storage.from('chat').remove([image_path]);throw new Error(r.error.message);}},
  async edit(id,body){must(await sb.rpc('chat_edit',{m:id,body}));},
  async unsend(id){const path=must(await sb.rpc('chat_unsend',{m:id})) as string|null;if(path)await sb.storage.from('chat').remove([path]);},
  async hide(id){must(await sb.rpc('chat_hide',{m:id}));},
  async react(id,emoji){must(await sb.rpc('chat_react',{m:id,emoji}));},
  async createGroup(name,members,project,description){return must(await sb.rpc('chat_create_group',{name,members,project:project||null,description:description||null})) as string;},
  async addMembers(ch,members){must(await sb.rpc('chat_add_members',{ch,members}));},
  async leave(ch){must(await sb.rpc('chat_leave',{ch}));},
  async rename(ch,name,description){must(await sb.rpc('chat_rename',{ch,name,description:description||null}));},
  async openDm(other){return must(await sb.rpc('chat_open_dm',{other})) as string;},
  async markRead(ch){await sb.rpc('chat_mark_read',{ch});},
  async imageUrl(path){const c=urls.get(path);if(c&&c.until>Date.now())return c.url;const r=must(await sb.storage.from('chat').createSignedUrl(path,3600))!;urls.set(path,{url:r.signedUrl,until:Date.now()+50*60000});return r.signedUrl;},
  subscribe(cb){const ch=sb.channel('hq-chat-'+crypto.randomUUID());for(const table of ['chat_messages','chat_reactions','chat_members','chat_channels'])ch.on('postgres_changes' as any,{event:'*',schema:'public',table},(p:any)=>cb({table,channel_id:p.new?.channel_id||p.old?.channel_id}));ch.subscribe();return()=>{void sb.removeChannel(ch)};},
 };
}

// ── Demo: everything in this browser's localStorage, shared across tabs. ──
type Store={channels:Channel[];members:Member[];messages:Message[];reactions:Reaction[];hidden:{message_id:string;user_id:string}[]};
const KEY='silenthelp-hq-chat-demo-v1';const now=()=>new Date().toISOString();const id=()=>crypto.randomUUID();
function seed():Store{const people=readDemo().profiles;const team:Channel={id:id(),kind:'team',name:'Everyone',description:'The whole SilentHelp team',project_id:null,dm_key:null,created_by:null,created_at:now()};const t=Date.now();
 const msg=(author:string,body:string,ago:number):Message=>({id:id(),channel_id:team.id,author_id:author,body,image_path:null,image_name:null,reply_to:null,created_at:new Date(t-ago*60000).toISOString(),edited_at:null,unsent_at:null});
 return {channels:[team],members:people.map(p=>({channel_id:team.id,user_id:p.id,last_read_at:new Date(t-90*60000).toISOString()})),messages:[msg(people[0].id,'Welcome to team chat! This is the channel for everyone.',80),msg(people[2]?.id||people[0].id,'Hi all — excited to get started 👋',60)],reactions:[],hidden:[]};}
function readStore():Store{try{const v=localStorage.getItem(KEY);if(v)return JSON.parse(v)}catch{}const s=seed();localStorage.setItem(KEY,JSON.stringify(s));return s;}
function demoChat():ChatApi{
 const me=()=>sessionStorage.getItem('hq-demo-user')||'';const fire=()=>window.dispatchEvent(new Event('hq-chat-demo'));
 const write=(fn:(s:Store)=>void)=>{const s=readStore();fn(s);localStorage.setItem(KEY,JSON.stringify(s));fire();};
 const member=(s:Store,ch:string)=>s.members.some(m=>m.channel_id===ch&&m.user_id===me());
 const need=(s:Store,ch:string)=>{if(!member(s,ch))throw new Error('You are not in this conversation');};
 const msgOf=(s:Store,mid:string)=>{const m=s.messages.find(x=>x.id===mid);if(!m)throw new Error('Message not found');need(s,m.channel_id);return m;};
 return {
  me,
  async load(){const s=readStore();const mine=s.members.filter(m=>m.user_id===me()).map(m=>m.channel_id);const hidden=new Set(s.hidden.filter(h=>h.user_id===me()).map(h=>h.message_id));
   const overview=mine.map(ch=>{const read=s.members.find(m=>m.channel_id===ch&&m.user_id===me())!.last_read_at;const ms=s.messages.filter(m=>m.channel_id===ch&&!hidden.has(m.id)).sort((a,b)=>a.created_at.localeCompare(b.created_at));const last=ms[ms.length-1];return {channel_id:ch,unread:ms.filter(m=>m.created_at>read&&m.author_id!==me()&&!m.unsent_at).length,last_at:last?.created_at||null,last_body:last?.body.slice(0,140)||null,last_author:last?.author_id||null,last_unsent:!!last?.unsent_at,last_image:!!last?.image_path};});
   const people=readDemo().profiles.filter(p=>p.active).map(p=>({id:p.id,full_name:p.full_name,avatar_path:p.avatar_path||null,role:p.role,bio:p.bio||null}));
   return {channels:s.channels.filter(c=>mine.includes(c.id)),members:s.members.filter(m=>mine.includes(m.channel_id)),overview,people};},
  async messages(ch,before){const s=readStore();if(!member(s,ch))return {messages:[],reactions:[],hidden:[]};const all=s.messages.filter(m=>m.channel_id===ch&&(!before||m.created_at<before)).sort((a,b)=>a.created_at.localeCompare(b.created_at));const messages=all.slice(-PAGE);const ids=new Set(messages.map(m=>m.id));return {messages,reactions:s.reactions.filter(r=>ids.has(r.message_id)),hidden:s.hidden.filter(h=>h.user_id===me()&&ids.has(h.message_id)).map(h=>h.message_id)};},
  async send(ch,body,file,replyTo){const b=body.trim();let image_path:string|null=null;if(file){checkImage(file);image_path=await new Promise<string>((ok,no)=>{const r=new FileReader();r.onload=()=>ok(String(r.result));r.onerror=()=>no(new Error('Could not read picture'));r.readAsDataURL(file)});}if(!b&&!image_path)throw new Error('Write a message or add a picture');write(s=>{need(s,ch);s.messages.push({id:id(),channel_id:ch,author_id:me(),body:b,image_path,image_name:file?.name||null,reply_to:replyTo||null,created_at:now(),edited_at:null,unsent_at:null});const m=s.members.find(x=>x.channel_id===ch&&x.user_id===me());if(m)m.last_read_at=now();});},
  async edit(mid,body){write(s=>{const m=msgOf(s,mid);if(m.author_id!==me())throw new Error('You can only edit your own messages');if(m.unsent_at)throw new Error('This message was unsent');if(!body.trim()&&!m.image_path)throw new Error('A message cannot be empty');m.body=body.trim();m.edited_at=now();});},
  async unsend(mid){write(s=>{const m=msgOf(s,mid);const admin=readDemo().profiles.find(p=>p.id===me())?.role==='admin';if(m.author_id!==me()&&!admin)throw new Error('You can only unsend your own messages');Object.assign(m,{body:'',image_path:null,image_name:null,unsent_at:now()});s.reactions=s.reactions.filter(r=>r.message_id!==mid);});},
  async hide(mid){write(s=>{msgOf(s,mid);if(!s.hidden.some(h=>h.message_id===mid&&h.user_id===me()))s.hidden.push({message_id:mid,user_id:me()});});},
  async react(mid,emoji){write(s=>{const m=msgOf(s,mid);if(m.unsent_at)throw new Error('This message was unsent');const i=s.reactions.findIndex(r=>r.message_id===mid&&r.user_id===me()&&r.emoji===emoji);if(i>=0)s.reactions.splice(i,1);else s.reactions.push({message_id:mid,user_id:me(),emoji});});},
  async createGroup(name,members,project,description){if(!name.trim())throw new Error('Give the channel a name');const ch=id();write(s=>{s.channels.push({id:ch,kind:'group',name:name.trim(),description:description?.trim()||null,project_id:project||null,dm_key:null,created_by:me(),created_at:now()});for(const u of new Set([me(),...members]))s.members.push({channel_id:ch,user_id:u,last_read_at:now()});});return ch;},
  async addMembers(ch,members){write(s=>{need(s,ch);for(const u of members)if(!s.members.some(m=>m.channel_id===ch&&m.user_id===u))s.members.push({channel_id:ch,user_id:u,last_read_at:now()});});},
  async leave(ch){write(s=>{if(s.channels.find(c=>c.id===ch)?.kind!=='group')throw new Error('You can only leave group channels');s.members=s.members.filter(m=>!(m.channel_id===ch&&m.user_id===me()));});},
  async rename(ch,name,description){write(s=>{need(s,ch);const c=s.channels.find(x=>x.id===ch);if(c&&c.kind==='group'){c.name=name.trim();c.description=description?.trim()||null;}});},
  async openDm(other){if(other===me())throw new Error('Pick someone else to message');const k=[me(),other].sort().join(':');let ch='';write(s=>{let c=s.channels.find(x=>x.dm_key===k);if(!c){c={id:id(),kind:'dm',name:null,description:null,project_id:null,dm_key:k,created_by:me(),created_at:now()};s.channels.push(c);}ch=c.id;for(const u of [me(),other])if(!s.members.some(m=>m.channel_id===c!.id&&m.user_id===u))s.members.push({channel_id:c!.id,user_id:u,last_read_at:now()});});return ch;},
  async markRead(ch){const s=readStore();const m=s.members.find(x=>x.channel_id===ch&&x.user_id===me());if(m){m.last_read_at=now();localStorage.setItem(KEY,JSON.stringify(s));}},
  async imageUrl(path){return path;},
  subscribe(cb){const on=()=>cb({table:'chat_messages'});const st=(e:StorageEvent)=>{if(e.key===KEY)on()};window.addEventListener('hq-chat-demo',on);window.addEventListener('storage',st);return()=>{window.removeEventListener('hq-chat-demo',on);window.removeEventListener('storage',st)};},
 };
}

export const chatApi=(userId:string):ChatApi=>demo?demoChat():supabaseChat(userId);
export const resetDemoChat=()=>{try{localStorage.removeItem(KEY)}catch{}};
