-- Serialize final upload registration against submission transitions.
create function public.register_file(actor uuid, kind text, record uuid, object_path text, filename text, mime_type text, byte_size integer) returns uuid language plpgsql security definer set search_path=public as $$
declare me profiles; s submissions; fid uuid;
begin
 select * into me from profiles where id=actor;
 if me.id is null or not me.active or me.must_change_password then raise exception 'Access denied'; end if;
 if kind='task' then
 if me.role<>'admin' or not exists(select 1 from tasks where id=record) then raise exception 'Access denied'; end if;
 insert into task_attachments(task_id,path,name,mime,size,uploaded_by) values(record,object_path,filename,mime_type,byte_size,actor) returning id into fid;
 elsif kind='submission' then
 select * into s from submissions where id=record for update;
 if s.id is null or s.author_id<>actor or s.status not in ('draft','revision_requested','rejected') then raise exception 'Submission is not editable'; end if;
 insert into submission_files(submission_id,path,name,mime,size,uploaded_by) values(record,object_path,filename,mime_type,byte_size,actor) returning id into fid;
 else raise exception 'Invalid file kind'; end if;
 insert into activity_logs(actor_id,action,record_id,metadata) values(actor,'file.upload',fid,jsonb_build_object('kind',kind));return fid;
end $$;
revoke all on function public.register_file(uuid,text,uuid,text,text,text,integer) from public,anon,authenticated;
grant execute on function public.register_file(uuid,text,uuid,text,text,text,integer) to service_role;
