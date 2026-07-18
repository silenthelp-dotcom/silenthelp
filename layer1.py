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
# Spelling-tolerant core emotion words. Students misspell ("depresed"),
# double letters ("depresssed"), or drop letters ("alon"). Exact regex can't
# catch those, so for a small, high-value set of core mental-health words we
# fuzzy-match: collapse repeated letters, then allow up to 1 edit (Levenshtein)
# against each canonical word. Fast — it's a fixed ~40-word list, checked once.
#   category level: 1 burnout · 2 stress · 3 isolation/hopelessness
_FUZZY_WORDS = {
    # isolation / hopelessness (level 3)
    "depressed": 3, "depression": 3, "alone": 3, "lonely": 3, "hopeless": 3,
    "worthless": 3, "empty": 3, "numb": 3, "isolated": 3, "unwanted": 3,
    "unloved": 3, "abandoned": 3, "invisible": 3, "helpless": 3, "miserable": 3,
    "lost": 3, "broken": 3, "pointless": 3, "useless": 3,
    # stress / overwhelm (level 2)
    "stressed": 2, "anxious": 2, "anxiety": 2, "overwhelmed": 2, "panicking": 2,
    "panic": 2, "scared": 2, "afraid": 2, "terrified": 2, "drowning": 2,
    # burnout / fatigue (level 1)
    "exhausted": 1, "burntout": 1, "burnout": 1, "drained": 1, "tired": 1,
    "sad": 3, "crying": 2, "struggling": 2,
}
# words too short to fuzzy-match safely (1 edit would swallow common words)
_FUZZY_MIN_LEN = 4


def _collapse_repeats(w: str) -> str:
    """depresssed -> depresed  (squash 3+ repeats to 1, so double letters stay)."""
    return re.sub(r"(.)\1{1,}", r"\1", w)


def _lev1(a: str, b: str) -> bool:
    """True if `a` is within edit distance 1 of `b` (Damerau: also allows one
    adjacent transposition, e.g. 'exhuasted' vs 'exhausted'). Cheap early-outs."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    # find first differing char
    i = 0
    while i < min(la, lb) and a[i] == b[i]:
        i += 1
    if la == lb:
        # substitution: rest matches...
        if a[i + 1:] == b[i + 1:]:
            return True
        # ...or an adjacent transposition (swap a[i], a[i+1])
        return (i + 1 < la and a[i] == b[i + 1] and a[i + 1] == b[i]
                and a[i + 2:] == b[i + 2:])
    if la < lb:   # insertion into a
        return a[i:] == b[i + 1:]
    return a[i + 1:] == b[i:]  # deletion from a


def _lev2(a: str, b: str) -> bool:
    """Within edit distance 2 — used only for longer words (>=7 chars) where two
    typos are common and false positives are unlikely ('lonley' vs 'lonely')."""
    la, lb = len(a), len(b)
    if abs(la - lb) > 2:
        return False
    # simple DP, tiny strings
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[lb] <= 2


_WORD_RE = re.compile(r"[a-z']+")


def _fuzzy_scan(text: str) -> Dict[str, int]:
    """Return {canonical_word: level} for any token that (after collapsing
    repeats) is within 1 edit of a core emotion word. Misspelling-tolerant."""
    found: Dict[str, int] = {}
    for tok in _WORD_RE.findall(text.lower()):
        if len(tok) < 3:
            continue
        c = _collapse_repeats(tok)
        for word, lvl in _FUZZY_WORDS.items():
            cw = _collapse_repeats(word)
            # Short words (<4) must match closely (collapsed-equal only) to avoid
            # swallowing common words. Longer words allow 1 edit; 7+ allow 2.
            if len(word) < 4:
                match = (c == cw)
            elif len(word) >= 7:
                match = _lev1(c, cw) or _lev1(tok, word) or _lev2(tok, word)
            else:
                match = _lev1(c, cw) or _lev1(tok, word)
            if match:
                found[word] = lvl
                break
    return found

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
    | \b(?:so\s+|im\s+so\s+|i'?m\s+so\s+)?done\s+with\s+(?:this|the|that)\s+(?:show|season|episode|series|book|game|movie|level|semester|assignment|project|essay|homework)\b
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

# Threats DIRECTED AT the user (someone said this TO them) — bullying, threats,
# intimidation. This is a safety concern even though the user isn't the one in
# distress. "i want to kill you", "im going to hurt you", "you should die",
# "kill yourself" (told to them), "i'll beat you up".
_RECEIVED_THREAT_RE = re.compile(
    r"(?:"
    r"\b(?:i(?:'?m| am| will|'?ll| wanna| want to| gonna|'?d)?\s+"
    r"(?:kill|hurt|beat|hit|end|destroy|find|get|stab|shoot|jump)\s+(?:you|u|ya|yall|y'all)\b)"
    r"|\byou(?:'?re| are)?\s+(?:gonna|going to|finna)\s+(?:die|regret|pay|suffer)\b"
    r"|\b(?:you should|u should|go)\s+(?:die|kill\s+(?:yourself|urself|urslf))\b"
    r"|\bkill\s+(?:yourself|urself|urslf|yrself)\b"
    r"|\b(?:im|i am|imma|i'?ma)\s+(?:gonna|going to|finna)\s+(?:kill|hurt|beat|end)\s+(?:you|u|ya)\b"
    r"|\bwatch\s+your\s+back\b"
    r"|\byou(?:'?re| are)\s+(?:dead|done|finished)\b(?!\s*(?:lol|lmao|😂|🤣|inside|to me))"
    r"|\bi'?ll\s+make\s+you\s+(?:pay|suffer|regret)\b"
    r"|\bnobody\s+(?:likes|wants)\s+you\b"
    r"|\byou(?:'?re| are)\s+(?:worthless|nothing|pathetic|a\s+loser|ugly|stupid|a\s+freak)\b"
    r")",
    re.IGNORECASE,
)

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
    # A threat aimed AT the user (bullying / intimidation they received). A joke
    # marker right next to it ("i'll kill you lol") reads as banter; an explicit
    # threat with no laughter stays serious.
    threat_m = _RECEIVED_THREAT_RE.search(text)
    received_threat = False
    if threat_m:
        near_joke = any(s <= threat_m.end() + _JOKE_RADIUS and e >= threat_m.start() - _JOKE_RADIUS
                        for s, e in laugh_spans)
        received_threat = not near_joke

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

    # Spelling-tolerant core-word pass: catches "depresed", "im so alon", etc.
    # Suppressed when the message is clearly joking (unless always-serious).
    fuzzy_level = 0
    if not (joking and not always_serious):
        fuzzy = _fuzzy_scan(text)
        for word, lvl in fuzzy.items():
            fuzzy_level = max(fuzzy_level, lvl)
            hits.append({"phrase": word, "category": "fuzzy", "tier": "1"})

    # A received threat is a safety concern → at least level 3 (high).
    if received_threat:
        hits.append({"phrase": threat_m.group(0).lower().strip(),
                     "category": "received_threat", "tier": "3"})
        if "received_threat" not in categories:
            categories.append("received_threat")

    # Highest level wins. Tier-3 (self crisis) = 4. Received threat = 3.
    cat_level = max((CATEGORY_LEVEL.get(c, 0) for c in categories), default=0)
    level = 4 if tier3_phrases else max(cat_level, fuzzy_level, 3 if received_threat else 0)

    return {
        "tier3": bool(tier3_phrases),
        "matched": bool(hits),
        "categories": categories,
        "hits": hits,
        "level": level,
        "level_name": LEVEL_NAME[level],
        "joking_context": joking and not always_serious,
        "received_threat": received_threat,
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
