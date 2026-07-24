"""
Clerk authentication for SilentHelp (Flask).

Clerk's CLI only scaffolds JS frameworks, so this is a manual integration. The
job is small and specific:

  * The browser signs in with Clerk's frontend JS and gets a short-lived session
    JWT (Clerk sets it as the `__session` cookie, and also exposes it to JS).
  * This module verifies that JWT against Clerk's public keys (JWKS) — no secret
    needed for verification, but we fetch the JWKS with the instance's issuer.
  * A verified token yields a stable Clerk user id (`sub`). We hand that back as
    the app's `uid`, so the existing per-user data store (user_<uid>.json) binds
    exactly as it did with the old file-based accounts — the battery, chat, and
    history all keep working unchanged.

Keys (from the Clerk Dashboard → API Keys), read from the environment:
  CLERK_SECRET_KEY       — sk_... — used for the Backend API (fetch user details).
                           NEVER sent to the client.
  CLERK_PUBLISHABLE_KEY  — pk_... — public; the frontend needs it. We also derive
                           the Frontend API / issuer from it so JWKS resolves
                           without a second env var.

If the keys are absent the module reports `configured() == False` and the app
falls back to "not signed in" rather than crashing — so the code can ship before
the keys are set.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.request
from typing import Any, Dict, Optional

try:
    import jwt  # PyJWT
    from jwt import PyJWKClient
    _HAVE_JWT = True
except Exception:  # PyJWT not installed yet
    _HAVE_JWT = False


def _env(*names: str) -> str:
    """First non-empty value among several env var names.

    Clerk's dashboard copy-buttons hand out the publishable key under the
    Next.js name NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY. This is a Flask app, so we
    also accept that spelling rather than silently failing when someone pastes
    the value Render/Clerk suggested.
    """
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return ""


def _secret() -> str:
    return _env("CLERK_SECRET_KEY")


def _publishable() -> str:
    return _env("CLERK_PUBLISHABLE_KEY", "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY")


def configured() -> bool:
    """True only when Clerk can actually run: keys present and PyJWT installed."""
    return _HAVE_JWT and bool(_secret()) and bool(_publishable())


def _frontend_api() -> str:
    """Clerk encodes the Frontend API host inside the publishable key.

    pk_test_<base64(host$)> / pk_live_<...>. Decoding it gives e.g.
    "clerk.example.com", from which the issuer and JWKS URL follow — so we don't
    need a separate FRONTEND_API env var.
    """
    pk = _publishable()
    if not pk:
        return ""
    try:
        b64 = pk.split("_", 2)[2]
        host = base64.b64decode(b64 + "==").decode("utf-8").rstrip("$")
        return host
    except Exception:
        return ""


def _issuer() -> str:
    host = _frontend_api()
    return f"https://{host}" if host else ""


_jwk_client: Optional["PyJWKClient"] = None


def _jwks_client() -> Optional["PyJWKClient"]:
    global _jwk_client
    if _jwk_client is None and _issuer():
        _jwk_client = PyJWKClient(f"{_issuer()}/.well-known/jwks.json")
    return _jwk_client


def verify_session(token: str) -> Optional[str]:
    """Verify a Clerk session JWT. Returns the Clerk user id (`sub`) or None.

    Checks the signature against Clerk's JWKS, the issuer, and expiry. A failure
    for any reason returns None — the caller treats that as "not signed in", and
    a malformed or forged token can never authenticate.
    """
    if not (configured() and token):
        return None
    client = _jwks_client()
    if not client:
        return None
    try:
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=_issuer(),
            options={"require": ["exp", "sub", "iat"]},
        )
        # Clerk tokens are short-lived; PyJWT already checks exp, but re-check the
        # not-before-ish `nbf`/`iat` skew defensively.
        if claims.get("iat", 0) > time.time() + 60:
            return None
        return claims.get("sub")
    except Exception:
        return None


def get_user(clerk_uid: str) -> Optional[Dict[str, Any]]:
    """Fetch a user's public profile from Clerk's Backend API (needs the secret).

    Returns {id, name, email} shaped like the old auth.get_user(), so callers
    that expect that dict keep working. Network/секret failures return None.
    """
    if not (configured() and clerk_uid):
        return None
    req = urllib.request.Request(
        f"https://api.clerk.com/v1/users/{clerk_uid}",
        headers={"Authorization": f"Bearer {_secret()}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            u = json.load(resp)
    except Exception:
        return None
    emails = u.get("email_addresses") or []
    primary = ""
    for e in emails:
        if e.get("id") == u.get("primary_email_address_id"):
            primary = e.get("email_address", "")
            break
    if not primary and emails:
        primary = emails[0].get("email_address", "")
    name = " ".join(x for x in [u.get("first_name"), u.get("last_name")] if x).strip()
    return {"id": u.get("id"), "name": name or primary.split("@")[0], "email": primary}


# The publishable key is safe to expose to the browser — the frontend needs it
# to boot Clerk.js.
def publishable_key() -> str:
    return _publishable()
