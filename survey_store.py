"""
SilentHelp Survey — anonymous response store
=============================================

Backs the public /survey page. Every response is anonymous by design: no
uid, no session, no cookie, no IP is ever written to a response record.
Same backend-selection pattern as hq_store.py / qa_store.py (Postgres when
DATABASE_URL is set, a local JSON file otherwise), but the shape here is
just an append-only list of response rows, not a mutable document — a
submission only ever adds a row, never edits or reads back another one.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any, Dict, List

SURVEY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "silenthelp_survey.json")
_LOCK = threading.RLock()

_DB_URL = os.environ.get("DATABASE_URL", "").strip()
if _DB_URL.startswith("postgres://"):
    _DB_URL = "postgresql://" + _DB_URL[len("postgres://"):]

_USE_DB = bool(_DB_URL)
_pool = None
_db_error = None


def _get_pool():
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool
        url = _DB_URL
        if "sslmode=" not in url:
            url += ("&" if "?" in url else "?") + "sslmode=require"
        pool = ConnectionPool(url, min_size=1, max_size=4,
                              kwargs={"autocommit": True}, open=False)
        pool.open(wait=True, timeout=15)
        with pool.connection() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS survey_responses ("
                "  id TEXT PRIMARY KEY,"
                "  answers JSONB NOT NULL,"
                "  would_use TEXT NOT NULL,"
                "  submitted_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        _pool = pool
    return _pool


def _use_db() -> bool:
    return _USE_DB and _db_error is None


# QUESTIONS is the source of truth the frontend renders from and the only
# place that needs editing to change the survey. answers submitted must
# match this length/order; anything else is rejected server-side.
QUESTIONS: List[str] = [
    "When's the last time you sat somewhere for 10 minutes doing literally nothing?",
    "If your phone died right now, what's the first thing you'd feel — relief, panic, or don't care?",
    "How many tabs or apps do you have open right now, roughly?",
    "You have an extra free hour today. Do you use it to rest, or to catch up on something?",
    "On a scale of \"mildly annoyed\" to \"irrationally furious,\" how do you react when someone interrupts you mid-task?",
    "Do you ever catch yourself holding your breath or clenching your jaw during the day?",
    "When was the last time you actually laughed — not just smiled at a text?",
    "If a friend described your week back to you, would it sound calm, busy, or chaotic?",
    "How many times today have you thought about something other than what you're currently doing?",
    "Be honest: are you sleeping because you're tired, or because you're trying to escape the day?",
]


def _file_load() -> Dict[str, Any]:
    if not os.path.exists(SURVEY_PATH):
        return {"responses": []}
    try:
        with open(SURVEY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"responses": []}


def _file_write(data: Dict[str, Any]) -> None:
    tmp = SURVEY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SURVEY_PATH)


def submit(answers: List[str], would_use: str) -> bool:
    """Append one anonymous response. Returns False on malformed input
    (wrong answer count) rather than raising, so a bad client request just
    fails the submission instead of 500ing."""
    if not isinstance(answers, list) or len(answers) != len(QUESTIONS):
        return False
    if would_use not in ("yes", "no", "maybe"):
        return False
    row = {
        "id": uuid.uuid4().hex[:12],
        "answers": [str(a).strip()[:2000] for a in answers],
        "would_use": would_use,
        "submitted_at": int(time.time() * 1000),
    }
    with _LOCK:
        global _db_error
        if _use_db():
            try:
                pool = _get_pool()
                with pool.connection() as conn:
                    conn.execute(
                        "INSERT INTO survey_responses (id, answers, would_use, submitted_at) "
                        "VALUES (%s, %s, %s, to_timestamp(%s / 1000.0))",
                        (row["id"], json.dumps(row["answers"]), row["would_use"], row["submitted_at"]),
                    )
                return True
            except Exception as e:  # noqa: BLE001 — fall back to file, don't 500 the submitter
                _db_error = str(e)
                print(f"[survey_store] DB write failed, using file fallback — {_db_error}", flush=True)
        data = _file_load()
        data["responses"].append(row)
        _file_write(data)
        return True


def count() -> int:
    """Total responses so far — used only for an internal sanity check, not
    shown to survey takers (nothing about aggregate results is exposed
    publicly to avoid influencing answers)."""
    with _LOCK:
        if _use_db():
            try:
                pool = _get_pool()
                with pool.connection() as conn:
                    row = conn.execute("SELECT count(*) FROM survey_responses").fetchone()
                    return int(row[0]) if row else 0
            except Exception:
                pass
        return len(_file_load().get("responses", []))
