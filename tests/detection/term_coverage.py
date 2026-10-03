"""
Term-coverage harness: feed EVERY signal term in the Layer-1 database through
the real local detection path (layer1.scan — the same call app._pipeline makes
first, and the one that alone decides the tier-3 crisis fast path).

What counts as a "term":
  * every phrase in the SIGNAL groups of layer1_db/*.json
      level1/level2 `states`, level3 `self_harm_actions`,
      level3 `reported_crisis_actions`
  * every `exact_high_precision_phrases` entry (all three files)
  * level3 `threat_actions`  (glue on purpose -> tested inside a threat frame,
      "he threatened to <term>", never bare: bare "kill me" is "this homework
      is killing me")
  * level3 `violent_actions` (glue on purpose -> tested with a person target,
      "im going to <term> him")
  * the fuzzy emotion-word list in layer1._FUZZY_WORDS
  * a short list of teen slang / euphemisms that are NOT in the database
      (kms, kys, unalive, sewerslide, self delete ...) -- tracked separately
Glue groups (starters, modifiers, time words, "because of school" contexts,
person targets, reporters) carry no signal alone and are not terms.

Each term is checked plain and in realistic variants (sentence, case,
punctuation, typos, leetspeak, stretched letters, spacing tricks, slang
contractions, emoji). Two numbers per variant:
  detected   level >= 1 (the app noticed at all)
  full       level >= the term's own database severity (1 / 2 / 4, or 3 for
             threats received)
Plus a false-positive guard list that must stay silent ("skill" vs "kill").

Run:
    python3 tests/detection/term_coverage.py            # working tree
    python3 tests/detection/term_coverage.py --ref HEAD # before (last commit)
    python3 tests/detection/term_coverage.py -v         # list every miss
Exit code is 1 if any plain term or any guard case fails.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _impl  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"

# ---------------------------------------------------------------- slang list
# (term, sentence frame, expected minimum level). Bare nouns / verbs with no
# subject ("suicide", "unalive", "sh") are only tested inside their frame: on
# their own they are as likely to be a topic, a video title or "shh".
FRAME_ONLY_SLANG = {"unalive", "sewerslide", "sewer slide", "off myself", "suicide",
                    "sh", "end it tonight"}
SLANG = [
    ("kms", "honestly {t} rn", 4),
    ("kys", "{t}", 3),                        # said TO the student -> bullying
    ("go kys", "{t}", 3),
    ("unalive myself", "i want to {t}", 4),
    ("unaliving myself", "ive been thinking about {t}", 4),
    ("unalive", "i just wanna {t}", 4),
    ("sewerslide", "thinking about {t} ngl", 4),
    ("sewer slide", "thinking about {t} ngl", 4),
    ("self delete", "i want to {t}", 4),
    ("self-delete", "i want to {t}", 4),
    ("off myself", "i want to {t}", 4),
    ("commit sudoku", "i want to {t}", 4),
    ("suicidal", "i feel {t}", 4),
    ("suicide", "i keep thinking about {t}", 4),
    ("selfharm", "i relapsed on {t}", 3),
    ("sh", "i relapsed on {t} last night", 3),
    ("killmyself", "i want to {t}", 4),
    ("wanna kms", "i {t}", 4),
    ("kmsss", "{t}", 4),
    ("end it tonight", "im going to {t}", 4),
]

# ------------------------------------------------- false-positive guard list
# (text, max allowed level). Substrings and look-alikes must not fire.
GUARDS = [
    ("i have a new skill", 0), ("skillful players win", 0),
    ("the skillet is hot", 0), ("we ran 5 kms today", 0),
    ("i gave up soda for lent", 0), ("i wish i didnt eat that much", 0),
    ("hes gonna pick me up at 5", 0), ("wat do u mean", 0), ("i ran 3.5 kms", 0),
    ("the sewer smells bad", 0), ("self checkout is broken", 0),
    ("let me just finish this", 0), ("omg wyd rn", 0),
    ("its like 20 kms away", 0), ("1.5 kms to the school", 0),
    ("kmsl that video 😂", 1), ("i studied all night", 0),
    ("die hard is a christmas movie", 0), ("my dice rolled a six", 0),
    ("he got a killstreak", 0), ("that was overkill", 0),
    ("hanging out with friends", 0), ("im hanging the poster", 0),
    ("i hung out by myself", 0), ("suicide doors on that car are cool", 0),
    ("she cut her hair", 0), ("cutting the cake now", 0),
    ("the therapist was nice", 0), ("im dyeing my hair", 0),
    ("diet coke please", 0), ("im on a diet", 0),
    ("assassins creed is fun", 0), ("i took my allergy pills", 0),
    ("i bought a rope for the swing", 0), ("the bridge was closed for traffic", 0),
    ("we jumped off the dock into the lake", 0), ("id kill for a coffee rn", 0),
    ("ill be there at 5", 0), ("the sheriff showed up", 0),
    ("she said shh", 0), ("my skin is so dry", 0), ("good game, ez kill", 0),
    ("the plants will die if you dont water them", 0),
    ("i killed the exam lets go", 0), ("this homework is killing me", 0),
    ("im dying laughing", 0), ("my phone is dead", 0),
    ("the character dies at the end", 0), ("i love myself", 0),
    ("i taught myself guitar", 0), ("i need to fill myself up before practice", 0),
    ("i cut myself a slice of cake", 0), ("im over the moon", 0),
]

LEET1 = str.maketrans({"a": "4", "e": "3", "i": "1", "o": "0"})
LEET2 = str.maketrans({"s": "$", "a": "@", "i": "!", "o": "0"})
SLANG_SUBS = [("i am ", "im "), ("i'm ", "im "), ("do not ", "dont "),
              ("don't ", "dont "), ("cannot ", "cant "), ("can't ", "cant "),
              ("want to ", "wanna "), ("going to ", "gonna "), ("you ", "u "),
              ("your ", "ur "), ("because ", "bc "), ("people", "ppl"),
              ("about ", "abt "), ("really ", "rly "), ("though", "tho")]


def _key_word(term: str) -> str:
    words = [w for w in term.replace("'", "").split() if w.isalpha()]
    return max(words, key=len) if words else ""


def _replace_word(s: str, word: str, new: str) -> str:
    import re
    return re.sub(rf"(?<![a-z']){re.escape(word)}(?![a-z'])", new, s, count=1)


def variants(term: str, sentence: str):
    """Yield (variant_name, text). Variants are applied to the sentence form."""
    kw = _key_word(term)
    yield "sentence", sentence
    yield "upper", sentence.upper()
    yield "mixed_case", "".join(c.upper() if i % 2 else c for i, c in enumerate(sentence))
    yield "title", sentence.title()
    yield "punct_bang", sentence + "!!!"
    yield "punct_ellipsis", sentence + "..."
    yield "punct_wrapped", "..." + sentence + "?!"
    yield "emoji_end", sentence + " 😭"
    yield "emoji_start", "💔 " + sentence
    yield "emoji_mid", sentence + " 😞 idk"
    yield "double_space", sentence.replace(" ", "  ")
    s2 = sentence
    for a, b in SLANG_SUBS:
        s2 = s2.replace(a, b)
    yield "slang_contract", s2 + " fr"
    if " " in term:
        yield "no_space", sentence.replace(term, term.replace(" ", ""))
        yield "hyphenated", sentence.replace(term, term.replace(" ", "-"))
    if len(kw) >= 3:
        yield "spaced_letters", _replace_word(sentence, kw, " ".join(kw))
        yield "leet", _replace_word(sentence, kw, kw.translate(LEET1)) if kw.translate(LEET1) != kw else None
        yield "leet_symbols", _replace_word(sentence, kw, kw.translate(LEET2)) if kw.translate(LEET2) != kw else None
        # stretch the last vowel ("diiiie", "myseeeelf")
        idx = max((i for i, c in enumerate(kw) if c in "aeiouy"), default=len(kw) - 1)
        yield "stretched", _replace_word(sentence, kw, kw[:idx] + kw[idx] * 4 + kw[idx + 1:])
        yield "stretched_end", _replace_word(sentence, kw, kw + kw[-1] * 3)
    if len(kw) >= 4:
        m = len(kw) // 2
        yield "typo_drop", _replace_word(sentence, kw, kw[:m] + kw[m + 1:])
        yield "typo_swap", _replace_word(sentence, kw, kw[:m - 1] + kw[m] + kw[m - 1] + kw[m + 1:])
        yield "typo_double", _replace_word(sentence, kw, kw[:m] + kw[m] + kw[m:])
    if len(term) <= 4 and term.isalpha():  # abbreviations: k.m.s / k m s
        yield "dotted", sentence.replace(term, ".".join(term))


def build_terms(root: Path, layer1):
    db = {}
    for fname, lvl in (("level1_everyday_stress.json", 1), ("level2_major_stress.json", 2),
                       ("level3_crisis.json", 3)):
        db[lvl] = json.loads((root / "layer1_db" / fname).read_text())
    terms = []  # dicts: term, source, expected, plain(bool), sentence

    def add(term, source, expected, sentence, plain=True, note=""):
        terms.append({"term": term, "source": source, "expected": expected,
                      "sentence": sentence, "plain": plain, "note": note})

    for lvl, frame, exp in ((1, "ngl im {t} rn", 1), (2, "honestly im {t} lately", 2)):
        for t in db[lvl]["components"]["states"]:
            add(t, f"level{lvl}.states", exp, frame.format(t=t))
    c3 = db[3]["components"]
    for t in c3["self_harm_actions"]:
        if t == "die":
            add(t, "level3.self_harm_actions", 4, "i just want to die", plain=False,
                note="bare 'die' is too common ('the plants will die'); tested in a first-person frame")
        else:
            add(t, "level3.self_harm_actions", 4, f"ok so honestly {t}, idk")
    for t in c3["reported_crisis_actions"]:
        add(t, "level3.reported_crisis_actions", 4, f"my friend said they want to {t}",
            plain=(t != "die"),
            note="bare 'die' tested only in the reporter frame" if t == "die" else "")
    for t in c3["threat_actions"]:
        add(t, "level3.threat_actions", 4, f"he threatened to {t}", plain=False,
            note="glue by design: tested inside a threat frame")
    for t in c3["violent_actions"]:
        words = t.split()
        if t in ("make disappear", "make pay", "put in the hospital"):
            phrase = f"{words[0]} him {' '.join(words[1:])}"
        else:
            phrase = f"{t} him"
        add(t, "level3.violent_actions", 4, f"im going to {phrase}", plain=False,
            note="glue by design: tested with a person target")
    received = {"go kill yourself", "you should kill yourself", "go kys"}
    for lvl, exp in ((1, 1), (2, 2), (3, 4)):
        for t in db[lvl]["exact_high_precision_phrases"]:
            e = 3 if t in received else exp
            add(t, f"level{lvl}.exact", e, f"ugh {t} tbh")
    nouns = {"depression", "anxiety", "panic", "burnout"}
    gerunds = {"crying", "struggling", "panicking", "drowning"}
    for w, lvl in getattr(layer1, "_FUZZY_WORDS", {}).items():
        frame = "i have so much {t}" if w in nouns else ("im {t}" if w in gerunds else "i feel {t}")
        add(w, "fuzzy_words", lvl, frame.format(t=w))
    for t, frame, exp in SLANG:
        add(t, "slang(not in db)", exp, frame.format(t=t), plain=t not in FRAME_ONLY_SLANG,
            note="tested in its frame only" if t in FRAME_ONLY_SLANG else "")
    return terms


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", help="git ref to test instead of the working tree (read-only)")
    ap.add_argument("--impl", help="directory containing layer1.py to test")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--save", help="write results JSON under tests/detection/results/<name>.json")
    args = ap.parse_args()

    root, layer1, _ctx = _impl.load(args.ref, args.impl)
    scan = _impl.scanner(layer1)
    terms = build_terms(root, layer1)
    t0 = time.time()

    per_group = defaultdict(lambda: {"terms": 0, "plain_det": 0, "plain_full": 0,
                                     "sent_det": 0, "sent_full": 0,
                                     "var_n": 0, "var_det": 0, "var_full": 0})
    per_variant = defaultdict(lambda: [0, 0, 0])  # n, detected, full
    missed_plain, missed_sentence, missed_variants = [], [], []
    db_terms = [t for t in terms if not t["source"].startswith("slang")]

    for t in terms:
        g = per_group[t["source"]]
        g["terms"] += 1
        exp = t["expected"]
        base = t["term"] if t["plain"] else t["sentence"]
        lv = scan(base)["level"]
        g["plain_det"] += lv >= 1
        g["plain_full"] += lv >= exp
        if lv < 1 or lv < exp:
            missed_plain.append((t["source"], t["term"], base, lv, exp))
        for name, text in variants(t["term"], t["sentence"]):
            if not text:
                continue
            lv = scan(text)["level"]
            if name == "sentence":
                g["sent_det"] += lv >= 1
                g["sent_full"] += lv >= exp
                if lv < exp:
                    missed_sentence.append((t["source"], t["term"], text, lv, exp))
            g["var_n"] += 1
            g["var_det"] += lv >= 1
            g["var_full"] += lv >= exp
            pv = per_variant[name]
            pv[0] += 1; pv[1] += lv >= 1; pv[2] += lv >= exp
            if lv < exp:
                missed_variants.append((t["source"], t["term"], name, text, lv, exp))

    guard_fail = []
    for text, mx in GUARDS:
        lv = scan(text)["level"]
        if lv > mx:
            guard_fail.append((text, lv, mx))
    elapsed = time.time() - t0

    def pct(a, b):
        return f"{100 * a / b:5.1f}%" if b else "  n/a"

    label = _impl.label_for(root, args.ref, args.impl)
    print("=" * 96)
    print(f"SilentHelp term coverage  [{label}]   {len(db_terms)} database terms + "
          f"{len(terms) - len(db_terms)} slang terms   ({elapsed:.1f}s)")
    print("=" * 96)
    print(f"{'source':34} {'terms':>5}  {'plain det':>9} {'plain full':>10}  "
          f"{'sentence':>8}  {'variants det':>12} {'variants full':>13}")
    tot = defaultdict(int)
    for src, g in per_group.items():
        print(f"{src:34} {g['terms']:5}  {pct(g['plain_det'], g['terms']):>9} "
              f"{pct(g['plain_full'], g['terms']):>10}  {pct(g['sent_full'], g['terms']):>8}  "
              f"{pct(g['var_det'], g['var_n']):>12} {pct(g['var_full'], g['var_n']):>13}")
        if not src.startswith("slang"):
            for k, v in g.items():
                tot[k] += v
    print("-" * 96)
    print(f"{'ALL DATABASE TERMS':34} {tot['terms']:5}  {pct(tot['plain_det'], tot['terms']):>9} "
          f"{pct(tot['plain_full'], tot['terms']):>10}  {pct(tot['sent_full'], tot['terms']):>8}  "
          f"{pct(tot['var_det'], tot['var_n']):>12} {pct(tot['var_full'], tot['var_n']):>13}")
    print(f"  plain: {tot['plain_full']}/{tot['terms']} at full severity, "
          f"{tot['plain_det']}/{tot['terms']} detected at all;  "
          f"variants: {tot['var_full']}/{tot['var_n']} full, {tot['var_det']}/{tot['var_n']} detected")
    print()
    print("By variant type (all terms incl. slang):   n   detected   full-severity")
    for name, (n, d, f) in sorted(per_variant.items(), key=lambda kv: kv[1][2] / max(1, kv[1][0])):
        print(f"  {name:16} {n:6} {pct(d, n):>9} {pct(f, n):>9}")
    print()
    print(f"False-positive guards: {len(GUARDS) - len(guard_fail)}/{len(GUARDS)} stayed silent")
    for text, lv, mx in guard_fail:
        print(f"  FP  level {lv} (max {mx}) :: {text}")
    print(f"Plain-form misses (below full severity): {len(missed_plain)}")
    for src, term, base, lv, exp in missed_plain[: (None if args.verbose else 40)]:
        print(f"  MISS {src:30} got {lv} want {exp} :: {base}")
    if args.verbose:
        print(f"Variant misses: {len(missed_variants)}")
        for row in missed_variants:
            print("  VMISS {0:28} {2:15} got {4} want {5} :: {3}".format(*row))
    else:
        print(f"Variant misses: {len(missed_variants)}  (run with -v to list)")

    if args.save:
        RESULTS_DIR.mkdir(exist_ok=True)
        out = {"label": label, "db_terms": tot["terms"],
               "plain_full": tot["plain_full"], "plain_detected": tot["plain_det"],
               "variants": tot["var_n"], "variants_full": tot["var_full"],
               "variants_detected": tot["var_det"],
               "per_group": per_group, "per_variant": per_variant,
               "guard_failures": guard_fail, "missed_plain": missed_plain,
               "missed_variants": missed_variants}
        (RESULTS_DIR / f"{args.save}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return 1 if (missed_plain or guard_fail) else 0


if __name__ == "__main__":
    raise SystemExit(main())
