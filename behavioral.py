"""
SilentHelp — Layer 3 Behavioral Engine (Prototype mock)
========================================================

L3 reads NO text. It looks only at *behavioral* signals from the device and
compares them to the user's own personal baseline. Deviation from baseline is
the signal — not absolute values.

PROTOTYPE NOTE
--------------
A real macOS build would source these signals live (CGEventTap for keystroke
rhythm / backspacing, active-hours from the session, tab/app switching, etc.).
Here they are passed in from the dashboard sliders so the scoring logic can be
demoed without any system monitoring. The *scoring* below is the real Phase-1
rule-based logic from the roadmap; only the data source is mocked.

Nothing here leaves the device. The web layer never persists or transmits it.
"""

from __future__ import annotations

from typing import Any, Dict, List

# The user's personal "normal". In production this is learned per-user over the
# first weeks of use; here it's a fixed reference point.
BASELINE: Dict[str, float] = {
    "tab_switches": 25.0,        # switches per active hour
    "late_night_min": 15.0,      # minutes active after midnight
    "avg_session_min": 50.0,     # average focused session length
    "interruptions": 10.0,       # context switches per active hour
    "backspace_rate": 0.10,      # fraction of keystrokes that are corrections
}

# A neutral "today" that sits right at baseline — the dashboard starts here.
DEFAULT_TODAY: Dict[str, float] = dict(BASELINE)


def _excess(value: float, base: float) -> float:
    """How far ABOVE baseline, as a ratio (0 when at or below baseline)."""
    if base <= 0:
        return 0.0
    return max(0.0, (value - base) / base)


def _shortfall(value: float, base: float) -> float:
    """How far BELOW baseline, as a ratio (used for fragmented sessions)."""
    if base <= 0:
        return 0.0
    return max(0.0, (base - value) / base)


def _clamp(n: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, n))


def compute_metrics(signals: Dict[str, Any]) -> Dict[str, Any]:
    """
    Turn raw behavioral signals into the dashboard's three headline numbers
    plus a burnout risk score and recovery suggestions. Pure + deterministic.
    """
    s = {k: float(signals.get(k, BASELINE[k])) for k in BASELINE}

    late = _excess(s["late_night_min"], BASELINE["late_night_min"])
    tabs = _excess(s["tab_switches"], BASELINE["tab_switches"])
    intr = _excess(s["interruptions"], BASELINE["interruptions"])
    back = _excess(s["backspace_rate"], BASELINE["backspace_rate"])
    frag = _shortfall(s["avg_session_min"], BASELINE["avg_session_min"])

    # --- Marathon / "stuck on tabs for hours" signal (no breaks) ---
    # active_minutes isn't a baseline key, so read it from the raw signals.
    active_min = float(signals.get("active_minutes", 0) or 0)
    session_min = s["avg_session_min"]
    marathon = 0.0
    if session_min > 120:            # 2h+ glued to one thing without a break
        marathon += min(15.0, (session_min - 120) / 120 * 15.0)
    if active_min > 240:             # 4h+ total screen time today
        marathon += min(12.0, (active_min - 240) / 240 * 12.0)

    # --- Burnout risk (Phase-1 rule-based, continuous so sliders feel live) ---
    burnout = 0.0
    burnout += min(25.0, late * 25.0)   # late-night usage
    burnout += min(25.0, tabs * 20.0)   # excessive tab switching
    burnout += min(15.0, intr * 18.0)   # constant interruptions
    burnout += min(15.0, back * 18.0)   # rapid backspacing (frustration)
    burnout += min(20.0, frag * 25.0)   # fragmented attention
    burnout += marathon                 # hours without a break
    burnout = round(_clamp(burnout))

    # --- Focus score: attention stability (penalize thrash + fragmentation) ---
    focus = 100.0
    focus -= min(35.0, tabs * 28.0)
    focus -= min(30.0, intr * 30.0)
    focus -= min(25.0, frag * 30.0)
    focus = round(_clamp(focus))

    # --- Mental battery: remaining energy (fatigue from burnout + late nights) ---
    battery = round(_clamp(100.0 - burnout * 0.9 - min(10.0, late * 10.0)))

    # --- Status label ---
    if burnout < 25:
        status = "Healthy"
    elif burnout < 50:
        status = "Slightly elevated"
    elif burnout < 75:
        status = "Elevated"
    else:
        status = "High strain"

    return {
        "mental_battery": battery,
        "focus_score": focus,
        "burnout_risk": burnout,
        "status": status,
        "deltas": _deltas(s),
        "suggestions": _suggestions(late, tabs, intr, back, frag, marathon),
    }


def _deltas(s: Dict[str, float]) -> List[Dict[str, Any]]:
    """Percent change vs baseline for the signals the user can feel."""
    labels = {
        "tab_switches": "Tab switching",
        "late_night_min": "Late-night activity",
        "interruptions": "Interruptions",
        "avg_session_min": "Avg session length",
        "backspace_rate": "Correction typing",
    }
    out = []
    for key, label in labels.items():
        base = BASELINE[key]
        if base <= 0:
            continue
        pct = round((s[key] - base) / base * 100)
        out.append({"label": label, "pct": pct})
    return out


def _suggestions(late: float, tabs: float, intr: float, back: float, frag: float, marathon: float = 0.0) -> List[str]:
    tips: List[str] = []
    if marathon > 0:
        tips.append("You've been locked in for hours without a break — stand up and stretch for five.")
    if late > 0.5:
        tips.append("Wind down earlier — your late-night activity is well above your usual.")
    if tabs > 0.5:
        tips.append("Reduce multitasking — try a single-tab focus session.")
    if intr > 0.5:
        tips.append("Batch your notifications and protect one uninterrupted focus block.")
    if back > 0.5:
        tips.append("Lots of corrections lately — a short break can reset your focus.")
    if frag > 0.4:
        tips.append("Your sessions are fragmented — try one 25-minute focused block.")
    if not tips:
        tips.append("You're tracking close to your healthy baseline. Keep it steady.")
    return tips


def weekly_trend(today_focus: int) -> List[int]:
    """Mock 7-day focus trend ending at today's score (for the dashboard chart)."""
    seed = [72, 68, 75, 64, 70, 66]
    return seed + [int(today_focus)]
