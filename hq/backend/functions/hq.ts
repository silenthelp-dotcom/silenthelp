import { createClient } from '@supabase/supabase-js';
import { validateCommand, validateFile, validateAvatar } from '../validation/index.ts';
import { reviewResearch } from '../services/ai.ts';
import { extractAll } from '../services/extract.ts';
const env=(k:string)=>Deno.env.get(k)||'';
const db=createClient(env('SUPABASE_URL'),env('SUPABASE_SERVICE_ROLE_KEY'),{auth:{persistSession:false,autoRefreshToken:false}});
const check=<T extends {error:any}>(r:T):T=>{if(r.error)throw new Error(r.error.message);return r};
export async function handler(req:Request):Promise<Response>{
 const origin=req.headers.get('Origin');const allowed=new URL(env('APP_URL')).origin;
 const headers:Record<string,string>={'Content-Type':'application/json','Cache-Control':'no-store','Vary':'Origin'};
 if(origin===allowed)headers['Access-Control-Allow-Origin']=allowed;
 if(origin&&origin!==allowed)return new Response('Origin forbidden',{status:403});
 if(req.method==='OPTIONS')return new Response(null,{status:204,headers:{...headers,'Access-Control-Allow-Headers':'authorization, apikey, content-type, x-client-info','Access-Control-Allow-Methods':'POST, OPTIONS'}});
 try{
 if(req.method!=='POST')return new Response('Method not allowed',{status:405});
 const token=req.headers.get('Authorization')?.replace(/^Bearer /,'');if(!token)throw new Error('Unauthorized');
 const {data:{user},error}=await db.auth.getUser(token);if(error||!user)throw new Error('Unauthorized');
 const me=check(await db.from('profiles').select('*').eq('id',user.id).single()).data;
 if(!me.active)throw new Error('Account inactive');
 const rate=check(await db.rpc('consume_rate',{k:`api:${user.id}`,max_requests:120,seconds:60}));if(!rate.data)return new Response(JSON.stringify({error:'Too many requests. Try again shortly.'}),{status:429,headers});
 const multipart=req.headers.get('Content-Type')?.startsWith('multipart/form-data');
 if(multipart){
 if(me.must_change_password)throw new Error('Change your temporary password first');
 if(Number(req.headers.get('Content-Length')||0)>11*1024*1024)throw new Error('Upload exceeds limit');
 const form=await req.formData();const file=form.get('file');if(!(file instanceof File))throw new Error('Missing file');
 const kind=String(form.get('kind'));const record=String(form.get('record_id'));if(!['task','submission'].includes(kind))throw new Error('Invalid upload type');
 const bytes=new Uint8Array(await file.arrayBuffer());const mime=validateFile(file.name,file.size,bytes);
 if(kind==='task'){if(me.role!=='admin')throw new Error('Administrator required');check(await db.from('tasks').select('id').eq('id',record).single());}
 else{const s=check(await db.from('submissions').select('*').eq('id',record).single()).data;if(s.author_id!==user.id||!['draft','revision_requested','rejected'].includes(s.status))throw new Error('Submission is not editable');}
 const path=`${kind}/${record}/${crypto.randomUUID()}/${file.name.replace(/[^a-zA-Z0-9._-]/g,'_')}`;
 check(await db.storage.from('research').upload(path,bytes,{contentType:mime,upsert:false}));
 const saved=await db.rpc('register_file',{actor:user.id,kind,record,object_path:path,filename:file.name,mime_type:mime,byte_size:file.size});
 if(saved.error){await db.storage.from('research').remove([path]);throw new Error(saved.error.message);}
 
 return new Response(JSON.stringify(saved.data),{headers});
 }
 const raw=await req.text();if(raw.length>250000)throw new Error('Request too large');
 const {operation,payload}=JSON.parse(raw);const p:any=validateCommand(operation,payload);
 if(operation==='password.change'){
 check(await db.auth.admin.updateUserById(user.id,{password:p.password}));
 check(await db.from('profiles').update({must_change_password:false,last_activity:new Date().toISOString()}).eq('id',user.id));
 check(await db.from('invitations').update({status:'accepted'}).eq('user_id',user.id));
 check(await db.from('activity_logs').insert({actor_id:user.id,action:'account.password_changed',record_id:user.id}));
 return new Response(JSON.stringify({ok:true}),{headers});
 }
 if(me.must_change_password)throw new Error('Change your temporary password first');
 if(operation==='invite'){
 if(me.role!=='admin')throw new Error('Administrator required');
 const limited=check(await db.rpc('consume_rate',{k:`invite:${user.id}`,max_requests:10,seconds:3600}));if(!limited.data)throw new Error('Invitation rate limit reached');
 const redirectTo=`${env('APP_URL').replace(/\/$/,'')}/invite/accept`;
 const result=p.temporary_password?await db.auth.admin.createUser({email:p.email,password:p.temporary_password,email_confirm:true}):await db.auth.admin.inviteUserByEmail(p.email,{redirectTo});
 check(result);const invited=result.data.user!;
 const prof=await db.from('profiles').insert({id:invited.id,email:p.email,full_name:p.full_name,role:p.role,department_id:p.department_id||null,must_change_password:true});
 if(prof.error){await db.auth.admin.deleteUser(invited.id);throw new Error(prof.error.message);}
 check(await db.from('invitations').insert({email:p.email,invited_by:user.id,user_id:invited.id,status:'sent'}));
 check(await db.from('activity_logs').insert({actor_id:user.id,action:p.temporary_password?'account.created':'employee.invited',record_id:invited.id,metadata:{role:p.role}}));
 return new Response(JSON.stringify({id:invited.id}),{headers});
 }
 if(operation==='task.delete'){
 if(me.role!=='admin')throw new Error('Administrator required');
 const paths=check(await db.rpc('delete_task',{actor:user.id,t:p.id})).data as string[]|null;
 if(paths&&paths.length){const rm=await db.storage.from('research').remove(paths);if(rm.error)console.error('task.delete storage cleanup',rm.error.message);}
 return new Response(JSON.stringify({ok:true}),{headers});
 }
 const rpcOps:Record<string,string>={'meeting.create':'hq_meeting_create','meeting.cancel':'hq_meeting_cancel','poll.create':'hq_poll_create','poll.respond':'hq_poll_respond','poll.close':'hq_poll_close'};
 if(rpcOps[operation]){const r=check(await db.rpc(rpcOps[operation],{actor:user.id,payload:p}));return new Response(JSON.stringify(r.data),{headers});}
 if(operation==='snapshot.download'||operation==='snapshot.run'){
 if(me.role!=='admin')throw new Error('Administrator required');
 if(operation==='snapshot.run'){
 if(!check(await db.rpc('consume_rate',{k:`snapshot:${user.id}`,max_requests:3,seconds:3600})).data)throw new Error('You can update the code snapshot 3 times an hour.');
 const r=await fetch(`${env('SUPABASE_URL')}/functions/v1/snapshot?trigger=manual`,{method:'POST',headers:{Authorization:`Bearer ${env('WORKER_SECRET')}`}});
 const out=await r.json().catch(()=>({}));if(!r.ok)throw new Error(out.error||'Snapshot failed');
 return new Response(JSON.stringify(out),{headers});
 }
 const s=check(await db.from('code_snapshots').select('*').eq('id',p.id).single()).data;if(!s.zip_path)throw new Error('This week’s .zip is no longer stored. Download a newer week.');
 const signed=check(await db.storage.from('code-snapshots').createSignedUrl(s.zip_path,60,{download:`silenthelp-${s.zip_path}`}));
 return new Response(JSON.stringify({url:signed.data!.signedUrl}),{headers});
 }
 if(operation==='profile.update'){
 check(await db.from('profiles').update({full_name:p.full_name,...(p.bio!==undefined?{bio:p.bio||null}:{})}).eq('id',user.id));
 return new Response(JSON.stringify({ok:true}),{headers});
 }
 if(operation==='avatar.prepare'||operation==='avatar.finish'||operation==='avatar.remove'){
 if(me.must_change_password)throw new Error('Change your temporary password first');
 const old=me.avatar_path as string|null;
 if(operation==='avatar.prepare'){
 validateAvatar(p.name,p.size);
 const ext=p.name.split('.').pop().toLowerCase().replace('jpeg','jpg');
 const path=`${user.id}/${crypto.randomUUID()}.${ext}`;
 const up=check(await db.storage.from('avatars').createSignedUploadUrl(path)).data!;
 return new Response(JSON.stringify({path,token:up.token}),{headers});
 }
 if(operation==='avatar.finish'){
 if(!new RegExp(`^${user.id}/[0-9a-f-]{36}\\.(png|jpg|webp)$`).test(p.path))throw new Error('Invalid photo path');
 try{
 const head=await fetch(`${env('SUPABASE_URL')}/storage/v1/object/public/avatars/${p.path}`,{headers:{Range:'bytes=0-15'}});if(!head.ok)throw new Error('Photo upload not found. Try again.');
 const size=Number(head.headers.get('Content-Range')?.split('/')[1]||head.headers.get('Content-Length')||0);
 validateAvatar(p.path,size,new Uint8Array(await head.arrayBuffer()).slice(0,16));
 }catch(e){await db.storage.from('avatars').remove([p.path]);throw e}
 check(await db.from('profiles').update({avatar_path:p.path}).eq('id',user.id));
 }else check(await db.from('profiles').update({avatar_path:null}).eq('id',user.id));
 if(old&&old!==p.path)await db.storage.from('avatars').remove([old]);
 return new Response(JSON.stringify({ok:true}),{headers});
 }
 if(operation==='file.prepare'||operation==='file.finish'){
 // Large files (videos) go straight to Storage with a one-time signed upload URL; this function never holds the bytes.
 if(me.must_change_password)throw new Error('Change your temporary password first');
 if(p.kind==='task'){if(me.role!=='admin')throw new Error('Administrator required');check(await db.from('tasks').select('id').eq('id',p.record_id).single());}
 else{const s=check(await db.from('submissions').select('*').eq('id',p.record_id).single()).data;if(s.author_id!==user.id||!['draft','revision_requested','rejected'].includes(s.status))throw new Error('Submission is not editable');}
 const safe=p.name.replace(/[^a-zA-Z0-9._-]/g,'_');
 if(operation==='file.prepare'){
 validateFile(p.name,p.size);
 const path=`${p.kind}/${p.record_id}/${crypto.randomUUID()}/${safe}`;
 const up=check(await db.storage.from('research').createSignedUploadUrl(path)).data!;
 return new Response(JSON.stringify({path,token:up.token}),{headers});
 }
 const pre=`${p.kind}/${p.record_id}/`;const rest=p.path.slice(pre.length);
 if(!p.path.startsWith(pre)||!/^[0-9a-f-]{36}\/[^/]+$/.test(rest)||rest.split('/')[1]!==safe)throw new Error('Invalid upload path');
 const remove=()=>db.storage.from('research').remove([p.path]);
 try{
 const link=check(await db.storage.from('research').createSignedUrl(p.path,60)).data!.signedUrl;
 const head=await fetch(link,{headers:{Range:'bytes=0-15'}});if(!head.ok)throw new Error('Upload not found. Try again.');
 const size=Number(head.headers.get('Content-Range')?.split('/')[1]||head.headers.get('Content-Length')||0);
 const bytes=new Uint8Array(await head.arrayBuffer()).slice(0,16);
 const mime=validateFile(p.name,size,bytes);
 const saved=await db.rpc('register_file',{actor:user.id,kind:p.kind,record:p.record_id,object_path:p.path,filename:p.name,mime_type:mime,byte_size:size});
 if(saved.error)throw new Error(saved.error.message);
 return new Response(JSON.stringify(saved.data),{headers});
 }catch(e){await remove();throw e}
 }
 if(operation==='file.download'){
 const f=check(await db.from(p.kind==='task'?'task_attachments':'submission_files').select('*').eq('id',p.id).single()).data;
 if(me.role!=='admin'){
 if(p.kind==='task')check(await db.from('task_assignees').select('id').eq('task_id',f.task_id).eq('user_id',user.id).single());
 else check(await db.from('submissions').select('id').eq('id',f.submission_id).eq('author_id',user.id).single());
 }
 const signed=check(await db.storage.from('research').createSignedUrl(f.path,60,{download:f.name}));return new Response(JSON.stringify({url:signed.data!.signedUrl}),{headers});
 }
 if(operation==='ai.review'){
 if(me.role!=='admin')throw new Error('Administrator required');
 if(!env('AI_API_KEY')||!env('AI_MODEL')||!env('AI_API_URL'))throw new Error('AI review is not configured');
 if(!check(await db.rpc('consume_rate',{k:`ai:${user.id}`,max_requests:10,seconds:3600})).data)throw new Error('AI review rate limit reached');
 const version=check(await db.from('submission_versions').select('*').eq('id',p.version_id).single()).data;
 const s=check(await db.from('submissions').select('*').eq('id',version.submission_id).single()).data;
 const task=check(await db.from('tasks').select('*').eq('id',s.task_id).single()).data;
 const files=check(await db.from('submission_files').select('*').eq('version_id',version.id).order('created_at')).data||[];
 const attachments=await extractAll(files.map((f:any)=>({name:f.name,mime:f.mime,load:async()=>new Uint8Array(await check(await db.storage.from('research').download(f.path)).data!.arrayBuffer())})));
 const result=await reviewResearch(version.content,task,{url:env('AI_API_URL'),key:env('AI_API_KEY'),model:env('AI_MODEL')},fetch,attachments);
 check(await db.from('ai_review_results').insert({version_id:version.id,reviewer_id:user.id,result,model:env('AI_MODEL')}));
 check(await db.from('activity_logs').insert({actor_id:user.id,action:'ai.review',record_id:version.id}));
 return new Response(JSON.stringify(result),{headers});
 }
 const result=check(await db.rpc('apply_command',{actor:user.id,operation,payload:p}));return new Response(JSON.stringify(result.data),{headers});
 }catch(e){const message=e instanceof Error?e.message:'Request failed';return new Response(JSON.stringify({error:message}),{status:/Unauthorized/.test(message)?401:/denied|Administrator|inactive/.test(message)?403:400,headers});}
}
