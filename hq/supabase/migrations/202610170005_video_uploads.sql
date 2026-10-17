-- Allow video evidence (MP4, MOV, WebM) up to 50 MB, the project's per-file storage cap.
-- Per-type limits (10 MB documents/pictures, 50 MB video) are enforced by the hq Edge function.
update storage.buckets set file_size_limit=52428800,
 allowed_mime_types=array['application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document','text/plain','text/markdown','image/png','image/jpeg','image/webp','video/mp4','video/quicktime','video/webm']
where id='research';
do $$ declare t text; c text; begin
 foreach t in array array['task_attachments','submission_files'] loop
  select conname into c from pg_constraint where conrelid=('public.'||t)::regclass and contype='c' and pg_get_constraintdef(oid) like '%size%10485760%';
  if c is not null then execute format('alter table public.%I drop constraint %I',t,c); end if;
  execute format('alter table public.%I add constraint %I check (size between 1 and 52428800)',t,t||'_size_limit');
 end loop;
end $$;
