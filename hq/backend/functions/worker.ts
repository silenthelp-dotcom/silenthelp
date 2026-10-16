import { createClient } from '@supabase/supabase-js';
import { deliverEmail } from '../services/email.ts';
const env=(k:string)=>Deno.env.get(k)||'';
export async function handler(req:Request){
 if(req.method!=='POST'||!env('WORKER_SECRET')||req.headers.get('Authorization')!==`Bearer ${env('WORKER_SECRET')}`)return new Response('Unauthorized',{status:401});
 if(!env('RESEND_API_KEY')||!env('EMAIL_FROM'))return new Response('Email provider not configured',{status:503});
 const db=createClient(env('SUPABASE_URL'),env('SUPABASE_SERVICE_ROLE_KEY'));
 const reminders=await db.rpc('enqueue_reminders');if(reminders.error)return new Response('Reminder queue failed',{status:500});
 const {data:jobs,error}=await db.rpc('claim_emails');if(error)return new Response('Queue unavailable',{status:500});
 const results=await Promise.allSettled((jobs||[]).map(async(row:any)=>{
 try{const provider=await deliverEmail(row,{key:env('RESEND_API_KEY'),from:env('EMAIL_FROM'),appUrl:env('APP_URL')});const r=await db.from('email_delivery_logs').update({status:'sent',provider_id:provider,last_error:null,locked_until:null}).eq('id',row.id);if(r.error)throw r.error;}
 catch(e){await db.from('email_delivery_logs').update({status:'failed',last_error:e instanceof Error?e.message:'Delivery failed',locked_until:null,next_attempt_at:new Date(Date.now()+Math.min(3600,30*2**row.attempts)*1000).toISOString()}).eq('id',row.id);}
 }));return Response.json({processed:results.length});
}
