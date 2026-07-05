"""
SilentHelp — minimal account system (prototype)
===============================================

Email + password sign-in so a user's data (settings, history, baseline) lives
under their account on the server. Passwords are salted + PBKDF2-hashed; we
never store them in the clear.

Cross-device sync: data is keyed per user on the server, so any device pointed
at the SAME running server sees the same account data. True multi-device sync
needs the server hosted online (not just localhost) — the mechanism here is
ready for that.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from typing import Any, Dict, Optional

USERS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")
_LOCK = threading.RLock()
_ITERATIONS = 200_000


def _load() -> Dict[str, Any]:
    if not os.path.exists(USERS_PATH):
        return {"users": {}, "by_email": {}}
    try:
        with open(USERS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"users": {}, "by_email": {}}


def _save(data: Dict[str, Any]) -> None:
    tmp = USERS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, USERS_PATH)


def _hash(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), _ITERATIONS).hex()


def signup(email: str, password: str, name: str = "") -> Optional[str]:
    """Create an account. Returns the new uid, or None if the email is taken."""
    email = (email or "").strip().lower()
    if not email or "@" not in email or len(password or "") < 4:
        return None
    with _LOCK:
        data = _load()
        if email in data["by_email"]:
            return None
        uid = secrets.token_hex(8)
        salt = secrets.token_hex(8)
        data["users"][uid] = {
            "email": email,
            "name": (name or email.split("@")[0]).strip(),
            "salt": salt,
            "hash": _hash(password, salt),
        }
        data["by_email"][email] = uid
        _save(data)
        return uid


def login(email: str, password: str) -> Optional[str]:
    """Return uid on correct credentials, else None."""
    email = (email or "").strip().lower()
    with _LOCK:
        data = _load()
        uid = data["by_email"].get(email)
        if not uid:
            return None
        u = data["users"][uid]
        if secrets.compare_digest(_hash(password, u["salt"]), u["hash"]):
            return uid
        return None


def get_user(uid: str) -> Optional[Dict[str, Any]]:
    if not uid:
        return None
    with _LOCK:
        u = _load()["users"].get(uid)
        return {"uid": uid, "email": u["email"], "name": u["name"]} if u else None
