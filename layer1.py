"""
SilentHelp — Layer 1 Keyword Engine
===================================

The cheap, fully-local pre-filter. NO AI. It loads layer1_blocks.json and
compiles, ONCE at import, the same regex the macOS app builds at runtime:

    <starter> <modifier>? <root>       (per category)  -> contextual match
    <standalone tier-3 crisis phrase>                  -> tier-3, bypasses gating

Layer 1's only job: catch obvious signals fast and pass them to Layer 2. It is
deliberately dumb — string/regex matching, no understanding. Tier-3 standalone
hits are high-precision crisis vocabulary and are flagged to BYPASS Layer 4's
trend gate (a single hit is enough).

scan(text) -> {
    "tier3": bool,                 # standalone crisis vocabulary present
    "matched": bool,               # any L1 hit at all (tier3 or contextual)
    "categories": [str, ...],      # which root categories fired
    "hits": [{"phrase","category","tier"}, ...],
}
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

_BLOCKS_PATH = Path(__file__).resolve().parent / "layer1_blocks.json"


def _alt(words: List[str]) -> str:
    """Regex alternation, longest-first so greedy matching prefers longer phrases."""
    return "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True))


def _load() -> Dict[str, Any]:
    with _BLOCKS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


_DATA = _load()

# Contextual pattern per category: starter (+ optional modifier) + root.
_STARTERS = _alt(_DATA["starters"])
_MODIFIERS = _alt(_DATA["modifiers"])
_CATEGORY_RE: Dict[str, re.Pattern] = {
    category: re.compile(
        rf"\b(?:{_STARTERS})\s+(?:(?:{_MODIFIERS})\s+)?(?:{_alt(roots)})\b",
        re.IGNORECASE,
    )
    for category, roots in _DATA["roots"].items()
}

# Bare-root pattern: roots strong enough to count on their own (e.g. "i'm cooked"
# where "cooked" is also a starter). Catches root-only phrasings the contextual
# regex would miss. Kept separate so we can label it lower-confidence if needed.
_ROOT_ONLY_RE: Dict[str, re.Pattern] = {
    category: re.compile(rf"\b(?:{_alt(roots)})\b", re.IGNORECASE)
    for category, roots in _DATA["roots"].items()
}

# Standalone tier-3 crisis vocabulary — bypasses trend gating.
_TIER3_RE = re.compile(rf"\b(?:{_alt(_DATA['standalone_tier_3_crisis'])})\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Context guard — jokes, idioms, and hyperbole must NOT trigger.
# "damn bro im dying laughing" / "this meme killed me" / "my phone is dead"
# are everyday speech, not signals. Two mechanisms:
#   1. _BENIGN_RE: idiom patterns. Any keyword hit whose span overlaps a benign
#      idiom span is discarded outright (the words were part of the idiom).
#   2. _LAUGH_RE + _HYPERBOLE: if the text has clear joking/laughter markers,
#      hyperbole-prone phrases ("dying", "im dead", "kill me"...) are dropped.
# Explicit self-directed crisis phrases (suicide, kill myself, unalive myself,
# end my life, self harm...) are NEVER suppressed — a joke marker next to those
# still routes to the semantic layer / crisis path.
# ---------------------------------------------------------------------------
_BENIGN_RE = re.compile(
    r"""
      \b(?:dying|dyin|dead|died|ded)\s+(?:of\s+|from\s+|with\s+)?(?:laugh\w*|cackl\w*|cring\w*|giggl\w*)\b
    | \b(?:dying|dyin)\s+to\s+(?:see|know|hear|try|go|meet|watch|play|eat|read|tell|show|find|get|visit)\b
    | \bto\s+die\s+for\b
    | \b(?:killing|killed|kills)\s+(?:it|the\s+game|this|that)\b
    | \byou(?:'re|r|\s+are)?\s+killing\s+me\b
    | \b(?:this|that|it|he|she|bro|dude)\s+(?:is\s+)?(?:killing|killed|kills)\s+me\b
    | \bdead(?:ass)?\s+(?:serious|tired|week|line|lift|end|zone|inside\s+joking)\b
    | \bdrop[-\s]?dead\s+gorgeous\b
    | \b(?:my|the)\s+(?:phone|battery|laptop|car|mic|controller|wifi|airpods?)\s+(?:is\s+|was\s+)?(?:dead|dying|died)\b
    | \b(?:phone|battery|laptop)\s+(?:about\s+to\s+|finna\s+|gonna\s+)?die\b
    | \bdead\s+(?:meme|chat|server|game|silence|air)\b
    | \bi(?:'m|m|\s+am)\s+(?:dead|dying|ded)\s*(?:rn|fr|bro|dude|omg|lol|lmao|lmfao|😂|🤣|💀)
    | \bkilled\s+(?:that|the)\s+(?:test|exam|quiz|interview|presentation|game|set|workout)\b
    | \bsuicide\s+(?:squad|prevention|hotline|awareness|lifeline)\b
    | \bhopeless\s+romantic\b
    | \bcut\s+myself\s+(?:a|some|off|short)\b
    | \bcutting\s+(?:the|a|an|some|this|that|out|down|back|up|it|corners|paper|onions?|hair|grass|wood|costs?|class|carbs|calories)\b
    | \b(?:suspense|curiosity|wait(?:ing)?)\s+is\s+killing\s+me\b
    | \bcould\s+kill\s+for\s+a\b
    | \bdying\s+(?:my|your|her|his|their)\s+hair\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_LAUGH_RE = re.compile(
    r"(?:\blo+l+\b|\blm(?:f?a+o+)\b|\bro+fl\b|\bha(?:ha)+h?\b|\bhehe+\b|\bja(?:ja)+\b"
    r"|😂|🤣|😹|💀|\bso+\s+funny\b|\bhilarious\b|\bfunniest\b|\bcomedy\b"
    r"|\bmeme\b|\bjk\b|\bjus+t?\s+kidding\b|\bjoking\b|\bim\s+jokin\w*\b|\bcrying\s+laughing\b)",
    re.IGNORECASE,
)

# A laugh marker only neutralizes a phrase when it's CLOSE to it (same breath).
# On a big OCR'd screen a "lol" in one corner must not mask a serious sentence
# somewhere else entirely.
_JOKE_RADIUS = 60  # characters on either side of the hit

# Hyperbole-prone phrases safe to drop when the text is clearly joking.
_HYPERBOLE = {
    "dying", "dyin", "i'm dying", "im dying", "i am dying",
    "dead", "ded", "i'm dead", "im dead", "i am dead", "dead inside",
    "kill me", "killing me", "kill me now", "die", "i died", "died",
    # "… lmao" at a meme = hyperbole; the semantic layer still sees the raw text
    "i want to die", "want to die", "wanna die", "i wanna die",
    "i'm done", "im done", "i am done", "i can't anymore", "i cant anymore",
    "this is torture", "end me",
}

# Never suppress these, joke markers or not — self-directed, explicit.
_ALWAYS_SERIOUS_RE = re.compile(
    r"(?:suicid|kill\s+myself|killing\s+myself|unalive\s+myself|end\s+my\s+life"
    r"|take\s+my\s+(?:own\s+)?life|self[\s-]?harm|hurt\s+myself|cut\s+myself"
    r"|don'?t\s+want\s+to\s+(?:be\s+alive|live|wake\s+up)|better\s+off\s+without\s+me"
    r"|no\s+reason\s+to\s+live|\bkms\b)",
    re.IGNORECASE,
)


def _benign_spans(text: str) -> List[tuple]:
    return [m.span() for m in _BENIGN_RE.finditer(text)]


def _in_benign(span: tuple, benign: List[tuple]) -> bool:
    return any(s <= span[0] and span[1] <= e for s, e in benign)


# Four severity levels (the app's 1–4 scale):
#   1 = not that critical   (burnout / fatigue)
#   2 = somewhat            (high stress / overwhelm)
#   3 = critical            (isolation / hopelessness)
#   4 = very critical       (standalone crisis vocabulary → send the email)
CATEGORY_LEVEL = {
    "burnout_and_fatigue": 1,
    "high_stress_and_overwhelm": 2,
    "isolation_and_hopelessness": 3,
}
LEVEL_NAME = {0: "none", 1: "low", 2: "moderate", 3: "high", 4: "crisis"}


def scan(text: str, *, root_only: bool = True) -> Dict[str, Any]:
    """Scan one chunk of text. Pure, fast, local. Returns a 1–4 severity level.

    Context-aware: hits inside benign idioms ("dying laughing", "phone is dead")
    are discarded, and when the text carries clear joking/laughter markers,
    hyperbole-prone phrases are dropped too — unless an explicit self-directed
    crisis phrase is present, which always stays serious.
    """
    # Normalize typographic quotes (OCR/macOS smart quotes) so "can’t" matches
    # the database's "can't", and collapse runs of whitespace/newlines.
    text = (text or "").replace("’", "'").replace("‘", "'")
    text = re.sub(r"\s+", " ", text)
    benign = _benign_spans(text)
    laugh_spans = [m.span() for m in _LAUGH_RE.finditer(text)]
    always_serious = bool(_ALWAYS_SERIOUS_RE.search(text))

    def _near_laugh(span: tuple) -> bool:
        return any(s <= span[1] + _JOKE_RADIUS and e >= span[0] - _JOKE_RADIUS
                   for s, e in laugh_spans)

    def _keep(m: "re.Match") -> bool:
        if _in_benign(m.span(), benign):
            return False
        phrase = m.group(0).lower()
        if not always_serious and phrase in _HYPERBOLE and _near_laugh(m.span()):
            return False
        return True

    joking = bool(laugh_spans)

    hits: List[Dict[str, str]] = []

    # Tier-3 first — highest stakes, bypasses gating.
    tier3_phrases = {m.group(0).lower() for m in _TIER3_RE.finditer(text) if _keep(m)}
    for phrase in sorted(tier3_phrases):
        hits.append({"phrase": phrase, "category": "crisis", "tier": "3"})

    categories: List[str] = []
    for category, pattern in _CATEGORY_RE.items():
        found = {m.group(0).lower() for m in pattern.finditer(text) if _keep(m)}
        if root_only:
            found |= {m.group(0).lower() for m in _ROOT_ONLY_RE[category].finditer(text) if _keep(m)}
        if found:
            categories.append(category)
            for phrase in sorted(found):
                hits.append({"phrase": phrase, "category": category, "tier": "1"})

    # Highest level wins. Tier-3 is always level 4.
    level = 4 if tier3_phrases else max((CATEGORY_LEVEL.get(c, 0) for c in categories), default=0)

    return {
        "tier3": bool(tier3_phrases),
        "matched": bool(hits),
        "categories": categories,
        "hits": hits,
        "level": level,
        "level_name": LEVEL_NAME[level],
        "joking_context": joking and not always_serious,
    }


# Quick counts for diagnostics / startup logging.
STATS = {
    "starters": len(_DATA["starters"]),
    "modifiers": len(_DATA["modifiers"]),
    "tier3": len(_DATA["standalone_tier_3_crisis"]),
    "roots": {c: len(r) for c, r in _DATA["roots"].items()},
}


if __name__ == "__main__":
    for t in [
        "what time does the library close",
        "i'm so burnt out and everything is pointless",
        "ngl i wanna unalive myself tonight",
        "lowkey cooked and running on empty for weeks",
    ]:
        r = scan(t)
        print(f"tier3={r['tier3']} cats={r['categories']!r:50} :: {t}")
