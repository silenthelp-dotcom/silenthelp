import {useCallback,useEffect,useMemo,useRef,useState,type KeyboardEvent,type ClipboardEvent} from 'react';
import {useSearchParams} from 'react-router-dom';
import {Hash,Plus,Users,ImagePlus,Send,X,Reply,Pencil,Undo2,Trash2,SmilePlus,ArrowLeft,LogOut,UserPlus,MessageCircle} from 'lucide-react';
import {useHQ,avatarUrl} from './api';
import {chatApi,checkImage,PAGE,type Channel,type Member,type Message,type Overview,type Person,type Reaction} from './chatClient';
import {Notice,initials} from './components';

const QUICK=['❤️','👍','😂','😮','😢','🎉'];
const time=(iso:string)=>new Date(iso).toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit'});
const day=(iso:string)=>{const d=new Date(iso),t=new Date();const y=new Date();y.setDate(t.getDate()-1);if(d.toDateString()===t.toDateString())return 'Today';if(d.toDateString()===y.toDateString())return 'Yesterday';return d.toLocaleDateString('en-US',{weekday:'long',month:'short',day:'numeric'});};

function Face({p,size}:{p?:Person;size?:'small'}){const src=avatarUrl(p?.avatar_path);return <span className={'avatar'+(size?' '+size:'')} title={p?.full_name}>{src?<img src={src} alt=""/>:initials(p?.full_name)}</span>}

/** Total unread messages, for the sidebar badge. */
export function useChatUnread(){const {user}=useHQ();const [n,setN]=useState(0);useEffect(()=>{if(!user||user.must_change_password)return;const api=chatApi(user.id);let live=true;const load=()=>api.load().then(r=>{if(live)setN(r.overview.reduce((a,o)=>a+o.unread,0))}).catch(()=>{});load();const off=api.subscribe(load);const t=setInterval(load,60000);return()=>{live=false;off();clearInterval(t)}},[user?.id]);return n;}

function ChatImage({api,path,name}:{api:ReturnType<typeof chatApi>;path:string;name:string|null}){const [src,setSrc]=useState('');useEffect(()=>{let live=true;api.imageUrl(path).then(u=>live&&setSrc(u)).catch(()=>{});return()=>{live=false}},[path]);return src?<a href={src} target="_blank" rel="noopener noreferrer" className="chat-image"><img src={src} alt={name||'Picture'}/></a>:<span className="chat-image loading"/>}

export function Chat(){
 const {user,data}=useHQ();const admin=user?.role==='admin';const api=useMemo(()=>chatApi(user!.id),[user?.id]);const me=user!.id;
 const [params,setParams]=useSearchParams();const active=params.get('c')||'';
 const [channels,setChannels]=useState<Channel[]>([]),[members,setMembers]=useState<Member[]>([]),[overview,setOverview]=useState<Overview[]>([]),[people,setPeople]=useState<Person[]>([]);
 const [messages,setMessages]=useState<Message[]>([]),[reactions,setReactions]=useState<Reaction[]>([]),[hidden,setHidden]=useState<string[]>([]),[more,setMore]=useState(false);
 const [error,setError]=useState(''),[loaded,setLoaded]=useState(false),[modal,setModal]=useState<null|'group'|'dm'|'add'|'rename'>(null);
 const [text,setText]=useState(''),[file,setFile]=useState<File|null>(null),[replyTo,setReplyTo]=useState<Message|null>(null),[editing,setEditing]=useState<string>(''),[editText,setEditText]=useState(''),[busy,setBusy]=useState(false),[picker,setPicker]=useState(''),[tapped,setTapped]=useState('');
 const listRef=useRef<HTMLDivElement>(null),stick=useRef(true),fileRef=useRef<HTMLInputElement>(null),inputRef=useRef<HTMLTextAreaElement>(null);
 const filePreview=useMemo(()=>file?URL.createObjectURL(file):'',[file]);useEffect(()=>()=>{if(filePreview)URL.revokeObjectURL(filePreview)},[filePreview]);
 const person=useCallback((id:string|null)=>people.find(p=>p.id===id),[people]);
 const others=(c:Channel)=>members.filter(m=>m.channel_id===c.id&&m.user_id!==me).map(m=>person(m.user_id)).filter(Boolean) as Person[];
 const title=(c?:Channel)=>!c?'':c.kind==='dm'?(others(c)[0]?.full_name||'Direct message'):c.name||'Channel';
 const run=async(fn:()=>Promise<unknown>)=>{setError('');try{await fn()}catch(e:any){setError(e.message||'Something went wrong')}};

 const loadList=useCallback(async()=>{const r=await api.load();setChannels(r.channels);setMembers(r.members);setOverview(r.overview);setPeople(r.people);setLoaded(true);return r;},[api]);
 const loadMessages=useCallback(async(ch:string)=>{if(!ch)return;const r=await api.messages(ch);setMessages(r.messages);setReactions(r.reactions);setHidden(r.hidden);setMore(r.messages.length>=PAGE);},[api]);
 useEffect(()=>{run(async()=>{const r=await loadList();if(!active){const team=r.channels.find(c=>c.kind==='team');if(team)setParams({c:team.id},{replace:true});}})},[loadList]);
 useEffect(()=>{if(!active)return;stick.current=true;setReplyTo(null);setEditing('');run(async()=>{await loadMessages(active);await api.markRead(active);setOverview(o=>o.map(x=>x.channel_id===active?{...x,unread:0}:x));})},[active,loadMessages]);
 useEffect(()=>api.subscribe(e=>{void loadList().catch(()=>{});if(active&&(!e.channel_id||e.channel_id===active||e.table==='chat_reactions')){void loadMessages(active).then(()=>api.markRead(active)).catch(()=>{});}}),[api,active,loadList,loadMessages]);
 useEffect(()=>{const el=listRef.current;if(el&&stick.current)el.scrollTop=el.scrollHeight;},[messages]);

 const channel=channels.find(c=>c.id===active);
 const team=channels.filter(c=>c.kind==='team'),groups=channels.filter(c=>c.kind==='group').sort((a,b)=>(a.name||'').localeCompare(b.name||'')),dms=channels.filter(c=>c.kind==='dm').sort((a,b)=>(overview.find(o=>o.channel_id===b.id)?.last_at||b.created_at).localeCompare(overview.find(o=>o.channel_id===a.id)?.last_at||a.created_at));
 const visible=messages.filter(m=>!hidden.includes(m.id));
 const byId=new Map(messages.map(m=>[m.id,m]));

 const send=async()=>{if(busy||!active)return;if(!text.trim()&&!file)return;setBusy(true);await run(async()=>{await api.send(active,text,file,replyTo?.id);setText('');setFile(null);setReplyTo(null);stick.current=true;await loadMessages(active);void loadList();});setBusy(false);inputRef.current?.focus();};
 const onKey=(e:KeyboardEvent<HTMLTextAreaElement>)=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();void send();}};
 const pick=(f?:File|null)=>{if(!f)return;try{checkImage(f);setFile(f);setError('')}catch(e:any){setError(e.message)}};
 const onPaste=(e:ClipboardEvent<HTMLTextAreaElement>)=>{const f=[...e.clipboardData.files].find(f=>f.type.startsWith('image/'));if(f){e.preventDefault();pick(f);}};
 const saveEdit=async(m:Message)=>{await run(async()=>{await api.edit(m.id,editText);setEditing('');await loadMessages(active);});};
 const loadEarlier=async()=>{const first=messages[0];if(!first)return;const el=listRef.current;const h=el?.scrollHeight||0;stick.current=false;await run(async()=>{const r=await api.messages(active,first.created_at);setMessages(m=>[...r.messages,...m]);setReactions(x=>[...r.reactions,...x]);setHidden(x=>[...r.hidden,...x]);setMore(r.messages.length>=PAGE);requestAnimationFrame(()=>{if(el)el.scrollTop=el.scrollHeight-h})});};

 const Row=({c}:{c:Channel})=>{const o=overview.find(x=>x.channel_id===c.id);const who=c.kind==='dm'?others(c)[0]:undefined;const preview=!o?.last_at?'No messages yet':o.last_unsent?'Message unsent':(o.last_author===me?'You: ':c.kind!=='dm'&&o.last_author?(person(o.last_author)?.full_name.split(' ')[0]||'')+': ':'')+(o.last_body||(o.last_image?'📷 Picture':''));
  return <button className={'chat-row'+(c.id===active?' active':'')+(o?.unread?' unread':'')} onClick={()=>setParams({c:c.id})}>{c.kind==='dm'?<Face p={who}/>:<span className="chat-hash">{c.kind==='team'?<Users size={16}/>:<Hash size={16}/>}</span>}<span className="chat-row-text"><strong>{title(c)}</strong><small>{preview}</small></span>{o?.unread?<span className="nav-count">{o.unread}</span>:null}</button>};

 return <div className={'chat-app'+(active?' has-active':'')}>
  <aside className="chat-list" aria-label="Conversations">
   <div className="chat-list-head"><h1>Chat</h1></div>
   {!loaded&&<p className="muted padded">Loading…</p>}
   {team.map(c=><Row key={c.id} c={c}/>)}
   <div className="chat-section"><span>CHANNELS</span><button className="icon-button" aria-label="New channel" onClick={()=>setModal('group')}><Plus size={15}/></button></div>
   {groups.map(c=><Row key={c.id} c={c}/>)}{loaded&&!groups.length&&<p className="chat-empty-hint">Make a channel for a project and add the people on it.</p>}
   <div className="chat-section"><span>DIRECT MESSAGES</span><button className="icon-button" aria-label="New direct message" onClick={()=>setModal('dm')}><Plus size={15}/></button></div>
   {dms.map(c=><Row key={c.id} c={c}/>)}{loaded&&!dms.length&&<p className="chat-empty-hint">Message one teammate privately.</p>}
  </aside>

  <section className="chat-main" aria-label={title(channel)||'Conversation'}>
   {!channel?<div className="chat-placeholder"><MessageCircle size={36}/><p>Pick a conversation.</p></div>:<>
   <header className="chat-head"><button className="icon-button chat-back" aria-label="Back to conversations" onClick={()=>setParams({})}><ArrowLeft size={18}/></button>
    <div className="chat-head-title"><h2>{channel.kind==='dm'?title(channel):<>{channel.kind==='team'?<Users size={18}/>:<Hash size={18}/>} {title(channel)}</>}</h2><small className="muted">{channel.kind==='dm'?(others(channel)[0]?.role==='admin'?'Admin':'Team member'):`${members.filter(m=>m.channel_id===channel.id).length} members${channel.description?' · '+channel.description:''}${channel.project_id?' · '+(data.projects.find(p=>p.id===channel.project_id)?.name||'Project'):''}`}</small></div>
    {channel.kind!=='dm'&&<div className="chat-head-faces">{members.filter(m=>m.channel_id===channel.id).slice(0,5).map(m=><Face key={m.user_id} p={person(m.user_id)} size="small"/>)}</div>}
    {channel.kind==='group'&&<div className="button-row"><button className="button" onClick={()=>setModal('add')}><UserPlus size={15}/>Add people</button><button className="button" onClick={()=>setModal('rename')}>Rename</button><button className="button" onClick={()=>{if(confirm(`Leave #${channel.name}?`))void run(async()=>{await api.leave(channel.id);setParams({});await loadList();})}}><LogOut size={15}/>Leave</button></div>}
   </header>
   <div className="chat-messages" ref={listRef} onScroll={e=>{const el=e.currentTarget;stick.current=el.scrollHeight-el.scrollTop-el.clientHeight<80;}}>
    {more&&<button className="button chat-earlier" onClick={loadEarlier}>Load earlier messages</button>}
    {!visible.length&&<div className="chat-placeholder"><p>{channel.kind==='dm'?`Start your conversation with ${title(channel)}.`:'No messages yet. Say hello!'}</p></div>}
    {visible.map((m,i)=>{const prev=visible[i-1];const newDay=!prev||day(prev.created_at)!==day(m.created_at);const grouped=!newDay&&prev&&prev.author_id===m.author_id&&!prev.unsent_at&&new Date(m.created_at).getTime()-new Date(prev.created_at).getTime()<5*60000;const mine=m.author_id===me;const author=person(m.author_id);const rs=reactions.filter(r=>r.message_id===m.id);const counts=[...new Set(rs.map(r=>r.emoji))].map(e=>({e,n:rs.filter(r=>r.emoji===e).length,me:rs.some(r=>r.emoji===e&&r.user_id===me),who:rs.filter(r=>r.emoji===e).map(r=>person(r.user_id)?.full_name).join(', ')}));const parent=m.reply_to?byId.get(m.reply_to):undefined;
     return <div key={m.id} className="msg-wrap">{newDay&&<div className="chat-day"><span>{day(m.created_at)}</span></div>}
      <div className={'msg'+(mine?' mine':'')+(grouped?' grouped':'')+(m.unsent_at?' unsent':'')+(tapped===m.id?' tapped':'')}>
       {!mine&&<div className="msg-face">{!grouped&&<Face p={author}/>}</div>}
       <div className="msg-col" onClick={()=>setTapped(t=>t===m.id?'':m.id)}>
        {!grouped&&<div className="msg-meta">{!mine&&<strong>{author?.full_name||'Former teammate'}</strong>}<span>{time(m.created_at)}</span></div>}
        {parent&&<div className="msg-reply-to"><Reply size={12}/> {person(parent.author_id)?.full_name.split(' ')[0]}: {parent.unsent_at?'Message unsent':parent.body||'📷 Picture'}</div>}
        {editing===m.id?<div className="msg-edit"><textarea autoFocus value={editText} onChange={e=>setEditText(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();void saveEdit(m)}if(e.key==='Escape')setEditing('')}} maxLength={4000} aria-label="Edit message"/><div className="button-row"><button className="button" onClick={()=>setEditing('')}>Cancel</button><button className="button primary" onClick={()=>saveEdit(m)}>Save</button></div></div>
        :m.unsent_at?<div className="bubble-unsent">{mine?'You unsent a message':'Message unsent'}</div>
        :<>{m.image_path&&<ChatImage api={api} path={m.image_path} name={m.image_name}/>}{m.body&&<div className="bubble">{m.body}{m.edited_at&&<span className="msg-edited"> · edited</span>}</div>}</>}
        {counts.length>0&&<div className="msg-reactions">{counts.map(c=><button key={c.e} className={'reaction'+(c.me?' mine':'')} title={c.who} onClick={()=>run(async()=>{await api.react(m.id,c.e);await loadMessages(active)})}>{c.e} {c.n}</button>)}</div>}
       </div>
       {!m.unsent_at&&editing!==m.id&&<div className="msg-tools" role="toolbar" aria-label="Message actions">
        <button className="icon-button" aria-label="React" onClick={()=>setPicker(picker===m.id?'':m.id)}><SmilePlus size={15}/></button>
        <button className="icon-button" aria-label="Reply" onClick={()=>{setReplyTo(m);inputRef.current?.focus()}}><Reply size={15}/></button>
        {mine&&m.body!==undefined&&<button className="icon-button" aria-label="Edit" onClick={()=>{setEditing(m.id);setEditText(m.body)}}><Pencil size={15}/></button>}
        {(mine||admin)&&<button className="icon-button" aria-label="Unsend" title={mine?'Unsend for everyone':'Remove for everyone (admin)'} onClick={()=>{if(confirm(mine?'Unsend this message for everyone?':'Remove this message for everyone?'))void run(async()=>{await api.unsend(m.id);await loadMessages(active)})}}><Undo2 size={15}/></button>}
        <button className="icon-button" aria-label="Delete for me" title="Delete for me" onClick={()=>run(async()=>{await api.hide(m.id);setHidden(h=>[...h,m.id])})}><Trash2 size={15}/></button>
        {picker===m.id&&<div className="emoji-pick">{QUICK.map(e=><button key={e} aria-label={'React '+e} onClick={()=>{setPicker('');void run(async()=>{await api.react(m.id,e);await loadMessages(active)})}}>{e}</button>)}</div>}
       </div>}
      </div></div>})}
   </div>
   {error&&<div className="chat-error"><Notice error>{error}</Notice></div>}
   <footer className="chat-compose" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();pick([...e.dataTransfer.files].find(f=>f.type.startsWith('image/')))}}>
    {replyTo&&<div className="compose-reply"><Reply size={13}/> Replying to {person(replyTo.author_id)?.full_name.split(' ')[0]}: <span>{replyTo.body||'📷 Picture'}</span><button className="icon-button" aria-label="Cancel reply" onClick={()=>setReplyTo(null)}><X size={14}/></button></div>}
    {file&&<div className="compose-file"><img src={filePreview} alt=""/><span>{file.name}</span><button className="icon-button" aria-label="Remove picture" onClick={()=>setFile(null)}><X size={14}/></button></div>}
    <div className="compose-row"><button className="icon-button" aria-label="Add a picture" onClick={()=>fileRef.current?.click()}><ImagePlus size={19}/></button><input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" hidden aria-label="Picture to send" onChange={e=>{pick(e.target.files?.[0]);e.target.value=''}}/>
     <textarea ref={inputRef} rows={1} value={text} maxLength={4000} onChange={e=>setText(e.target.value)} onKeyDown={onKey} onPaste={onPaste} placeholder={`Message ${channel.kind==='dm'?title(channel):'#'+title(channel)}`} aria-label="Message"/>
     <button className="button primary" aria-label="Send" disabled={busy||(!text.trim()&&!file)} onClick={send}><Send size={16}/></button></div>
   </footer></>}
  </section>
  {modal&&<ChatModal kind={modal} channel={channel} people={people} members={members} me={me} onClose={()=>setModal(null)} onDone={async(ch?:string)=>{setModal(null);await loadList();if(ch)setParams({c:ch});}} api={api}/>}
 </div>;
}

function ChatModal({kind,channel,people,members,me,api,onClose,onDone}:{kind:'group'|'dm'|'add'|'rename';channel?:Channel;people:Person[];members:Member[];me:string;api:ReturnType<typeof chatApi>;onClose:()=>void;onDone:(ch?:string)=>Promise<void>}){
 const {data}=useHQ();const [chosen,setChosen]=useState<string[]>([]),[name,setName]=useState(kind==='rename'?channel?.name||'':''),[desc,setDesc]=useState(kind==='rename'?channel?.description||'':''),[project,setProject]=useState(''),[q,setQ]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const inChannel=new Set(members.filter(m=>m.channel_id===channel?.id).map(m=>m.user_id));
 const list=people.filter(p=>p.id!==me&&(kind!=='add'||!inChannel.has(p.id))&&p.full_name.toLowerCase().includes(q.toLowerCase()));
 const go=async(fn:()=>Promise<string|void>)=>{setBusy(true);setError('');try{await onDone((await fn())||undefined)}catch(e:any){setError(e.message)}finally{setBusy(false)}};
 const toggle=(id:string)=>setChosen(c=>c.includes(id)?c.filter(x=>x!==id):[...c,id]);
 const heading={group:'New channel',dm:'New message',add:`Add people to #${channel?.name}`,rename:'Rename channel'}[kind];
 return <div className="modal-backdrop" onClick={onClose}><div className="modal" role="dialog" aria-modal="true" aria-label={heading} onClick={e=>e.stopPropagation()}><div className="modal-head"><h2>{heading}</h2><button className="icon-button" aria-label="Close" onClick={onClose}><X size={18}/></button></div>
  {(kind==='group'||kind==='rename')&&<><label className="field"><span>Channel name</span><input autoFocus value={name} maxLength={60} onChange={e=>setName(e.target.value)} placeholder="pilot-project"/></label><label className="field"><span>What it’s for (optional)</span><input value={desc} maxLength={300} onChange={e=>setDesc(e.target.value)}/></label></>}
  {kind==='group'&&data.projects.length>0&&<label className="field"><span>Project (optional)</span><select value={project} onChange={e=>{setProject(e.target.value);const p=data.projects.find(p=>p.id===e.target.value);if(p&&!name)setName(p.name.slice(0,60))}}><option value="">Not linked to a project</option>{data.projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>}
  {kind!=='rename'&&<><label className="field"><span>{kind==='dm'?'Who do you want to message?':'People'}</span><input autoFocus={kind!=='group'} value={q} onChange={e=>setQ(e.target.value)} placeholder="Search teammates"/></label>
   <div className="people-pick">{list.map(p=>kind==='dm'?<button key={p.id} className="person-pick" disabled={busy} onClick={()=>go(()=>api.openDm(p.id))}><Face p={p}/><span><strong>{p.full_name}</strong><small>{p.role==='admin'?'Admin':'Team member'}</small></span></button>
    :<label key={p.id} className="person-pick"><input type="checkbox" checked={chosen.includes(p.id)} onChange={()=>toggle(p.id)}/><Face p={p}/><span><strong>{p.full_name}</strong><small>{p.role==='admin'?'Admin':'Team member'}</small></span></label>)}{!list.length&&<p className="muted">No one else to add.</p>}</div></>}
  {error&&<Notice error>{error}</Notice>}
  {kind!=='dm'&&<div className="form-actions"><button className="button" onClick={onClose}>Cancel</button><button className="button primary" disabled={busy||(kind!=='add'&&!name.trim())||(kind==='add'&&!chosen.length)} onClick={()=>go(()=>kind==='group'?api.createGroup(name,chosen,project||null,desc):kind==='add'?api.addMembers(channel!.id,chosen):api.rename(channel!.id,name,desc))}>{kind==='group'?'Create channel':kind==='add'?`Add ${chosen.length||''}`.trim():'Save'}</button></div>}
 </div></div>;
}
