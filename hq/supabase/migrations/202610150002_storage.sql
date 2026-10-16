insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types) values('research','research',false,10485760,array['application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document','text/plain','text/markdown','image/png','image/jpeg','image/webp']) on conflict(id) do nothing;
-- No storage client policies: all uploads/download links pass authenticated Edge checks.
-- Bucket is private. URLs expire after 60 seconds; files download as attachments.
