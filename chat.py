"""
SilentHelp — Coping Chat (Prototype)
====================================

The opt-in support conversation. UNLIKE the detection layers, the user KNOWS
they are talking to an AI here, so sending text to the cloud model is honest.

This module only generates a supportive reply. Safety routing is NOT decided
here — app.py still runs detection.classify_message()/decide_response() on the
user's message in parallel, so crisis resources surface from the same hard-coded
authority the rest of the app uses. The chat is a support layer, never a therapy
replacement, and always defers to human help when things get serious.

Prototype note: uses the same Groq client/model as detection. In production
the coping chat would use a purpose-fit conversational model (e.g. Sonnet 4.6),
not the classifier model — see project notes.
"""

from __future__ import annotations

from typing import Any, Dict, List

import detection

CHAT_SYSTEM_PROMPT = """\
You are SilentHelp, a warm, grounded support companion inside a digital-wellness \
app for students. You are NOT a therapist and you never claim to be. You are a \
calm first layer of support.

How you talk:
- Brief and human. 1-3 short sentences. No lectures, no bullet lists, no clinical \
  jargon.
- Validate first, then gently open a door ("that sounds heavy — what's been the \
  hardest part?"). Ask at most one gentle question.
- Never diagnose, never minimize, never toxically positive ("just cheer up").
- You are a support layer, not a fix. If someone is in real danger, your job is \
  to steer them toward a trusted person and real help, not to handle it alone.

Safety:
- If the message suggests crisis, self-harm, or suicidal intent, respond with calm \
  care and clearly encourage reaching out right now to 988 (call or text) or the \
  Crisis Text Line (text HOME to 741741), and to a trusted adult. Do not be casual \
  about it. The app also surfaces these resources separately — reinforce them.
"""


def reply(messages: List[Dict[str, str]]) -> str:
    """
    messages: full chat history as [{"role": "user"|"assistant", "content": ...}].
    Returns the assistant's next message. Falls back to a safe canned line if the
    model is unavailable (key unset / throttled) — the chat never hard-fails.
    """
    try:
        client = detection._make_client()
        resp = client.chat.completions.create(
            model=detection.MODEL,
            temperature=0.7,
            max_tokens=220,
            messages=[{"role": "system", "content": CHAT_SYSTEM_PROMPT}, *messages],
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or _fallback(messages)
    except Exception:
        return _fallback(messages)


def _fallback(messages: List[Dict[str, str]]) -> str:
    """Safe, warm reply when the model can't be reached. Never goes silent."""
    return (
        "I'm here with you. I'm having trouble reaching my words right now, but "
        "you don't have to carry this alone — if things feel heavy, talking to "
        "someone you trust can help. If it's urgent, you can call or text 988 anytime."
    )
