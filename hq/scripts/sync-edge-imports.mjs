import fs from 'node:fs';
const lock=JSON.parse(fs.readFileSync('package-lock.json','utf8'));
const version=name=>lock.packages['node_modules/'+name].version;
fs.writeFileSync('supabase/functions/deno.json',JSON.stringify({imports:{'@supabase/supabase-js':'npm:@supabase/supabase-js@'+version('@supabase/supabase-js'),zod:'npm:zod@'+version('zod')}},null,2)+'\n');
