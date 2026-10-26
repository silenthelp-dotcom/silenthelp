-- Meetings (Google Meet / Zoom links) and polls that admins post to the whole team.
-- Everyone active can read meetings and polls; a person sees only their own poll answer, admins see all.
-- Writes go through the hq Edge function, which calls the hq_* functions below as service_role.
create table public.meetings(
 id uuid primary key default gen_random_uuid(),
 title text not null check (char_length(title) between 1 and 200),
 link text check (link is null or link ~* '^https://([a-z0-9-]+\.)*(zoom\.us|meet\.google\.com)/'),
 starts_at timestamptz not null,
 duration_min integer not null default 30 check (duration_min between 5 and 600),
 notes text check (char_length(notes) <= 2000),
 created_by uuid not null references public.profiles(id),
 created_at timestamptz not null default now(),
 cancelled_at timestamptz
);
create table public.polls(
 id uuid primary key default gen_random_uuid(),
 question text not null check (char_length(question) between 1 and 300),
 options text[] not null check (array_length(options,1) between 1 and 8),
 allow_suggestion boolean not null default true,
 meeting_id uuid references public.meetings(id) on delete set null,
 closes_at timestamptz,
 closed_at timestamptz,
 created_by uuid not null references public.profiles(id),
 created_at timestamptz not null default now()
);
create table public.poll_responses(
 id uuid primary key default gen_random_uuid(),
 poll_id uuid not null references public.polls(id) on delete cascade,
 user_id uuid not null references public.profiles(id),
 choice text check (char_length(choice) <= 80),
 suggestion text check (char_length(suggestion) <= 500),
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 unique(poll_id,user_id),
 check (choice is not null or suggestion is not null)
);
create index meetings_start on public.meetings(starts_at);
create index polls_open on public.polls(created_at desc) where closed_at is null;

DO $$ declare t text; begin foreach t in array array['meetings','polls','poll_responses'] loop
 execute format('alter table public.%I enable row level security',t);
 execute format('grant select on public.%I to authenticated',t);
 execute format('grant all on public.%I to service_role',t);
end loop; end $$;
create policy meetings_read on public.meetings for select to authenticated using(public.is_active());
create policy polls_read on public.polls for select to authenticated using(public.is_active());
create policy poll_responses_read on public.poll_responses for select to authenticated using(public.is_admin() or (public.is_active() and user_id=auth.uid()));

create function public.hq_require(actor uuid, admin_only boolean) returns profiles language plpgsql security definer set search_path=public as $$
declare me profiles;
begin
 select * into me from profiles where id=actor;
 if me.id is null or not me.active or me.must_change_password then raise exception 'Access denied' using errcode='42501'; end if;
 if admin_only and me.role<>'admin' then raise exception 'Administrator required' using errcode='42501'; end if;
 return me;
end $$;

-- "Fri, Oct 30 at 5:00 PM Central": the team works in Illinois.
create function public.hq_when(t timestamptz) returns text language sql immutable set search_path=public as $$
 select to_char(t at time zone 'America/Chicago','Dy, Mon FMDD "at" FMHH12:MI AM')||' Central'
$$;

create function public.hq_notify_team(actor uuid, heading text, message text, route text) returns void language plpgsql security definer set search_path=public as $$
declare uid uuid;
begin
 for uid in select id from profiles where active and not must_change_password and id<>actor loop perform notify_user(uid,heading,message,route); end loop;
end $$;

create function public.hq_poll_insert(actor uuid, p jsonb, meeting uuid) returns uuid language plpgsql security definer set search_path=public as $$
declare pid uuid; opts text[];
begin
 select array_agg(btrim(x)) into opts from jsonb_array_elements_text(coalesce(p->'options','["Yes","No"]'::jsonb)) x where btrim(x)<>'';
 if opts is null or array_length(opts,1) is null then opts:=array['Yes','No']; end if;
 insert into polls(question,options,allow_suggestion,meeting_id,closes_at,created_by)
 values(btrim(p->>'question'),opts,coalesce((p->>'allow_suggestion')::boolean,true),meeting,nullif(p->>'closes_at','')::timestamptz,actor) returning id into pid;
 return pid;
end $$;

create function public.hq_meeting_create(actor uuid, payload jsonb) returns jsonb language plpgsql security definer set search_path=public as $$
declare mid uuid; pid uuid; m meetings;
begin
 perform hq_require(actor,true);
 insert into meetings(title,link,starts_at,duration_min,notes,created_by)
 values(btrim(payload->>'title'),nullif(btrim(coalesce(payload->>'link','')),''),(payload->>'starts_at')::timestamptz,coalesce((payload->>'duration_min')::integer,30),nullif(btrim(coalesce(payload->>'notes','')),''),actor)
 returning * into m;
 mid:=m.id;
 if jsonb_typeof(payload->'poll')='object' and coalesce(btrim(payload->'poll'->>'question'),'')<>'' then pid:=hq_poll_insert(actor,payload->'poll',mid); end if;
 perform hq_notify_team(actor,'Meeting: '||m.title,
  hq_when(m.starts_at)||' · '||m.duration_min||' min'||coalesce(E'\nJoin: '||m.link,'')||coalesce(E'\n'||m.notes,'')||case when pid is not null then E'\nThere is a quick poll for this meeting in HQ.' else '' end,
  '/meetings');
 insert into activity_logs(actor_id,action,record_id,metadata) values(actor,'meeting.create',mid,jsonb_build_object('title',m.title));
 return jsonb_build_object('id',mid,'poll_id',pid);
end $$;

create function public.hq_meeting_cancel(actor uuid, payload jsonb) returns jsonb language plpgsql security definer set search_path=public as $$
declare m meetings;
begin
 perform hq_require(actor,true);
 update meetings set cancelled_at=now() where id=(payload->>'id')::uuid and cancelled_at is null returning * into m;
 if m.id is null then raise exception 'Meeting not found or already cancelled'; end if;
 update polls set closed_at=now() where meeting_id=m.id and closed_at is null;
 perform hq_notify_team(actor,'Meeting cancelled: '||m.title,'Was scheduled for '||hq_when(m.starts_at)||'.','/meetings');
 return jsonb_build_object('ok',true);
end $$;

create function public.hq_poll_create(actor uuid, payload jsonb) returns jsonb language plpgsql security definer set search_path=public as $$
declare pid uuid; q text;
begin
 perform hq_require(actor,true);
 pid:=hq_poll_insert(actor,payload,nullif(payload->>'meeting_id','')::uuid);
 select question into q from polls where id=pid;
 perform hq_notify_team(actor,'New poll: '||q,'Answer it in HQ — it takes a few seconds.','/meetings');
 insert into activity_logs(actor_id,action,record_id,metadata) values(actor,'poll.create',pid,jsonb_build_object('question',q));
 return jsonb_build_object('id',pid);
end $$;

create function public.hq_poll_respond(actor uuid, payload jsonb) returns jsonb language plpgsql security definer set search_path=public as $$
declare p polls; c text; s text;
begin
 perform hq_require(actor,false);
 select * into p from polls where id=(payload->>'poll_id')::uuid;
 if p.id is null then raise exception 'Poll not found'; end if;
 if p.closed_at is not null or (p.closes_at is not null and p.closes_at<=now()) then raise exception 'This poll is closed'; end if;
 c:=nullif(btrim(coalesce(payload->>'choice','')),''); s:=nullif(btrim(coalesce(payload->>'suggestion','')),'');
 if c is not null and not (c = any(p.options)) then raise exception 'Pick one of the poll options'; end if;
 if s is not null and not p.allow_suggestion then raise exception 'This poll does not take suggestions'; end if;
 if c is null and s is null then raise exception 'Pick an option or write a suggestion'; end if;
 insert into poll_responses(poll_id,user_id,choice,suggestion) values(p.id,actor,c,s)
 on conflict(poll_id,user_id) do update set choice=excluded.choice,suggestion=excluded.suggestion,updated_at=now();
 return jsonb_build_object('ok',true);
end $$;

create function public.hq_poll_close(actor uuid, payload jsonb) returns jsonb language plpgsql security definer set search_path=public as $$
begin
 perform hq_require(actor,true);
 update polls set closed_at=now() where id=(payload->>'id')::uuid and closed_at is null;
 return jsonb_build_object('ok',true);
end $$;

revoke all on function public.hq_require(uuid,boolean), public.hq_when(timestamptz), public.hq_notify_team(uuid,text,text,text), public.hq_poll_insert(uuid,jsonb,uuid),
 public.hq_meeting_create(uuid,jsonb), public.hq_meeting_cancel(uuid,jsonb), public.hq_poll_create(uuid,jsonb), public.hq_poll_respond(uuid,jsonb), public.hq_poll_close(uuid,jsonb) from public,anon,authenticated;
grant execute on function public.hq_require(uuid,boolean), public.hq_when(timestamptz), public.hq_notify_team(uuid,text,text,text), public.hq_poll_insert(uuid,jsonb,uuid),
 public.hq_meeting_create(uuid,jsonb), public.hq_meeting_cancel(uuid,jsonb), public.hq_poll_create(uuid,jsonb), public.hq_poll_respond(uuid,jsonb), public.hq_poll_close(uuid,jsonb) to service_role;

-- Live updates: polls pop up on everyone's screen as soon as they are posted.
DO $$ begin
 if exists(select 1 from pg_publication where pubname='supabase_realtime') then
  alter publication supabase_realtime add table public.meetings, public.polls, public.poll_responses, public.notifications;
 end if;
end $$;
