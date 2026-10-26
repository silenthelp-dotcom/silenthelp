-- Team chat: one channel for everyone, group channels (e.g. per project) and one-to-one messages.
-- Members only: every read is limited by membership, and every write goes through the chat_* functions
-- below, which run as the signed-in person (auth.uid()) and check membership themselves.
create table public.chat_channels(
 id uuid primary key default gen_random_uuid(),
 kind text not null check (kind in ('team','group','dm')),
 name text check (kind='dm' or char_length(name) between 1 and 60),
 description text check (char_length(description) <= 300),
 project_id uuid references public.projects(id) on delete set null,
 dm_key text unique,
 created_by uuid references public.profiles(id),
 created_at timestamptz not null default now()
);
create unique index chat_one_team on public.chat_channels(kind) where kind='team';
create table public.chat_members(
 channel_id uuid not null references public.chat_channels(id) on delete cascade,
 user_id uuid not null references public.profiles(id) on delete cascade,
 joined_at timestamptz not null default now(),
 last_read_at timestamptz not null default now(),
 primary key(channel_id,user_id)
);
create index chat_members_user on public.chat_members(user_id);
create table public.chat_messages(
 id uuid primary key default gen_random_uuid(),
 channel_id uuid not null references public.chat_channels(id) on delete cascade,
 author_id uuid not null references public.profiles(id),
 body text not null default '' check (char_length(body) <= 4000),
 image_path text,
 image_name text check (char_length(image_name) <= 240),
 reply_to uuid references public.chat_messages(id) on delete set null,
 created_at timestamptz not null default now(),
 edited_at timestamptz,
 unsent_at timestamptz
);
create index chat_messages_channel on public.chat_messages(channel_id,created_at desc);
create table public.chat_reactions(
 message_id uuid not null references public.chat_messages(id) on delete cascade,
 user_id uuid not null references public.profiles(id) on delete cascade,
 emoji text not null check (char_length(emoji) between 1 and 16),
 created_at timestamptz not null default now(),
 primary key(message_id,user_id,emoji)
);
create table public.chat_hidden(
 message_id uuid not null references public.chat_messages(id) on delete cascade,
 user_id uuid not null references public.profiles(id) on delete cascade,
 primary key(message_id,user_id)
);

-- Everyone (active) is in the team channel, now and as they join.
insert into public.chat_channels(kind,name,description) values('team','Everyone','The whole SilentHelp team');
insert into public.chat_members(channel_id,user_id) select c.id,p.id from public.chat_channels c cross join public.profiles p where c.kind='team' on conflict do nothing;
create function public.chat_join_team() returns trigger language plpgsql security definer set search_path=public as $$
begin insert into chat_members(channel_id,user_id) select id,new.id from chat_channels where kind='team' on conflict do nothing; return new; end $$;
create trigger chat_join_team after insert on public.profiles for each row execute function public.chat_join_team();

create function public.chat_is_member(ch uuid) returns boolean language sql stable security definer set search_path=public as $$
 select public.is_active() and exists(select 1 from chat_members where channel_id=ch and user_id=auth.uid())
$$;

DO $$ declare t text; begin foreach t in array array['chat_channels','chat_members','chat_messages','chat_reactions','chat_hidden'] loop
 execute format('alter table public.%I enable row level security',t);
 execute format('grant select on public.%I to authenticated',t);
 execute format('grant all on public.%I to service_role',t);
end loop; end $$;
create policy chat_channels_read on public.chat_channels for select to authenticated using(public.chat_is_member(id));
create policy chat_members_read on public.chat_members for select to authenticated using(public.chat_is_member(channel_id));
create policy chat_messages_read on public.chat_messages for select to authenticated using(public.chat_is_member(channel_id));
create policy chat_reactions_read on public.chat_reactions for select to authenticated using(exists(select 1 from public.chat_messages m where m.id=message_id and public.chat_is_member(m.channel_id)));
create policy chat_hidden_read on public.chat_hidden for select to authenticated using(user_id=auth.uid());

create function public.chat_me() returns uuid language plpgsql stable security definer set search_path=public as $$
begin if not is_active() then raise exception 'Access denied' using errcode='42501'; end if; return auth.uid(); end $$;
create function public.chat_need(ch uuid) returns void language plpgsql stable security definer set search_path=public as $$
begin if not chat_is_member(ch) then raise exception 'You are not in this conversation' using errcode='42501'; end if; end $$;

-- People you can message: active teammates (names and photos only).
create function public.team_directory() returns table(id uuid, full_name text, avatar_path text, role text, bio text) language plpgsql stable security definer set search_path=public as $$
begin perform chat_me(); return query select p.id,p.full_name,p.avatar_path,p.role,p.bio from profiles p where p.active order by p.full_name; end $$;

create function public.chat_send(ch uuid, body text, image_path text default null, image_name text default null, reply_to uuid default null) returns public.chat_messages language plpgsql security definer set search_path=public as $$
#variable_conflict use_variable
declare me uuid:=chat_me(); m chat_messages; b text:=btrim(coalesce(body,''));
begin
 perform chat_need(ch);
 if b='' and image_path is null then raise exception 'Write a message or add a picture'; end if;
 if image_path is not null and (image_path not like ch::text||'/'||me::text||'/%' or image_path like '%..%') then raise exception 'Invalid picture'; end if;
 if reply_to is not null and not exists(select 1 from chat_messages where id=reply_to and channel_id=ch) then raise exception 'Reply not found'; end if;
 insert into chat_messages(channel_id,author_id,body,image_path,image_name,reply_to) values(ch,me,b,image_path,image_name,reply_to) returning * into m;
 update chat_members set last_read_at=now() where channel_id=ch and user_id=me;
 return m;
end $$;

create function public.chat_edit(m uuid, body text) returns public.chat_messages language plpgsql security definer set search_path=public as $$
#variable_conflict use_variable
declare me uuid:=chat_me(); r chat_messages; b text:=btrim(coalesce(body,''));
begin
 select * into r from chat_messages where id=m;
 if r.id is null or r.author_id<>me then raise exception 'You can only edit your own messages'; end if;
 if r.unsent_at is not null then raise exception 'This message was unsent'; end if;
 if b='' and r.image_path is null then raise exception 'A message cannot be empty'; end if;
 update chat_messages set body=b,edited_at=now() where id=m returning * into r;
 return r;
end $$;

-- Unsend removes the message for everyone. The author can unsend; admins can remove any message.
create function public.chat_unsend(m uuid) returns text language plpgsql security definer set search_path=public as $$
declare me uuid:=chat_me(); r chat_messages;
begin
 select * into r from chat_messages where id=m;
 if r.id is null or not (r.author_id=me or is_admin()) then raise exception 'You can only unsend your own messages'; end if;
 perform chat_need(r.channel_id);
 update chat_messages set body='',image_path=null,image_name=null,unsent_at=now() where id=m;
 delete from chat_reactions where message_id=m;
 return r.image_path;
end $$;

create function public.chat_hide(m uuid) returns void language plpgsql security definer set search_path=public as $$
declare me uuid:=chat_me(); ch uuid;
begin
 select channel_id into ch from chat_messages where id=m; if ch is null then raise exception 'Message not found'; end if;
 perform chat_need(ch);
 insert into chat_hidden(message_id,user_id) values(m,me) on conflict do nothing;
end $$;

create function public.chat_react(m uuid, emoji text) returns boolean language plpgsql security definer set search_path=public as $$
#variable_conflict use_variable
declare me uuid:=chat_me(); r chat_messages;
begin
 select * into r from chat_messages where id=m; if r.id is null then raise exception 'Message not found'; end if;
 perform chat_need(r.channel_id);
 if r.unsent_at is not null then raise exception 'This message was unsent'; end if;
 if exists(select 1 from chat_reactions where message_id=m and user_id=me and chat_reactions.emoji=chat_react.emoji) then
  delete from chat_reactions where message_id=m and user_id=me and chat_reactions.emoji=chat_react.emoji; return false;
 end if;
 insert into chat_reactions(message_id,user_id,emoji) values(m,me,emoji); return true;
end $$;

create function public.chat_create_group(name text, members uuid[], project uuid default null, description text default null) returns uuid language plpgsql security definer set search_path=public as $$
#variable_conflict use_variable
declare me uuid:=chat_me(); ch uuid;
begin
 if coalesce(btrim(name),'')='' then raise exception 'Give the channel a name'; end if;
 insert into chat_channels(kind,name,description,project_id,created_by) values('group',btrim(name),nullif(btrim(coalesce(description,'')),''),project,me) returning id into ch;
 insert into chat_members(channel_id,user_id) select ch,p.id from profiles p where p.active and (p.id=me or p.id=any(coalesce(members,'{}'))) on conflict do nothing;
 return ch;
end $$;

create function public.chat_add_members(ch uuid, members uuid[]) returns void language plpgsql security definer set search_path=public as $$
#variable_conflict use_variable
begin
 perform chat_me(); perform chat_need(ch);
 if not exists(select 1 from chat_channels where id=ch and kind='group') then raise exception 'People can only be added to group channels'; end if;
 insert into chat_members(channel_id,user_id) select ch,p.id from profiles p where p.active and p.id=any(coalesce(members,'{}')) on conflict do nothing;
end $$;

create function public.chat_leave(ch uuid) returns void language plpgsql security definer set search_path=public as $$
declare me uuid:=chat_me();
begin
 if not exists(select 1 from chat_channels where id=ch and kind='group') then raise exception 'You can only leave group channels'; end if;
 delete from chat_members where channel_id=ch and user_id=me;
end $$;

create function public.chat_rename(ch uuid, name text, description text default null) returns void language plpgsql security definer set search_path=public as $$
#variable_conflict use_variable
begin
 perform chat_me(); perform chat_need(ch);
 if coalesce(btrim(name),'')='' then raise exception 'Give the channel a name'; end if;
 update chat_channels set name=btrim(chat_rename.name),description=nullif(btrim(coalesce(chat_rename.description,'')),'') where id=ch and kind='group';
end $$;

create function public.chat_open_dm(other uuid) returns uuid language plpgsql security definer set search_path=public as $$
declare me uuid:=chat_me(); k text; ch uuid;
begin
 if other=me then raise exception 'Pick someone else to message'; end if;
 if not exists(select 1 from profiles where id=other and active) then raise exception 'That person is not in the workspace'; end if;
 k:=least(me::text,other::text)||':'||greatest(me::text,other::text);
 insert into chat_channels(kind,dm_key,created_by) values('dm',k,me) on conflict(dm_key) do nothing;
 select id into ch from chat_channels where dm_key=k;
 insert into chat_members(channel_id,user_id) values(ch,me),(ch,other) on conflict do nothing;
 return ch;
end $$;

create function public.chat_mark_read(ch uuid) returns void language plpgsql security definer set search_path=public as $$
declare me uuid:=chat_me();
begin update chat_members set last_read_at=now() where channel_id=ch and user_id=me; end $$;

-- One row per conversation I am in: unread count and the latest message, for the sidebar.
create function public.chat_overview() returns table(channel_id uuid, unread integer, last_at timestamptz, last_body text, last_author uuid, last_unsent boolean, last_image boolean) language plpgsql stable security definer set search_path=public as $$
declare me uuid:=chat_me();
begin
 return query
 select mb.channel_id,
  (select count(*)::integer from chat_messages x where x.channel_id=mb.channel_id and x.created_at>mb.last_read_at and x.author_id<>me and x.unsent_at is null),
  l.created_at, left(l.body,140), l.author_id, l.unsent_at is not null, l.image_path is not null
 from chat_members mb
 left join lateral (select * from chat_messages y where y.channel_id=mb.channel_id and not exists(select 1 from chat_hidden h where h.message_id=y.id and h.user_id=me) order by y.created_at desc limit 1) l on true
 where mb.user_id=me;
end $$;

revoke all on function public.chat_join_team(), public.chat_me(), public.chat_need(uuid), public.team_directory(),
 public.chat_send(uuid,text,text,text,uuid), public.chat_edit(uuid,text), public.chat_unsend(uuid), public.chat_hide(uuid), public.chat_react(uuid,text),
 public.chat_create_group(text,uuid[],uuid,text), public.chat_add_members(uuid,uuid[]), public.chat_leave(uuid), public.chat_rename(uuid,text,text),
 public.chat_open_dm(uuid), public.chat_mark_read(uuid), public.chat_overview(), public.chat_is_member(uuid) from public,anon;
revoke all on function public.chat_join_team() from authenticated;
grant execute on function public.chat_is_member(uuid), public.chat_me(), public.chat_need(uuid), public.team_directory(),
 public.chat_send(uuid,text,text,text,uuid), public.chat_edit(uuid,text), public.chat_unsend(uuid), public.chat_hide(uuid), public.chat_react(uuid,text),
 public.chat_create_group(text,uuid[],uuid,text), public.chat_add_members(uuid,uuid[]), public.chat_leave(uuid), public.chat_rename(uuid,text,text),
 public.chat_open_dm(uuid), public.chat_mark_read(uuid), public.chat_overview() to authenticated;
grant execute on all functions in schema public to service_role;

-- Pictures: private bucket; the first folder is the conversation, the second the sender.
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('chat','chat',false,10485760,array['image/png','image/jpeg','image/webp','image/gif']) on conflict(id) do nothing;
create function public.chat_object_member(objname text) returns boolean language plpgsql stable security definer set search_path=public as $$
declare part text:=split_part(objname,'/',1);
begin
 if part !~ '^[0-9a-f-]{36}$' then return false; end if;
 return chat_is_member(part::uuid);
end $$;
create function public.chat_object_mine(objname text) returns boolean language sql stable security definer set search_path=public as $$
 select split_part(objname,'/',2)=auth.uid()::text and objname not like '%..%'
$$;
revoke all on function public.chat_object_member(text), public.chat_object_mine(text) from public,anon;
grant execute on function public.chat_object_member(text), public.chat_object_mine(text) to authenticated;
DO $$ begin
 if to_regclass('storage.objects') is not null then
  execute $p$create policy chat_pictures_read on storage.objects for select to authenticated using (bucket_id='chat' and public.chat_object_member(name))$p$;
  execute $p$create policy chat_pictures_upload on storage.objects for insert to authenticated with check (bucket_id='chat' and public.chat_object_member(name) and public.chat_object_mine(name))$p$;
  execute $p$create policy chat_pictures_remove on storage.objects for delete to authenticated using (bucket_id='chat' and public.chat_object_mine(name))$p$;
 end if;
 if exists(select 1 from pg_publication where pubname='supabase_realtime') then
  alter publication supabase_realtime add table public.chat_channels, public.chat_members, public.chat_messages, public.chat_reactions;
 end if;
end $$;
