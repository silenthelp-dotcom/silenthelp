# Security and privacy model

## Trust boundaries

This is a single-company internal application. Browser requests are untrusted. Supabase verifies credentials and hashes passwords. The Edge API derives user identity from a validated bearer token, never from payload actor IDs. Profiles control admin/employee role, active status and mandatory password change. SQL repeats actor checks before mutations. Browser writes have no grants/policies; server-only functions are not executable by anon/authenticated roles.

RLS prevents employees from reading other employees' profiles, drafts, submitted versions, reviews, files or private comments. Shared tasks do not imply shared submissions. Admins can read company data. Project membership grants project visibility but not employee-private submissions. All application tables enable RLS, and audit logs have no browser write policy. Service-role holders and database owners are trusted operators and can modify the database; audit history is not tamper-proof against them. Export audit records to independent immutable storage if that assurance is required.

## Files and document handling

Private storage with a 10 MB object limit, extension allowlist, MIME mapping and magic-signature checks for PDF, DOCX ZIP, PNG, JPEG and WebP. HTML, SVG and executable uploads are rejected. File registration locks the submission and rejects files arriving after submission. Original files are downloaded using 60-second signed URLs after ownership checks. A signed URL remains usable until expiry even after deactivation; protect URLs as credentials. Reference files are for assigned users; research files are for their author and admins.

Signature validation is not antivirus or full container validation. No malware scanner is included. Deploy a quarantine/scanning service before permitting untrusted external uploads. PDF/DOCX originals are not parsed by the server or rendered as arbitrary HTML. Review files in appropriately protected document software. Rich-text editor output is sanitized through DOMPurify with a narrow element/attribute allowlist. React escapes other text. CSV cells protect against spreadsheet formula injection.

## Requests and sessions

The API accepts POST plus CORS preflight and permits only the configured frontend origin for browser access. Requests use Authorization bearer tokens, not automatic application cookies; standard cookie-based CSRF does not apply. CORS is not authentication. Auth SDK credentials are stored by Supabase's standard browser session mechanism, making XSS protection and CSP important. Application idle logout is a UI control; Supabase server-side session controls and RLS/active checks provide enforcement. Configure Auth sign-in/reset throttling; authenticated API and AI/invitation routes have database-backed limits.

## AI and personnel decisions

Only an administrator can send a submitted editor snapshot to the configured AI provider. Never put secrets or sensitive health records into those documents. Prompt instructions explicitly treat assignment and research text as untrusted content. The result is schema validated and escaped. Prompt injection can still influence model judgments, so reports are advisory and never mutate review decisions. Source verification is always Not Verified because no external retrieval occurs. Uploaded files are outside the AI review scope. Authorship indicators cannot establish AI use and cannot alone justify accusations, penalties or rejection. No authorship probability or employee ranking is computed.

## Production requirements / limitations

Live Supabase Auth, SMTP, Storage, Resend and AI provider credentials were unavailable. Local tests do not certify hosted behavior, deliverability or production security. Configure headers using the supplied generator; run real integration tests on staging. Review organization-specific legal/privacy obligations, retention, backups, MFA and malware scanning. No student mental-health data belongs in the demo, seed or test fixtures. Use a dedicated security review before processing sensitive operational data.
