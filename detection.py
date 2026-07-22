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
import re
import time
from pathlib import Path
from typing import Any, Dict

from openai import OpenAI

# Load the untracked .env sitting next to this file, so API keys are present no
# matter which entry point started the process (app.py, chat.py, helper.py, or
# running this module directly). Without this every provider lookup fails and
# ALL traffic silently falls through to the fail-safe. Real environment
# variables win — override=False keeps prod/CI config authoritative.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env"), override=False)
except ImportError:  # dotenv absent: rely on the real environment
    pass


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
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 1.5  # base backoff; overridden by the server's "try again in" hint
MAX_RETRY_WAIT = 8.0         # never block a request longer than this on retries


def _retry_wait_from(exc: Exception, attempt: int) -> float:
    """How long to wait before retrying. Prefer the provider's own 'Please try
    again in Xs' hint (429 responses include it); else exponential backoff.
    Capped so the UI never hangs — the local keyword layer already responded."""
    msg = str(getattr(exc, "message", "")) or str(exc)
    m = re.search(r"try again in ([\d.]+)\s*s", msg, re.IGNORECASE)
    if m:
        try:
            return min(MAX_RETRY_WAIT, float(m.group(1)) + 0.3)
        except ValueError:
            pass
    return min(MAX_RETRY_WAIT, RETRY_BACKOFF_SECONDS * attempt)


# ---------------------------------------------------------------------------
# Providers: Groq is primary; a FALLBACK provider takes over automatically when
# Groq is rate-limited/unreachable, so detection is never fully blocked by one
# plan's cap. All must be OpenAI-compatible. Configure the fallback in .env:
#   FALLBACK_API_KEY   — the second provider's key
#   FALLBACK_BASE_URL  — its OpenAI-compatible endpoint
#   FALLBACK_MODEL     — a model id on that provider
# Common free/cheap options (any OpenAI-compatible endpoint works):
#   • OpenRouter : https://openrouter.ai/api/v1        (many free models)
#   • Cerebras   : https://api.cerebras.ai/v1          (fast, free tier)
#   • Together   : https://api.together.xyz/v1
# ---------------------------------------------------------------------------

def _providers() -> "list[dict]":
    """Ordered list of provider configs to try. Primary first, fallback(s) next."""
    out = []
    groq_key = os.environ.get("GROQ_API_KEY") or os.environ.get("NVIDIA_API_KEY")
    if groq_key:
        out.append({"name": "groq", "key": groq_key,
                    "base_url": GROQ_BASE_URL, "model": MODEL, "timeout": 8.0})
    fb_key = os.environ.get("FALLBACK_API_KEY")
    if fb_key:
        out.append({
            "name": "fallback",
            "key": fb_key,
            "base_url": os.environ.get("FALLBACK_BASE_URL", "https://openrouter.ai/api/v1"),
            "model": os.environ.get("FALLBACK_MODEL", "openai/gpt-oss-20b:free"),
            "timeout": 20.0,  # free fallback models are slower
        })
    if not out:
        raise RuntimeError(
            "No AI provider configured. Set GROQ_API_KEY (and optionally "
            "FALLBACK_API_KEY/FALLBACK_BASE_URL/FALLBACK_MODEL) in .env.")
    return out


def _client_for(p: "dict") -> OpenAI:
    # Hard timeout so a slow/throttled endpoint can never hang the app; we do our
    # own bounded retry, so disable the SDK's. Free fallback models are slower,
    # so they get a longer per-call budget than the fast primary.
    return OpenAI(base_url=p["base_url"], api_key=p["key"],
                  timeout=p.get("timeout", 8.0), max_retries=0)


def _make_client() -> OpenAI:
    """The PRIMARY client (Groq). Kept for chat.py / helper.py which use one
    provider. Detection itself uses _complete() so it can fail over."""
    return _client_for(_providers()[0])


def _complete(messages: "list[dict]", *, temperature: float, max_tokens: "int | None" = None) -> str:
    """Run a chat completion, trying each provider in order and, within a
    provider, retrying transient errors. Returns the raw text, or raises the
    last error if every provider fails (caller then fails SAFE)."""
    last_error: Exception = RuntimeError("no providers")
    for p in _providers():
        client = _client_for(p)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                kw = {"model": p["model"], "temperature": temperature, "messages": messages}
                if max_tokens:
                    kw["max_tokens"] = max_tokens
                resp = client.chat.completions.create(**kw)
                return resp.choices[0].message.content or ""
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if _is_transient(exc) and attempt < MAX_RETRIES:
                    time.sleep(_retry_wait_from(exc, attempt))
                    continue
                break  # non-transient or out of retries → try the next provider
    raise last_error


# ---------------------------------------------------------------------------
# Classifier prompt (used exactly as the system prompt)
# ---------------------------------------------------------------------------

CLASSIFIER_SYSTEM_PROMPT = """\
You classify ONE student message for SilentHelp (a student wellness app) and \
return ONLY JSON. You judge what the message MEANS, not keywords. Read intent: \
jokes/idioms/literal talk = "none"; genuine distress = flagged even if mild or \
hedged with humor. The message may be something the student WROTE, or one they \
RECEIVED (a threat/bullying aimed AT them) — both are concerns.

Concerns (any of these, not just suicide): suicidal thoughts/intent; self-harm; \
harm to others; threats/bullying the student received; abuse or being unsafe; \
disordered eating; substance use to cope; panic/anxiety/trauma/flashbacks; \
psychosis (hearing voices, paranoia); depression/hopelessness/worthlessness/ \
numbness; severe stress/burnout/overwhelm.

Return exactly: {"risk_level": "none|low|moderate|high|crisis", "categories": \
[from: distress,hopelessness,self_harm,suicidal_ideation,harm_to_others,\
disordered_eating,abuse_or_safety,none], "confidence": 0.0-1.0, "rationale": \
"one short sentence, no quote of the message"}

Levels:
- crisis: explicit intent/plan/active desire to die or seriously harm self/others \
  now; a threat to kill/seriously hurt the student; active ongoing abuse. ONE \
  message is enough.
- high: strong self-harm/suicidal ideation w/o plan; active self-harm; serious \
  disordered eating (starving/purging); disclosed abuse; psychosis; dangerous \
  relapse; wanting to hurt someone; a serious threat/bullying received.
- moderate: persistent depression/hopelessness/worthlessness/numbness; recurring \
  panic or severe anxiety; coping by drinking/using w/o immediate danger; \
  eating-disorder worry.
- low: elevated stress/burnout/sadness/overwhelm, or a first mention of feeling \
  down/anxious.
- none: neutral, positive, logistical, or clearly non-serious (jokes, idioms, \
  hyperbole about something external).

When genuinely unsure it's a concern, pick at least "low" — missing a struggling \
student is worse than a false check-in. But don't invent risk from scary \
vocabulary in obviously playful/literal messages. Output JSON only.

Examples (msg -> level):
jump on a trampoline->none | jump off a building->crisis | "so funny its killing \
me"->none | "kill myself lol"->crisis | "i am so stressed"->low | "so stressed i \
cant breathe"->moderate | "cooked for this test lol"->low | "nobody would notice \
if i was gone"->high | "unalive myself tonight"->crisis | "game killed me \
again"->none | "i hate my life"->moderate | "whats the point of anything"->high | \
"i think im depressed"->moderate | "cant stop self harming"->high | "my dad hits \
me"->crisis | "havent eaten in 3 days on purpose"->high | "i make myself throw \
up"->high | "drank to numb the pain"->moderate | "i relapsed"->high | "panic \
attacks"->moderate | "flashbacks and cant sleep"->moderate | "hear voices telling \
me things"->high | "feel like hurting someone"->high | "numb and empty all the \
time"->moderate | "whats the chem homework"->none | "i want to kill you" (received \
threat)->crisis | "you should kill yourself" (received)->crisis | "beat you up \
after school" (received)->high | "nobody likes you youre worthless" \
(received)->high | "i'll kill you lol jk"->none
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

    # _complete() tries Groq, then the fallback provider, with transient retries.
    try:
        raw = _complete(
            [{"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
             {"role": "user", "content": text}],
            temperature=TEMPERATURE,
        )
    except Exception as exc:  # every provider failed → fail SAFE
        fail_safe["rationale"] = "Classifier call failed; failing safe to human review."
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
    failsafed = 0
    first_error = None
    for message, expected in TEST_MESSAGES:
        judgment = classify_message(message)
        action = decide_response(judgment)
        actual = judgment.get("risk_level", "?")
        if judgment.get("_source") == "fail_safe":
            failsafed += 1
            first_error = first_error or judgment.get("_error")

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
    # A provider outage makes every message fail-safe to "high", which reads as a
    # wall of plausible verdicts. Say so loudly: these rows measure the provider,
    # not the prompt, and no conclusion about classifier quality can be drawn.
    if failsafed:
        print(f"!!! PROVIDER FAILURE: {failsafed}/{len(TEST_MESSAGES)} message(s) never "
              f"reached the model and fail-safed to 'high'.")
        print(f"!!! These rows say NOTHING about classifier accuracy — fix the provider first.")
        if first_error:
            print(f"!!! First error: {first_error}")
    if underrated:
        print(f"RESULT: {underrated} crisis/high message(s) were UNDER-RATED. Investigate.")
    elif failsafed == len(TEST_MESSAGES):
        print("RESULT: inconclusive — no message reached the classifier.")
    else:
        print("RESULT: no crisis/high messages were under-rated.")
    print("=" * 78)


if __name__ == "__main__":
    _run_harness()
