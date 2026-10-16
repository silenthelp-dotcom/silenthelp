-- Single-company installation. All application writes use server-only commands.
create extension if not exists pgcrypto;
create table public.roles(name text primary key check(name in ('admin','employee')));
insert into public.roles values ('admin'),('employee');
create table public.departments(id uuid primary key default gen_random_uuid(), name text not null unique);
create table public.profiles(id uuid primary key references auth.users(id) on delete cascade, email text not null unique, full_name text not null, role text not null default 'employee' references public.roles(name), department_id uuid references public.departments(id), active boolean not null default true, must_change_password boolean not null default false, last_activity timestamptz, created_at timestamptz not null default now());
create table public.invitations(id uuid primary key default gen_random_uuid(), email text not null, invited_by uuid references public.profiles(id), user_id uuid references public.profiles(id), status text not null check(status in ('sent','accepted','failed')), created_at timestamptz not null default now());
create table public.projects(id uuid primary key default gen_random_uuid(), name text not null, description text not null default '', owner_id uuid references public.profiles(id), start_date date, target_date date not null default '2026-11-15', status text not null default 'active' check(status in ('active','paused','completed')), q1 boolean not null default false, created_at timestamptz not null default now());
create table public.project_members(project_id uuid references public.projects(id) on delete cascade, user_id uuid references public.profiles(id), primary key(project_id,user_id));
create table public.tasks(id uuid primary key default gen_random_uuid(), title text not null check(length(title) between 1 and 200), description text not null default '', project_id uuid references public.projects(id), department_id uuid references public.departments(id), priority text not null check(priority in ('low','medium','high','urgent')), start_date date, due_date date not null, details jsonb not null default '{}', created_by uuid references public.profiles(id), created_at timestamptz not null default now(), check(start_date is null or start_date<=due_date));
create table public.task_assignees(id uuid primary key default gen_random_uuid(), task_id uuid not null references public.tasks(id) on delete cascade, user_id uuid not null references public.profiles(id), status text not null default 'not_started' check(status in ('not_started','in_progress','submitted','under_review','revision_requested','approved','completed')), completed_at timestamptz, unique(task_id,user_id));
create table public.task_dependencies(task_id uuid references public.tasks(id), depends_on uuid references public.tasks(id), primary key(task_id,depends_on), check(task_id<>depends_on));
create table public.task_comments(id uuid primary key default gen_random_uuid(), task_id uuid not null references public.tasks(id), author_id uuid not null references public.profiles(id), body text not null check(length(body) between 1 and 10000), kind text not null default 'comment' check(kind in ('comment','progress','extension')), created_at timestamptz not null default now());
create table public.task_attachments(id uuid primary key default gen_random_uuid(), task_id uuid not null references public.tasks(id), path text not null unique, name text not null, mime text not null, size integer not null check(size between 1 and 10485760), uploaded_by uuid not null references public.profiles(id), created_at timestamptz not null default now());
create table public.submissions(id uuid primary key default gen_random_uuid(), task_id uuid not null references public.tasks(id), author_id uuid not null references public.profiles(id), draft jsonb not null default '{}', draft_revision integer not null default 0, status text not null default 'draft' check(status in ('draft','submitted','under_review','revision_requested','approved','rejected')), created_at timestamptz not null default now(), updated_at timestamptz not null default now(), unique(task_id,author_id));
create table public.submission_versions(id uuid primary key default gen_random_uuid(), submission_id uuid not null references public.submissions(id), version integer not null, content jsonb not null, created_at timestamptz not null default now(), unique(submission_id,version));
create table public.submission_files(id uuid primary key default gen_random_uuid(), submission_id uuid not null references public.submissions(id), version_id uuid references public.submission_versions(id), path text not null unique, name text not null, mime text not null, size integer not null check(size between 1 and 10485760), uploaded_by uuid not null references public.profiles(id), created_at timestamptz not null default now());
create table public.submission_reviews(id uuid primary key default gen_random_uuid(), submission_id uuid not null references public.submissions(id), version_id uuid not null references public.submission_versions(id), reviewer_id uuid not null references public.profiles(id), decision text not null check(decision in ('under_review','revision_requested','approved','rejected')), feedback text not null, created_at timestamptz not null default now());
create table public.ai_review_results(id uuid primary key default gen_random_uuid(), version_id uuid not null references public.submission_versions(id), reviewer_id uuid not null references public.profiles(id), result jsonb not null, model text not null, created_at timestamptz not null default now());
create table public.notifications(id uuid primary key default gen_random_uuid(), user_id uuid not null references public.profiles(id), title text not null, body text not null, link text not null, read_at timestamptz, dedupe_key text unique, created_at timestamptz not null default now());
create table public.email_delivery_logs(id uuid primary key default gen_random_uuid(), notification_id uuid unique references public.notifications(id), recipient text not null, subject text not null, body text not null, link text not null, status text not null default 'pending' check(status in ('pending','processing','sent','failed')), attempts integer not null default 0, next_attempt_at timestamptz not null default now(), locked_until timestamptz, provider_id text, last_error text, created_at timestamptz not null default now());
create table public.activity_logs(id uuid primary key default gen_random_uuid(), actor_id uuid references public.profiles(id), action text not null, record_id uuid, metadata jsonb not null default '{}', created_at timestamptz not null default now());
create table public.company_milestones(id uuid primary key default gen_random_uuid(), project_id uuid references public.projects(id), title text not null, target_date date not null default '2026-11-15', completed boolean not null default false, risk text not null default '', created_at timestamptz not null default now());
create table public.rate_limits(key text primary key, window_start timestamptz not null, count integer not null);
create index tasks_due on public.tasks(due_date);
create index tasks_project on public.tasks(project_id);
create index assignments_user on public.task_assignees(user_id,task_id);
create index submissions_author on public.submissions(author_id,task_id);
create index versions_submission on public.submission_versions(submission_id,version desc);
create index comments_task on public.task_comments(task_id,created_at);
create index files_submission on public.submission_files(submission_id);
create index notifications_user on public.notifications(user_id,created_at desc);
create index email_pending on public.email_delivery_logs(status,next_attempt_at);
create index activity_created on public.activity_logs(created_at desc);

create function public.is_active() returns boolean language sql stable security definer set search_path=public as $$ select exists(select 1 from profiles where id=auth.uid() and active and not must_change_password) $$;
create function public.is_admin() returns boolean language sql stable security definer set search_path=public as $$ select exists(select 1 from profiles where id=auth.uid() and active and not must_change_password and role='admin') $$;
create function public.can_task(t uuid) returns boolean language sql stable security definer set search_path=public as $$ select public.is_active() and (public.is_admin() or exists(select 1 from task_assignees where task_id=t and user_id=auth.uid())) $$;
create function public.can_submission(s uuid) returns boolean language sql stable security definer set search_path=public as $$ select public.is_active() and exists(select 1 from submissions where id=s and (author_id=auth.uid() or public.is_admin())) $$;
create function public.can_project(p uuid) returns boolean language sql stable security definer set search_path=public as $$ select public.is_active() and (public.is_admin() or exists(select 1 from project_members where project_id=p and user_id=auth.uid()) or exists(select 1 from tasks join task_assignees on task_id=tasks.id where project_id=p and user_id=auth.uid())) $$;
DO $$ declare t text; begin foreach t in array array['roles','departments','profiles','invitations','projects','project_members','tasks','task_assignees','task_dependencies','task_comments','task_attachments','submissions','submission_versions','submission_files','submission_reviews','ai_review_results','notifications','email_delivery_logs','activity_logs','company_milestones','rate_limits'] loop execute format('alter table public.%I enable row level security',t); execute format('grant select on public.%I to authenticated',t); execute format('grant all on public.%I to service_role',t); end loop; end $$;
create policy roles_read on public.roles for select to authenticated using(public.is_active());
create policy departments_read on public.departments for select to authenticated using(public.is_active());
create policy profiles_read on public.profiles for select to authenticated using(id=auth.uid() or public.is_admin());
create policy invitations_read on public.invitations for select to authenticated using(public.is_admin());
create policy projects_read on public.projects for select to authenticated using(public.can_project(id));
create policy members_read on public.project_members for select to authenticated using(public.is_admin() or (public.is_active() and user_id=auth.uid()));
create policy tasks_read on public.tasks for select to authenticated using(public.can_task(id));
create policy assignees_read on public.task_assignees for select to authenticated using(public.is_admin() or (public.is_active() and user_id=auth.uid()));
create policy dependencies_read on public.task_dependencies for select to authenticated using(public.can_task(task_id) and public.can_task(depends_on));
-- Comments are private between their author and admins, even on shared tasks.
create policy comments_read on public.task_comments for select to authenticated using(public.is_admin() or (public.can_task(task_id) and author_id=auth.uid()));
create policy task_files_read on public.task_attachments for select to authenticated using(public.can_task(task_id));
create policy submissions_read on public.submissions for select to authenticated using(public.can_submission(id));
create policy versions_read on public.submission_versions for select to authenticated using(public.can_submission(submission_id));
create policy submission_files_read on public.submission_files for select to authenticated using(public.can_submission(submission_id));
create policy reviews_read on public.submission_reviews for select to authenticated using(public.can_submission(submission_id));
create policy ai_read on public.ai_review_results for select to authenticated using(public.is_admin());
create policy notifications_read on public.notifications for select to authenticated using(public.is_active() and user_id=auth.uid());
create policy emails_read on public.email_delivery_logs for select to authenticated using(public.is_admin());
create policy activity_read on public.activity_logs for select to authenticated using(public.is_admin());
create policy milestones_read on public.company_milestones for select to authenticated using(public.is_admin() or public.can_project(project_id));
-- No browser INSERT/UPDATE/DELETE policies. No access policy for rate_limits.

create function public.notify_user(u uuid, heading text, message text, route text, dedupe text default null) returns void language plpgsql security definer set search_path=public as $$
declare n uuid; e text;
begin
 select email into e from profiles where id=u and active; if e is null then return; end if;
 insert into notifications(user_id,title,body,link,dedupe_key) values(u,heading,message,route,dedupe) on conflict(dedupe_key) do nothing returning id into n;
 if n is not null then insert into email_delivery_logs(notification_id,recipient,subject,body,link) values(n,e,'SilentHelp HQ — '||heading,message,route); end if;
end $$;

create function public.apply_command(actor uuid, operation text, payload jsonb) returns jsonb language plpgsql security definer set search_path=public as $$
declare me profiles; tid uuid; sid uuid; pid uuid; uid uuid; vid uuid; s submissions; n integer; obj jsonb; old_due date; vstatus text;
begin
 select * into me from profiles where id=actor for update;
 if me.id is null or not me.active or me.must_change_password then raise exception 'Access denied' using errcode='42501'; end if;
 if operation in ('task.create','task.update','employee.update','project.save','milestone.save','department.create','submission.review','assignment.complete') and me.role<>'admin' then raise exception 'Administrator required' using errcode='42501'; end if;
 case operation
 when 'task.create' then
 insert into tasks(title,description,project_id,department_id,priority,start_date,due_date,details,created_by) values(payload->>'title',coalesce(payload->>'description',''),nullif(payload->>'project_id','')::uuid,nullif(payload->>'department_id','')::uuid,payload->>'priority',nullif(payload->>'start_date','')::date,(payload->>'due_date')::date,coalesce(payload->'details','{}'),actor) returning id into tid;
 if jsonb_array_length(payload->'assignees')<1 then raise exception 'Choose an assignee'; end if;
 for uid in select jsonb_array_elements_text(payload->'assignees')::uuid loop
 if not exists(select 1 from profiles where id=uid and active) then raise exception 'Inactive assignee'; end if;
 insert into task_assignees(task_id,user_id) values(tid,uid);
 perform notify_user(uid,'New assignment: '||(payload->>'title'),'Priority: '||(payload->>'priority')||E'\nDue: '||(payload->>'due_date')||E'\n'||coalesce(payload->>'description',''),'/my-tasks/'||tid);
 end loop;
 for uid in select jsonb_array_elements_text(coalesce(payload->'dependencies','[]'))::uuid loop insert into task_dependencies values(tid,uid); end loop;
 when 'task.update' then
 tid:=(payload->>'id')::uuid;
 select due_date into old_due from tasks where id=tid for update; if not found then raise exception 'Task not found'; end if;
 update tasks set due_date=(payload->>'due_date')::date, priority=payload->>'priority',title=payload->>'title',description=payload->>'description' where id=tid;
 if payload ? 'assignees' then
 -- Preserve history: reassign only assignments without submissions.
 if exists(select 1 from submissions where task_id=tid and not (payload->'assignees' ? author_id::text)) then raise exception 'Cannot remove a contributor with submission history'; end if;
 delete from task_assignees where task_id=tid and not (payload->'assignees' ? user_id::text);
 for uid in select jsonb_array_elements_text(payload->'assignees')::uuid loop
 if not exists(select 1 from profiles where id=uid and active) then raise exception 'Inactive assignee'; end if;
 insert into task_assignees(task_id,user_id) values(tid,uid) on conflict do nothing;
 end loop;
 end if;
 for uid in select user_id from task_assignees where task_id=tid loop perform notify_user(uid,case when old_due<>(payload->>'due_date')::date then 'Deadline changed' else 'Assignment updated' end,payload->>'title','/my-tasks/'||tid); end loop;
 when 'assignment.start' then
 tid:=(payload->>'task_id')::uuid;
 update task_assignees set status='in_progress' where task_id=tid and user_id=actor and status='not_started'; if not found then raise exception 'Assignment cannot be started'; end if;
 when 'assignment.complete' then
 tid:=(payload->>'task_id')::uuid;
 update task_assignees set status='completed',completed_at=now() where task_id=tid and user_id=(payload->>'user_id')::uuid and status='approved'; if not found then raise exception 'Approve submission first'; end if;
 when 'comment.add' then
 tid:=(payload->>'task_id')::uuid;
 if me.role<>'admin' and not exists(select 1 from task_assignees where task_id=tid and user_id=actor) then raise exception 'Access denied' using errcode='42501'; end if;
 insert into task_comments(task_id,author_id,body,kind) values(tid,actor,payload->>'body',payload->>'kind');
 if payload->>'kind'='extension' then for uid in select id from profiles where role='admin' and active loop perform notify_user(uid,'Extension requested',payload->>'body','/admin/tasks/'||tid); end loop; end if;
 when 'draft.save' then
 tid:=(payload->>'task_id')::uuid;
 if not exists(select 1 from task_assignees where task_id=tid and user_id=actor and status in ('not_started','in_progress','revision_requested')) then raise exception 'Assignment is not editable'; end if;
 insert into submissions(task_id,author_id) values(tid,actor) on conflict do nothing;
 select * into s from submissions where task_id=tid and author_id=actor for update;
 if s.draft_revision<>(payload->>'revision')::integer then raise exception 'Draft changed in another tab. Reload before editing.'; end if;
 update submissions set draft=payload->'content',draft_revision=draft_revision+1,updated_at=now() where id=s.id;
 return jsonb_build_object('id',s.id,'revision',s.draft_revision+1);
 when 'submission.submit' then
 tid:=(payload->>'task_id')::uuid;
 select * into s from submissions where task_id=tid and author_id=actor for update;
 if s.id is null or s.draft_revision<>(payload->>'revision')::integer then raise exception 'Save the latest draft first'; end if;
 if not exists(select 1 from task_assignees where task_id=tid and user_id=actor and status in ('not_started','in_progress','revision_requested')) then raise exception 'Submission not editable'; end if;
 if length(coalesce(s.draft->>'title',''))<1 or length(coalesce(s.draft->>'findings',''))<20 then raise exception 'A title and findings are required'; end if;
 if exists(select 1 from task_dependencies d join task_assignees a on a.task_id=d.depends_on where d.task_id=tid and a.status not in ('approved','completed')) then raise exception 'Complete prerequisite assignments first'; end if;
 select coalesce(max(version),0)+1 into n from submission_versions where submission_id=s.id;
 insert into submission_versions(submission_id,version,content) values(s.id,n,s.draft) returning id into vid;
 update submission_files set version_id=vid where submission_id=s.id and version_id is null;
 update submissions set status='submitted',updated_at=now() where id=s.id;
 update task_assignees set status='submitted' where task_id=tid and user_id=actor;
 for uid in select id from profiles where role='admin' and active loop perform notify_user(uid,'Research submitted',s.draft->>'title','/admin/submissions/'||s.id); end loop;
 sid:=s.id;
 when 'submission.review' then
 sid:=(payload->>'id')::uuid;
 select * into s from submissions where id=sid for update;
 if s.id is null or s.status not in ('submitted','under_review') then raise exception 'Submission is not awaiting review'; end if;
 select id into vid from submission_versions where submission_id=sid order by version desc limit 1;
 if vid<>(payload->>'version_id')::uuid then raise exception 'Review is stale. Reload latest version.'; end if;
 vstatus:=payload->>'decision';
 if length(trim(payload->>'feedback'))<3 then raise exception 'Document a review reason'; end if;
 insert into submission_reviews(submission_id,version_id,reviewer_id,decision,feedback) values(sid,vid,actor,vstatus,payload->>'feedback');
 update submissions set status=vstatus,updated_at=now() where id=sid;
 update task_assignees set status=case when vstatus='rejected' then 'revision_requested' else vstatus end, completed_at=case when vstatus='approved' then now() else null end where task_id=s.task_id and user_id=s.author_id;
 perform notify_user(s.author_id,'Research '||replace(vstatus,'_',' '),payload->>'feedback','/my-tasks/'||s.task_id);
 when 'employee.update' then
 uid:=(payload->>'id')::uuid;
 -- Serialize admin changes via one shared advisory lock, protecting the last admin.
 perform pg_advisory_xact_lock(810052);
 if exists(select 1 from profiles where id=uid and role='admin' and active) and (payload->>'role'<>'admin' or not (payload->>'active')::boolean) and (select count(*) from profiles where role='admin' and active)<2 then raise exception 'Keep at least one active administrator'; end if;
 update profiles set full_name=payload->>'full_name',role=payload->>'role',active=(payload->>'active')::boolean,department_id=nullif(payload->>'department_id','')::uuid where id=uid;
 when 'profile.update' then update profiles set full_name=payload->>'full_name' where id=actor;
 when 'notification.read' then update notifications set read_at=now() where id=(payload->>'id')::uuid and user_id=actor;
 when 'project.save' then
 pid:=coalesce(nullif(payload->>'id','')::uuid,gen_random_uuid());
 insert into projects(id,name,description,owner_id,start_date,target_date,status) values(pid,payload->>'name',payload->>'description',nullif(payload->>'owner_id','')::uuid,nullif(payload->>'start_date','')::date,(payload->>'target_date')::date,payload->>'status') on conflict(id) do update set name=excluded.name,description=excluded.description,owner_id=excluded.owner_id,start_date=excluded.start_date,target_date=excluded.target_date,status=excluded.status;
 delete from project_members where project_id=pid;
 for uid in select jsonb_array_elements_text(coalesce(payload->'members','[]'))::uuid loop insert into project_members values(pid,uid); end loop;
 when 'milestone.save' then
 pid:=nullif(payload->>'project_id','')::uuid;
 insert into company_milestones(id,project_id,title,target_date,completed,risk) values(coalesce(nullif(payload->>'id','')::uuid,gen_random_uuid()),pid,payload->>'title',(payload->>'target_date')::date,(payload->>'completed')::boolean,coalesce(payload->>'risk','')) on conflict(id) do update set title=excluded.title,target_date=excluded.target_date,completed=excluded.completed,risk=excluded.risk;
 when 'department.create' then insert into departments(name) values(payload->>'name');
 else raise exception 'Unknown command';
 end case;
 update profiles set last_activity=now() where id=actor;
 -- Avoid storing research, comments, or other confidential prose in audit metadata.
 insert into activity_logs(actor_id,action,record_id,metadata) values(actor,operation,coalesce(tid,sid,pid,uid,nullif(payload->>'id','')::uuid),jsonb_build_object('decision',payload->>'decision','due_date',payload->>'due_date','role',payload->>'role','active',payload->>'active'));
 return jsonb_build_object('id',coalesce(tid,sid,pid,uid));
end $$;

create function public.consume_rate(k text, max_requests integer, seconds integer) returns boolean language plpgsql security definer set search_path=public as $$ declare c integer; begin
 insert into rate_limits(key,window_start,count) values(k,now(),1) on conflict(key) do update set count=case when rate_limits.window_start<now()-make_interval(secs=>seconds) then 1 else rate_limits.count+1 end,window_start=case when rate_limits.window_start<now()-make_interval(secs=>seconds) then now() else rate_limits.window_start end returning count into c;
 return c<=max_requests; end $$;
create function public.claim_emails() returns setof public.email_delivery_logs language sql security definer set search_path=public as $$
 update email_delivery_logs set status='processing',locked_until=now()+interval '2 minutes',attempts=attempts+1 where id in (select id from email_delivery_logs where ((status in ('pending','failed') and next_attempt_at<=now()) or (status='processing' and locked_until<now())) and attempts<6 order by created_at for update skip locked limit 25) returning *;
$$;
create function public.enqueue_reminders() returns void language plpgsql security definer set search_path=public as $$ declare r record; begin
 for r in select a.user_id,t.id,t.title,t.due_date from task_assignees a join tasks t on t.id=a.task_id join profiles p on p.id=a.user_id where p.active and a.status not in ('approved','completed') and t.due_date<=current_date+2 loop
 perform notify_user(r.user_id,case when r.due_date<current_date then 'Assignment overdue' else 'Deadline approaching' end,r.title||' — due '||r.due_date,'/my-tasks/'||r.id,r.id||':'||r.user_id||':'||current_date);
 end loop;
 delete from rate_limits where window_start<now()-interval '1 day';
 end $$;
-- Deny EXECUTE by default; only explicitly safe predicates are browser callable.
revoke all on all functions in schema public from public,anon,authenticated;
grant execute on function public.is_active(),public.is_admin(),public.can_task(uuid),public.can_submission(uuid),public.can_project(uuid) to authenticated;
grant execute on all functions in schema public to service_role;
