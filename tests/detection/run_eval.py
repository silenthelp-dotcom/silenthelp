"""
Joke-vs-serious / context evaluation for SilentHelp detection.

Feeds every item of tests/detection/eval_set.json (181 labeled teen messages,
36 of them multi-message conversations) through detection and scores it:

  joke / benign  pass if final level <= 1  (no popup; "low" is logged only)
  ambiguous      pass if final level >= 1  (lean toward flagging)
  serious        pass if final level >= 2, or >= 3 when the item is "acute"
                 (high/crisis = the 988 / Crisis Text Line resources show)

Modes
  --mode offline  (default) the deterministic local path: layer1.scan(text,
                  history). This is what decides the tier-3 crisis fast path,
                  what the app falls back to when the model is unreachable or
                  switched off, and (after this change) the floor the model
                  can never go under. Free, instant, reproducible.
  --mode live     the full app pipeline (app._pipeline: L1 + Groq L2 + floors)
                  inside a fake /api/chat request so conversation history flows
                  exactly as it does from the chat UI. Uses the real provider
                  quota (Groq free tier: ~8K tokens/min), so it is paced and
                  cached; use --limit to sample.

Before/after: add --ref HEAD to run the last commit's detection code instead of
the working tree (read-only `git show`, nothing is checked out).

    python3 tests/detection/run_eval.py
    python3 tests/detection/run_eval.py --ref HEAD
    python3 tests/detection/run_eval.py --split holdout
    python3 tests/detection/run_eval.py --mode live --limit 30
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _impl  # noqa: E402

LEVEL = {"none": 0, "low": 1, "moderate": 2, "high": 3, "crisis": 4}
NAME = {v: k for k, v in LEVEL.items()}


def passes(item, level: int) -> bool:
    lab = item["label"]
    if lab in ("joke", "benign"):
        return level <= 1
    if lab == "ambiguous":
        return level >= 1
    return level >= (3 if item["acute"] else 2)


def run_offline(items, layer1):
    scan = _impl.scanner(layer1)
    out = []
    for it in items:
        r = scan(it["text"], it["history"])
        out.append({"level": r["level"], "why": _why(r)})
    return out


def _why(r) -> str:
    ctx = r.get("context") or {}
    bits = []
    if r.get("hits"):
        bits.append("hits=" + ",".join(sorted({h["phrase"] for h in r["hits"]}))[:80])
    for k in ("risk_signals", "joke_markers", "history_signals"):
        if ctx.get(k):
            bits.append(f"{k}={','.join(ctx[k])}")
    if ctx.get("adjustment"):
        bits.append(f"adj={ctx['adjustment']}")
    return " ".join(bits)


def run_live(items, root, limit, pace, cache_path):
    """Full app pipeline. app.py is imported from the repo root, but its
    `import layer1` / `import detection` resolve to `root` (first on sys.path),
    so --ref HEAD exercises the old detection code through the same app.py."""
    sys.path.insert(1, str(_impl.REPO))
    import app  # noqa: E402
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    # Cache per code version: editing detection code invalidates old answers.
    code_id = hashlib.sha1(b"".join(
        (root / f).read_bytes() for f in ("layer1.py", "detection.py", "context_signals.py",
                                          "layer1_db/level1_everyday_stress.json",
                                          "layer1_db/level2_major_stress.json",
                                          "layer1_db/level3_crisis.json")
        if (root / f).exists()) + (_impl.REPO / "app.py").read_bytes()).hexdigest()
    toggles = {"keyword": True, "semantic": True, "behavioral": True, "trend": True,
               "popup_policy": "balanced"}
    out = []
    for i, it in enumerate(items[:limit] if limit else items):
        key = hashlib.sha1(json.dumps([code_id, it["history"], it["text"]]).encode()).hexdigest()
        if key not in cache:
            msgs = [{"role": "user", "content": h} for h in it["history"]]
            # Mirror the chat UI: prior turns travel as `messages`, the new one as `message`.
            with app.app.test_request_context("/api/chat", method="POST",
                                              json={"message": it["text"], "messages": msgs}):
                l1, judgment, action = app._pipeline(it["text"], toggles=toggles)
            called_model = judgment.get("_source") not in ("layer1", "fast_reject")
            cache[key] = {"level": LEVEL.get(judgment.get("risk_level"), 3),
                          "why": f"src={judgment.get('_source')} l1={judgment.get('_l1_level')} "
                                 f"l2={judgment.get('_l2_level')} floor={judgment.get('_floor', '')}",
                          "resources": [r["contact"] for r in action.get("resources", [])]}
            cache_path.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
            if called_model and pace:
                time.sleep(pace)
        out.append(cache[key])
        print(f"  [{i + 1}/{limit or len(items)}] {NAME[cache[key]['level']]:8} {it['text'][:60]}", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref"); ap.add_argument("--impl")
    ap.add_argument("--mode", choices=("offline", "live"), default="offline")
    ap.add_argument("--split", choices=("all", "dev", "holdout"), default="all")
    ap.add_argument("--limit", type=int, default=0, help="live mode: only the first N items")
    ap.add_argument("--ids", help="comma-separated item ids to run (live sampling)")
    ap.add_argument("--pace", type=float, default=11.0,
                    help="live mode: seconds between model calls (Groq free tier ~8K tokens/min)")
    ap.add_argument("--save", help="write results JSON under tests/detection/results/<name>.json")
    ap.add_argument("-q", "--quiet", action="store_true", help="don't list failures")
    args = ap.parse_args()

    data = json.loads((HERE / "eval_set.json").read_text())
    items = [it for it in data["items"] if args.split == "all" or it["split"] == args.split]
    if args.ids:
        want = set(args.ids.split(","))
        items = [it for it in items if it["id"] in want]
    root, layer1, _ctx = _impl.load(args.ref, args.impl)
    label = _impl.label_for(root, args.ref, args.impl)

    if args.mode == "offline":
        res = run_offline(items, layer1)
    else:
        (HERE / "results").mkdir(exist_ok=True)
        tag = hashlib.sha1(label.encode()).hexdigest()[:8]
        res = run_live(items, root, args.limit, args.pace, HERE / "results" / f"live_cache_{tag}.json")
        items = items[: len(res)]

    groups = defaultdict(lambda: [0, 0])
    fails = []
    serious_n = serious_miss = acute_n = acute_miss = joke_n = joke_fa = 0
    for it, r in zip(items, res):
        ok = passes(it, r["level"])
        g = f"{it['kind']}/{it['label']}" if it["kind"] == "conversation" else it["kind"]
        groups[g][0] += 1; groups[g][1] += ok
        groups["ALL"][0] += 1; groups["ALL"][1] += ok
        if it["label"] == "serious":
            serious_n += 1; serious_miss += not ok
            if it["acute"]:
                acute_n += 1; acute_miss += r["level"] < 3
        if it["label"] in ("joke", "benign"):
            joke_n += 1; joke_fa += r["level"] >= 2
        if not ok:
            fails.append((it, r))

    pct = lambda a, b: f"{100 * a / b:5.1f}%" if b else "  n/a"
    print("=" * 90)
    print(f"SilentHelp joke-vs-serious eval  [{label}]  mode={args.mode} split={args.split}  n={len(items)}")
    print("=" * 90)
    for g in sorted(groups, key=lambda k: (k == "ALL", k)):
        n, ok = groups[g]
        print(f"  {g:28} {ok:4}/{n:<4} {pct(ok, n)}")
    print(f"  serious-message MISS rate     {serious_miss:4}/{serious_n:<4} {pct(serious_miss, serious_n)}"
          f"   (acute scored below high: {acute_miss}/{acute_n})")
    print(f"  joke/benign FALSE-ALARM rate  {joke_fa:4}/{joke_n:<4} {pct(joke_fa, joke_n)}")
    if not args.quiet:
        print("Failures:")
        for it, r in fails:
            want = ("<=low" if it["label"] in ("joke", "benign") else ">=low" if it["label"] == "ambiguous"
                    else ">=high" if it["acute"] else ">=moderate")
            hist = (" | ".join(it["history"]) + " >> ") if it["history"] else ""
            print(f"  {it['id']:9} {it['split']:7} want {want:10} got {NAME[r['level']]:8} :: {hist}{it['text']}")
            if r.get("why"):
                print(f"            {r['why']}")
    if args.save:
        (HERE / "results").mkdir(exist_ok=True)
        (HERE / "results" / f"{args.save}.json").write_text(json.dumps({
            "label": label, "mode": args.mode, "split": args.split,
            "groups": groups, "serious_miss": [serious_miss, serious_n],
            "acute_below_high": [acute_miss, acute_n], "joke_false_alarm": [joke_fa, joke_n],
            "results": [{"id": it["id"], "level": r["level"], "pass": passes(it, r["level"])}
                        for it, r in zip(items, res)]}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
