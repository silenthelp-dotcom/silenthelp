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


# A fixed dummy salt used to burn the same PBKDF2 time when the email is unknown,
# so login can't be used as a timing oracle to enumerate which emails exist.
_DUMMY_SALT = "00" * 8


def signup(email: str, password: str, name: str = "") -> Optional[str]:
    """Create an account. Returns the new uid, or None if the email is taken
    or the details are invalid. Password minimum is 6 (matches the UI + policy)."""
    email = (email or "").strip().lower()
    if not email or "@" not in email or len(password or "") < 6:
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
    """Return uid on correct credentials, else None.

    Constant-work: even when the email is unknown we still run one PBKDF2 hash
    against a dummy salt, so response time doesn't reveal which emails have
    accounts (no user-enumeration timing oracle)."""
    email = (email or "").strip().lower()
    with _LOCK:
        data = _load()
        uid = data["by_email"].get(email)
        if not uid:
            # Burn equivalent time, then fail — same cost as a wrong password.
            _hash(password or "", _DUMMY_SALT)
            return None
        u = data["users"][uid]
        if secrets.compare_digest(_hash(password, u["salt"]), u["hash"]):
            return uid
        return None


def change_password(uid: str, current_password: str, new_password: str) -> bool:
    """Change a signed-in user's password. Requires the current password to be
    correct. Returns True on success; False if the user is unknown, the current
    password is wrong, or the new password is too short."""
    if not uid or len((new_password or "")) < 6:
        return False
    with _LOCK:
        data = _load()
        u = data["users"].get(uid)
        if not u:
            return False
        if not secrets.compare_digest(_hash(current_password or "", u["salt"]), u["hash"]):
            return False
        # New salt on every change, so an old leaked hash can't be reused.
        salt = secrets.token_hex(8)
        u["salt"] = salt
        u["hash"] = _hash(new_password, salt)
        _save(data)
        return True


def reset_password(email: str, new_password: str) -> bool:
    """Set a new password for an account by email, WITHOUT the old one.

    This backs a "forgot password" flow. It is only safe to call once the
    caller has proven control of the email (e.g. a verified reset link/code) —
    the route that calls this owns that check. Returns True on success."""
    email = (email or "").strip().lower()
    if len((new_password or "")) < 6:
        return False
    with _LOCK:
        data = _load()
        uid = data["by_email"].get(email)
        if not uid:
            return False
        u = data["users"][uid]
        salt = secrets.token_hex(8)
        u["salt"] = salt
        u["hash"] = _hash(new_password, salt)
        _save(data)
        return True


def email_exists(email: str) -> bool:
    email = (email or "").strip().lower()
    with _LOCK:
        return email in _load().get("by_email", {})


def get_user(uid: str) -> Optional[Dict[str, Any]]:
    if not uid:
        return None
    with _LOCK:
        u = _load()["users"].get(uid)
        return {"uid": uid, "email": u["email"], "name": u["name"]} if u else None


def delete_user(uid: str) -> bool:
    """Permanently remove an account. Frees the email for future re-signup."""
    if not uid:
        return False
    with _LOCK:
        data = _load()
        u = data["users"].pop(uid, None)
        if not u:
            return False
        data["by_email"].pop(u.get("email", ""), None)
        _save(data)
        return True
