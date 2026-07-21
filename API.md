# SilentHelp — Backend API

Prototype Flask backend. Base URL `http://127.0.0.1:5055`. All JSON.
Run: `python3 app.py` (uses the framework Python; key auto-loads from `.env`).

> The model only **flags**; hard-coded code **decides**. A Layer-1 tier-3 hit
> bypasses everything and forces the crisis action (fail safe upward).

---

## Layers
- **L1 — keyword** (`layer1.py`, local, instant): regex from `layer1_db/level{1,2,3}*.json`.
- **L2 — semantic** (`detection.py`, NIM cloud): classifier, fails safe to HIGH.
- **L3 — behavioral** (`behavioral.py`, local): rule-based scores vs baseline.
- **L4 — trend gate**: front-end accumulates strained checks; gate at streak ≥ 4.
  Tier-3 / crisis bypasses the gate.

---

## Endpoints

### POST /api/scan  — Layer 1 only (fast, local, no AI)
Req: `{ "text": "..." }`
Res: `{ "tier3": bool, "matched": bool, "categories": [str], "hits": [{ "phrase", "category", "tier" }] }`

### POST /classify  — L1 + L2 + decision
Req: `{ "message": "..." }`
Res: `{ "judgment": { risk_level, categories[], confidence, rationale, _source, _l1_tier3? },
        "action":   { risk_level, action, resources[], route_to_human, dismissible, message },
        "l1":       { tier3, matched, categories[], hits[] } }`
- `risk_level`: none | low | moderate | high | crisis
- L1 tier-3 → `action` is the crisis action even if `judgment.risk_level` is lower.

### POST /api/chat  — coping chat turn (reply + same detection)
Req: `{ "message": "...", "messages": [ { "role": "user"|"assistant", "content": "..." } ] }`
Res: `{ "reply": str, "judgment": {...}, "action": {...}, "l1": {...} }`
- `action.resources` is populated when `route_to_human` is true → show resource card.

### POST /api/behavioral  — L3 scores (no text read)
Req (any subset; missing keys default to baseline):
`{ tab_switches, late_night_min, avg_session_min, interruptions, backspace_rate }`
Res: `{ mental_battery (0-100), focus_score (0-100), burnout_risk (0-100),
        status, deltas: [{label, pct}], suggestions: [str], trend: [int x7] }`
Baseline: tab_switches 25/hr · late_night 15min · avg_session 50min · interruptions 10/hr · backspace_rate 0.10

### POST /api/escalation/draft  — build counselor email (NOT sending)
Req: `{ "contact"?: "..." }`  Res: `{ contact, subject, body }`

### POST /api/escalation/send  — user explicitly sends (mock)
Req: `{ "contact": "..." }`  Res: `{ sent: true, contact }`
> Nothing is ever sent automatically. The UI must require an explicit send.

---

## Action shapes by level (from `detection.decide_response`)
| level | action | route_to_human | dismissible | resources |
|-------|--------|----------------|-------------|-----------|
| crisis | show_crisis_resources | true | **false** | yes |
| high | show_crisis_resources_with_support_prompt | true | true | yes |
| moderate | gentle_nudge | false | true | no |
| low | supportive_nudge | false | true | no |
| none | none | false | true | no |
