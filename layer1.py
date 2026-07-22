"""
SilentHelp — Layer 1 Keyword Engine (schema silenthelp.merged/v2)
=================================================================

The cheap, fully-local pre-filter. NO AI, no network. It loads the three merged
databases in layer1_db/ and compiles everything ONCE at import.

Each merged database carries FOUR independent matchers, because no single one
catches everything:

  1. regex_rules      — the v1 regex-pack grammar. Filler-tolerant slot chains
                        ("i'm so extremely fucking burnt out today"). Very high
                        precision, but REQUIRES a first-person starter.
  2. regex_templates  — the legacy 4.0.0 slot templates. Extra recall on
                        contextual sentences the pack's grammar misses.
  3. exact phrases    — short standalone phrases ("i wish i was dead").
  4. root vocabulary  — every signal-bearing component phrase, matched DIRECTLY.

Matcher 4 is the one that makes detection starter-independent. The grammar rules
alone miss "kill myself", "kms", "commit suicide", "i wish i was dead" — all of
which score 0 without a starter, because the rules are built as
<starter><filler><action>. A user in crisis does not reliably supply a starter.
So the roots fire on their own and the final level is the MAX across all four.

Precision is preserved by three mechanisms, in order of authority:
  * negative_context_regex (from the pack) — jokes/idioms per level.
  * the local benign-idiom / laughter guard — "dying laughing", "phone is dead".
  * signal-vs-glue split — "him", "really", "today" are grammar glue and never
    fire alone; only signal groups produce standalone hits.
  * ambiguity guard — roots that are also ordinary English ("no way out",
    "dark thoughts") need the sentence to lack an innocent explanation.

Explicit self-directed crisis phrasing is NEVER suppressed by any guard.

scan(text) -> {
    "tier3": bool,                 # crisis vocabulary present (bypasses gating)
    "matched": bool,               # any L1 hit at all
    "categories": [str, ...],
    "hits": [{"phrase","category","tier"}, ...],
    "level": int,                  # 0-4 severity
    "level_name": str,
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


# ---------------------------------------------------------------------------
# Signal vs glue.
#
#   SIGNAL — means something on its own: "kill myself", "having a breakdown",
#            "kill me". These match bare and set the level.
#   GLUE   — meaningless alone: "him", "really", "today", "i am". Matching these
#            bare would fire on every sentence in English, so they NEVER produce
#            a standalone hit; they only feed the grammar rules and templates.
#
# Glue is an explicit deny-list AND signal an explicit allow-list, so a group
# added to a database later defaults to safe-but-silent rather than matching
# the word "today" at crisis level.
# ---------------------------------------------------------------------------
_SIGNAL_GROUPS = frozenset({
    "states", "self_harm_actions", "reported_crisis_actions", "threat_actions",
})
_GLUE_GROUPS = frozenset({
    "self_starters", "intent_starters", "modifiers", "intensifiers",
    "contexts", "time", "time_or_immediacy", "other_speakers",
    "person_targets", "violent_actions", "reason_context",
    "reason_context_third", "third_party_reporters", "threat_subjects",
})

# "violent_actions" is glue on purpose: "kill" / "hurt" / "end" alone are far
# too common ("kill the lights", "that hurt", "end of class"). They need a
# target, which the action+target pairing below supplies.

_MIN_ROOT_LEN = 4  # below this a "root" is a fragment, not a phrase
_SHORT_ROOT_ALLOW = frozenset({"kms"})  # unambiguous despite being short

# The databases store one canonical inflection ("hurt myself"), but people write
# the gerund just as often ("thinking about hurting myself"). Derive it rather
# than bloating the JSON with every form.
_VERB_ING = {
    "kill": "killing", "hurt": "hurting", "end": "ending", "take": "taking",
    "cut": "cutting", "harm": "harming", "stab": "stabbing", "shoot": "shooting",
    "attack": "attacking", "beat": "beating", "destroy": "destroying",
    "unalive": "unaliving", "delete": "deleting", "make": "making",
    "commit": "committing", "give": "giving", "leave": "leaving",
    "say": "saying", "stop": "stopping", "do": "doing", "die": "dying",
    "jump": "jumping", "threaten": "threatening", "starve": "starving",
    "burn": "burning", "hang": "hanging", "slit": "slitting",
    "poison": "poisoning", "bleed": "bleeding", "punish": "punishing",
    "overdose": "overdosing",
}

# People type "cant"/"can't" where the database says "cannot". Expanding the
# TEXT would shift match offsets and desync the benign-idiom spans, so each
# stored phrase instead gains its contracted variants here, at build time.
_CONTRACTIONS = [
    ("cannot", ["can't", "cant"]),
    ("do not", ["don't", "dont"]),
    ("does not", ["doesn't", "doesnt"]),
    ("did not", ["didn't", "didnt"]),
    ("will not", ["won't", "wont"]),
    ("i am", ["i'm", "im"]),
    ("i have", ["i've", "ive"]),
    ("i will", ["i'll", "ill"]),
    ("i would", ["i'd", "id"]),
    ("want to", ["wanna"]),
    ("going to", ["gonna"]),
    ("unable to", ["can't", "cant", "cannot"]),
]


def _contraction_variants(phrase: str) -> List[str]:
    out = []
    for full, shorts in _CONTRACTIONS:
        if full in phrase:
            out.extend(phrase.replace(full, s) for s in shorts)
    return out


def _inflect(phrase: str) -> List[str]:
    """`phrase` plus its gerund and contracted variants."""
    forms = [phrase]
    head, _, rest = phrase.partition(" ")
    ing = _VERB_ING.get(head)
    if ing and rest:
        forms.append(f"{ing} {rest}")
    for f in list(forms):
        forms.extend(_contraction_variants(f))
    return forms


def _root_phrases(doc: Dict[str, Any]) -> List[str]:
    """Every component phrase that is signal on its own, plus its variants."""
    out: List[str] = []
    for group, values in (doc.get("components") or {}).items():
        if group in _GLUE_GROUPS or group not in _SIGNAL_GROUPS:
            continue
        for v in values:
            if not isinstance(v, str):
                continue
            v = v.strip().lower()
            if len(v) >= _MIN_ROOT_LEN or v in _SHORT_ROOT_ALLOW:
                out.extend(_inflect(v))
    return out


def _pair_regex(doc: Dict[str, Any]) -> "re.Pattern | None":
    """Violent action + person target as one unit.

    "kill" is glue and "him" is glue, but "kill him" is a crisis phrase. Pairing
    the groups lets intent fire without a matching starter slot.
    """
    comp = doc.get("components") or {}
    raw = [a.lower() for a in comp.get("violent_actions", []) if isinstance(a, str)]
    actions = [f for a in raw for f in _inflect(a)]
    # bare verbs have no " rest" to inflect — add their gerunds explicitly
    actions += [_VERB_ING[a] for a in raw if a in _VERB_ING]
    targets = [t for t in comp.get("person_targets", []) if isinstance(t, str)]
    if not actions or not targets:
        return None
    return re.compile(
        rf"(?<!\w)(?:{_alt(actions)})\s+(?:{_alt(targets)})(?!\w)",
        re.IGNORECASE | re.UNICODE,
    )


def _load_db() -> List[Dict[str, Any]]:
    levels = []
    for fname, severity, category in _DB_FILES:
        with (_DB_DIR / fname).open(encoding="utf-8") as f:
            doc = json.load(f)

        # 1. v1 pack grammar rules (filler-tolerant, starter-required)
        rules = [
            (r["id"], re.compile(r["regex"]))
            for r in doc.get("regex_rules", [])
        ]
        # 2. legacy slot templates (extra recall)
        templates = [
            (t["id"], re.compile(t["regex"], re.IGNORECASE | re.UNICODE))
            for t in doc.get("regex_templates", [])
        ]
        # 3. exact standalone phrases
        exact = [e.lower() for e in doc.get("exact_high_precision_phrases", [])]
        exact_re = (
            re.compile(rf"(?<!\w)(?:{_alt(exact)})(?!\w)", re.IGNORECASE | re.UNICODE)
            if exact else None
        )
        # 4. root vocabulary — starter-independent
        roots = _root_phrases(doc)
        roots_re = (
            re.compile(rf"(?<!\w)(?:{_alt(roots)})(?!\w)", re.IGNORECASE | re.UNICODE)
            if roots else None
        )
        # per-level joke/idiom guard shipped by the pack
        neg = [re.compile(p, re.IGNORECASE) for p in doc.get("negative_context_regex", [])]

        levels.append({
            "file": fname,
            "severity": severity,
            "category": category,
            "name": doc.get("name", category),
            "bypasses_gate": bool(doc.get("bypasses_four_day_trend_gate")),
            "routing": doc.get("routing", {}),
            "rules": rules,
            "templates": templates,
            "exact_re": exact_re,
            "roots_re": roots_re,
            "pair_re": _pair_regex(doc),
            "neg": neg,
            "counts": {
                "rules": len(rules), "templates": len(templates),
                "exact": len(exact), "roots": len(roots),
            },
        })
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


# The fuzzy pass matches a bare word with no notion of WHOSE feeling it is, so
# "my dog looks sad" and "sad news about the team" scored the same level 3 as
# "i am depressed". Require first-person attribution shortly before the word.
# "i'm", "i feel", "im so", "i've been", "feeling", "me" — anything that ties
# the emotion to the speaker.
_SELF_ATTRIB_RE = re.compile(
    # Deliberately no "my" — it usually introduces someone else ("my dog looks
    # sad", "my friend is stressed"), which is not the user's own distress.
    r"(?:\bi\b|\bi'?m\b|\bim\b|\bme\b|\bmyself\b|\bive\b|\bi'?ve\b"
    r"|\bfeel\w*\b|\bbeen\b|\bam\b|\bi'?d\b)",
    re.IGNORECASE,
)
# How far back to look for that attribution. One short clause.
_ATTRIB_WINDOW = 40


def _fuzzy_scan(text: str, benign: List[tuple] | None = None) -> Dict[str, int]:
    """Return {canonical_word: level} for any token that (after collapsing
    repeats) is within 1 edit of a core emotion word. Misspelling-tolerant.

    Tokens sitting inside a benign idiom span ("hopeless romantic", "dying
    laughing") are skipped — otherwise the fuzzy pass re-fires the very hits the
    context guard just discarded.

    A hit also needs first-person attribution nearby, so describing a sad movie
    or a stressed friend doesn't read as the user's own distress.
    """
    found: Dict[str, int] = {}
    benign = benign or []
    for m in _WORD_RE.finditer(text.lower()):
        tok = m.group(0)
        if len(tok) < 3 or _is_real_word(tok):
            continue
        # Whose feeling is this? Look back one clause for a first-person marker.
        if not _SELF_ATTRIB_RE.search(text, max(0, m.start() - _ATTRIB_WINDOW), m.start()):
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
    | \btired\s+of\s+(?:waiting|hearing|listening|explaining|repeating|arguing|talking\s+about)\b
    | \b(?:sick\s+and\s+)?tired\s+of\s+(?:this\s+)?(?:weather|traffic|rain|noise|ads|commute)\b
    # "running on empty" is an idiom for TIREDNESS (level 1). The fuzzy pass
    # matches the bare word "empty" inside it as level-3 hopelessness ("i feel
    # empty"), which escalated 408 everyday-stress phrases to an urgent crisis
    # popup. Same for the other fuel/capacity idioms.
    | \b(?:running|runnin)\s+on\s+(?:empty|fumes)\b
    | \b(?:out\s+of|low\s+on)\s+(?:gas|steam|juice|fuel|spoons|bandwidth)\b
    | \bempty\s+(?:stomach|calories|nest|handed|promise|threat|seat|chair|room|box|bottle|cup|glass|tank|file|folder|list|space)\b
    | \b(?:the|my|his|her|their|an?)\s+empty\b
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


# ---------------------------------------------------------------------------
# Ambiguous roots — real ideation vocabulary that is ALSO ordinary English.
#
# "kill myself" means one thing. "no way out", "dark thoughts", "i can't do this
# anymore", "giving my stuff away" mean distress in one context and a parking
# garage, a band name, decaf, and moving to college in another. Adding them to
# the root vocabulary bought real recall and cost real precision, so they are
# only counted when nothing in the sentence explains them away.
# ---------------------------------------------------------------------------
_AMBIGUOUS_ROOTS = frozenset({
    "no way out", "no way out of this", "dark thoughts", "having dark thoughts",
    "cant do this anymore", "cannot do this anymore", "give up on everything",
    "want it to stop", "want it all to stop", "want everything to stop",
    "giving my stuff away", "giving away my things", "left a note",
    "wrote a note for my parents", "thinking about ending things",
    "thinking of ending things", "end things tonight", "ready to end things",
    "im a burden", "i am a burden", "burden to everyone", "burden to my family",
    "give up", "i give up", "gave up",
    "the world would be better off", "too much right now", "everything is too much",
    "cant stop crying", "cannot stop crying", "havent slept in days",
    "have not slept in days", "cant sleep at all", "chest feels tight",
    "chest is tight all the time", "cant get out of bed", "cannot get out of bed",
    # "running on empty" is NOT listed here: _BENIGN_RE now scopes it as a
    # tiredness idiom, so it lands at level 1 on its own. Listing it as
    # ambiguous too meant any mundane referent nearby ("in this group chat")
    # suppressed it to level 0 — a real everyday-stress signal, lost.
    "cant catch a break", "if i disappeared",
    "shutting everyone out", "pushing everyone away", "wouldnt be missed",
})

def _is_ambiguous(phrase: str) -> bool:
    """True if `phrase` IS or CONTAINS an ambiguous root.

    The matchers often return a span wider than the root itself ("i give up" for
    "give up on everything", "i cant do this anymore" for "cant do this
    anymore"), so equality alone lets the innocent sentence through.
    """
    if phrase in _AMBIGUOUS_ROOTS:
        return True
    return any(r in phrase or phrase in r for r in _AMBIGUOUS_ROOTS)


# A concrete everyday referent that explains an ambiguous phrase innocently.
_MUNDANE_OBJECT_RE = re.compile(
    r"\b(?:"
    r"parking\s+garage|garage|maze|elevator|escape\s+room|building|exit|"
    r"puzzle|video\s*game|game|level|boss\s+fight|quest|match|"
    r"movie|film|show|episode|book|novel|band|album|song|theme|character|plot|"
    r"decaf|coffee|caffeine|spicy|food|pizza|diet|"
    r"puppy|kitten|dog|cat|baby|newborn|"
    r"field\s+trip|homework|assignment|essay|project|worksheet|"
    r"workout|gym|run|marathon|practice|rehearsal|"
    r"wedding|birthday|party|concert|vacation|"
    r"college|dorm|move|moving|packing|donate|donating|thrift|"
    r"traffic|weather|rain|snow|allergies|construction|wifi|printer|laptop"
    r")\b",
    re.IGNORECASE,
)

# Several ambiguous phrases take their own object right after them, which is
# what makes them innocent: "want it to stop RAINING", "the world would be
# better off WITH MORE DOGS". A completion re-scopes the phrase onto something
# concrete. Genuine distress phrasing trails off or ends instead.
_INNOCENT_COMPLETION_RE = re.compile(
    r"\s*(?:"
    r"rain\w*|snow\w*|"
    r"with\s+(?:more|less|fewer|a|an|some|out)\b|"
    r"early\b|late\b|now\s+so\b|so\s+(?:everyone|we|they)\b|"
    r"it'?s?\s+(?:so|too|really)\b|"
    r"in\s+(?:this|the|that|my)\s+\w+|"
    r"im\s+switching\b|because\s+of\s+the\b|"
    r"at\s+(?:this|the|that)\s+\w+"
    r")",
    re.IGNORECASE,
)

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

    Runs all four matchers (pack grammar rules, legacy slot templates, exact
    phrases, and starter-independent root vocabulary) and takes the max, so a
    phrase is caught whether or not the user supplied a first-person starter.

    `root_only` is accepted for call-site compatibility.
    """
    text = (text or "").replace("’", "'").replace("‘", "'")
    text = re.sub(r"\s+", " ", text).strip().lower()
    if not text:
        return {"tier3": False, "matched": False, "categories": [], "hits": [],
                "level": 0, "level_name": "none", "joking_context": False,
                "received_threat": False}

    benign = _benign_spans(text)
    laugh_spans = [m.span() for m in _LAUGH_RE.finditer(text)]
    always_serious = bool(_ALWAYS_SERIOUS_RE.search(text))

    threat_m = _RECEIVED_THREAT_RE.search(text)
    received_threat = False
    if threat_m:
        near = any(s <= threat_m.end() + _JOKE_RADIUS and e >= threat_m.start() - _JOKE_RADIUS
                   for s, e in laugh_spans)
        received_threat = not near

    def _near_laugh(span: tuple) -> bool:
        return any(s <= span[1] + _JOKE_RADIUS and e >= span[0] - _JOKE_RADIUS
                   for s, e in laugh_spans)

    mundane = bool(_MUNDANE_OBJECT_RE.search(text))

    def _keep(m: "re.Match") -> bool:
        if _in_benign(m.span(), benign):
            return False
        phrase = m.group(0).lower()
        if not always_serious and phrase in _HYPERBOLE and _near_laugh(m.span()):
            return False
        # An ambiguous root may be matched as part of a slightly longer span
        # ("i cant do this anymore" contains "cant do this anymore"), so test
        # containment rather than equality — otherwise the guard silently
        # misses and the innocent sentence scores.
        if not always_serious and _is_ambiguous(phrase):
            if mundane or _near_laugh(m.span()):
                return False
            if _INNOCENT_COMPLETION_RE.match(text, m.end()):
                return False
        return True

    joking = bool(laugh_spans)

    hits: List[Dict[str, str]] = []
    categories: List[str] = []
    tier3 = False

    for lvl in _LEVELS:
        category = lvl["category"]
        tier = "3" if lvl["bypasses_gate"] else "1"
        # A level's own negative-context guard (jokes/idioms shipped by the
        # pack). Explicit crisis phrasing overrides it.
        if not always_serious and any(p.search(text) for p in lvl["neg"]):
            continue
        found = set()
        for _rid, pattern in lvl["rules"]:          # 1. pack grammar
            found |= {m.group(0) for m in pattern.finditer(text) if _keep(m)}
        for _tid, pattern in lvl["templates"]:      # 2. legacy templates
            found |= {m.group(0) for m in pattern.finditer(text) if _keep(m)}
        if lvl["exact_re"] is not None:             # 3. exact phrases
            found |= {m.group(0) for m in lvl["exact_re"].finditer(text) if _keep(m)}
        if lvl["roots_re"] is not None:             # 4. starter-independent roots
            found |= {m.group(0) for m in lvl["roots_re"].finditer(text) if _keep(m)}
        if lvl["pair_re"] is not None:              #    violent action + target
            found |= {m.group(0) for m in lvl["pair_re"].finditer(text) if _keep(m)}
        if found:
            categories.append(category)
            if lvl["bypasses_gate"]:
                tier3 = True
            for phrase in sorted(found):
                hits.append({"phrase": phrase, "category": category, "tier": tier})

    fuzzy_level = 0
    if not (joking and not always_serious):
        for word, lvl_num in _fuzzy_scan(text, benign).items():
            fuzzy_level = max(fuzzy_level, lvl_num)
            hits.append({"phrase": word, "category": "fuzzy", "tier": "1"})

    if received_threat:
        hits.append({"phrase": threat_m.group(0).lower().strip(),
                     "category": "received_threat", "tier": "3"})
        if "received_threat" not in categories:
            categories.append("received_threat")

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


STATS = {
    "schema": "silenthelp.merged/v2",
    "levels": {
        lvl["category"]: {
            "file": lvl["file"], "name": lvl["name"], "severity": lvl["severity"],
            "bypasses_gate": lvl["bypasses_gate"], **lvl["counts"],
        }
        for lvl in _LEVELS
    },
}
