"""
SilentHelp — On-device store
============================

Single local JSON file (silenthelp_data.json next to this module) that holds
everything the app remembers: settings, per-day behavioral metrics, detection
events (categories/levels only — never raw text), chat history, and the trend
streak that drives Layer-4 gating.

This is the "stays on your Mac" promise made concrete: nothing here is ever
transmitted; the file lives beside the app. Thread-safe enough for the Flask
dev server (single lock around read-modify-write).
"""

from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

import behavioral

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "silenthelp_data.json")
# Reentrant: some readers (e.g. findings) call other locked helpers (analytics).
_LOCK = threading.RLock()

# Per-user data file, bound per request (thread-local). Falls back to the shared
# anonymous file when no one is signed in.
_local = threading.local()


def set_data_file(path: "str | None") -> None:
    _local.path = path


def _data_path() -> str:
    return getattr(_local, "path", None) or DATA_PATH

DEFAULTS: Dict[str, Any] = {
    "settings": {
        "name": "",
        "contact": "School Counselor <counselor@school.edu>",
        "onboarded": False,
        "toggles": {"keyword": True, "semantic": True, "behavioral": True, "trend": True},
        # How aggressively detections interrupt the user.
        #   "balanced" (default) — crisis/high → urgent popup, moderate → gentle
        #                          popup, low → detected + logged silently, feeding
        #                          the trend graph without interrupting.
        #   "everything"        — EVERY detection pops up, including everyday
        #                          stress ("i'm tired from studying"). Nothing is
        #                          detected that wasn't detected before; this only
        #                          changes what interrupts. Expect frequent popups
        #                          during normal use.
        "popup_policy": "balanced",
    },
    "days": {},        # "YYYY-MM-DD" -> {signals, metrics}
    "events": [],      # {ts, layer:int, level:str, category:str}  (no raw text)
    "chat": [],        # active conversation: {role, content, ts}
    "chat_threads": [],  # archived conversations: {id, title, messages, ts}
    "trend_streak": 0,
}

_LEVEL_ORDER = {"none": 0, "low": 1, "moderate": 2, "high": 3, "crisis": 4}


def _today() -> str:
    return date.today().isoformat()


def _load() -> Dict[str, Any]:
    if not os.path.exists(_data_path()):
        return json.loads(json.dumps(DEFAULTS))
    try:
        with open(_data_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(DEFAULTS))
    # backfill any missing top-level keys
    for k, v in DEFAULTS.items():
        data.setdefault(k, json.loads(json.dumps(v)))
    return data


def _save(data: Dict[str, Any]) -> None:
    tmp = _data_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _data_path())


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_settings() -> Dict[str, Any]:
    with _LOCK:
        return _load()["settings"]


def update_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    with _LOCK:
        data = _load()
        s = data["settings"]
        for key, value in patch.items():
            if key == "toggles" and isinstance(value, dict):
                s["toggles"].update({k: bool(v) for k, v in value.items()})
            elif key in ("name", "contact"):
                s[key] = str(value)
            elif key == "onboarded":
                s["onboarded"] = bool(value)
            elif key == "popup_policy":
                # Unknown values fall back to "balanced" rather than silently
                # disabling popups entirely.
                s["popup_policy"] = (
                    "everything" if str(value) == "everything" else "balanced"
                )
        _save(data)
        return s


# ---------------------------------------------------------------------------
# Behavioral (Layer 3) — record a day, derive dashboard/analytics/findings
# ---------------------------------------------------------------------------

def record_behavioral(signals: Dict[str, Any]) -> Dict[str, Any]:
    """Compute today's metrics from real signals and persist them."""
    metrics = behavioral.compute_metrics(signals)
    with _LOCK:
        data = _load()
        data["days"][_today()] = {"signals": signals, "metrics": metrics}
        # Layer-3 event when strain is high (feeds gating; no text).
        if metrics["burnout_risk"] > 55:
            _append_event(data, layer=3, level="moderate", category="behavioral_strain")
        _recompute_streak(data)
        _save(data)
    return metrics


# Seed values match the design so a brand-new install still looks alive.
_SEED_DASH = {
    "mental_battery": 76, "focus_score": 84, "tab_switches": 42,
    "active_minutes": 312, "late_night_min": 18, "corrections": 9, "status": "Charged",
}


def dashboard() -> Dict[str, Any]:
    with _LOCK:
        data = _load()
        days = data["days"]
        today = days.get(_today())
        if not today:
            # No data yet → show the user's healthy baseline (real, not a demo).
            m = behavioral.compute_metrics(behavioral.BASELINE)
            return {
                "mental_battery": m["mental_battery"], "focus_score": m["focus_score"],
                "tab_switches": round(behavioral.BASELINE["tab_switches"]),
                "active_minutes": 0, "late_night_min": 0,
                "corrections": round(behavioral.BASELINE["backspace_rate"] * 100),
                "status": "Charged", "delta": 0, "burnout_risk": m["burnout_risk"],
                "suggestions": ["Your baseline is set — SilentHelp will learn your rhythm as you go."],
                "seeded": False,
            }
        m = today["metrics"]
        sig = today["signals"]

        # The battery is only meaningful once there's enough real activity to
        # measure. With just a few minutes logged, the extrapolated rates (a
        # couple of tab-switches over a tiny window) swing wildly, so the number
        # jumped up and down. Below a real threshold, hold the stable "learning"
        # state instead of showing a volatile computed value.
        MIN_ACTIVE_MIN = 20
        active_min = float(sig.get("active_minutes", 0))
        if active_min < MIN_ACTIVE_MIN:
            base = behavioral.compute_metrics(behavioral.BASELINE)
            return {
                "mental_battery": base["mental_battery"], "focus_score": base["focus_score"],
                "tab_switches": round(behavioral.BASELINE["tab_switches"]),
                "active_minutes": round(active_min), "late_night_min": round(float(sig.get("late_night_min", 0))),
                "corrections": round(behavioral.BASELINE["backspace_rate"] * 100),
                "status": "Charged", "delta": 0, "burnout_risk": base["burnout_risk"],
                "suggestions": [f"Still learning your rhythm — about {round(active_min)} of {MIN_ACTIVE_MIN} "
                                "minutes of activity measured today. Your reading settles once there's enough."],
                "learning": True, "seeded": False,
            }

        # delta vs the most recent previous day
        prev_keys = sorted(k for k in days if k < _today())
        delta = 0
        if prev_keys:
            delta = m["mental_battery"] - days[prev_keys[-1]]["metrics"]["mental_battery"]
        label = ("Charged" if m["mental_battery"] >= 67
                 else "Holding" if m["mental_battery"] >= 40 else "Low")
        return {
            "mental_battery": m["mental_battery"],
            "focus_score": m["focus_score"],
            "tab_switches": round(float(sig.get("tab_switches", 0))),
            "active_minutes": round(float(sig.get("active_minutes", 0))),
            "late_night_min": round(float(sig.get("late_night_min", 0))),
            "corrections": round(float(sig.get("backspace_rate", 0)) * 100),
            "status": label,
            "delta": delta,
            "burnout_risk": m["burnout_risk"],
            "suggestions": m["suggestions"],
            "seeded": False,
        }


def analytics() -> Dict[str, Any]:
    with _LOCK:
        data = _load()
        days = data["days"]
        # last 7 calendar days of focus
        trend: List[Any] = []
        for i in range(6, -1, -1):
            k = (date.today() - timedelta(days=i)).isoformat()
            trend.append(days[k]["metrics"]["focus_score"] if k in days else None)
        present = [v for v in trend if isinstance(v, (int, float))]
        # tab-switching bars (last 7 days)
        bars: List[Any] = []
        for i in range(6, -1, -1):
            k = (date.today() - timedelta(days=i)).isoformat()
            bars.append(round(float(days[k]["signals"].get("tab_switches", 0))) if k in days else None)

        # No real data yet → return an EMPTY state, not an invented curve. The
        # old code seeded a fake week (e.g. a Saturday trend) even when nothing
        # had been tracked, which read as made-up data. The UI shows an empty
        # state instead ("install the agent to start tracking").
        if not present:
            return {"trend": [], "bars": [], "baseline_tabs": 45,
                    "week_change": 0, "empty": True, "seeded": False}

        week_change = 0
        if len(present) >= 2:
            week_change = round((present[-1] - present[0]) / max(present[0], 1) * 100)
        return {"trend": trend, "bars": bars, "baseline_tabs": 45,
                "week_change": week_change, "empty": False, "seeded": False}


def findings() -> Dict[str, Any]:
    with _LOCK:
        data = _load()
        days = data["days"]
        last7 = []
        for i in range(6, -1, -1):
            k = (date.today() - timedelta(days=i)).isoformat()
            if k in days:
                last7.append(days[k]["metrics"])
        if not last7:  # seed to the design
            return {
                "avg_battery": 73, "avg_focus": 81, "deep_focus_h": 27, "late_nights": 3,
                "narrative": ("Your focus climbed nine percent — the steadiest stretch in "
                              "three weeks. A few late nights gathered midweek, then dissolved, "
                              "and by Friday your tab-switching had settled below its usual line."),
                "suggestions": [
                    {"title": "Protect your mornings", "body": "10–12 is your peak — guard it for deep work."},
                    {"title": "Wind down by eleven", "body": "A softer cutoff would steady your battery."},
                    {"title": "One screen at a time", "body": "Single-tasking kept your interruptions low."},
                ],
                "seeded": True,
            }
        avg_b = round(sum(m["mental_battery"] for m in last7) / len(last7))
        avg_f = round(sum(m["focus_score"] for m in last7) / len(last7))
        late = sum(1 for i in range(6, -1, -1)
                   if (date.today() - timedelta(days=i)).isoformat() in days
                   and float(days[(date.today() - timedelta(days=i)).isoformat()]["signals"].get("late_night_min", 0)) > 45)
        trend = analytics()["trend"]
        present = [v for v in trend if isinstance(v, (int, float))]
        change = round((present[-1] - present[0]) / max(present[0], 1) * 100) if len(present) >= 2 else 0
        direction = "climbed" if change >= 0 else "dipped"
        narrative = (f"Your focus {direction} {abs(change)} percent across the week. "
                     f"Your battery averaged {avg_b}%, and you logged "
                     f"{late} late night{'s' if late != 1 else ''}. "
                     "SilentHelp keeps watching the rhythm, not the words.")
        # pull suggestions from the worst recent day
        worst = min(last7, key=lambda m: m["mental_battery"])
        sugg = [{"title": s.split(" — ")[0][:40], "body": s} for s in worst["suggestions"][:3]]
        return {"avg_battery": avg_b, "avg_focus": avg_f, "deep_focus_h": len(last7) * 4,
                "late_nights": late, "narrative": narrative, "suggestions": sugg, "seeded": False}


# ---------------------------------------------------------------------------
# Events + Layer-4 trend gating
# ---------------------------------------------------------------------------

def _append_event(data: Dict[str, Any], layer: int, level: str, category: str) -> None:
    data["events"].append({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "layer": layer, "level": level, "category": category,
    })
    data["events"] = data["events"][-500:]  # cap


def record_event(layer: int, level: str, category: str) -> None:
    with _LOCK:
        data = _load()
        _append_event(data, layer, level, category)
        _recompute_streak(data)
        _save(data)


def crisis_count_24h() -> int:
    """How many separate crisis-level events in the last 24 hours.

    Drives auto-escalation: a single crisis message is not enough, but a
    repeated pattern within a day is. Counts events, not messages, so the same
    text re-scanned by the agent's polling loop does not inflate it — the
    pipeline records one event per distinct detection.
    """
    with _LOCK:
        data = _load()
        cutoff = datetime.now() - timedelta(hours=24)
        n = 0
        for e in data.get("events", []):
            if _LEVEL_ORDER.get(e.get("level"), 0) < 4:
                continue
            try:
                if datetime.fromisoformat(e["ts"]) >= cutoff:
                    n += 1
            except (ValueError, KeyError):
                continue
        return n


def mark_auto_sent() -> None:
    """Record that the automatic note went out, so it fires once per episode."""
    with _LOCK:
        data = _load()
        data["last_auto_send"] = datetime.now().isoformat()
        _save(data)


def auto_sent_recently(hours: int = 24) -> bool:
    """True if an automatic note already went out inside `hours`."""
    with _LOCK:
        ts = _load().get("last_auto_send")
    if not ts:
        return False
    try:
        return datetime.fromisoformat(ts) >= datetime.now() - timedelta(hours=hours)
    except ValueError:
        return False


def _recompute_streak(data: Dict[str, Any]) -> None:
    """Count distinct recent days that carried any flagged event."""
    cutoff = datetime.now() - timedelta(days=7)
    flagged_days = set()
    for e in data["events"]:
        try:
            ts = datetime.fromisoformat(e["ts"])
        except ValueError:
            continue
        if ts >= cutoff and _LEVEL_ORDER.get(e["level"], 0) >= 1:
            flagged_days.add(ts.date().isoformat())
    data["trend_streak"] = len(flagged_days)


def gating() -> Dict[str, Any]:
    """
    Decide what (if anything) should surface, from the event history.
      - urgent: a crisis/tier-3 event recently, OR all four layers fired AND the
        trend has persisted (streak >= 4 distinct flagged days).
      - gentle: content flags present but not urgent.
    """
    with _LOCK:
        data = _load()
        toggles = data["settings"]["toggles"]
        cutoff = datetime.now() - timedelta(days=4)
        recent = []
        for e in data["events"]:
            try:
                ts = datetime.fromisoformat(e["ts"])
            except ValueError:
                continue
            if ts >= cutoff:
                recent.append(e)
        layers_seen = {e["layer"] for e in recent}
        crisis = any(_LEVEL_ORDER.get(e["level"], 0) >= 4 for e in recent)
        content = any(e["layer"] in (1, 2) for e in recent)
        streak = data["trend_streak"]
        gate_ok = toggles.get("trend", True)

        urgent = crisis or (layers_seen >= {1, 2, 3} and streak >= 4 and gate_ok)
        gentle = (content or streak >= 2) and not urgent
        return {"gentle": bool(gentle), "urgent": bool(urgent),
                "streak": streak, "layers": sorted(layers_seen)}


# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------

def add_chat(role: str, content: str) -> None:
    with _LOCK:
        data = _load()
        data["chat"].append({"role": role, "content": content,
                             "ts": datetime.now().isoformat(timespec="seconds")})
        data["chat"] = data["chat"][-200:]
        _save(data)


def get_chat() -> List[Dict[str, Any]]:
    with _LOCK:
        return _load()["chat"]


def clear_chat() -> None:
    with _LOCK:
        data = _load()
        data["chat"] = []
        _save(data)


# --- Multiple chat threads (ChatGPT-style history) -------------------------
#
# `data["chat"]` stays the ACTIVE conversation, so every existing caller keeps
# working unchanged. Past conversations are archived in `data["chat_threads"]`
# as {id, title, messages, ts}. Starting a new chat archives the current one.

def _thread_title(messages: List[Dict[str, Any]]) -> str:
    """Name a thread after its first user message, trimmed."""
    for m in messages:
        if m.get("role") == "user":
            t = " ".join((m.get("content") or "").split())
            return (t[:44] + "…") if len(t) > 44 else (t or "New conversation")
    return "New conversation"


def list_threads() -> List[Dict[str, Any]]:
    """Archived threads, newest first, plus whether the active chat has content."""
    with _LOCK:
        data = _load()
        out = []
        for t in reversed(data.get("chat_threads", [])):
            out.append({"id": t.get("id"), "title": t.get("title") or "Conversation",
                        "ts": t.get("ts"), "count": len(t.get("messages") or [])})
        return out


def new_thread() -> None:
    """Archive the current conversation and start an empty one."""
    with _LOCK:
        data = _load()
        cur = data.get("chat") or []
        # Only archive if there's a real exchange (not just the greeting).
        if any(m.get("role") == "user" for m in cur):
            data.setdefault("chat_threads", []).append({
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "title": _thread_title(cur),
                "messages": cur,
                "ts": datetime.now().isoformat(timespec="seconds"),
            })
            data["chat_threads"] = data["chat_threads"][-50:]   # keep the last 50
        data["chat"] = []
        _save(data)


def open_thread(thread_id: str) -> bool:
    """Make an archived thread the active one (archiving whatever's open)."""
    with _LOCK:
        data = _load()
        threads = data.get("chat_threads", [])
        idx = next((i for i, t in enumerate(threads) if t.get("id") == thread_id), None)
        if idx is None:
            return False
        cur = data.get("chat") or []
        if any(m.get("role") == "user" for m in cur):
            threads.append({
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "title": _thread_title(cur), "messages": cur,
                "ts": datetime.now().isoformat(timespec="seconds"),
            })
            idx = next((i for i, t in enumerate(threads) if t.get("id") == thread_id), None)
        picked = threads.pop(idx)
        data["chat"] = picked.get("messages") or []
        data["chat_threads"] = threads
        _save(data)
        return True


def delete_thread(thread_id: str) -> bool:
    with _LOCK:
        data = _load()
        threads = data.get("chat_threads", [])
        n = len(threads)
        data["chat_threads"] = [t for t in threads if t.get("id") != thread_id]
        if len(data["chat_threads"]) == n:
            return False
        _save(data)
        return True


# ---------------------------------------------------------------------------
# Export / wipe
# ---------------------------------------------------------------------------

def export() -> Dict[str, Any]:
    with _LOCK:
        return _load()


def wipe() -> None:
    with _LOCK:
        if os.path.exists(_data_path()):
            os.remove(_data_path())


# ---------------------------------------------------------------------------
# Moments (history) · connection status · baseline reset
# ---------------------------------------------------------------------------

_LAYER_LABEL = {1: "Keyword", 2: "Semantic", 3: "Behavioral", 4: "Trend gate"}


def moments(limit: int = 50) -> List[Dict[str, Any]]:
    """A human timeline of past surfaced signals (newest first). No raw text."""
    with _LOCK:
        data = _load()
        out: List[Dict[str, Any]] = []
        for e in reversed(data["events"]):
            if e.get("level", "none") == "none":
                continue
            try:
                dt = datetime.fromisoformat(e["ts"])
            except ValueError:
                continue
            cat = (e.get("category") or "").replace("_", " ")
            if cat in ("", "none"):
                cat = "general concern"
            out.append({
                "date": dt.strftime("%b %d"),
                "time": dt.strftime("%I:%M %p").lstrip("0"),
                "level": e.get("level"),
                "category": cat,
                "source": _LAYER_LABEL.get(e.get("layer"), "Signal"),
            })
            if len(out) >= limit:
                break
        return out


def status() -> Dict[str, Any]:
    with _LOCK:
        data = _load()
        days = data["days"]
        return {
            "toggles": data["settings"]["toggles"],
            "events": len(data["events"]),
            "days_tracked": len(days),
            "last_day": (max(days) if days else None),
            "last_event": (data["events"][-1]["ts"] if data["events"] else None),
            "streak": data["trend_streak"],
        }


def reset_baseline() -> None:
    """Forget learned behavior + history, keep settings/contact."""
    with _LOCK:
        data = _load()
        data["days"] = {}
        data["events"] = []
        data["trend_streak"] = 0
        _save(data)
