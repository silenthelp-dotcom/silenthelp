# SilentHelp — Codebase Context (for humans and AI tools)

SilentHelp is a privacy-first digital-wellness app for students. It notices early
signals of burnout, stress, isolation, and crisis in what a student writes and how
they use their device, understands **context** (jokes/idioms never trigger; genuine
self-directed distress always does), and responds in proportion — from a gentle
check-in to a user-approved email to a trusted adult. Live at **https://silenthelp.org**
(Render; repo auto-deploys on push to `main`).

**Core design rule: the AI model only FLAGS; deterministic code DECIDES.**
**Second rule: the semantic layer decides severity; keywords only find candidates fast.**

## Architecture in one paragraph

Text enters from three places: the web Coping Chat, the web live monitor, or the
native macOS agent (reads the focused text field via Accessibility + OCRs the
frontmost window via ScreenCaptureKit/Vision). Every path runs the same pipeline in
`app.py:_pipeline()`: Layer 1 (`layer1.py`, local regex over `layer1_blocks.json`)
finds candidates in ~15 ms — an explicit tier-3 crisis phrase short-circuits to an
instant crisis verdict; anything softer goes to Layer 2 (`detection.py`, Groq
`openai/gpt-oss-120b`) which reads intent and returns the final severity
(none/low/moderate/high/crisis). `decide_response()` (hard-coded) maps severity to
an action; a `surface` field (urgent/gentle/none) sets popup policy — background
monitoring only interrupts for moderate+. Layer 3 (`behavioral.py`) scores rhythm
signals (tab switches, typing corrections, late nights) against a baseline — reads
no text. Layer 4 (`store.py:gating()`) only escalates when a pattern persists
across days. Every user has an isolated data file; sessions are Flask signed
cookies; anonymous remote visitors get 401s on personal APIs and a sign-up gate.

## File-by-file

### Backend (Python / Flask)

- **`app.py`** — The server. Everything routes through here.
  - `_load_local_env()` reads `.env` (GROQ_API_KEY, SECRET_KEY, SILENTHELP_OWNER, SMTP_*).
  - `ProxyFix` trusts X-Forwarded-* (Render/Cloudflare) so redirects keep the real host.
  - `_bind_user_store()` (before_request): binds `store` to `userdata/user_<uid>.json`
    for the session user; anonymous LOCAL traffic (the Mac agent, no cookies) is
    attributed to the owner account (`_owner_uid()`, `SILENTHELP_OWNER` env); anonymous
    REMOTE traffic gets 401 on any `/api/*` not in `_PUBLIC_PATHS`.
  - `_pipeline(message, record)` — the detection authority described above. Returns
    `(l1, judgment, action)`; `judgment.surface` ∈ urgent/gentle/none is the popup policy.
  - Auth: `/api/signup`, `/api/login`, `/api/logout`, `/api/me` (local owner appears
    signed-in with `via: "local"`), `/api/account/delete` (wipes account + data, frees email).
  - Detection: `/classify` (stateless), `/api/scan` (Layer-1 only, instant), `/api/monitor`
    (full pipeline; PUBLIC so friends' agents work, but records nothing for anonymous).
  - Chat: `/api/chat` runs the supportive reply (`chat.py`) and detection IN PARALLEL
    (ThreadPoolExecutor).
  - Data: `/api/state`, `/api/dashboard`, `/api/analytics`, `/api/findings`,
    `/api/behavioral/log`, `/api/gating`, `/api/moments`, `/api/status`, `/api/export`,
    `/api/wipe`, `/api/reset-baseline`, `/api/settings`.
  - Escalation: `/api/escalation/draft` (builds counselor email), `/api/escalation/send`
    (real SMTP if SMTP_* env set, else client falls back to mailto). Never auto-sends.
  - Pages: `/` (hero), `/app` (SPA), `/privacy`, `/terms`, `/robots.txt`, `/sitemap.xml`,
    `/download/agent` (serves `dist/SilentHelpAgent.zip`), `/chat` → 302 `/app#chat`
    (RELATIVE redirect — absolute would send visitors to 127.0.0.1).

- **`layer1.py`** — Layer 1 keyword engine. No AI. Compiles once at import from the
  three `layer1_db/level*.json` databases: each ships pre-built `regex_templates`
  (full contextual sentences — `<starter> <modifier> <state> <context> <time>`) plus
  `exact_high_precision_phrases`. **Context guard**: `_BENIGN_RE` (idioms —
  "dying laughing", "phone is dead", "suicide squad", "cut myself a slice"…) discards
  overlapping hits; `_LAUGH_RE` markers (lol/lmao/😂/💀/jk…) suppress `_HYPERBOLE`
  phrases ("im dead", "i want to die"…) only within `_JOKE_RADIUS` (60 chars) of the
  hit; `_ALWAYS_SERIOUS_RE` (kill myself, kms, unalive, self harm…) can never be
  suppressed. Also keeps two nets the database does not cover: a spelling-tolerant
  fuzzy pass over ~40 core emotion words ("depresed", "alon") and `_RECEIVED_THREAT_RE`
  (bullying aimed AT the user). Normalizes curly quotes (OCR produces `can’t`),
  lowercases, and collapses whitespace, per each database's `matching.normalization`.
  `scan(text)` returns `{tier3, matched, categories, hits[{phrase,category,tier}],
  level 0-4, level_name, joking_context, received_threat}`. Severity: everyday_stress=1,
  major_stress=2, received_threat=3, crisis=4. Highest wins.

- **`layer1_db/level1_everyday_stress.json`**, **`level2_major_stress.json`**,
  **`level3_crisis.json`** — The keyword database (schema `4.0.0-regex`). Each file
  carries its `components` (the raw slot word-lists), the compiled `regex_templates`,
  and `exact_high_precision_phrases`. Together ~855M theoretical phrase combinations
  across 8 templates. Only level 3 sets `bypasses_four_day_trend_gate` — a single
  crisis hit skips Layer 4. Because every template requires a full contextual
  sentence, bare words that fire on everyday speech can never match on their own.

- **`build_layer1_db.py`** — Generator for `layer1_db/`. Edit the component lists at
  the top and re-run (`python3 build_layer1_db.py`); `layer1.py` picks up the new
  vocabulary on its next import.

- **`detection.py`** — Layer 2, the decider. `classify_message(text)` calls Groq
  (`https://api.groq.com/openai/v1`, model `openai/gpt-oss-120b`, temp 0, timeout 8s,
  1 retry) with `CLASSIFIER_SYSTEM_PROMPT` — includes intent-vs-idiom rules and
  calibration examples (trampoline→none, "killing me"+joke→none, "kill myself lol"→crisis,
  "i am so stressed"→low). Fails SAFE to "high" on any error. `decide_response(judgment)`
  is pure hard-coded mapping → action dict with `route_to_human`, `dismissible`,
  `resources` (988 / Crisis Text Line constants), message. Test harness at bottom
  (`python3 detection.py`).

- **`behavioral.py`** — Layer 3 scoring. Pure math, reads no text. Baselines
  (tab_switches 25/hr, late_night 15m, session 50m, interruptions 10/hr, backspace 10%).
  `compute_metrics(signals)` → mental_battery, focus_score, burnout_risk, status,
  suggestions. **Confidence ramp**: penalties scale by `min(1, active_minutes/45)` so
  a few minutes of noisy data can't crash the battery (was the 100→57 whiplash bug).
  Marathon signal: 2h+ unbroken session / 4h+ active adds burnout.

- **`store.py`** — Per-user persistence. One JSON file per user
  (`userdata/user_<uid>.json`), selected per-request via thread-local
  `set_data_file()`; falls back to shared `silenthelp_data.json` (anonymous local).
  Holds settings (name, trusted contact, 4 layer toggles), days (behavioral),
  events (category+level+timestamp ONLY — never raw text), chat history (last 200),
  trend_streak. `gating()` = Layer 4: urgent if recent crisis event OR layers {1,2,3}
  all fired with streak ≥ 4 days; gentle for lighter patterns. `dashboard()/analytics()/
  findings()` feed the UI; `seeded: true` flags sample data (UI shows SAMPLE PREVIEW
  badge). `wipe()`, `reset_baseline()`, `export()`.

- **`auth.py`** — Accounts. `users.json` (gitignored): email, name, salt,
  PBKDF2-SHA256(200k) hash. `signup/login/get_user/delete_user`. Sessions are Flask
  signed cookies set in app.py (`session["uid"]`).

- **`chat.py`** — Coping-chat reply generation (same Groq client). Warm 1-3 sentence
  support persona; never a therapist; crisis-safe fallback line if the model is
  unreachable. Safety routing does NOT happen here — app.py runs detection in parallel.

- **`hq_store.py` + `silenthelp_hq.json` + `templates/careers.html`** — "HQ": shared
  company site data (careers/team/founder admin) — intentionally NOT per-user;
  `/api/hq*` is public. Uses Postgres if DATABASE_URL is set, else the JSON file.

- **`_legacy/`** — Retired v2 keyword database (`layer1_blocks.json`) and its
  generator, superseded by `layer1_db/`. Kept for reference only; nothing imports it.

### Native macOS agent (Swift)

- **`SilentHelpAgent/Sources/SilentHelpAgent/main.swift`** — Menu-bar accessory app
  (🟢 SH = all good, 🟡 = Screen Recording missing, 🔴 = Accessibility missing,
  💤 = snoozed). Backend resolution at launch: config-file override →
  localhost:5055 if alive (owner's private setup) → https://silenthelp.org →
  https://silenthelp.onrender.com. Three monitors:
  - `Monitor` (Accessibility): reads the focused text field every 1.5s → `/api/monitor`
    → pops per `judgment.surface`.
  - `ScreenReader` (ScreenCaptureKit + Vision OCR): captures the FRONTMOST WINDOW
    every 1.2s (downscaled to 1500px), OCRs it → `/api/scan`; explicit tier-3 pops
    instantly; softer candidates go to `/api/monitor` for the context verdict.
    Skips its own UI and the SilentHelp web app's screen (feedback-loop guard). Never
    attempts capture without permission (attempting while denied re-spams the macOS
    permission dialog). 15s popup cooldown, 40s same-phrase window; crisis bypasses.
  - `Behavioral`: counts keystrokes (codes only, never characters), backspaces, app
    switches, late-night minutes → `/api/behavioral/log` every 45s.
  - `Popup`: borderless NSPanel above full-screen apps; buttons: Talk it through
    (opens the HOSTED app's /chat — never localhost), Ignore 1h / 2h (Snooze), Dismiss.
  - Translocation guard: if launched from a quarantine path (unzipped in Downloads),
    tells the user to move it to /Applications instead of failing silently.
  - Logs to `/tmp/silenthelp-agent.log`.

- **`SilentHelpAgent/make-app.sh`** — Builds release, wraps in SilentHelpAgent.app
  with a STABLE code-signing identity ("SilentHelp Dev") so macOS permissions survive
  rebuilds, packages `dist/SilentHelpAgent.zip`.
- **`SilentHelpAgent/Package.swift`** — SwiftPM manifest (macOS 14+).

### Frontend (server-rendered static HTML, no framework)

- **`templates/hero.html`** — Landing page (silenthelp.org). SEO meta/OG tags,
  canonical, favicon. Pure static.
- **`templates/app.html`** — The entire SPA (~2,400 lines: markup + one `App` JS
  object). Screens: sign-in gate (`scr-auth`, shown first for anonymous visitors),
  3-step onboarding, Dashboard (mental-battery orb, live readings), Analytics,
  Findings, Moments, Coping Chat, Connection (agent install steps + status +
  popup previews), Settings (layer toggles, trusted contact, privacy explainer,
  export/delete), Account (profile, sign in/out, DANGER ZONE delete account).
  Popups: gentle check-in + full-screen urgent with an editable escalation email
  draft. Snooze (1h/2h) persisted in localStorage; dismissed popups stay dismissed
  until a NEW detection. `api()` helper: any 401 routes to the sign-in gate.
  White "liquid glass" button style (`.glass`).
- **`templates/privacy.html` / `terms.html`** — Standalone legal pages (also linked
  from the sign-up gate).
- **`templates/detection.html`, `today.html`, `chat.html`, `base.html`** — Older
  standalone demo pages (Layer-2 tester, behavioral sliders); kept for reference.
- **`static/silenthelp.css`** — Styles for those older pages.

### Deploy / ops

- **`render.yaml`** — Render blueprint: free web service, gunicorn 1 worker,
  GROQ_API_KEY (dashboard-set), SECRET_KEY (generated), Python 3.12.7.
- **`Procfile`, `requirements.txt`** — flask, openai, gunicorn.
- **`run.sh`** — Local dev: starts backend + builds/launches the agent.
- **`share.sh` / `watchdog.sh`** — Legacy Cloudflare quick-tunnel sharing with
  self-healing watchdog (superseded by the Render deploy; kept for offline demos).
- **`API.md`** — Endpoint reference (may lag the code; app.py is the truth).
- **`.gitignore`** — Excludes `.env` (GROQ_API_KEY etc.), `users.json`, `userdata/`,
  `silenthelp_data.json`, build dirs. NEVER commit these.

### Not in git (by design)

- **`.env`** — GROQ_API_KEY, SECRET_KEY, SILENTHELP_OWNER, optional SMTP_* creds.
- **`users.json`, `userdata/`, `silenthelp_data.json`** — real accounts + personal data.

## Invariants an AI editing this code must preserve

1. Raw message text is NEVER persisted in events — categories/levels/timestamps only.
2. The model flags; `decide_response()` and the gating code decide. Don't let model
   output pick actions directly.
3. Layer-2 failure fails SAFE (high), never silent none.
4. Explicit self-directed crisis phrases (`_ALWAYS_SERIOUS_RE`) can never be
   suppressed by joke context.
5. Nothing is ever emailed/escalated without the user pressing send.
6. Per-user isolation: no endpoint may serve one user's data to another; anonymous
   remote = 401 on personal APIs.
7. Popup policy: background monitoring interrupts only for moderate+; crisis is
   instant and bypasses cooldowns/snooze (web urgent) by design.
8. The agent must never attempt screen capture without permission (dialog spam).
