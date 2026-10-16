# Verification

Run from repository root after `npm ci`:

```sh
npm run build
npm run typecheck:backend
npm test
npm run test:db
npx playwright install chromium
npm run test:e2e
# Or use an existing Chromium:
# CHROMIUM_PATH=/usr/bin/chromium npm run test:e2e
```

`tests/domain.test.ts` validates isolation, roles, invitations, tasks, draft conflicts, immutable revisions, approval, deactivation, overdue metrics, safe CSV, upload validation, schemas, and mocked email/AI provider contracts. Mock provider tests do not prove live deliverability or provider access.

`tests/database.mjs` runs the actual migrations and SQL commands inside PGlite PostgreSQL. Its small auth/storage schema adapters emulate `auth.uid()`, user IDs, roles and bucket metadata. RLS, grants, security-definer functions, transaction behavior and constraints are real PostgreSQL behavior. It does not run Supabase GoTrue, Storage HTTP, PostgREST or Edge runtime.

`tests/e2e/workflows.spec.ts` runs Chromium against the isolated local demo: login/logout and unauthorized routes; invitation and assignment; rich-text draft and file upload; submit, AI demo report, revision and approval; navigation across all admin routes; desktop/tablet/mobile layout checks. Reports and screenshots are generated in `playwright-report/` and `test-results/`.

No live services or deployment were tested: real Auth invitation/recovery emails and expiration, actual Supabase Storage signed URLs, hosted Edge Functions, Resend delivery/retries, and an external AI model still need staging verification. No load/stress or penetration test was performed. The source includes complete adapters and setup guidance, but local passing tests do not guarantee zero bugs or zero lag.

See `VERIFICATION.txt` for the final local command outcomes included with the ZIP.
