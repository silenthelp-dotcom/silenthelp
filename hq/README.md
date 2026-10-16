# SilentHelp HQ

A private research and company operations application for a single company. React + TypeScript + Vite, Supabase PostgreSQL/Auth/Storage, Supabase Edge Functions, Resend and an OpenAI-compatible review provider.

**Status:** implemented and locally tested; not deployed or certified production-ready. Read `TESTING.md` and `SECURITY.md` before production use. All demo people and research are synthetic. No student or mental-health records are bundled.

## Quick demo

Use Node.js 22.12+ (tested with Node 24) and npm 10+.

```sh
npm ci
# macOS/Linux:
VITE_DEMO_MODE=true npm run dev
# Windows PowerShell:
# $env:VITE_DEMO_MODE='true'; npm run dev
```

Open http://localhost:5173 and choose **Explore admin workspace** or **Explore employee workspace**. Demo records persist in this browser's localStorage; files use IndexedDB. Log out to switch roles. Settings → Reset demo workspace resets records. Demo mode never creates a Supabase client and never calls email or AI providers. Demo accounts are not production credentials.

## Production setup

Follow `SETUP.md` in order:

1. Install with `npm ci`.
2. Create a Supabase project; apply all SQL migrations and the production-safe seed.
3. Configure Supabase Auth redirects, invitation/recovery SMTP and password policies.
4. Configure Resend, a verified sending domain and the scheduled outbox worker.
5. Configure the server-side AI endpoint/key/model.
6. Bootstrap the first administrator with `scripts/bootstrap.mjs`.
7. Invite employees from People; assign work from Assignments.
8. Run locally with `frontend/.env`, or build/deploy using `DEPLOYMENT.md`.
9. Run `npm test`, `npm run test:db`, `npm run test:e2e`, `npm run build`, and `npm run typecheck:backend`.

## Implemented workflows

- Separate admin/employee experiences, account invitations and temporary credentials, mandatory initial password change, reset and logout.
- Employee management and deactivation; SQL protects the last active administrator.
- Multi-person assignments, required deliverables, sources, criteria, deadlines, priorities, dependencies, comments, progress and extension requests.
- Table, Kanban and calendar views; search, sorting and filters; CSV export with spreadsheet-injection protection.
- Rich-text editor with headings, tables, links/citations, 1.5-second debounced autosave, concurrent-edit conflict detection, saved drafts and immutable submitted snapshots.
- Private typed/size-checked attachments, expiring authenticated download links, human review, version comparison, approval/rejection/revision requests.
- Structured AI quality review and separate uncertain authorship indicators. No invented probabilities, source-verification claims or automated personnel decisions.
- Real-data charts, workstream and milestone progress, operational analytics, notifications, transactional email outbox, delivery history and protected audit history.
- Thirty Q1 categories targeting November 15, 2026. Categories do not count as completed work.

## Architecture

`frontend/src/api.tsx` is the production Supabase adapter plus an explicitly enabled demo adapter. Browser reads obey RLS. Writes go through the `hq` Edge Function, which verifies the bearer token with Supabase Auth, checks profile status, rate limits, validates inputs and calls a transactional server-only SQL command. The SQL command repeats actor authorization. Database writes and outbox events commit together.

`worker` claims email jobs with `FOR UPDATE SKIP LOCKED`, sends through Resend with stable idempotency keys, and backs off failed deliveries. Invitations and recovery emails use Supabase Auth SMTP (configure Resend SMTP there); application notifications use the Resend API worker.

AI API calls are server-side and accept only schema-validated responses. External URLs are not fetched, preventing arbitrary network access through submitted citations. Attachments are not silently represented as reviewed.

## Repository

- `frontend/`: UI, static assets and public build.
- `backend/functions/`: authenticated API and scheduled worker.
- `backend/services/`: AI/email integrations and calculations.
- `backend/validation/`: shared server/client schemas and upload validation.
- `supabase/`: migrations, RLS, storage, safe category seed and function entrypoints.
- `tests/`: unit/provider-contract, PostgreSQL RLS and browser tests.
- `scripts/`: admin bootstrap, CSP generation, packaging helpers.

No backend secrets are committed. `.env.example` contains placeholders only. `package-lock.json` pins the tested dependency tree. Native Supabase and Resend verification remains required on your deployment.
