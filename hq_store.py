"""
SilentHelp HQ — shared company store
====================================

Unlike the per-user on-device detection store, the HQ (careers / team /
founder admin) is *shared*: every visitor sees the same live company state —
open positions, the team directory, applicants moving through the pipeline,
and company-progress numbers.

Backed by a single JSON file (silenthelp_hq.json). Thread-safe for the Flask
dev server and a single gunicorn worker (one lock around read-modify-write).
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import date
from typing import Any, Dict, List

HQ_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "silenthelp_hq.json")
_LOCK = threading.RLock()

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
    }


def _load() -> Dict[str, Any]:
    if not os.path.exists(HQ_PATH):
        data = _seed()
        _write(data)
        return data
    try:
        with open(HQ_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        data = _seed()
        _write(data)
        return data
    # Guarantee shape for older files.
    seed = _seed()
    for k, v in seed.items():
        data.setdefault(k, v)
    return data


def _write(data: Dict[str, Any]) -> None:
    tmp = HQ_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, HQ_PATH)


def state() -> Dict[str, Any]:
    with _LOCK:
        d = _load()
        d["_meta"] = {"target": TEAM_TARGET, "depts": DEPTS, "stages": STAGES}
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
        d["tasks"].setdefault(mid, []).append({"t": t, "due": due, "done": False})
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


def mark_notes_read() -> Dict[str, Any]:
    with _LOCK:
        d = _load()
        for n in d["notes"]:
            n["read"] = True
        _write(d)
        return d
