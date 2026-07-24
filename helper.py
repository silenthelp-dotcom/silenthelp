"""
SilentHelp — Help a Friend (coach mode)
=======================================

A distinct mode from the coping chat. Here the SilentHelp user is NOT the one
struggling — their FRIEND is. The user pastes/forwards what their friend said,
and SilentHelp coaches them, turn by turn, on how to support that friend:

  • a ready-to-send SUGGESTED REPLY the user can copy to their friend, and
  • short GUIDANCE (validate first, don't panic, ask if they're safe), and
  • an ESCALATION signal that turns on when — after a real back-and-forth — the
    friend STILL expresses wanting to die / active danger, i.e. support alone
    isn't enough and a trusted adult must be looped in.

The model returns structured JSON so the UI can render the reply and guidance
separately. Everything fails safe: if the model is unreachable, we return a
warm, safe fallback that still points to 988 and a trusted adult.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import detection

HELPER_SYSTEM_PROMPT = """\
You are SilentHelp's "Help a Friend" coach. The person talking to you is a \
student whose FRIEND is going through something hard. You are NOT talking to the \
friend — you are coaching the student on how to support their friend. You are \
not a therapist and never claim to be.

You are given the conversation so far: messages the FRIEND sent (role "friend") \
and messages the student already sent to the friend (role "user"). Coach the \
student on their NEXT reply to the friend.

Return ONLY a valid JSON object — no preamble, no markdown — in exactly this shape:
{
  "reply": "a short, warm, ready-to-send message the student can copy and send to their friend (1-3 sentences, sound like a caring teenager, not a counselor)",
  "guidance": "one or two short sentences coaching the student on WHY this reply helps and what to watch for",
  "danger": "none" | "watch" | "escalate",
  "escalation_reason": "if danger is 'escalate', one sentence on why it's time to loop in a trusted adult; else empty"
}

How to coach:
- The suggested "reply" should VALIDATE the friend first ("that sounds really \
  heavy, i'm glad you told me"), stay calm, and gently keep the door open. Never \
  panic, never lecture, never toxic positivity ("just cheer up").
- Ask gentle questions that keep the friend talking and check if they're safe \
  ("are you safe right now?", "have you been able to tell anyone?").
- Match the tone of a supportive friend texting, not a hotline script.

Read tone and context BEFORE deciding anything:
- Casual hyperbole and jokes are NOT distress. "this test is killing me lol", \
  "i'm dying 😂", "ugh this homework is the end of me haha" are normal venting \
  or humor — respond casually and warmly like a friend ("lmao same, that test \
  was brutal — you got this"), set danger to "none", and do NOT ask if they're \
  safe or mention getting help. Treating a joke as a crisis makes the student \
  look alarmist and pushes the friend away.
- Only read genuine distress when the words AND tone actually point to it — a \
  sincere "i don't see the point anymore", "everyone would be better off \
  without me", not a punchline with "lol"/"haha"/"😂".

Danger levels:
- "none": the friend is joking, venting, or sad but not in danger — keep it \
  light or supportive to match their tone.
- "watch": worrying signs (hopelessness, self-harm hints) — the reply should \
  gently ask if they're safe and whether they've told a trusted adult.
- "escalate": set this when, ACROSS THE CONVERSATION (not just one message), the \
  friend keeps expressing wanting to die, a plan, or active danger EVEN AFTER the \
  student has tried to support them. This means friend-support alone isn't enough. \
  In "reply", still give a caring message, but in "guidance" and "escalation_reason" \
  make clear the student should now involve a trusted adult and 988, and WHY: a \
  friend in real danger needs more help than one person can give, and telling an \
  adult is being a good friend, not betraying them.

Output the JSON and nothing else.
"""


def coach(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    messages: the friend-conversation so far, each {"role": "friend"|"user",
    "content": ...} — "friend" = what the struggling friend sent, "user" = what
    the SilentHelp user sent back.

    Returns {reply, guidance, danger, escalation_reason}. Fails safe.
    """
    # The model expects OpenAI-style roles; map friend->user, user->assistant so
    # the transcript reads naturally, and label each line so the model can tell
    # who said what.
    convo = []
    for m in messages:
        who = "FRIEND" if m.get("role") == "friend" else "STUDENT (me)"
        convo.append({"role": "user" if m.get("role") == "friend" else "assistant",
                      "content": f"[{who}] {m.get('content', '')}"})
    try:
        client = detection._make_client()
        resp = client.chat.completions.create(
            model=detection.MODEL,
            temperature=0.6,
            max_tokens=320,
            messages=[{"role": "system", "content": HELPER_SYSTEM_PROMPT}, *convo],
        )
        raw = (resp.choices[0].message.content or "").strip()
        parsed = _parse(raw)
        if parsed:
            return parsed
    except Exception:
        pass
    return _fallback(messages)


def _parse(raw: str) -> Dict[str, Any] | None:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            first, rest = text.split("\n", 1)
            if first.strip().lower() in ("json", ""):
                text = rest
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or "reply" not in data:
        return None
    danger = data.get("danger")
    if danger not in ("none", "watch", "escalate"):
        danger = "watch"
    return {
        "reply": str(data.get("reply", "")).strip(),
        "guidance": str(data.get("guidance", "")).strip(),
        "danger": danger,
        "escalation_reason": str(data.get("escalation_reason", "")).strip(),
    }


def _fallback(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """Warm, safe coaching when the model can't be reached. Never goes silent."""
    return {
        "reply": ("Hey, I'm really glad you told me. That sounds so heavy and "
                  "you're not alone in it. Are you safe right now?"),
        "guidance": ("Lead by validating them and asking if they're safe. Stay "
                     "calm — you don't have to fix it, just be there and keep them talking."),
        "danger": "watch",
        "escalation_reason": "",
    }
