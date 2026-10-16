# Deployment

## Frontend: Cloudflare Pages

1. Deploy database migrations and both Supabase functions first (SETUP.md).
2. Connect the source repository to Cloudflare Pages, framework Vite.
3. Root directory: repository root. Build: `npm ci && npm run build`. Output: `frontend/dist`.
4. Set VITE_DEMO_MODE=false, VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY. Node 22.12+ or 24.
5. Set the production APP_URL Edge secret and exact Supabase Auth callback URL.
6. Generate restrictive headers before building: `node scripts/headers.mjs https://YOUR_PROJECT.supabase.co`. It writes `frontend/public/_headers`. Do not use a wildcard connect-src in production. `_redirects` provides SPA history fallback.
7. Configure HTTPS, DNS, monitoring and your email worker schedule. Keep staging separate from production.

The frontend is static; it contains no server passwords or secrets. Supabase functions and PostgreSQL perform all privileged operations. Cloudflare Pages alone cannot replace the backend. Hosting on another static provider requires equivalent SPA fallback and response headers.

## First deployment verification (required)

Use separate administrator and employee test accounts. Verify invitation expiration, password reset, mandatory temporary password change, sign-out, inactive-account rejection, expired-token rejection, real storage download authorization, task and revision emails, queue retry, and one approved-provider AI review. Confirm unauthorized clients cannot directly call SQL write functions or read private storage. Review all RLS tests against actual Supabase using its local/full staging stack as well as the portable harness.

Run `npm run build` and tests with production configuration in CI. Do not deploy a build made with VITE_DEMO_MODE=true to the production hostname. Demo builds and browser storage are explicitly separate; they are not authorization mechanisms.

## Operations

- Enable database backups/PITR appropriate to your plan and test restoration.
- Monitor Edge errors, email failed jobs and Auth abuse. Set cloud and AI spending limits.
- Schedule retention/deletion policies with legal/operations owners. The app intentionally does not automatically delete audit/history records.
- Uploaded object cleanup: a failed metadata registration attempts immediate deletion; periodically reconcile orphaned objects after runtime crashes.
- Restore order: database and private objects, then Auth users/secrets, then application; validate references before reopening access.
- For dependency updates, update lockfile, run `node scripts/sync-edge-imports.mjs`, test and redeploy both frontend and functions.
- Scale: lists are paginated in the UI but the small-team application currently reads all authorized rows in 1,000-row batches. Large installations should move filtering/analytics to server-side aggregate endpoints and add query caching before tens of thousands of records.

No live deployment has been performed as part of this delivery.
