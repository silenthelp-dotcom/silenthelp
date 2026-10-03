# SilentHelp detection tests

All commands run from the repo root. Nothing here commits, checks out or
calls a paid service. `--ref HEAD` reads the committed code with `git show`
(read-only) to give "before" numbers.

| What | Command |
|---|---|
| Term coverage: every database term + variants (typos, leet, spacing, emoji, slang) | `python3 tests/detection/term_coverage.py [--ref HEAD] [-v]` |
| Joke vs serious eval, offline (Layer 1 + context rules, free, instant) | `python3 tests/detection/run_eval.py [--split dev\|holdout\|all] [--ref HEAD]` |
| Same eval through the real app pipeline + Groq model (uses free-tier quota) | `python3 tests/detection/run_eval.py --mode live --split holdout --limit 30` |
| Crisis resources (988 / Text HOME to 741741) unchanged vs HEAD | `python3 tests/detection/test_resources.py` |
| Existing suites | `python3 test_layer1.py` and `python3 test_pack_corpus.py` |

`--save NAME` writes a JSON result to `tests/detection/results/`.

* `eval_set.json`: 181 labelled teen messages and conversations (joke,
  serious, ambiguous, benign, multi-message). Every 3rd item of each kind is
  in the `holdout` split. Tune rules on `dev` only and use `holdout` to check.
* Pass rule: joke/benign must score at most low. Ambiguous must score at
  least low. Serious must score at least moderate (acute ones at least high).
* After editing `layer1_db/*.json`, rebuild the typo guard lists:
  `pip install wordfreq && python3 build_typo_guard.py`.
