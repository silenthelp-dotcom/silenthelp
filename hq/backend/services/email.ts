export async function deliverEmail(row:{id:string;recipient:string;subject:string;body:string;link:string},config:{key:string;from:string;appUrl:string},fetcher:typeof fetch=fetch){
 const base=new URL(config.appUrl.replace(/\/?$/,'/'));const link=/^[a-z][a-z0-9+.-]*:/i.test(row.link)||row.link.startsWith('//')?new URL(row.link,base):new URL(row.link.replace(/^\/+/,''),base);if(!link.href.startsWith(base.href))throw new Error('Invalid email link');
 const r=await fetcher('https://api.resend.com/emails',{method:'POST',headers:{Authorization:`Bearer ${config.key}`,'Content-Type':'application/json','Idempotency-Key':`hq-${row.id}`},signal:AbortSignal.timeout(15000),body:JSON.stringify({from:config.from,to:[row.recipient],subject:row.subject,text:`${row.body}\n\nSign in to SilentHelp HQ:\n${link.href}\n\nSilentHelp HQ`})});
 if(!r.ok)throw new Error(`Email provider returned ${r.status}`);return (await r.json()).id as string;
}
