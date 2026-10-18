-- Team members can add a short bio and a profile photo.
alter table public.profiles add column if not exists bio text check (char_length(bio)<=600);
alter table public.profiles add column if not exists avatar_path text;
-- Photos are served from a public bucket under unguessable paths (avatars/<user>/<uuid>.<ext>).
-- Writes only happen through the hq Edge function with one-time signed upload URLs.
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('avatars','avatars',true,5242880,array['image/png','image/jpeg','image/webp']) on conflict(id) do nothing;
