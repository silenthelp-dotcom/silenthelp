"""
SilentHelp HQ — shared company store
====================================

Unlike the per-user on-device detection store, the HQ (careers / team /
founder admin) is *shared*: every visitor sees the same live company state —
open positions, the team directory, applicants moving through the pipeline,
and company-progress numbers.

Storage backend is chosen at import time:

  • If DATABASE_URL is set (e.g. Render Postgres), the whole HQ document is
    stored as a single JSONB row (table hq_state, id=1). This survives restarts
    and redeploys — the reason this module exists in DB form.
  • Otherwise it falls back to a local JSON file (silenthelp_hq.json), so local
    development needs no database.

Either way, all mutations go through _load()/_write() under one lock, so the
rest of the module (seed + mutation helpers) is backend-agnostic.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from datetime import date
from typing import Any, Dict, List

HQ_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "silenthelp_hq.json")
_LOCK = threading.RLock()
# Set on every write; SSE listeners wait on it to push live updates.
_rev_event = threading.Event()


def _hash_pw(pw: str) -> str:
    return hashlib.sha256(("shq::" + pw).encode("utf-8")).hexdigest()

# ---------------------------------------------------------------------------
# Storage backend selection
# ---------------------------------------------------------------------------
# Render hands us a postgres:// URL; SQLAlchemy/psycopg want postgresql://.
_DB_URL = os.environ.get("DATABASE_URL", "").strip()
if _DB_URL.startswith("postgres://"):
    _DB_URL = "postgresql://" + _DB_URL[len("postgres://"):]

_USE_DB = bool(_DB_URL)
_pool = None            # lazy psycopg connection pool when using Postgres
_db_error = None        # last DB error (surfaced in _meta so we can diagnose)


def _get_pool():
    """Lazily build a small psycopg connection pool. Imported only when a
    DATABASE_URL is configured, so local dev never needs psycopg installed."""
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool
        # sslmode=require for Render managed Postgres; harmless elsewhere.
        url = _DB_URL
        if "sslmode=" not in url:
            url += ("&" if "?" in url else "?") + "sslmode=require"
        # open=True (eager connect) is deprecated; open explicitly after build.
        pool = ConnectionPool(url, min_size=1, max_size=4,
                              kwargs={"autocommit": True}, open=False)
        pool.open(wait=True, timeout=15)
        with pool.connection() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS hq_state ("
                "  id INT PRIMARY KEY DEFAULT 1,"
                "  data JSONB NOT NULL,"
                "  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        _pool = pool
    return _pool

TEAM_TARGET = 10
DEPTS = [
    "Executive", "Engineering", "Artificial Intelligence", "Product", "Design",
    "Privacy & Compliance", "Community Outreach", "Marketing", "Research",
]
STAGES = [
    "Applied", "Under Review", "Interview Scheduled",
    "Technical Assessment", "Final Interview", "Offer Extended", "Hired",
]


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _seed() -> Dict[str, Any]:
    return {
        "stats": {"activeProjects": 4, "ai": 72, "macos": 55, "beta": 48, "outreach": 30},
        "positions": [
            {"id": "cto", "title": "Chief Technology Officer", "dept": "Executive",
             "type": "Founding team · Equity", "loc": "Remote / Hybrid", "status": "open",
             "desc": "Own SilentHelp's technical vision — the on-device detection engine, the macOS agent, and the path from prototype to product.",
             "resp": ["Set the technical roadmap from Flask prototype to native macOS product", "Own the 4-layer detection architecture (keyword → semantic → behavioral → trend)", "Make the on-device privacy guarantee real in every technical decision", "Recruit and lead the engineering team"],
             "skills": ["Systems architecture", "Python + Swift", "ML fundamentals", "Shipping under constraints"],
             "pref": ["Has built and shipped a real product", "Cares about mental-health tech"],
             "tech": ["Swift / ScreenCaptureKit", "Flask", "NVIDIA NIM", "Vision OCR"],
             "projects": ["macOS agent v2", "Detection engine hardening"], "team": "Works directly with the founder"},
            {"id": "ai-lead", "title": "Lead AI Engineer", "dept": "Artificial Intelligence",
             "type": "Founding team · Equity", "loc": "Remote", "status": "open",
             "desc": "Make the semantic layer smart enough to catch what keywords miss — and small enough to run fully on-device.",
             "resp": ["Own Layer 2 (semantic classification) and its move from cloud NIM to a local model", "Tune precision so alerts fire when they matter and never when they don't", "Design evaluation sets for crisis-language detection", "Keep every inference on-device in production"],
             "skills": ["NLP / transformers", "Model distillation & quantization", "Python", "Eval design"],
             "pref": ["Experience with on-device ML (CoreML, ONNX)", "Read papers for fun"],
             "tech": ["CoreML", "ONNX Runtime", "NVIDIA NIM", "PyTorch"],
             "projects": ["Local semantic model", "Tier-3 precision pass"], "team": "AI team · reports to CTO"},
            {"id": "fullstack", "title": "Full Stack Engineer", "dept": "Engineering",
             "type": "Core team · Equity", "loc": "Remote", "status": "open",
             "desc": "Build the product surface — dashboard, coping chat, analytics — on a backend that never sees user text.",
             "resp": ["Ship features across the Flask backend and web app", "Own the API contract (/classify, /api/chat, /api/behavioral…)", "Build the analytics and findings views", "Keep the data model strictly on-device"],
             "skills": ["Python / Flask", "Vanilla JS or a framework", "REST API design", "SQL / JSON stores"],
             "pref": ["Has deployed something real (Render, Vercel…)"],
             "tech": ["Flask", "Vanilla JS", "Render"],
             "projects": ["Web app v2", "Findings redesign"], "team": "Engineering"},
            {"id": "designer", "title": "UI/UX Designer", "dept": "Design", "status": "open",
             "type": "Core team · Equity", "loc": "Remote",
             "desc": "Design calm. SilentHelp appears at someone's worst moment — every screen has to feel like a hand on the shoulder, not an alarm.",
             "resp": ["Own the design language (Playfair + Inter, light product UI)", "Design the escalation and popup flows with care", "Prototype in Figma or claude.ai/design", "Run the design system as the team grows"],
             "skills": ["Product design", "Typography & hierarchy", "Prototyping", "Empathy"],
             "pref": ["Interest in crisis UX / calm technology"],
             "tech": ["Figma", "claude.ai/design", "CSS"],
             "projects": ["Escalation flow v2", "Design system"], "team": "Design · works with founder + engineering"},
            {"id": "pm", "title": "Product Manager", "dept": "Product", "status": "open",
             "type": "Core team · Equity", "loc": "Remote / Hybrid",
             "desc": "Decide what we build next and why — balancing student needs, school requirements, and a hard privacy line.",
             "resp": ["Own the roadmap from prototype to school beta", "Talk to students, counselors, and administrators", "Write specs the team can build from", "Define success metrics that respect privacy"],
             "skills": ["Prioritization", "User interviews", "Clear writing", "Scrappiness"],
             "pref": ["Knows the school-counseling world"],
             "tech": ["Linear-style tracking", "Docs"],
             "projects": ["School beta plan", "Onboarding v2"], "team": "Product · everyone"},
            {"id": "privacy", "title": "Privacy & Compliance Director", "dept": "Privacy & Compliance", "status": "open",
             "type": "Advisory · Equity", "loc": "Remote",
             "desc": "Our whole promise is that data never leaves the device. Prove it, document it, and keep us honest as we enter schools.",
             "resp": ["Own the privacy architecture review", "Handle COPPA / FERPA questions for school deployments", "Write the plain-language privacy policy", "Audit every feature before it ships"],
             "skills": ["Privacy law basics", "Threat modeling", "Clear writing"],
             "pref": ["Background in ed-tech or health-tech compliance"],
             "tech": ["—"], "projects": ["School compliance pack"], "team": "Reports to founder"},
            {"id": "community", "title": "Community Partnerships Lead", "dept": "Community Outreach", "status": "open",
             "type": "Core team", "loc": "Hybrid",
             "desc": "Get SilentHelp into the hands of schools, counselors, and community programs — starting with our own city.",
             "resp": ["Build relationships with schools and counselors", "Run the pilot-program pipeline", "Represent SilentHelp at community events", "Collect feedback loops from partners"],
             "skills": ["Communication", "Organization", "Persistence"],
             "pref": ["Connected to local school community"],
             "tech": ["—"], "projects": ["City pilot", "Counselor advisory board"], "team": "Outreach"},
            {"id": "marketing", "title": "Marketing Director", "dept": "Marketing", "status": "open",
             "type": "Core team", "loc": "Remote",
             "desc": "Tell the story of technology that notices — without ever exploiting the pain it exists to catch.",
             "resp": ["Own brand voice and the public site", "Launch content for the school beta", "Handle press and social presence", "Keep marketing as ethical as the product"],
             "skills": ["Copywriting", "Social strategy", "Basic design"],
             "pref": ["Portfolio of real campaigns, any size"],
             "tech": ["—"], "projects": ["Beta launch campaign"], "team": "Marketing · works with design"},
            # ---- expanded scale ----
            {"id": "coo", "title": "Chief Operating Officer", "dept": "Executive", "status": "open",
             "type": "Founding team · Equity", "loc": "Remote / Hybrid",
             "desc": "Run the company day-to-day so the founder can build. Own operations, hiring, and the path to a real organization.",
             "resp": ["Own hiring and onboarding across every team", "Build the operating cadence (sprints, standups, reviews)", "Manage budget, tooling, and vendor relationships", "Turn the vision into an executable plan"],
             "skills": ["Operations", "People management", "Planning", "Systems thinking"],
             "pref": ["Has scaled a small team before"],
             "tech": ["Notion / Linear", "Spreadsheets"], "projects": ["Operating system", "Hiring pipeline"], "team": "Partners with the CEO"},
            {"id": "ios-eng", "title": "iOS / macOS Engineer", "dept": "Engineering", "status": "open",
             "type": "Core team · Equity", "loc": "Remote",
             "desc": "Own the native macOS agent — the piece that quietly watches for the signals a browser never can.",
             "resp": ["Own the SwiftUI menu-bar agent", "Work with ScreenCaptureKit + Vision OCR", "Keep every capture on-device", "Ship signed, notarized builds"],
             "skills": ["Swift / SwiftUI", "macOS APIs", "Accessibility API", "Codesigning"],
             "pref": ["Has shipped a Mac app"],
             "tech": ["Swift", "ScreenCaptureKit", "Vision"], "projects": ["macOS agent v2"], "team": "Engineering · with CTO"},
            {"id": "backend-eng", "title": "Backend Engineer", "dept": "Engineering", "status": "open",
             "type": "Core team · Equity", "loc": "Remote",
             "desc": "Own the server, the data model, and the APIs — on a backend designed to never see user text.",
             "resp": ["Own the Flask backend and its API contract", "Design the on-device-first data model", "Own deployments and reliability", "Keep the privacy boundary airtight"],
             "skills": ["Python", "Flask / FastAPI", "Postgres", "API design"],
             "pref": ["Cares about privacy engineering"],
             "tech": ["Flask", "Postgres", "Render"], "projects": ["HQ platform", "API v2"], "team": "Engineering"},
            {"id": "ml-research", "title": "ML Research Engineer", "dept": "Research", "status": "open",
             "type": "Core team · Equity", "loc": "Remote",
             "desc": "Push the science of catching crisis signals earlier — behavioral models, trend detection, honest evaluation.",
             "resp": ["Research behavioral (Layer 3) signals", "Design the trend-gate (Layer 4) methodology", "Build honest, bias-aware evaluation sets", "Publish what's safe to publish"],
             "skills": ["ML research", "Statistics", "Python", "Careful evaluation"],
             "pref": ["Research or strong self-study background"],
             "tech": ["PyTorch", "NumPy"], "projects": ["Behavioral model", "Trend gate"], "team": "Research · with AI lead"},
            {"id": "data-analyst", "title": "Data Analyst", "dept": "Research", "status": "open",
             "type": "Part-time · Equity", "loc": "Remote",
             "desc": "Turn on-device, privacy-safe aggregates into the insights that guide the product — without ever touching raw text.",
             "resp": ["Define privacy-safe metrics", "Build the analytics that inform the roadmap", "Validate detection precision/recall", "Report honestly, including bad news"],
             "skills": ["SQL", "Statistics", "Data viz", "Skepticism"],
             "pref": ["Interest in health / behavioral data"],
             "tech": ["SQL", "Python", "Charts"], "projects": ["Metrics layer"], "team": "Research"},
            {"id": "clinical-advisor", "title": "Clinical Advisor (Counselor)", "dept": "Privacy & Compliance", "status": "open",
             "type": "Advisory", "loc": "Remote",
             "desc": "Keep us clinically honest. Every escalation, every message, every threshold gets a counselor's eyes before students see it.",
             "resp": ["Review detection thresholds and copy", "Advise on escalation and safety flows", "Guardrail against harm", "Bridge to the school-counseling world"],
             "skills": ["School counseling / clinical background", "Crisis response", "Judgment"],
             "pref": ["Licensed counselor or social worker"],
             "tech": ["—"], "projects": ["Safety review"], "team": "Advises founder + product"},
            {"id": "content-writer", "title": "Content & UX Writer", "dept": "Marketing", "status": "open",
             "type": "Part-time", "loc": "Remote",
             "desc": "Write the words that appear at someone's hardest moment — and the words that get schools to say yes.",
             "resp": ["Write in-product microcopy with care", "Own the blog and school-facing content", "Keep the voice calm and honest", "Never exploit the pain we exist to catch"],
             "skills": ["UX writing", "Content strategy", "Empathy"],
             "pref": ["Portfolio of writing, any kind"],
             "tech": ["Docs"], "projects": ["Voice guide", "School content"], "team": "Marketing · with design"},
            {"id": "growth", "title": "Growth & Partnerships Associate", "dept": "Community Outreach", "status": "open",
             "type": "Part-time", "loc": "Hybrid",
             "desc": "Open doors — to schools, districts, and community orgs — and keep the pilot pipeline full.",
             "resp": ["Source and qualify school pilots", "Support partnership conversations", "Run outreach experiments", "Track what actually converts"],
             "skills": ["Outreach", "Organization", "Communication"],
             "pref": ["Connected to a school community"],
             "tech": ["CRM / sheets"], "projects": ["Pilot pipeline"], "team": "Outreach"},
            {"id": "qa", "title": "QA / Test Engineer", "dept": "Engineering", "status": "open",
             "type": "Part-time · Equity", "loc": "Remote",
             "desc": "Make sure the thing that's supposed to catch a crisis never silently breaks.",
             "resp": ["Own the test suite across layers", "Build detection regression tests", "Catch failures before students do", "Guard the fail-safe-upward behavior"],
             "skills": ["Testing", "Python", "Attention to detail"],
             "pref": ["Cares about reliability of safety-critical code"],
             "tech": ["pytest", "CI"], "projects": ["Detection test harness"], "team": "Engineering"},
            {"id": "brand-designer", "title": "Brand / Visual Designer", "dept": "Design", "status": "open",
             "type": "Part-time", "loc": "Remote",
             "desc": "Give SilentHelp a face that feels trustworthy to a scared 15-year-old and credible to a school board.",
             "resp": ["Own brand identity and visual system", "Design the marketing site and decks", "Create calm, non-clinical imagery", "Keep it consistent everywhere"],
             "skills": ["Visual design", "Brand", "Illustration"],
             "pref": ["Strong portfolio"],
             "tech": ["Figma", "Illustrator"], "projects": ["Brand system"], "team": "Design"},
        ],
        "team": [
            {"id": "sree", "name": "Sree Lakkaraju", "role": "Founder & CEO", "dept": "Executive",
             "skills": ["Product vision", "Company strategy", "Leadership"],
             "projects": ["macOS agent", "Detection engine", "School pilot"],
             "progress": 80, "joined": "2026-05-01", "contact": "", "photo": "",
             "bio": "Founded SilentHelp to catch the signals people don't say out loud."},
        ],
        "applicants": [],
        "notes": [
            {"id": _uid(), "t": "SilentHelp HQ is live — shared across everyone who opens it.", "ts": int(time.time() * 1000), "read": False},
        ],
        "tasks": {},
        # HQ accounts (separate from product login): teammates sign up here and,
        # if their email matches a team member the founder added, they're linked
        # to that member and see their own assigned tasks.
        "accounts": {},   # accId -> {id, name, email, pw (sha256), memberId, ts}
        # Target headcount per department — powers the "filled vs open slots" view
        # and lets the team scale visibly beyond the current roster.
        "department_plan": {
            "Executive": 3, "Engineering": 6, "Artificial Intelligence": 3,
            "Product": 2, "Design": 3, "Privacy & Compliance": 2,
            "Community Outreach": 2, "Marketing": 3, "Research": 3,
        },
        "rev": 1,   # bumped on every write — clients poll/stream this for live updates
    }


def _load() -> Dict[str, Any]:
    """Read the current HQ document, seeding it on first use. Backend-agnostic.
    If the DB is configured but unreachable, log it and fall back to the local
    file so the site stays up (degraded to non-persistent) instead of 500ing."""
    global _db_error
    if _use_db():
        try:
            data = _db_load()
            _db_error = None
        except Exception as e:  # noqa: BLE001 — never let the site 500 on DB issues
            _db_error = f"{type(e).__name__}: {e}"
            print(f"[hq_store] DB read failed, using file fallback — {_db_error}", flush=True)
            data = _file_load()
    else:
        data = _file_load()

    if data is None:
        data = _seed()
        _write(data)
        return data
    seed = _seed()
    for k, v in seed.items():
        data.setdefault(k, v)
    return data


def _write(data: Dict[str, Any]) -> None:
    global _db_error, _rev_event
    # Bump the revision counter so live clients (poll / SSE) detect the change.
    data["rev"] = int(data.get("rev", 0)) + 1
    if _use_db():
        try:
            _db_write(data)
            _db_error = None
            _rev_event.set()  # wake any SSE listeners
            return
        except Exception as e:  # noqa: BLE001
            _db_error = f"{type(e).__name__}: {e}"
            print(f"[hq_store] DB write failed, using file fallback — {_db_error}", flush=True)
    _file_write(data)
    _rev_event.set()


def _use_db() -> bool:
    """Use Postgres only while it's healthy. After a hard failure we stick to
    the file for the rest of the process so we don't thrash on every request."""
    return _USE_DB and _db_error is None


# ---- file backend (local dev) ----

def _file_load() -> "Dict[str, Any] | None":
    if not os.path.exists(HQ_PATH):
        return None
    try:
        with open(HQ_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _file_write(data: Dict[str, Any]) -> None:
    tmp = HQ_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, HQ_PATH)


# ---- Postgres backend (Render, persistent across restarts) ----

def _db_load() -> "Dict[str, Any] | None":
    pool = _get_pool()
    with pool.connection() as conn:
        row = conn.execute("SELECT data FROM hq_state WHERE id = 1").fetchone()
    if not row:
        return None
    data = row[0]
    # psycopg returns JSONB as a dict already; be defensive if it's a string.
    return json.loads(data) if isinstance(data, str) else data


def _db_write(data: Dict[str, Any]) -> None:
    pool = _get_pool()
    payload = json.dumps(data, ensure_ascii=False)
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO hq_state (id, data, updated_at) VALUES (1, %s, now()) "
            "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()",
            (payload,),
        )


def state() -> Dict[str, Any]:
    with _LOCK:
        d = _load()
        d["_meta"] = {
            "target": TEAM_TARGET, "depts": DEPTS, "stages": STAGES,
            "backend": "postgres" if _use_db() else ("file (db-fallback)" if _USE_DB else "file"),
            "db_error": _db_error,
        }
        return d


# ---------- mutations ----------

def _now() -> int:
    return int(time.time() * 1000)


def add_applicant(a: Dict[str, Any]) -> Dict[str, Any]:
    with _LOCK:
        d = _load()
        a = dict(a)
        a["id"] = _uid()
        a["stage"] = "Applied"
        a["ts"] = _now()
        d["applicants"].append(a)
        d["notes"].insert(0, {"id": _uid(), "t": f"New applicant: {a.get('name','?')} → {a.get('role','?')}", "ts": _now(), "read": False})
        _write(d)
        return d


def set_stage(app_id: str, stage: str) -> Dict[str, Any]:
    with _LOCK:
        d = _load()
        for a in d["applicants"]:
            if a["id"] == app_id:
                a["stage"] = stage
                d["notes"].insert(0, {"id": _uid(), "t": f"{a.get('name','?')} moved to “{stage}”", "ts": _now(), "read": False})
                break
        _write(d)
        return d


def hire(app_id: str) -> Dict[str, Any]:
    with _LOCK:
        d = _load()
        a = next((x for x in d["applicants"] if x["id"] == app_id), None)
        if a:
            a["stage"] = "Hired"
            pos = next((p for p in d["positions"] if p["title"] == a.get("role")), None)
            d["team"].append({
                "id": _uid(), "name": a.get("name", ""), "role": a.get("role", ""),
                "dept": pos["dept"] if pos else "Engineering",
                "skills": [], "projects": (pos.get("projects", []) if pos else []),
                "progress": 0, "joined": date.today().isoformat(),
                "contact": a.get("email", ""), "photo": "", "bio": "",
            })
            if pos:
                pos["status"] = "filled"
            d["notes"].insert(0, {"id": _uid(), "t": f"🎉 {a.get('name','?')} hired as {a.get('role','?')} — welcome to the team!", "ts": _now(), "read": False})
        _write(d)
        return d


def save_position(p: Dict[str, Any], pid: str | None) -> Dict[str, Any]:
    with _LOCK:
        d = _load()
        if pid:
            existing = next((x for x in d["positions"] if x["id"] == pid), None)
            if existing:
                existing.update(p)
        else:
            p["id"] = _uid()
            p["status"] = "open"
            d["positions"].append(p)
            d["notes"].insert(0, {"id": _uid(), "t": f"New position opened: {p.get('title','?')}", "ts": _now(), "read": False})
        _write(d)
        return d


def toggle_position(pid: str) -> Dict[str, Any]:
    with _LOCK:
        d = _load()
        for p in d["positions"]:
            if p["id"] == pid:
                p["status"] = "filled" if p["status"] == "open" else "open"
                d["notes"].insert(0, {"id": _uid(), "t": f"Position {'reopened' if p['status']=='open' else 'filled'}: {p.get('title','?')}", "ts": _now(), "read": False})
                break
        _write(d)
        return d


def delete_position(pid: str) -> Dict[str, Any]:
    with _LOCK:
        d = _load()
        d["positions"] = [p for p in d["positions"] if p["id"] != pid]
        _write(d)
        return d


def save_member(m: Dict[str, Any], mid: str | None) -> Dict[str, Any]:
    with _LOCK:
        d = _load()
        if mid:
            existing = next((x for x in d["team"] if x["id"] == mid), None)
            if existing:
                existing.update(m)
                d["notes"].insert(0, {"id": _uid(), "t": f"{existing.get('name','?')}'s profile updated", "ts": _now(), "read": False})
        else:
            m["id"] = _uid()
            m.setdefault("photo", "")
            d["team"].append(m)
            d["notes"].insert(0, {"id": _uid(), "t": f"{m.get('name','?')} joined as {m.get('role','?')}", "ts": _now(), "read": False})
        _write(d)
        return d


def delete_member(mid: str) -> Dict[str, Any]:
    with _LOCK:
        d = _load()
        m = next((x for x in d["team"] if x["id"] == mid), None)
        d["team"] = [x for x in d["team"] if x["id"] != mid]
        d["tasks"].pop(mid, None)
        if m:
            d["notes"].insert(0, {"id": _uid(), "t": f"{m.get('name','?')} removed from the team directory", "ts": _now(), "read": False})
        _write(d)
        return d


def set_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
    with _LOCK:
        d = _load()
        d["stats"].update({k: v for k, v in stats.items() if k in d["stats"]})
        _write(d)
        return d


def add_task(mid: str, t: str, due: str) -> Dict[str, Any]:
    with _LOCK:
        d = _load()
        d["tasks"].setdefault(mid, []).append(
            {"id": _uid(), "t": t, "due": due, "done": False, "ts": _now()}
        )
        m = next((x for x in d["team"] if x["id"] == mid), None)
        if m:
            d["notes"].insert(0, {"id": _uid(), "t": f"Task assigned to {m.get('name','?')}: {t}", "ts": _now(), "read": False})
        _write(d)
        return d


def toggle_task(mid: str, idx: int) -> Dict[str, Any]:
    with _LOCK:
        d = _load()
        try:
            d["tasks"][mid][idx]["done"] = not d["tasks"][mid][idx]["done"]
        except (KeyError, IndexError):
            pass
        _write(d)
        return d


def toggle_task_by_id(mid: str, task_id: str) -> Dict[str, Any]:
    """Toggle a task by its stable id (used by the teammate 'My Tasks' view)."""
    with _LOCK:
        d = _load()
        for task in d["tasks"].get(mid, []):
            if task.get("id") == task_id:
                task["done"] = not task.get("done", False)
                break
        _write(d)
        return d


def delete_task(mid: str, task_id: str) -> Dict[str, Any]:
    with _LOCK:
        d = _load()
        d["tasks"][mid] = [x for x in d["tasks"].get(mid, []) if x.get("id") != task_id]
        _write(d)
        return d


def mark_notes_read() -> Dict[str, Any]:
    with _LOCK:
        d = _load()
        for n in d["notes"]:
            n["read"] = True
        _write(d)
        return d


# ---------------------------------------------------------------------------
# HQ accounts (teammate signup / login) — separate from product login.
# ---------------------------------------------------------------------------

def _member_for_email(d: Dict[str, Any], email: str) -> "str | None":
    email = (email or "").strip().lower()
    for m in d["team"]:
        if (m.get("contact") or "").strip().lower() == email:
            return m["id"]
    return None


def _account_public(acc: Dict[str, Any], d: Dict[str, Any]) -> Dict[str, Any]:
    """Account view safe to send to the client (no password), with linked member."""
    member = next((m for m in d["team"] if m["id"] == acc.get("memberId")), None)
    return {
        "id": acc["id"], "name": acc["name"], "email": acc["email"],
        "memberId": acc.get("memberId"),
        "member": member,
        "isFounder": bool(member and member.get("role", "").lower().startswith("founder")),
    }


def signup(name: str, email: str, pw: str) -> "Dict[str, Any] | None":
    name, email = (name or "").strip(), (email or "").strip().lower()
    if not name or not email or not pw or len(pw) < 4:
        return None
    with _LOCK:
        d = _load()
        if any(a["email"] == email for a in d["accounts"].values()):
            return {"error": "That email already has an account — log in instead."}
        acc_id = _uid()
        acc = {
            "id": acc_id, "name": name, "email": email, "pw": _hash_pw(pw),
            "memberId": _member_for_email(d, email), "ts": _now(),
        }
        d["accounts"][acc_id] = acc
        # Auto-claim: if the founder already added a member with this email, link
        # the account to it and adopt the account's real name.
        if acc["memberId"]:
            for m in d["team"]:
                if m["id"] == acc["memberId"] and not m.get("name"):
                    m["name"] = name
            d["notes"].insert(0, {"id": _uid(), "t": f"{name} claimed their teammate account", "ts": _now(), "read": False})
        else:
            d["notes"].insert(0, {"id": _uid(), "t": f"{name} signed up for HQ ({email})", "ts": _now(), "read": False})
        _write(d)
        return {"account": _account_public(acc, d)}


def login(email: str, pw: str) -> "Dict[str, Any] | None":
    email = (email or "").strip().lower()
    with _LOCK:
        d = _load()
        acc = next((a for a in d["accounts"].values() if a["email"] == email), None)
        if not acc or acc["pw"] != _hash_pw(pw):
            return None
        # Re-link on every login in case the founder added the member afterwards.
        if not acc.get("memberId"):
            acc["memberId"] = _member_for_email(d, email)
            if acc["memberId"]:
                _write(d)
        return {"account": _account_public(acc, d)}


def account(acc_id: str) -> "Dict[str, Any] | None":
    with _LOCK:
        d = _load()
        acc = d["accounts"].get(acc_id)
        if not acc:
            return None
        if not acc.get("memberId"):
            acc["memberId"] = _member_for_email(d, acc["email"])
        return _account_public(acc, d)


def set_plan(dept: str, target: int) -> Dict[str, Any]:
    with _LOCK:
        d = _load()
        d.setdefault("department_plan", {})[dept] = max(0, min(50, int(target)))
        _write(d)
        return d


def rev() -> int:
    with _LOCK:
        return int(_load().get("rev", 0))
