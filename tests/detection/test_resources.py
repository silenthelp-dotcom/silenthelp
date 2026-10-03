"""The crisis resources must keep appearing EXACTLY as they do today.

Checks the hard-coded constant (988 / Text HOME to 741741 / school counselor)
and that decide_response() returns the same action for every risk level as the
committed code (git HEAD) does. Needs no API key and makes no model calls.

    python3 tests/detection/test_resources.py            # compare with HEAD
    python3 tests/detection/test_resources.py --ref <git-ref>
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _impl  # noqa: E402

EXPECTED = [
    {"name": "988 Suicide & Crisis Lifeline", "contact": "Call or text 988", "available": "24/7"},
    {"name": "Crisis Text Line", "contact": "Text HOME to 741741", "available": "24/7"},
    {"name": "School counselor", "contact": "[[PRE_SELECTED_SCHOOL_COUNSELOR_CONTACT]]",
     "available": "School hours"},
]
LEVELS = ("none", "low", "moderate", "high", "crisis")


def _load_detection(root: Path):
    for name in ("detection", "layer1", "context_signals"):
        sys.modules.pop(name, None)
    sys.path.insert(0, str(root))
    try:
        return importlib.import_module("detection")
    finally:
        sys.path.remove(str(root))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="HEAD", help="git ref to compare decide_response() against")
    args = ap.parse_args()
    os.environ.setdefault("GROQ_API_KEY", "test-not-used")  # import only; no calls are made

    fails = []
    cur = _load_detection(_impl.REPO)
    if cur.CRISIS_RESOURCES != EXPECTED:
        fails.append("CRISIS_RESOURCES changed:\n" + json.dumps(cur.CRISIS_RESOURCES, indent=1))
    cur_actions = {lvl: cur.decide_response({"risk_level": lvl}) for lvl in LEVELS}
    for lvl in ("high", "crisis"):
        blob = json.dumps(cur_actions[lvl])
        for needle in ("Call or text 988", "Text HOME to 741741"):
            if needle not in blob:
                fails.append(f"decide_response({lvl!r}) no longer contains {needle!r}")

    try:
        ref_root = _impl._extract_ref(args.ref)
        if (ref_root / "detection.py").exists():
            ref = _load_detection(ref_root)
            for lvl in LEVELS:
                a, b = ref.decide_response({"risk_level": lvl}), cur_actions[lvl]
                if a != b:
                    fails.append(f"decide_response({lvl!r}) differs from {args.ref}:\n  ref={a}\n  now={b}")
            if ref.CRISIS_RESOURCES != cur.CRISIS_RESOURCES:
                fails.append(f"CRISIS_RESOURCES differs from {args.ref}")
            print(f"compared decide_response() for {len(LEVELS)} levels against {args.ref}")
        else:
            print(f"(no git ref {args.ref!r} available; checked the constants only)")
    except Exception as exc:  # no git / not a repo
        print(f"(git comparison skipped: {exc})")

    if fails:
        print("FAIL\n" + "\n".join(fails))
        return 1
    print("PASS: crisis resources (988 / Text HOME to 741741) unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
