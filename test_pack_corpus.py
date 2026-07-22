"""
Layer 1 — full pack validation corpus (41,000 phrases).

The three regex packs each ship a `validation_corpus`: every phrase their
grammar is meant to match. This runs all of it through layer1.scan() and asserts
nothing scores 0.

A caveat worth keeping in mind: the corpus is machine-generated slot
permutations ("i kill him lately", "i'm shoot my professor after school"), not
real sentences. Passing it proves the engine is CONSISTENT with the packs' own
grammar — it does not prove real-world detection. test_layer1.py carries the
hand-written real-phrasing and precision cases, and that is the suite that
catches actual regressions.

Run:  python3 test_pack_corpus.py
"""

import json
import time
from pathlib import Path

import layer1

FIXTURE = Path(__file__).resolve().parent / "tests" / "fixtures" / "pack_validation_corpus.json"


def main() -> int:
    if not FIXTURE.exists():
        print(f"fixture missing: {FIXTURE}")
        return 1
    data = json.loads(FIXTURE.read_text())
    total = misses = 0
    t0 = time.time()
    for pack, spec in data.items():
        texts = spec["texts"]
        bad = [t for t in texts if layer1.scan(t)["level"] == 0]
        total += len(texts)
        misses += len(bad)
        print(f"  {pack:26} {len(texts) - len(bad)}/{len(texts)}")
        for t in bad[:5]:
            print(f"      MISS {t!r}")
    dt = time.time() - t0
    print(f"{total - misses}/{total} detected  ({dt:.1f}s, {total / dt:,.0f} scans/s)")
    return 1 if misses else 0


if __name__ == "__main__":
    raise SystemExit(main())
