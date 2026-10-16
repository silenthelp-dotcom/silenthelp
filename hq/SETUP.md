# Setup

## 1. Install

```sh
npm ci
cp frontend/.env.example frontend/.env
```

Do not copy server credentials into `frontend/.env`. For production, set `VITE_DEMO_MODE=false`, the project URL, and the public anonymous/publishable browser key. A service-role/secret key is NEVER a Vite variable.

## 2. Supabase database

Install the Supabase CLI using its supported package or native installer. From this repository:

```sh
supabase login
supabase link --project-ref YOUR_PROJECT_REF
supabase db push
```

Apply `supabase/seed.sql` through the SQL editor (or `psql` using your private database connection). It is idempotent and creates departments plus exactly 30 categories, not accounts or completed assignments. A local Supabase stack uses `supabase start` and `supabase db reset` (Docker required). The portable test harness uses PGlite and does not require Docker.

All migrations must run in filename order. All RLS policies are deployed with migration 001. Migration 002 creates the private `research` bucket; migration 003 serializes file registration against review transitions. Application installations are single-company; never put unrelated organizations in one database.

## 3. Authentication

In Supabase Authentication settings:

- Disable public sign-up. Accounts are provisioned using the service-role Admin API.
- Set Site URL to your exact frontend origin. Allow the exact `/invite/accept` callback on localhost and the deployed origin. Avoid wildcard production redirect origins.
- Require at least 12-character passwords; enable available breached-password protection.
- Set invitation/recovery token expiry to 3600 seconds. Invitation and recovery links use Supabase's built-in secure email-link workflow, with default `{{ .ConfirmationURL }}` templates so Supabase validates the token before redirecting.
- JWT lifetime: 3600 seconds. Configure server-side session lifetime/inactivity controls where supported by your plan. The UI also logs out after 30 minutes without keyboard/pointer input.
- Configure Auth rate limits, email throttling, and CAPTCHA if required by your threat model. Browser password sign-in and reset use Supabase Auth directly and inherit its rate limits.
- Set custom SMTP to Resend (host `smtp.resend.com`, provider-supported port/TLS, username `resend`, password your API key) and a verified sender. Use current Resend/Supabase SMTP instructions for your region.

The app accepts auth tokens at `/invite/accept` and sets the password via the authenticated Edge endpoint. Profiles with `must_change_password=true` have no workspace data access until that operation succeeds. Supabase hashes passwords. The application does not store them.

Temporary password accounts are created by an admin after identity verification and marked for mandatory password change. They are manually confirmed by the admin API; do not use this route without verifying the email owner. Deliver the password through a trusted channel; it is never included in assignment emails or database metadata.

## 4. Edge functions and secrets

Create an untracked server environment file (for example `.env.server`) using the server-only entries in `.env.example`. Generate `WORKER_SECRET` with at least 32 cryptographically random bytes. Set APP_URL to the exact frontend origin without a trailing slash. SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are provided automatically to hosted Supabase functions; do not override reserved variables there.

```sh
supabase secrets set --env-file .env.server
supabase functions deploy hq --no-verify-jwt
supabase functions deploy worker --no-verify-jwt
```

`--no-verify-jwt` disables the gateway's legacy JWT check, NOT application authentication. `hq` always calls `auth.getUser()` and checks the database profile. `worker` requires WORKER_SECRET and rejects empty configuration. Never expose the worker secret in the browser. Function entrypoints import the backend files relative to this repository; deploy from its root.

For local functions, pass the server env file to `supabase functions serve --env-file .env.server` and set browser URLs/keys to the local stack values. Sync pinned Deno imports after dependency upgrades with `node scripts/sync-edge-imports.mjs`.

## 5. Transactional email

Verify the sending domain with Resend and configure SPF/DKIM/DMARC. Set RESEND_API_KEY, EMAIL_FROM and APP_URL. Run the `worker` endpoint every 5 minutes using a scheduler that supports protected HTTP requests:

- Method: POST
- URL: `https://YOUR_PROJECT.supabase.co/functions/v1/worker`
- Authorization header: `Bearer YOUR_WORKER_SECRET`
- Empty body is sufficient.

Use Supabase Cron + Vault/pg_net or a trusted external scheduler; store the secret in the scheduler's secret store. Do not embed it in a public migration or frontend. Monitor scheduler failures. Worker batches are 25 jobs; increase frequency or run multiple workers for larger queues. Claims are locked atomically. Failed sends retry with exponential backoff up to six attempts. Settings shows attempts and errors. Investigate exhausted jobs and resend manually by resetting `status='pending', attempts=0, next_attempt_at=now()` for selected IDs in an administrator-only SQL session. Do not bulk retry delivered messages. Resend idempotency retention is finite; exactly-once delivery across provider outages is not guaranteed.

Daily deadline reminders are deduplicated per assignment/person/UTC day. Overdue means due date is earlier than today's UTC date and the assignment is neither approved nor completed.

## 6. AI review

Set AI_API_URL to an HTTPS OpenAI-compatible chat completions endpoint, AI_API_KEY, and AI_MODEL to a model supporting JSON-object response mode. Choose an approved provider and review its data-processing/retention terms. The request includes the assignment and submitted editor text, not uploaded files. Click Run AI Review on a submitted version. Failures produce an error, never a fabricated report. Limits: ten reviews per admin/hour, 45-second timeout, validated structured response. Citation URLs are labeled Not Verified because the app does not browse sources.

## 7. Bootstrap

On a trusted machine with service-role access, put SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, BOOTSTRAP_EMAIL, BOOTSTRAP_NAME and APP_URL into an untracked `.env.bootstrap`. Run once (not concurrently):

```sh
node --env-file=.env.bootstrap scripts/bootstrap.mjs
```

The script refuses to run if an admin exists. It sends an invitation and creates the first admin profile. Open the expiring link and choose a password. Subsequent admins are invited through People. Remove the bootstrap env file from shared machines after use. To recover an expired initial invitation, send a password-reset email to that same account using the supported recovery workflow.

## 8. Start using HQ

Invite a colleague → create a project or choose a Q1 workstream → create/assign a task → attach reference files → employee signs in and submits research → admin reviews the latest version → approve or request revisions. Deactivating an account blocks its existing token from accessing application data through RLS and Edge checks.

Extension requests are private task comments that notify administrators. The administrator explicitly changes the deadline; an extension request does not automatically alter it.
