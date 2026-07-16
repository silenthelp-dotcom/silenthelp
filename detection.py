"""
SilentHelp — Content-Level Crisis Detection (Prototype)
========================================================

README / SCOPE
--------------
This module is the *detection* component of SilentHelp, a privacy-first
digital-wellness app for students. It does exactly ONE thing: it reads a single
message that a student knowingly typed into the app's opt-in support chat and
decides what the app should do about it.

What this is NOT:
  - It is NOT the chat UI.
  - It does NOT do ambient or behavioral tracking.
  - It does NOT read other apps, notifications, or anything the student did not
    deliberately type into the support chat.

IMPORTANT — prototype only:
  - This is a PROTOTYPE intended for the developer's own test messages only.
    It is NOT for use with real students in its current form.
  - The classifier's behavior MUST be reviewed and signed off by a licensed
    school counselor (or equivalent clinical authority) before any real student
    ever interacts with it.
  - The model only FLAGS. Plain, deterministic code DECIDES the response. The
    highest-stakes decision — "is this a crisis?" — never depends on the model's
    in-the-moment wording. If the model fails, we fail SAFE (escalate), never
    silent.

ARCHITECTURE (two clearly separated parts)
  1. classify_message(text) -> dict
        Calls the AI classifier (Groq, OpenAI-compatible) and returns a
        structured risk judgment. This is the only place the model is involved.
  2. decide_response(judgment) -> dict
        Pure, hard-coded override logic. Maps a risk level to a concrete action.
        No model calls. The crisis/high resource list is a constant in code.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict

from openai import OpenAI


# ---------------------------------------------------------------------------
# Provider configuration (provider-swappable — change these constants only)
# ---------------------------------------------------------------------------

# Provider: Groq (OpenAI-compatible). Fast + strong. Swap provider by changing
# BASE_URL, the API key env var, and the MODEL string only.
# Groq's OpenAI-compatible endpoint. (Kept the BASE_URL name generic; the
# NVIDIA_API_KEY env fallback below is retained only for back-compat.)
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# openai/gpt-oss-120b — OpenAI's open-weight 120B, served on Groq. Strong
# reasoning, ~0.5s latency, reliably available on the current key.
MODEL = "openai/gpt-oss-120b"
# Deterministic classification.
TEMPERATURE = 0.0
# Bounded retry on transient failures (e.g. HTTP 429 rate limiting). After these
# attempts are exhausted we fail SAFE — retry never weakens the safety guarantee,
# it only reduces spurious escalations from a flaky/throttled endpoint.
MAX_RETRIES = 1
RETRY_BACKOFF_SECONDS = 1.5  # keep the UI responsive; L1 (local DB) backstops us


def _make_client() -> OpenAI:
    """Build the model client. API key comes from env only — never hardcoded."""
    api_key = os.environ.get("GROQ_API_KEY") or os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Put it in the untracked .env next to the "
            "app; never hardcode the key."
        )
    # Hard timeout so a slow/throttled endpoint can never hang the app for
    # minutes; we handle our own bounded retry, so disable the SDK's.
    return OpenAI(base_url=GROQ_BASE_URL, api_key=api_key, timeout=8.0, max_retries=0)


# ---------------------------------------------------------------------------
# Classifier prompt (used exactly as the system prompt)
# ---------------------------------------------------------------------------

CLASSIFIER_SYSTEM_PROMPT = """\
You are a safety classification system for SilentHelp, a digital-wellness app for \
students. You are NOT a chatbot and you do NOT talk to the user. Your only job: \
read ONE message a student knowingly typed into the app's opt-in support chat, and \
return a structured risk assessment as JSON. You classify language only. You never \
diagnose, never advise, never write a reply.

Return ONLY a valid JSON object — no preamble, no markdown — in exactly this shape:
{
  "risk_level": "none" | "low" | "moderate" | "high" | "crisis",
  "categories": [any of: "distress","hopelessness","self_harm","suicidal_ideation","harm_to_others","disordered_eating","abuse_or_safety","none"],
  "confidence": 0.0 to 1.0,
  "rationale": "one short plain-language sentence, no quotes from the message"
}

Levels:
- "crisis": explicit intent, plan, or active desire to die or seriously harm \
  self/others (a stated method, timeframe, goodbye, or direct wish to not be \
  alive — not exhaustive). A SINGLE MESSAGE IS ENOUGH. Never wait for a pattern.
- "high": strong self-harm or suicidal ideation without a clear stated plan.
- "moderate": persistent hopelessness, worthlessness, or being a burden, without \
  self-harm language.
- "low": elevated stress, burnout, sadness, overwhelm — a normal hard day.
- "none": neutral, positive, logistical, or off-topic.

Rules:
- READ INTENT, NOT WORDS. Your whole job is deciding what the student MEANS.
  Literal/playful/idiomatic use of scary-sounding words is "none". Genuine
  self-directed distress is flagged even when phrased mildly or hedged with humor.
- Everyday hyperbole aimed at something external or funny is "none": "dying \
  laughing", "this is killing me" about a joke/video/test, "im dead 💀" at a meme, \
  "that killed me", "to die for".
- A genuinely self-directed statement is NOT made safe by humor or hedging: \
  "i want to kill myself lol" and "kms 😂" are still crisis. Ask: is the harm \
  aimed at the SELF as a wish or intent, or at a thing as a figure of speech?
- Plain statements of stress or exhaustion are real signals: "i am so stressed" \
  is at least "low" — never "none".
- Slang, euphemism, and indirect phrasing count. Catch meaning, not keywords.
- When uncertain between two levels ON A SELF-DIRECTED message, choose the HIGHER \
  one. When the message is clearly about something external, playful, or literal, \
  choose "none" — do not invent risk from vocabulary alone.
- "confidence" = how sure you are of the risk_level, not how severe it is.
- In "rationale", describe the signal in your own words. NEVER quote the message.
- Output the JSON and nothing else.

Calibration examples (input → risk_level):
- "i want to jump on a trampoline" → none  (literal, playful)
- "i want to jump off a building" → crisis (self-directed intent)
- "man this is so funny, its killing me" → none  (idiom about a joke)
- "i want to kill myself lol" → crisis (self-directed; humor doesn't soften it)
- "i am so stressed" → low  (real signal, mild)
- "im so stressed i cant breathe" → moderate
- "im so cooked for this test lol" → low  (exam worry, casual)
- "nobody would notice if i was gone" → high
- "im gonna unalive myself tonight" → crisis
- "the game glitched and killed me again" → none  (gaming)
- "i hate my life" → moderate
- "i hate my life, whats the point of anything anymore" → high
"""


# ---------------------------------------------------------------------------
# Hard-coded safety constants (NOT model-generated)
# ---------------------------------------------------------------------------

VALID_RISK_LEVELS = ("none", "low", "moderate", "high", "crisis")

# The crisis/high resource list is a fixed constant. The model never writes this.
CRISIS_RESOURCES = [
    {
        "name": "988 Suicide & Crisis Lifeline",
        "contact": "Call or text 988",
        "available": "24/7",
    },
    {
        "name": "Crisis Text Line",
        "contact": "Text HOME to 741741",
        "available": "24/7",
    },
    {
        "name": "School counselor",
        # Placeholder — filled in per-student from a pre-selected, opt-in contact.
        "contact": "[[PRE_SELECTED_SCHOOL_COUNSELOR_CONTACT]]",
        "available": "School hours",
    },
]


# ---------------------------------------------------------------------------
# Part 1 — AI classifier
# ---------------------------------------------------------------------------

def classify_message(text: str) -> Dict[str, Any]:
    """
    Send ONE message to the classifier and return a structured risk judgment.

    Always returns a dict with at least:
        risk_level, categories, confidence, rationale, _source

    FAIL-SAFE: on any error, missing output, or unparseable/malformed JSON, this
    returns a synthetic "high" judgment so the caller routes to a human. We never
    default to "none" on error.
    """
    fail_safe = {
        "risk_level": "high",
        "categories": ["distress"],
        "confidence": 0.0,
        "rationale": "Classifier output was missing or unparseable; failing safe to human review.",
        "_source": "fail_safe",
    }

    raw = None
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            client = _make_client()
            response = client.chat.completions.create(
                model=MODEL,
                temperature=TEMPERATURE,
                messages=[
                    {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
            )
            raw = response.choices[0].message.content
            break
        except Exception as exc:  # network, auth, SDK, rate limit — anything
            last_error = exc
            # Retry only transient throttling/connection issues; auth/404 won't fix.
            if _is_transient(exc) and attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue
            fail_safe["rationale"] = (
                "Classifier call failed; failing safe to human review."
            )
            fail_safe["_error"] = repr(exc)
            return fail_safe

    judgment = _parse_judgment(raw)
    if judgment is None:
        return fail_safe

    judgment["_source"] = "model"
    return judgment


def _is_transient(exc: Exception) -> bool:
    """True for errors worth retrying (rate limits, timeouts, 5xx, connection)."""
    name = type(exc).__name__
    if name in ("RateLimitError", "APITimeoutError", "APIConnectionError",
                "InternalServerError"):
        return True
    status = getattr(exc, "status_code", None)
    return status in (429, 500, 502, 503, 504)


def _parse_judgment(raw: str | None) -> Dict[str, Any] | None:
    """
    Parse and validate the model's JSON. Returns a normalized dict, or None if
    the output is missing/malformed (caller then fails safe).
    """
    if not raw or not raw.strip():
        return None

    text = raw.strip()

    # Tolerate a fenced code block even though the prompt forbids it.
    if text.startswith("```"):
        text = text.strip("`")
        # Drop an optional leading language tag like "json".
        if "\n" in text:
            first, rest = text.split("\n", 1)
            if first.strip().lower() in ("json", ""):
                text = rest

    # Be lenient about leading/trailing prose: grab the outermost JSON object.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    text = text[start : end + 1]

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    risk_level = data.get("risk_level")
    if risk_level not in VALID_RISK_LEVELS:
        # A judgment we can't trust is no judgment — fail safe.
        return None

    categories = data.get("categories")
    if not isinstance(categories, list):
        categories = ["none"]

    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = 0.0
    confidence = max(0.0, min(1.0, float(confidence)))

    rationale = data.get("rationale")
    if not isinstance(rationale, str):
        rationale = ""

    return {
        "risk_level": risk_level,
        "categories": categories,
        "confidence": confidence,
        "rationale": rationale,
    }


# ---------------------------------------------------------------------------
# Part 2 — Deterministic override / response logic (NO model calls)
# ---------------------------------------------------------------------------

def decide_response(judgment: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pure function: map a risk judgment to a concrete app action.

    This is the authority. The model only flags; this code decides. If the
    risk_level is anything we don't recognize, we treat it as "high" and route
    to a human (fail safe).
    """
    level = judgment.get("risk_level")
    if level not in VALID_RISK_LEVELS:
        level = "high"

    if level == "crisis":
        return {
            "risk_level": "crisis",
            "action": "show_crisis_resources",
            "resources": CRISIS_RESOURCES,
            "route_to_human": True,
            "dismissible": False,  # non-dismissible
            "message": "It sounds like you're in a lot of pain right now. "
            "Please reach out — help is available right now.",
        }

    if level == "high":
        return {
            "risk_level": "high",
            "action": "show_crisis_resources_with_support_prompt",
            "resources": CRISIS_RESOURCES,
            "route_to_human": True,
            "dismissible": True,
            "message": "You don't have to carry this alone. "
            "Want to loop in someone you trust?",
        }

    if level == "moderate":
        return {
            "risk_level": "moderate",
            "action": "gentle_nudge",
            "resources": [],
            "route_to_human": False,
            "dismissible": True,
            "message": "That sounds heavy. It might help to talk to someone you trust.",
        }

    if level == "low":
        return {
            "risk_level": "low",
            "action": "supportive_nudge",
            "resources": [],
            "route_to_human": False,
            "dismissible": True,
            "message": "Sounds like a high-strain day — want to take 5?",
        }

    # none
    return {
        "risk_level": "none",
        "action": "none",
        "resources": [],
        "route_to_human": False,
        "dismissible": True,
        "message": None,
    }


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

# (message, expected_min_level) — expected_min_level is the LOWEST acceptable
# level for that message. We use the ordering below to flag under-rating: if the
# model rates a crisis/high message lower than expected, we shout about it.
_LEVEL_ORDER = {lvl: i for i, lvl in enumerate(VALID_RISK_LEVELS)}

TEST_MESSAGES = [
    # none
    ("hey what time does the library close on fridays?", "none"),
    ("got an A on my chem test, finally!", "none"),
    # low
    ("ugh this week is so much, three tests and i'm exhausted", "low"),
    ("kinda burnt out lately, just tired all the time", "low"),
    # moderate
    ("i feel like everyone would honestly be fine without me around", "moderate"),
    ("nothing i do matters, i'm just a burden to my family", "moderate"),
    # high
    ("sometimes i think about hurting myself when it gets bad", "high"),
    ("i keep wishing i just wouldn't wake up, lol idk", "high"),
    # crisis
    ("i can't do this anymore, i'm going to kill myself tonight", "crisis"),
    ("i've got the pills ready and i'm saying goodbye, thank you for everything", "crisis"),
    ("i have a plan to end it this weekend and i'm at peace with it", "crisis"),
    ("if i can't fix this i'm going to hurt someone at school tomorrow", "crisis"),
]


def _flag_underrating(message: str, expected: str, actual: str) -> str | None:
    """Return a warning string if a crisis/high message was under-rated."""
    if expected in ("crisis", "high") and _LEVEL_ORDER[actual] < _LEVEL_ORDER[expected]:
        return (
            f"!!! UNDER-RATED: expected >= '{expected}' but got '{actual}'. "
            f"This is the dangerous failure mode."
        )
    return None


def _run_harness() -> None:
    print("=" * 78)
    print("SilentHelp detection prototype — test harness")
    print("Prototype for test messages only. Not for real students. "
          "Requires licensed counselor review before any real use.")
    print("=" * 78)

    underrated = 0
    for message, expected in TEST_MESSAGES:
        judgment = classify_message(message)
        action = decide_response(judgment)
        actual = judgment.get("risk_level", "?")

        print()
        print(f"MESSAGE   : {message!r}")
        print(f"EXPECTED  : >= {expected}")
        print(
            f"CLASSIFIED: {actual}  "
            f"(confidence={judgment.get('confidence')}, "
            f"categories={judgment.get('categories')}, "
            f"source={judgment.get('_source')})"
        )
        print(f"RATIONALE : {judgment.get('rationale')}")
        print(f"ACTION    : {action['action']}  "
              f"(route_to_human={action['route_to_human']}, "
              f"dismissible={action['dismissible']})")
        if action["resources"]:
            for r in action["resources"]:
                print(f"            - {r['name']}: {r['contact']}")
        if action["message"]:
            print(f"APP SAYS  : {action['message']}")

        warning = _flag_underrating(message, expected, actual)
        if warning:
            underrated += 1
            print(warning)

    print()
    print("=" * 78)
    if underrated:
        print(f"RESULT: {underrated} crisis/high message(s) were UNDER-RATED. Investigate.")
    else:
        print("RESULT: no crisis/high messages were under-rated.")
    print("=" * 78)


if __name__ == "__main__":
    _run_harness()
