import {createClient} from '@supabase/supabase-js';
for(const name of ['SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','BOOTSTRAP_EMAIL','APP_URL'])if(!process.env[name])throw new Error(`Missing ${name}`);
const db=createClient(process.env.SUPABASE_URL,process.env.SUPABASE_SERVICE_ROLE_KEY,{auth:{persistSession:false}});
const {count,error}=await db.from('profiles').select('id',{count:'exact',head:true}).eq('role','admin');if(error)throw error;if(count)throw new Error('An administrator already exists. Use the app to invite further administrators.');
const {data,error:authError}=await db.auth.admin.inviteUserByEmail(process.env.BOOTSTRAP_EMAIL,{redirectTo:process.env.APP_URL.replace(/\/$/,'')+'/invite/accept'});if(authError)throw authError;
const {error:profileError}=await db.from('profiles').insert({id:data.user.id,email:process.env.BOOTSTRAP_EMAIL,full_name:process.env.BOOTSTRAP_NAME||'Administrator',role:'admin',active:true,must_change_password:true});
if(profileError){await db.auth.admin.deleteUser(data.user.id);throw profileError;}
const {error:auditError}=await db.from('activity_logs').insert({actor_id:data.user.id,action:'admin.bootstrapped',record_id:data.user.id});if(auditError)throw auditError;
console.log('Administrator invited. Open the expiring email link to set a password. No password was printed.');
