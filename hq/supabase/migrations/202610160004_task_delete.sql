-- Admin-only hard delete of an assignment and everything that belongs to it.
-- Runs as one transaction; returns the storage paths so the Edge function can
-- remove the files. Callable only by the service role (via the hq function).
create function public.delete_task(actor uuid, t uuid) returns text[] language plpgsql security definer set search_path=public as $$
declare v_title text; v_paths text[];
begin
  if not exists(select 1 from profiles where id=actor and role='admin' and active and not must_change_password) then
    raise exception 'Administrator required';
  end if;
  select title into v_title from tasks where id=t for update;
  if not found then raise exception 'Assignment not found'; end if;
  select coalesce(array_agg(path), '{}') into v_paths from (
    select path from task_attachments where task_id=t
    union all
    select f.path from submission_files f join submissions s on s.id=f.submission_id where s.task_id=t
  ) p;
  delete from ai_review_results where version_id in (select v.id from submission_versions v join submissions s on s.id=v.submission_id where s.task_id=t);
  delete from submission_reviews where submission_id in (select id from submissions where task_id=t);
  delete from submission_files where submission_id in (select id from submissions where task_id=t);
  delete from submission_versions where submission_id in (select id from submissions where task_id=t);
  delete from submissions where task_id=t;
  delete from task_comments where task_id=t;
  delete from task_attachments where task_id=t;
  delete from task_dependencies where task_id=t or depends_on=t;
  -- Cancel unsent emails about this assignment; keep the record of anything already delivered.
  delete from email_delivery_logs where status <> 'sent' and notification_id in (select id from notifications where link like '%' || t::text || '%');
  delete from notifications n where n.link like '%' || t::text || '%' and not exists(select 1 from email_delivery_logs e where e.notification_id=n.id);
  delete from tasks where id=t;  -- task_assignees cascade
  insert into activity_logs(actor_id, action, record_id, metadata) values (actor, 'task.deleted', t, jsonb_build_object('title', v_title));
  return v_paths;
end $$;
revoke all on function public.delete_task(uuid,uuid) from public,anon,authenticated;
grant execute on function public.delete_task(uuid,uuid) to service_role;
