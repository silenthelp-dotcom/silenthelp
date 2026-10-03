"""Shared loader for the detection test harnesses.

Lets every harness run against either the working tree (default) or the code
as it exists at any git ref, so "before vs after" numbers are reproducible:

    python3 tests/detection/term_coverage.py               # working tree
    python3 tests/detection/term_coverage.py --ref HEAD    # last commit

--ref only READS from git (`git show REF:path`) into a temp directory; it never
checks anything out, so it is safe to use while other work is in progress.
"""
from __future__ import annotations

import atexit
import importlib
import inspect
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Files that make up the detection path. Missing ones (e.g. a module that did
# not exist yet at an old ref) are simply skipped.
_DETECTION_FILES = [
    "layer1.py", "detection.py", "context_signals.py",
    "layer1_db/level1_everyday_stress.json",
    "layer1_db/level2_major_stress.json",
    "layer1_db/level3_crisis.json",
    "layer1_db/typo_guard_words.txt",
    "layer1_db/common_words.txt",
]


def _extract_ref(ref: str) -> Path:
    out = Path(tempfile.mkdtemp(prefix=f"silenthelp-{ref.replace('/', '_')}-"))
    atexit.register(shutil.rmtree, out, ignore_errors=True)
    for rel in _DETECTION_FILES:
        try:
            blob = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=REPO,
                                  check=True, capture_output=True).stdout
        except subprocess.CalledProcessError:
            continue
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
    return out


def load(ref: str | None = None, impl: str | None = None):
    """Import layer1 (and detection/context_signals if present) from the
    working tree, a git ref, or an explicit directory. Returns the modules."""
    root = Path(impl).resolve() if impl else (_extract_ref(ref) if ref else REPO)
    for name in ("layer1", "detection", "context_signals"):
        sys.modules.pop(name, None)
    sys.path.insert(0, str(root))
    layer1 = importlib.import_module("layer1")
    try:
        context_signals = importlib.import_module("context_signals")
    except ImportError:
        context_signals = None
    return root, layer1, context_signals


def scanner(layer1):
    """scan(text, history) that degrades gracefully on older layer1 versions
    which had no notion of conversation history (they see the last message only)."""
    params = inspect.signature(layer1.scan).parameters
    if "history" in params:
        return lambda text, history=None: layer1.scan(text, history=history or [])
    return lambda text, history=None: layer1.scan(text)


def label_for(root: Path, ref: str | None, impl: str | None) -> str:
    if impl:
        return f"impl:{impl}"
    return f"ref:{ref}" if ref else "working-tree"
