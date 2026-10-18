-- Weekly SilentHelp code snapshots: a plain-English summary of the week's commits plus a .zip of the code.
-- Written only by the `snapshot` Edge function (service role); readable by active admins.
create table public.code_snapshots(
 id uuid primary key default gen_random_uuid(),
 created_at timestamptz not null default now(),
 period_start timestamptz,
 commit_sha text not null,
 previous_sha text,
 commit_count integer not null default 0,
 files_changed integer not null default 0,
 headline text not null,
 summary jsonb not null default '[]',
 commits jsonb not null default '[]',
 zip_path text,
 zip_size bigint,
 trigger text not null default 'schedule' check (trigger in ('schedule','manual'))
);
alter table public.code_snapshots enable row level security;
create policy code_snapshots_read on public.code_snapshots for select to authenticated using (public.is_admin());
grant select on public.code_snapshots to authenticated;
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('code-snapshots','code-snapshots',false,52428800,array['application/zip']) on conflict(id) do nothing;
