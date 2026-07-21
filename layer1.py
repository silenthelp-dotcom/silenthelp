"""
SilentHelp — Layer 1 Keyword Engine
===================================

The cheap, fully-local pre-filter. NO AI. It loads the three level databases in
layer1_db/ (schema 4.0.0-regex) and compiles their regex templates ONCE at
import:

    layer1_db/level1_everyday_stress.json   -> level 1  (everyday stress)
    layer1_db/level2_major_stress.json      -> level 2  (major stress)
    layer1_db/level3_crisis.json            -> level 4  (crisis, bypasses gating)

Each level ships:
  * regex_templates — slot machines (<starter> <modifier> <state> <context>
    <time>) already compiled into a single alternation-per-slot pattern. A hit
    means a full, contextual sentence matched, so precision is high.
  * exact_high_precision_phrases — short standalone phrases that are signal on
    their own ("i wish i was dead", "screw this test").

Layer 1's only job: catch obvious signals fast and pass them to Layer 2. It is
deliberately dumb — string/regex matching, no understanding. Level-3 (crisis)
hits are flagged to BYPASS Layer 4's trend gate: a single hit is enough.

Alongside the database, three safety nets stay local to this file because they
are behaviour, not vocabulary:
  * a benign-idiom / joke guard so "dying laughing" never fires,
  * a spelling-tolerant pass over core emotion words ("depresed", "alon"),
  * a received-threat pattern (bullying aimed AT the user).

scan(text) -> {
    "tier3": bool,                 # crisis vocabulary present (level 3 db)
    "matched": bool,               # any L1 hit at all
    "categories": [str, ...],      # which level categories fired
    "hits": [{"phrase","category","tier"}, ...],
    "level": int,                  # 0-4 severity
    ...
}
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

_DB_DIR = Path(__file__).resolve().parent / "layer1_db"

# Each database file, and the 1-4 severity it maps onto. The db's own `level`
# is 1/2/3; the app's scale reserves 4 for "send the email" crisis, so the
# crisis database maps to 4.
_DB_FILES = [
    ("level1_everyday_stress.json", 1, "everyday_stress"),
    ("level2_major_stress.json", 2, "major_stress"),
    ("level3_crisis.json", 4, "crisis"),
]


def _alt(words: List[str]) -> str:
    """Regex alternation, longest-first so greedy matching prefers longer phrases."""
    return "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True))


def _load_db() -> List[Dict[str, Any]]:
    levels = []
    for fname, severity, category in _DB_FILES:
        with (_DB_DIR / fname).open(encoding="utf-8") as f:
            doc = json.load(f)
        patterns = [
            (t["id"], re.compile(t["regex"], re.IGNORECASE | re.UNICODE))
            for t in doc["regex_templates"]
        ]
        exact = doc.get("exact_high_precision_phrases", [])
        exact_re = (
            re.compile(rf"(?<!\w)(?:{_alt(exact)})(?!\w)", re.IGNORECASE | re.UNICODE)
            if exact
            else None
        )
        levels.append(
            {
                "file": fname,
                "severity": severity,
                "category": category,
                "name": doc.get("name", category),
                "bypasses_gate": bool(doc.get("bypasses_four_day_trend_gate")),
                "patterns": patterns,
                "exact_re": exact_re,
                "exact_count": len(exact),
                "template_count": len(patterns),
                "combinations": doc.get("statistics", {}).get(
                    "theoretical_phrase_combinations", 0
                ),
            }
        )
    return levels


_LEVELS = _load_db()

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


_WORD_RE = re.compile(r"[a-z']+")

# The fuzzy pass exists for MISSPELLINGS ("depresed", "alon"), not for words that
# merely look similar. Without a guard, edit-distance matching drags in ordinary
# English — "sacred"→scared, "drawing"→drowning, "beloved"→unloved,
# "painless"→pointless, "along"→alone, "tied"→tired — and every other sentence
# scores level 3. Two rules keep it honest:
#   1. A token that is ITSELF a real English word is never a misspelling of
#      something else. Checked against the system dictionary when present, plus
#      an always-on core list so behaviour never depends on the host OS.
#   2. Edit distance 1 only. Distance 2 caused ~73% of all false matches in a
#      198k-word dictionary audit and bought almost no real recall.
_FUZZY_STOPWORDS = frozenset("""
sacred scarred scored scaled drawing dawning downing drawling dropping
damned darned defined drained-out chained braided
painless countless jointless paintless
headless heedless helmless heatless endless useless-looking
beloved boneless hapless ageless baseless careless
envious noxious anxious-looking
along aloe alone-time aloft above
tied timed tired-eyes hired fired tiered tilted tinned tipped
empty-handed emptied temp tempt exempt
lost-and-found last list lust cost cast most post host
sand send said sat set sit bad had mad pad
band bend bond bind find fond fund hand land mind
lose loose close chose those whose house horse worse nurse
love dove cove cave gave gate late gaze maze live
score store stare share shore chore scare
number numb-ish lumber slumber
broke brook brown crown drown drawn brake break bread cream dream
""".split())


def _load_system_words() -> frozenset:
    """Real English words, used to reject 'this token is already a word' fuzzy
    matches. Optional — absent on some hosts, so the core list above still
    carries the common collisions on its own."""
    for p in ("/usr/share/dict/words", "/usr/dict/words"):
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                return frozenset(
                    w for w in (line.strip().lower() for line in f)
                    if w.isalpha() and len(w) >= 3
                )
        except OSError:
            continue
    return frozenset()


_SYSTEM_WORDS = _load_system_words()


def _is_real_word(tok: str) -> bool:
    """True if `tok` is itself ordinary English (so not a misspelling of an
    emotion word). Emotion words themselves are excluded — 'tired' is a real
    word AND a signal, and must keep matching."""
    if tok in _FUZZY_WORDS:
        return False
    return tok in _FUZZY_STOPWORDS or tok in _SYSTEM_WORDS


def _fuzzy_scan(text: str, benign: List[tuple] | None = None) -> Dict[str, int]:
    """Return {canonical_word: level} for any token that (after collapsing
    repeats) is within 1 edit of a core emotion word. Misspelling-tolerant.

    Tokens sitting inside a benign idiom span ("hopeless romantic", "dying
    laughing") are skipped — otherwise the fuzzy pass re-fires the very hits the
    context guard just discarded.
    """
    found: Dict[str, int] = {}
    benign = benign or []
    for m in _WORD_RE.finditer(text.lower()):
        tok = m.group(0)
        if len(tok) < 3 or _is_real_word(tok):
            continue
        if _in_benign(m.span(), benign):
            continue
        c = _collapse_repeats(tok)
        for word, lvl in _FUZZY_WORDS.items():
            cw = _collapse_repeats(word)
            # Short words (<4) must match collapsed-equal only — one edit on a
            # 3-letter word swallows half the language. Everything else allows a
            # single edit (or one adjacent transposition, via _lev1).
            if len(word) < 4:
                match = (c == cw)
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
    # "i'll kill you", "im gonna beat you up", "imma find you", "i want to hurt you".
    # The subject group must cover every contraction AND the going-to/gonna/finna
    # futures, or "i'm going to beat you up" slips through.
    r"\b(?:i(?:'?m| am|'?ma)?|imma)"
    r"(?:\s+(?:will|'?ll|wanna|want\s+to|gonna|finna|going\s+to|about\s+to|'?d))?\s+"
    r"(?:kill|hurt|beat|hit|end|destroy|find|get|stab|shoot|jump)\s+"
    r"(?:the\s+(?:shit|crap|hell)\s+out\s+of\s+)?(?:you|u|ya|yall|y'all)\b"
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
#   1 = not that critical   (everyday stress)
#   2 = somewhat            (major stress)
#   3 = critical            (received threat / fuzzy isolation+hopelessness)
#   4 = very critical       (crisis database → send the email)
CATEGORY_LEVEL = {
    "everyday_stress": 1,
    "major_stress": 2,
    "crisis": 4,
}
LEVEL_NAME = {0: "none", 1: "low", 2: "moderate", 3: "high", 4: "crisis"}


def scan(text: str, *, root_only: bool = True) -> Dict[str, Any]:
    """Scan one chunk of text. Pure, fast, local. Returns a 1–4 severity level.

    Context-aware: hits inside benign idioms ("dying laughing", "phone is dead")
    are discarded, and when the text carries clear joking/laughter markers,
    hyperbole-prone phrases are dropped too — unless an explicit self-directed
    crisis phrase is present, which always stays serious.

    `root_only` is accepted for call-site compatibility; the 4.0.0 databases are
    fully contextual, so there are no bare roots to opt into.
    """
    # Normalize typographic quotes (OCR/macOS smart quotes) so "can’t" matches
    # the database's "can't", lowercase, and collapse runs of whitespace, exactly
    # as each database's `matching.normalization` requires.
    text = (text or "").replace("’", "'").replace("‘", "'")
    text = re.sub(r"\s+", " ", text).strip().lower()
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
    categories: List[str] = []
    tier3 = False

    # Walk the three databases. Crisis (level 3 db) carries tier "3" and bypasses
    # the trend gate; the others are contextual signal for Layer 2 to judge.
    for lvl in _LEVELS:
        category = lvl["category"]
        tier = "3" if lvl["bypasses_gate"] else "1"
        found = set()
        for _tid, pattern in lvl["patterns"]:
            found |= {m.group(0) for m in pattern.finditer(text) if _keep(m)}
        if lvl["exact_re"] is not None:
            found |= {m.group(0) for m in lvl["exact_re"].finditer(text) if _keep(m)}
        if found:
            categories.append(category)
            if lvl["bypasses_gate"]:
                tier3 = True
            for phrase in sorted(found):
                hits.append({"phrase": phrase, "category": category, "tier": tier})

    # Spelling-tolerant core-word pass: catches "depresed", "im so alon", etc.
    # Suppressed when the message is clearly joking (unless always-serious).
    fuzzy_level = 0
    if not (joking and not always_serious):
        fuzzy = _fuzzy_scan(text, benign)
        for word, lvl_num in fuzzy.items():
            fuzzy_level = max(fuzzy_level, lvl_num)
            hits.append({"phrase": word, "category": "fuzzy", "tier": "1"})

    # A received threat is a safety concern → at least level 3 (high).
    if received_threat:
        hits.append({"phrase": threat_m.group(0).lower().strip(),
                     "category": "received_threat", "tier": "3"})
        if "received_threat" not in categories:
            categories.append("received_threat")

    # Highest level wins. Crisis database = 4. Received threat = 3.
    cat_level = max((CATEGORY_LEVEL.get(c, 0) for c in categories), default=0)
    level = 4 if tier3 else max(cat_level, fuzzy_level, 3 if received_threat else 0)

    return {
        "tier3": tier3,
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
    "schema": "4.0.0-regex",
    "levels": {
        lvl["category"]: {
            "file": lvl["file"],
            "name": lvl["name"],
            "severity": lvl["severity"],
            "templates": lvl["template_count"],
            "exact_phrases": lvl["exact_count"],
            "combinations": lvl["combinations"],
            "bypasses_gate": lvl["bypasses_gate"],
        }
        for lvl in _LEVELS
    },
    "total_combinations": sum(lvl["combinations"] for lvl in _LEVELS),
}


if __name__ == "__main__":
    for t in [
        "what time does the library close",
        "im really stressed out because of work today",
        "i'm completely overwhelmed by everything because of school lately",
        "i want to fucking kill myself tonight because i cannot take this anymore",
        "i wish i was dead",
        "bro im dying laughing lmao",
        "kill yourself loser",
        "im so depresed and alon",
    ]:
        r = scan(t)
        print(f"L{r['level']} {r['level_name']:9} tier3={r['tier3']!s:5} "
              f"cats={r['categories']!r:40} :: {t}")
