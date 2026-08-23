"""
SilentHelp — Prototype Web App
==============================

A thin web frontend over the prototype's two demoable pieces:

  • Detection  (templates/index.html) — Layer-2 semantic crisis detection over a
    message the user knowingly typed. The web layer makes NO safety decisions:
    it calls classify_message() (model flags) and decide_response() (hard-coded
    code decides), then renders whatever action comes back.

  • Dashboard  (templates/dashboard.html) — Layer-3 behavioral mock. Rule-based
    focus / mental-battery / burnout scoring against the user's baseline. No text
    is read; signals come from the dashboard sliders in this prototype.

  • Escalation — when a judgment routes to a human, the app DRAFTS a counselor
    email and shows it. Nothing is ever sent automatically: the user must press
    send. (Per product decision — no silent auto-escalation.)

PROTOTYPE — for the developer's own test messages only. Not for real students.
Classifier behavior must be reviewed by a licensed school counselor before any
real student use. No detection data leaves the device.

The Groq API key is read from the environment as GROQ_API_KEY (NVIDIA_API_KEY
still works as a legacy fallback). For local dev, put it in an untracked .env
file next to this script (see .gitignore) and it loads automatically — keep
real keys out of tracked source.

Run:
    cd ~/silenthelp-detection
    python3 app.py            # reads .env automatically
    # open http://127.0.0.1:5055
"""

from __future__ import annotations

import json
import os
import re
import secrets
import smtplib
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from email.message import EmailMessage

from flask import Flask, Response, jsonify, make_response, redirect, render_template, request, send_file, send_from_directory, session, stream_with_context
from werkzeug.middleware.proxy_fix import ProxyFix


def _load_local_env(filename: str = ".env") -> None:
    """Minimal .env loader (no dependency). Real shell env always wins."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_local_env()  # must run before detection builds its Groq client

import auth
import behavioral
import chat
import detection
import helper
import hq_store
import layer1
import qa_store
import store

app = Flask(__name__)
# Session-signing key. NEVER ship the old hardcoded default — a key that's
# public in the repo lets anyone forge a session cookie and impersonate any
# account. In production (Render sets PORT / RENDER) a missing SECRET_KEY is a
# hard error; in local dev we generate a random ephemeral key per process.
_secret = os.environ.get("SECRET_KEY")
if not _secret:
    _in_prod = bool(os.environ.get("RENDER") or os.environ.get("DATABASE_URL"))
    if _in_prod:
        raise RuntimeError(
            "SECRET_KEY is not set. Set it in the environment (Render dashboard) "
            "before starting — refusing to run with a guessable session key.")
    import secrets as _secrets
    _secret = _secrets.token_hex(32)  # ephemeral: dev sessions reset on restart
app.secret_key = _secret

# Session cookie hardening: not readable by JS, sent cross-site only as needed,
# HTTPS-only in production, and expiring rather than living forever.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER") or os.environ.get("DATABASE_URL")),
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    # Flask 2.2+ changed the static-file default to Cache-Control: no-cache
    # (forces a revalidation round-trip on every request, even for an
    # unchanging video file) instead of the old long-cache default. Measured
    # directly against production: the landing page's hero video was being
    # re-fetched multiple times per load partly because of this — every
    # range/metadata probe the browser made had to revalidate with the
    # server first. One hour is a reasonable middle ground for /static
    # (videos, css, fonts) — long enough to avoid needless revalidation
    # within a session, short enough that a redeployed asset isn't stuck
    # stale for long; the file's own etag/last-modified still let a client
    # skip a full re-download once the hour is up, it just won't need to
    # ask the server at all before then.
    SEND_FILE_MAX_AGE_DEFAULT=3600,
)

# Behind Cloudflare Tunnel: trust the X-Forwarded-* headers so Flask builds
# redirects/url_for with the real public host + https (not 127.0.0.1/http).
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)


@app.after_request
def _no_stale_html(resp: Response) -> Response:
    """Make browsers revalidate HTML pages so a new deploy is picked up at once.

    Symptom this fixes: after a deploy, other machines kept showing an OLD copy
    of /app because Flask sent no Cache-Control on HTML, and browsers then cache
    heuristically and serve a stale page for a long time ("it won't refresh").

    `no-cache` does NOT mean "don't store" — the browser may keep the copy but
    must revalidate with the server before using it, so a fresh deploy shows up
    on the next load. Only HTML is touched; static assets keep their own
    caching (they're immutable enough, and versioned when it matters).
    """
    ctype = resp.headers.get("Content-Type", "")
    if ctype.startswith("text/html"):
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp

DEFAULT_CONTACT = "School Counselor <counselor@school.edu>"
USERDATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "userdata")
os.makedirs(USERDATA_DIR, exist_ok=True)


def _is_local_request() -> bool:
    """True only for traffic from this Mac itself (the agent, a local browser).
    Tunnel visitors carry their real IP via X-Forwarded-For (ProxyFix).

    Security note: this is only a safe trust boundary if Render's edge is
    exactly one hop and doesn't pass through a client-supplied
    X-Forwarded-For verbatim (ProxyFix(x_for=1) trusts one hop). Verified
    directly against production: sending X-Forwarded-For: 127.0.0.1 to
    https://silenthelp.org/api/me does NOT get treated as local (confirmed
    2026-07-27) — Render's proxy overwrites/appends the header rather than
    passing an attacker value through. _owner_uid() below is also a second,
    independent guard: it only ever resolves to a single account when exactly
    one exists, so this bypass can't select among the (many) real accounts
    even in a hypothetical topology change."""
    return request.remote_addr in ("127.0.0.1", "::1")


def _owner_uid():
    """The Mac owner's account: SILENTHELP_OWNER email in .env, else the only
    account if exactly one exists. Local unauthenticated traffic (the native
    agent posts without cookies) is attributed to the owner so agent data and
    the owner's signed-in web account are ONE data set, not two."""
    email = os.environ.get("SILENTHELP_OWNER", "").strip().lower()
    if email:
        with auth._LOCK:
            uid = auth._load()["by_email"].get(email)
        if uid:
            return uid
    with auth._LOCK:
        users = auth._load()["users"]
    return next(iter(users)) if len(users) == 1 else None


# Endpoints anyone may call without an account: auth itself + stateless compute.
# /api/monitor is public so a friend's Mac agent (no login) still gets the
# context-checked verdict — the handler skips all storage for anonymous callers.
_PUBLIC_PATHS = {
    "/", "/app", "/chat", "/detection", "/today", "/download/agent",
    "/api/me", "/api/signup", "/api/login", "/api/logout",
    "/api/password/forgot", "/api/password/reset",
    "/api/scan", "/classify", "/api/behavioral", "/api/monitor", "/api/helper",
}


@app.before_request
def _bind_user_store():
    """Bind the store to the right per-user file, and refuse to serve personal
    data to anonymous REMOTE visitors (each friend must sign in — nobody ever
    sees anyone else's data)."""
    uid = session.get("uid")
    if not (uid and auth.get_user(uid)):
        uid = None
    if uid is None and _is_local_request():
        uid = _owner_uid()  # the Mac agent / local browser = the owner's data
    if uid is None:
        # A hosted deployment's agent isn't "local" — request.remote_addr is a
        # real IP, not 127.0.0.1 — so without this it always fell through to
        # anonymous and its behavioral data was silently discarded (agent
        # installed, dashboard/analytics stayed empty forever). The agent
        # proves which account it belongs to with a paired device token.
        token = request.headers.get("X-Device-Token", "")
        if token:
            paired_uid = auth.uid_for_device_token(token)
            if paired_uid and auth.get_user(paired_uid):
                uid = paired_uid

    if uid:
        store.set_data_file(os.path.join(USERDATA_DIR, f"user_{uid}.json"))
        return None
    store.set_data_file(None)

    # HQ (careers / team / founder admin) is shared company data, not personal
    # on-device data — always public so every visitor sees the same live site.
    if request.path.startswith("/api/hq"):
        return None

    # QA console (internal MVP-readiness dashboard) is likewise shared,
    # non-personal data — open, no login. On localhost this fell through to
    # _is_local_request()'s owner-account bypass above and worked fine, which
    # is exactly why it looked broken only in production: no such bypass
    # exists for a real remote visitor, so every /api/qa/* call 401'd before
    # ever reaching qa_console()'s own (already-removed) auth check.
    if request.path.startswith("/api/qa"):
        return None

    # Anonymous + remote: only public routes; personal APIs require sign-in.
    if request.path.startswith("/api/") and request.path not in _PUBLIC_PATHS:
        return jsonify({"error": "auth_required"}), 401
    return None


@app.route("/api/me")
def api_me():
    u = auth.get_user(session.get("uid"))
    if not u and _is_local_request():
        # On the owner's own Mac, an anonymous browser is the owner — the agent
        # posts without cookies too, and both map to the same account file.
        owner = _owner_uid()
        if owner:
            u = auth.get_user(owner)
            if u:
                u["via"] = "local"
    return jsonify({"signedIn": bool(u), "user": u})


_SIGNUP_ATTEMPTS: Dict[str, list] = {}   # ip -> [timestamps]; in-memory, best-effort
_SIGNUP_WINDOW_S = 60
_SIGNUP_MAX_PER_WINDOW = 10


def _signup_rate_limited(ip: str) -> bool:
    """A 409 vs 200 on /api/signup reveals whether an email is registered — an
    unavoidable property of any signup form that requires a self-chosen
    password, not something the response wording can hide. The practical
    mitigation is slowing down how fast one IP can probe emails, same idea as
    the reset-code attempt cap above."""
    now = time.time()
    hits = [t for t in _SIGNUP_ATTEMPTS.get(ip, []) if now - t < _SIGNUP_WINDOW_S]
    hits.append(now)
    _SIGNUP_ATTEMPTS[ip] = hits
    return len(hits) > _SIGNUP_MAX_PER_WINDOW


@app.route("/api/signup", methods=["POST"])
def api_signup():
    if _signup_rate_limited(request.remote_addr or ""):
        return jsonify({"error": "Too many attempts. Please wait a minute and try again."}), 429
    d = request.get_json(silent=True) or {}
    uid = auth.signup(d.get("email", ""), d.get("password", ""), d.get("name", ""))
    if not uid:
        return jsonify({"error": "That email is taken, or the details are invalid (password 6+ chars)."}), 409
    session["uid"] = uid
    # Without this, Flask issues a browser-SESSION cookie (dies when the tab/
    # browser closes) regardless of PERMANENT_SESSION_LIFETIME — that lifetime
    # only applies once permanent=True. This was the actual "sign-in doesn't
    # stick" bug: close the tab, cookie's gone, back to the sign-in screen.
    session.permanent = True
    # Seed the new account's profile with their real name (never a placeholder).
    user = auth.get_user(uid)
    store.set_data_file(os.path.join(USERDATA_DIR, f"user_{uid}.json"))
    store.update_settings({"name": user["name"]})
    return jsonify({"ok": True, "user": user})


@app.route("/api/login", methods=["POST"])
def api_login():
    d = request.get_json(silent=True) or {}
    uid = auth.login(d.get("email", ""), d.get("password", ""))
    if not uid:
        return jsonify({"error": "Wrong email or password."}), 401
    session["uid"] = uid
    # Without this, Flask issues a browser-SESSION cookie (dies when the tab/
    # browser closes) regardless of PERMANENT_SESSION_LIFETIME — that lifetime
    # only applies once permanent=True. This was the actual "sign-in doesn't
    # stick" bug: close the tab, cookie's gone, back to the sign-in screen.
    session.permanent = True
    return jsonify({"ok": True, "user": auth.get_user(uid)})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.pop("uid", None)
    return jsonify({"ok": True})


@app.route("/api/account/password", methods=["POST"])
def api_change_password():
    """Change the signed-in user's password. Requires the current password."""
    uid = session.get("uid")
    if not (uid and auth.get_user(uid)):
        return jsonify({"error": "not signed in"}), 401
    d = request.get_json(silent=True) or {}
    new = d.get("new_password", "")
    if len(new) < 6:
        return jsonify({"error": "New password must be at least 6 characters."}), 400
    if not auth.change_password(uid, d.get("current_password", ""), new):
        return jsonify({"error": "Current password is incorrect."}), 400
    return jsonify({"ok": True})


# Password reset ("forgot password").
#
# Proper reset needs a verified email link/code, which needs SMTP configured.
# When SMTP is set we email a one-time code; the user submits it with a new
# password. When SMTP is NOT set (current state), we cannot prove the person
# owns the email, so we DO NOT silently reset — that would let anyone change
# anyone's password by email alone. Instead we tell the user reset-by-email
# isn't available yet and to contact support. This keeps the flow honest.
_RESET_CODES: Dict[str, Any] = {}   # email -> (code, expires_at, attempts); in-memory, best-effort
# A 6-digit code has only 1,000,000 values. Unthrottled, that's exhaustible in
# well under the 15-minute window against a backend with no rate limiting.
# Lock the code out after a handful of wrong guesses instead of relying on the
# keyspace alone — the user just requests a fresh code if they fumble it.
_RESET_MAX_ATTEMPTS = 8


@app.route("/api/password/forgot", methods=["POST"])
def api_password_forgot():
    d = request.get_json(silent=True) or {}
    email = (d.get("email") or "").strip().lower()
    # Always return ok (don't reveal whether an email exists — no enumeration).
    if not (email and auth.email_exists(email)):
        return jsonify({"ok": True, "emailed": False})
    smtp_ready = bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"))
    if not smtp_ready:
        # Can't verify ownership without email delivery — say so plainly.
        return jsonify({"ok": True, "emailed": False,
                        "message": "Password reset by email isn't set up yet. "
                                   "Please contact silenthelp@silenthelp.org for help."})
    code = f"{secrets.randbelow(1000000):06d}"
    _RESET_CODES[email] = (code, time.time() + 900, 0)   # 15 min, 0 attempts so far
    _smtp_send(email, "Your SilentHelp reset code",
               f"Your password reset code is {code}. It expires in 15 minutes.")
    return jsonify({"ok": True, "emailed": True})


@app.route("/api/password/reset", methods=["POST"])
def api_password_reset():
    d = request.get_json(silent=True) or {}
    email = (d.get("email") or "").strip().lower()
    code = (d.get("code") or "").strip()
    new = d.get("new_password", "")
    rec = _RESET_CODES.get(email)
    if not rec:
        return jsonify({"error": "Invalid or expired code."}), 400
    stored_code, expires_at, attempts = rec
    if attempts >= _RESET_MAX_ATTEMPTS or time.time() >= expires_at:
        _RESET_CODES.pop(email, None)   # locked out or expired — request a fresh one
        return jsonify({"error": "Invalid or expired code."}), 400
    if not secrets.compare_digest(stored_code, code):
        _RESET_CODES[email] = (stored_code, expires_at, attempts + 1)
        return jsonify({"error": "Invalid or expired code."}), 400
    if not auth.reset_password(email, new):
        return jsonify({"error": "New password must be at least 6 characters."}), 400
    _RESET_CODES.pop(email, None)
    return jsonify({"ok": True})


@app.route("/api/account/delete", methods=["POST"])
def api_account_delete():
    """Permanently delete the signed-in account: credentials AND all data.
    The email is freed immediately, so re-signing up later works."""
    uid = session.get("uid")
    if not (uid and auth.get_user(uid)):
        return jsonify({"error": "not signed in"}), 401
    auth.delete_user(uid)
    data_file = os.path.join(USERDATA_DIR, f"user_{uid}.json")
    if os.path.exists(data_file):
        os.remove(data_file)
    session.pop("uid", None)
    return jsonify({"ok": True})


# --- Mac agent pairing -------------------------------------------------
#
# On a hosted deployment (silenthelp.org) the agent is a remote client, not
# "the same machine as the server" — so it needs a credential to prove which
# account its behavioral data belongs to. This token is that credential:
# generated here, pasted into the agent once, sent back on every request.

@app.route("/api/device/pair", methods=["POST"])
def api_device_pair():
    """Issue a fresh pairing token for the signed-in user. Generating a new one
    invalidates any previous token (one active device per account)."""
    uid = session.get("uid")
    if not (uid and auth.get_user(uid)):
        return jsonify({"error": "not signed in"}), 401
    token = auth.create_device_token(uid)
    if not token:
        return jsonify({"error": "could not create token"}), 500
    return jsonify({"token": token})


@app.route("/api/device/status")
def api_device_status():
    uid = session.get("uid")
    if not (uid and auth.get_user(uid)):
        return jsonify({"error": "not signed in"}), 401
    return jsonify({"paired": auth.has_device_token(uid)})


@app.route("/api/device/unpair", methods=["POST"])
def api_device_unpair():
    uid = session.get("uid")
    if not (uid and auth.get_user(uid)):
        return jsonify({"error": "not signed in"}), 401
    auth.revoke_device_token(uid)
    return jsonify({"ok": True})


@app.route("/pair-agent")
def pair_agent():
    """
    One-click Mac agent pairing. Replaces the old flow (Settings -> Mac Agent
    -> generate a token -> copy it -> paste into an NSAlert on the agent) with
    a single click: the agent's "Connect account..." menu item opens this page
    in the browser, where the user is (by definition) already signed in, and
    this issues a token and hands it straight back to the agent via the
    silenthelp:// URL scheme the agent registers as a handler for. No secret
    is ever shown on screen or copy-pasted.

    Not in _PUBLIC_PATHS: this must only ever run for a real signed-in session.
    """
    uid = session.get("uid")
    if not (uid and auth.get_user(uid)):
        # This flow only makes sense when the browser is already signed in
        # (that's the whole point — no code to type). If it isn't, there's
        # nothing to hand the agent yet; send them to sign in normally and
        # they can reopen "Connect account…" from the agent afterward.
        return redirect("/app")
    token = auth.create_device_token(uid)
    if not token:
        return ("Could not create a pairing token. Try again from "
                "Settings → Mac Agent in the app.", 500)
    return render_template("pair_agent.html", token=token)


@app.route("/robots.txt")
def robots():
    resp = make_response("User-agent: *\nAllow: /\nSitemap: https://silenthelp.org/sitemap.xml\n")
    resp.headers["Content-Type"] = "text/plain"
    return resp


@app.route("/sitemap.xml")
def sitemap():
    pages = ["", "app", "privacy", "terms"]
    urls = "".join(f"<url><loc>https://silenthelp.org/{p}</loc></url>" for p in pages)
    resp = make_response(
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
    resp.headers["Content-Type"] = "application/xml"
    return resp


@app.route("/privacy")
def privacy_page():
    return render_template("privacy.html")


@app.route("/terms")
def terms_page():
    return render_template("terms.html")


def _common():
    return {
        "model": detection.MODEL,
        "key_set": bool(os.environ.get("GROQ_API_KEY") or os.environ.get("NVIDIA_API_KEY")),
    }


_ORDER = {"none": 0, "low": 1, "moderate": 2, "high": 3, "crisis": 4}


# How many separate crisis detections inside 24h before the note sends itself.
AUTO_ESCALATE_AFTER = 3


def _maybe_auto_escalate(message: str) -> bool:
    """Send the counselor note automatically once crisis repeats.

    Requested behaviour: no confirmation, no countdown — once tier-3 crisis has
    fired AUTO_ESCALATE_AFTER times inside 24 hours, the note goes out on its
    own. This REVERSES the earlier "user must press send" rule, deliberately.

    Guards that remain, because they are about not making things worse:
      * one automatic note per 24h, so a person in a long crisis is not spammed
        and their counselor does not get a flood;
      * a single crisis message never triggers it — the threshold is a repeated
        pattern;
      * it needs a trusted contact and working SMTP, and it fails quietly.
        A failed auto-send must never break detection, and the manual draft
        path is still there as the fallback.
    """
    try:
        if store.crisis_count_24h() < AUTO_ESCALATE_AFTER:
            return False
        if store.auto_sent_recently(24):
            return False
        contact = (store.get_settings().get("contact") or "").strip()
        m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", contact)
        if not m:
            return False                     # nowhere to send it
        to_addr = m.group(0)
        name = (store.get_settings().get("name") or "").strip()
        snippet = (message or "").strip()[:140]
        body = (
            "Hi,\n\n"
            "This note was sent automatically by SilentHelp. Over the last day it "
            f"detected {AUTO_ESCALATE_AFTER} separate crisis-level signals in what "
            f"{name or 'this student'} wrote — a repeated pattern, not a single message.\n\n"
            f'The most recent one:\n\n  "{snippet}"\n\n'
            "They may not have asked for help directly. A gentle check-in soon would matter.\n\n"
            "— SilentHelp\n\n"
            "If this is an emergency, call or text 988 (US Suicide & Crisis Lifeline) "
            "or your local emergency number."
        )
        sent = _smtp_send(to_addr, "SilentHelp — automatic crisis alert", body)
        if sent:
            store.mark_auto_sent()
            store.record_event(1, "crisis", "auto_escalation")
        return sent
    except Exception:
        # Never let escalation failure take down the detection path.
        return False


def _pipeline(message: str, record: bool = False, toggles: dict | None = None):
    """
    Graded layered detection. Honors the Settings toggles.

    `toggles` lets a caller pass explicit layer settings. When omitted we read
    the bound user's store — but anonymous callers (a friend's agent) must NOT
    inherit the Mac owner's toggles, so they pass all-on defaults instead.

    Layer 1 (your keyword database, layer1_db/level{1,2,3}*.json) produces a
    graded signal:
      - a level-3 crisis phrase             -> "crisis"
      - an everyday/major stress sentence   -> "moderate"
      - nothing                             -> "none"
    Layer 2 (semantic model) reads meaning and returns its own level.

    Combine (so we get the FULL range of levels, not just crisis):
      - both layers off / L2 disabled      -> use L1's level (the database)
      - L2 unavailable (throttled/no key)   -> fall back to L1's level (NOT a blanket HIGH)
      - L2 says "none" (benign context)     -> trust it; a stray keyword like
                                               "cutting onions" won't force crisis
      - otherwise                           -> the higher of the two levels

    `record` persists category/level only (never raw text) for Layer-4 gating.
    """
    tog = toggles if toggles is not None else store.get_settings()["toggles"]
    keyword_on = tog.get("keyword", True)
    semantic_on = tog.get("semantic", True)

    l1 = layer1.scan(message) if keyword_on else {"tier3": False, "matched": False, "categories": [], "hits": [], "level": 0, "level_name": "none"}
    # Use the database's graded 1–4 severity (burnout→1, stress→2, isolation→3, crisis→4).
    l1_level = l1.get("level_name", "none")

    # FAST PATH: a Layer-1 tier-3 crisis phrase forces crisis anyway, so skip the
    # slow semantic model entirely — instant (~15ms) instead of a model round-trip.
    if keyword_on and l1["tier3"]:
        judgment = {
            "risk_level": "crisis",
            "categories": l1["categories"] or ["crisis"],
            "confidence": 1.0,
            "rationale": "Layer-1 crisis phrase matched.",
            "_source": "layer1", "_l1_level": "crisis", "_l2_level": "(skipped)",
            "_l1_tier3": True, "surface": "urgent",
        }
        action = detection.decide_response({"risk_level": "crisis"})
        if record:
            store.record_event(1, "crisis", (l1["categories"] or ["crisis"])[0])
            _maybe_auto_escalate(message)
        return l1, judgment, action

    # FAST PATH 2 (popup_policy="everything"): every L1 detection surfaces
    # anyway, so waiting on the semantic model just delays a popup whose outcome
    # is already decided. L2 costs 8-20s when the provider is slow or throttled
    # (measured: 16.8s for a level-1 phrase vs 0.09ms for L1) — the single
    # biggest source of "it takes a long time to pop up".
    #
    # L2 can only ever RAISE the level here, and under this policy low/moderate
    # both surface as gentle, so skipping it changes the popup for nobody except
    # the rare case where L2 would have escalated to high/crisis. That case is
    # already covered: tier-3 fast-pathed above, and the agent re-checks
    # /api/gating. Precision is unaffected — L1 scoring "none" still means no
    # popup, so jokes and benign text stay silent either way.
    _policy_pre = (tog.get("popup_policy")
                   or (store.get_settings().get("popup_policy", "balanced")
                       if toggles is None else "balanced"))
    if keyword_on and _policy_pre == "everything" and l1["level"] > 0:
        lvl = l1.get("level_name", "none")
        judgment = {
            "risk_level": lvl,
            "categories": l1["categories"] or [],
            "confidence": 0.9,
            "rationale": "Layer-1 match; semantic layer skipped for instant popup.",
            "_source": "layer1", "_l1_level": lvl, "_l2_level": "(skipped-fast)",
            "_l1_tier3": False,
            "surface": "urgent" if lvl in ("crisis", "high") else "gentle",
        }
        action = detection.decide_response({"risk_level": lvl})
        if record:
            store.record_event(1, lvl, (l1["categories"] or ["unknown"])[0])
        return l1, judgment, action

    if semantic_on:
        judgment = detection.classify_message(message)
        l2_failed = judgment.get("_source") == "fail_safe"
    else:
        judgment = {"risk_level": "none", "categories": [], "confidence": 0.0,
                    "rationale": "semantic layer disabled in settings", "_source": "disabled"}
        l2_failed = False

    l2_level = judgment.get("risk_level", "none")

    # THE SEMANTIC MODEL DECIDES. It reads intent — joke vs genuine — which the
    # keyword layer can't. Keywords only (a) fast-path explicit tier-3 crisis
    # above, and (b) act as the safety net when the model is off/unreachable.
    if not semantic_on:
        # Semantic layer turned off by the user → keyword result stands.
        final = l1_level
    elif l2_failed:
        # Model unreachable/errored. classify_message() already failed SAFE to
        # "high" — honor that. Take the HIGHER of the keyword level and the
        # fail-safe so a genuine concern the keywords can't see (abuse, ED,
        # psychosis…) still routes to a human instead of silently becoming none.
        fs_level = judgment.get("risk_level", "high")
        final = l1_level if _ORDER.get(l1_level, 0) >= _ORDER.get(fs_level, 0) else fs_level
    else:
        final = l2_level

    # KEYWORD FLOOR. The v4 database only matches a full contextual sentence
    # ("i'm completely overwhelmed by everything because of school lately") or a
    # curated high-precision phrase, so a hit is strong evidence — far stronger
    # than the loose bare-word matching this layer used to do. Letting the model
    # freely downgrade it meant real distress went silent: "i'm barely holding it
    # together and i need help today" scored L1=moderate, L2=low -> surface=none,
    # i.e. no popup for an explicit request for help.
    #
    # So the model may still VETO a hit outright (level "none" — it read a joke,
    # a quote, fiction, or negation, which is exactly its job), but it may not
    # quietly shave a genuine hit down to a level that never surfaces.
    if semantic_on and not l2_failed and l2_level != "none":
        if _ORDER.get(l1_level, 0) > _ORDER.get(final, 0):
            final = l1_level

    # A keyword-detected RECEIVED THREAT (someone threatening the user) is a
    # safety concern even if the model read it lower — floor it at "high" unless
    # the model actively judged it benign/joke (none). This keeps "i want to
    # kill you" surfacing while "i'll kill you lol" (model → none) stays quiet.
    received_threat = bool(l1.get("received_threat"))
    if received_threat and final != "none" and _ORDER.get(final, 0) < _ORDER["high"]:
        final = "high"
    if received_threat and not semantic_on:
        final = "high"

    categories = l1["categories"] or judgment.get("categories") or []
    # Popup policy for BACKGROUND monitoring (agent/OCR).
    #
    #   balanced (default) — interrupt only when it matters:
    #       crisis/high → urgent · moderate → gentle · low → logged silently
    #       (still detected; feeds trends/dashboard) · none → nothing.
    #
    #   everything — EVERY detection surfaces, including everyday stress
    #       ("i'm tired from studying"). Detection is unchanged; only the
    #       interrupt threshold moves. Low fires a gentle popup instead of
    #       logging quietly. Expect this to fire often during normal use.
    #
    # "none" never surfaces under either policy — there is nothing to show.
    policy = (tog.get("popup_policy")
              or (store.get_settings().get("popup_policy", "balanced")
                  if toggles is None else "balanced"))
    if policy == "everything":
        surface = ("urgent" if final in ("crisis", "high")
                   else "gentle" if final in ("moderate", "low") else "none")
    else:
        surface = ("urgent" if final in ("crisis", "high")
                   else "gentle" if final == "moderate" else "none")
    judgment = {**judgment, "risk_level": final, "_l1_level": l1_level,
                "_l2_level": l2_level, "_l1_tier3": bool(l1["tier3"]),
                "surface": surface, "received_threat": received_threat,
                "categories": categories or judgment.get("categories", [])}
    action = detection.decide_response({"risk_level": final})

    if record and final != "none":
        # Attribute the event to the layer that ACTUALLY produced the final
        # verdict. The semantic model now decides `final`, so:
        #   - semantic off / failed  -> L1 drove it (final == l1_level)
        #   - L1 independently reached the same level -> credit the keyword layer
        #   - otherwise the semantic layer is what caught it
        if not semantic_on or l2_failed:
            layer = 1
        elif l1["matched"] and _ORDER.get(l1_level, 0) >= _ORDER.get(final, 0):
            layer = 1
        else:
            layer = 2
        cat = (categories or ["signal"])[0]
        store.record_event(layer, final, cat)

    return l1, judgment, action


@app.route("/")
def landing():
    # Front page — Lithos hero rebuilt with looping video + liquid-glass chrome.
    #
    # Served as a STATIC file, not render_template(): the page is React/JSX
    # compiled in the browser by Babel, and JSX's `{{ ... }}` (an object literal
    # inside a prop) is indistinguishable from Jinja's print syntax, so Jinja
    # raises TemplateSyntaxError on it. There are no server-side variables in
    # this page, so there is nothing to render anyway.
    return send_from_directory(app.template_folder, "landing.html")


@app.route("/hero-lithos")
def hero_lithos():
    # The previous front page (Claude Design "SilentHelp Hero - Lithos"), kept
    # reachable so the rock/spotlight treatment isn't lost.
    return render_template("hero.html")


@app.route("/about")
def about():
    # Public about / team page. Self-contained static HTML (no Jinja vars),
    # served like the landing page.
    return send_from_directory(app.template_folder, "about.html")


@app.route("/stage")
def stage():
    # Demo film set: a wall of six laptops running Messages/Discord/Snapchat/
    # Instagram/WhatsApp/Slack. Messages type themselves, hit the REAL detector
    # via /classify, and raise popups on the laptop that fired — then the camera
    # pushes in. Built to be screen-recorded, not used; it is deliberately not
    # linked from the product nav. Press space (or add ?auto=1) to run.
    return render_template("stage.html")


@app.route("/careers")
def careers():
    # SilentHelp HQ — careers, team directory, and founder admin (shared, server-backed SPA).
    return render_template("careers.html")


# ----------------------------------------------------------------------------
# SilentHelp HQ — shared company state (positions, team, applicants, pipeline).
# Everyone who opens /careers sees the same live data (hq_store JSON file).
# ----------------------------------------------------------------------------

@app.route("/api/hq")
def hq_state():
    return jsonify(hq_store.state())


# ---- HQ teammate accounts (separate session key from product login) ----

def _hq_account():
    acc_id = session.get("hq_uid")
    return hq_store.account(acc_id) if acc_id else None


@app.route("/api/hq/me")
def hq_me():
    return jsonify({"account": _hq_account()})


@app.route("/api/hq/signup", methods=["POST"])
def hq_signup():
    d = request.get_json(silent=True) or {}
    res = hq_store.signup(d.get("name", ""), d.get("email", ""), d.get("password", ""))
    if not res:
        return jsonify({"error": "Enter a name, a valid email, and a 4+ character password."}), 400
    if res.get("error"):
        return jsonify({"error": res["error"]}), 409
    session["hq_uid"] = res["account"]["id"]
    return jsonify({"account": res["account"]})


@app.route("/api/hq/login", methods=["POST"])
def hq_login():
    d = request.get_json(silent=True) or {}
    res = hq_store.login(d.get("email", ""), d.get("password", ""))
    if not res:
        return jsonify({"error": "Wrong email or password."}), 401
    session["hq_uid"] = res["account"]["id"]
    return jsonify({"account": res["account"]})


@app.route("/api/hq/logout", methods=["POST"])
def hq_logout():
    session.pop("hq_uid", None)
    return jsonify({"ok": True})


@app.route("/api/hq/stream")
def hq_stream():
    """Server-Sent Events: push a small 'rev bumped' ping whenever HQ changes.
    The client refetches /api/hq on each ping. Falls back to polling if the
    stream drops (handled client-side)."""
    @stream_with_context
    def gen():
        last = -1
        # Prime with the current rev so a just-connected client syncs immediately.
        yield "retry: 3000\n\n"
        idle = 0
        while True:
            cur = hq_store.rev()
            if cur != last:
                last = cur
                idle = 0
                yield f"data: {cur}\n\n"
            else:
                # Wait for a write signal, but wake periodically to send a
                # keep-alive comment (stops proxies/Render from killing the conn).
                hq_store._rev_event.wait(timeout=15)
                hq_store._rev_event.clear()
                idle += 1
                if idle >= 1:
                    idle = 0
                    yield ": keepalive\n\n"
    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/hq/apply", methods=["POST"])
def hq_apply():
    d = request.get_json(silent=True) or {}
    fields = ["name", "email", "role", "resume", "portfolio", "linkedin", "github", "avail", "cover"]
    a = {k: str(d.get(k, "")).strip() for k in fields}
    if not a["name"] or not a["email"]:
        return jsonify(error="Name and email required"), 400
    return jsonify(hq_store.add_applicant(a))


@app.route("/api/hq/stage", methods=["POST"])
def hq_stage():
    d = request.get_json(silent=True) or {}
    return jsonify(hq_store.set_stage(d.get("id", ""), d.get("stage", "")))


@app.route("/api/hq/hire", methods=["POST"])
def hq_hire():
    d = request.get_json(silent=True) or {}
    return jsonify(hq_store.hire(d.get("id", "")))


@app.route("/api/hq/position", methods=["POST"])
def hq_position():
    d = request.get_json(silent=True) or {}
    pid = d.get("id") or None
    p = {k: d.get(k) for k in ["title", "dept", "loc", "type", "desc", "team", "resp", "skills", "pref", "tech", "projects"] if k in d}
    return jsonify(hq_store.save_position(p, pid))


@app.route("/api/hq/position/toggle", methods=["POST"])
def hq_position_toggle():
    d = request.get_json(silent=True) or {}
    return jsonify(hq_store.toggle_position(d.get("id", "")))


@app.route("/api/hq/position/delete", methods=["POST"])
def hq_position_delete():
    d = request.get_json(silent=True) or {}
    return jsonify(hq_store.delete_position(d.get("id", "")))


@app.route("/api/hq/member", methods=["POST"])
def hq_member():
    d = request.get_json(silent=True) or {}
    mid = d.get("id") or None
    m = {k: d.get(k) for k in ["name", "role", "dept", "joined", "skills", "projects", "progress", "contact", "bio", "photo"] if k in d}
    return jsonify(hq_store.save_member(m, mid))


@app.route("/api/hq/member/delete", methods=["POST"])
def hq_member_delete():
    d = request.get_json(silent=True) or {}
    return jsonify(hq_store.delete_member(d.get("id", "")))


@app.route("/api/hq/stats", methods=["POST"])
def hq_stats():
    d = request.get_json(silent=True) or {}
    return jsonify(hq_store.set_stats(d))


@app.route("/api/hq/task", methods=["POST"])
def hq_task():
    d = request.get_json(silent=True) or {}
    return jsonify(hq_store.add_task(d.get("id", ""), str(d.get("t", "")).strip(), d.get("due", "")))


@app.route("/api/hq/task/toggle", methods=["POST"])
def hq_task_toggle():
    d = request.get_json(silent=True) or {}
    # Prefer stable task id (from My Tasks); fall back to index (founder view).
    if d.get("taskId"):
        return jsonify(hq_store.toggle_task_by_id(d.get("id", ""), d.get("taskId")))
    return jsonify(hq_store.toggle_task(d.get("id", ""), int(d.get("idx", 0))))


@app.route("/api/hq/task/delete", methods=["POST"])
def hq_task_delete():
    d = request.get_json(silent=True) or {}
    return jsonify(hq_store.delete_task(d.get("id", ""), d.get("taskId", "")))


@app.route("/api/hq/notes/read", methods=["POST"])
def hq_notes_read():
    return jsonify(hq_store.mark_notes_read())


@app.route("/api/hq/plan", methods=["POST"])
def hq_plan():
    d = request.get_json(silent=True) or {}
    return jsonify(hq_store.set_plan(d.get("dept", ""), d.get("target", 0)))


# ---------------------------------------------------------------------------
# SilentHelp QA — MVP Readiness & AI Testing Console
# ---------------------------------------------------------------------------
# Open — no HQ login required. See qa_store.py for the storage layer and
# scoring rules.

def _qa_require_auth():
    """No-op: /qa is intentionally open, not gated behind HQ login."""
    return None


CONTEXT_LABELS = {
    "none": "no concern", "low": "low", "moderate": "moderate concern",
    "high": "high concern", "crisis": "crisis",
}


def _run_live_classification(message: str) -> Dict[str, Any]:
    """The QA console's runDetectionTest(input) bridge to the real pipeline.
    Never exposes model chain-of-thought — only the same judgment/action
    shape /classify already returns to the app, plus latency. Fails safe:
    if the pipeline throws, the caller gets a SYSTEM ERROR result rather
    than a silently wrong PASS."""
    t0 = time.time()
    l1, judgment, action = _pipeline(message)
    latency_ms = round((time.time() - t0) * 1000)
    severity = (judgment.get("risk_level") or "none").lower()
    context = ", ".join(judgment.get("categories") or []) or CONTEXT_LABELS.get(severity, severity)
    return {
        "context": context,
        "severity": severity,
        "confidence": judgment.get("confidence"),
        "recommendedAction": (action.get("action") or "").replace("_", " ").upper(),
        "latencyMs": latency_ms,
        "metadata": {
            "source": judgment.get("_source"),
            "l1Level": judgment.get("_l1_level"),
            "l2Level": judgment.get("_l2_level"),
            "tier3": judgment.get("_l1_tier3"),
            "rationale": judgment.get("rationale"),  # short safe explanation, not raw chain-of-thought
        },
    }


@app.route("/qa")
def qa_console():
    return render_template("qa.html")


@app.route("/api/qa/state")
def qa_state():
    err = _qa_require_auth()
    if err:
        return err
    return jsonify(qa_store.state())


@app.route("/api/qa/run-test", methods=["POST"])
def qa_run_test():
    """Runs ONE ad-hoc input through the live pipeline (AI Detection Lab's
    RUN TEST button) — not tied to a saved test case."""
    err = _qa_require_auth()
    if err:
        return err
    d = request.get_json(silent=True) or {}
    message = (d.get("message") or "").strip()
    if not message:
        return jsonify({"error": "empty message"}), 400
    try:
        result = _run_live_classification(message)
        result["mode"] = "live"
    except Exception as e:  # noqa: BLE001 — surface as a labeled system error, never a 500 the UI can't show
        result = {"context": "system error", "severity": "none", "confidence": 0,
                   "recommendedAction": "NONE", "latencyMs": 0, "metadata": {"error": str(e)},
                   "mode": "live", "error": True}
    return jsonify(result)


@app.route("/api/qa/test/<test_id>/run", methods=["POST"])
def qa_run_saved_test(test_id):
    """Runs one saved test case (from a suite) live and records the result."""
    err = _qa_require_auth()
    if err:
        return err
    d = qa_store.state()
    test = next((t for t in d["tests"] if t["id"] == test_id), None)
    if not test:
        return jsonify({"error": "test not found"}), 404
    try:
        actual = _run_live_classification(test["input"])
        source = "live"
    except Exception as e:  # noqa: BLE001
        actual = {"context": "system error", "severity": "none", "confidence": 0,
                   "recommendedAction": "NONE", "latencyMs": 0, "metadata": {"error": str(e)}, "error": True}
        source = "live"
    updated = qa_store.record_test_result(test_id, actual, source)
    return jsonify(updated)


@app.route("/api/qa/context-pair/<pair_id>/run", methods=["POST"])
def qa_run_context_pair(pair_id):
    err = _qa_require_auth()
    if err:
        return err
    d = qa_store.state()
    pair = next((p for p in d["contextPairs"] if p["id"] == pair_id), None)
    if not pair:
        return jsonify({"error": "pair not found"}), 404
    out = {}
    for side in ("a", "b"):
        try:
            actual = _run_live_classification(pair[side]["input"])
        except Exception as e:  # noqa: BLE001
            actual = {"context": "system error", "severity": "none", "confidence": 0,
                       "recommendedAction": "NONE", "latencyMs": 0, "metadata": {"error": str(e)}, "error": True}
        out[side] = qa_store.record_context_pair_result(pair_id, side, actual, "live")
    return jsonify(out["b"])  # both sides updated in the same doc; return the fresh pair


@app.route("/api/qa/suite/<suite_key>/run", methods=["POST"])
def qa_run_suite(suite_key):
    """Runs every test in a category live, sequentially, and records a run
    summary. Sequential (not threaded) so this stays gentle on the shared
    model rate limit — a suite is ~5-10 cases, a few seconds each is fine."""
    err = _qa_require_auth()
    if err:
        return err
    d = qa_store.state()
    tests = [t for t in d["tests"] if t["category"] == suite_key]
    if not tests:
        return jsonify({"error": "unknown suite"}), 404
    results = []
    for t in tests:
        try:
            actual = _run_live_classification(t["input"])
        except Exception as e:  # noqa: BLE001
            actual = {"context": "system error", "severity": "none", "confidence": 0,
                       "recommendedAction": "NONE", "latencyMs": 0, "metadata": {"error": str(e)}, "error": True}
        updated = qa_store.record_test_result(t["id"], actual, "live")
        results.append(updated)
    acc = _hq_account()
    run = qa_store.add_run(suite_key, results, acc.get("name", "") if acc else "")
    return jsonify({"run": run, "tests": results})


@app.route("/api/qa/checklist/toggle", methods=["POST"])
def qa_checklist_toggle():
    err = _qa_require_auth()
    if err:
        return err
    d = request.get_json(silent=True) or {}
    item = qa_store.toggle_checklist(d.get("category", ""), d.get("item", ""))
    if item is None:
        return jsonify({"error": "unknown checklist item"}), 404
    return jsonify(item)


@app.route("/api/qa/checklist/note", methods=["POST"])
def qa_checklist_note():
    err = _qa_require_auth()
    if err:
        return err
    d = request.get_json(silent=True) or {}
    item = qa_store.set_checklist_note(d.get("category", ""), d.get("item", ""), d.get("note", ""))
    if item is None:
        return jsonify({"error": "unknown checklist item"}), 404
    return jsonify(item)


@app.route("/api/qa/privacy-check", methods=["POST"])
def qa_privacy_check():
    err = _qa_require_auth()
    if err:
        return err
    d = request.get_json(silent=True) or {}
    status = d.get("status", "NOT TESTED")
    if status not in ("PASS", "FAIL", "NOT TESTED"):
        return jsonify({"error": "invalid status"}), 400
    item = qa_store.set_privacy_check(d.get("item", ""), status, d.get("note", ""))
    if item is None:
        return jsonify({"error": "unknown privacy check"}), 404
    return jsonify(item)


@app.route("/api/qa/resource-test", methods=["POST"])
def qa_resource_test():
    err = _qa_require_auth()
    if err:
        return err
    d = request.get_json(silent=True) or {}
    return jsonify(qa_store.add_resource_test(d))


@app.route("/api/qa/simulator-log", methods=["POST"])
def qa_simulator_log():
    err = _qa_require_auth()
    if err:
        return err
    d = request.get_json(silent=True) or {}
    return jsonify(qa_store.log_simulator_session(d))


@app.route("/api/qa/bug", methods=["POST"])
def qa_bug_create():
    err = _qa_require_auth()
    if err:
        return err
    d = request.get_json(silent=True) or {}
    if not (d.get("title") or "").strip():
        return jsonify({"error": "title required"}), 400
    return jsonify(qa_store.add_bug(d))


@app.route("/api/qa/bug/<bug_id>", methods=["POST"])
def qa_bug_update(bug_id):
    err = _qa_require_auth()
    if err:
        return err
    d = request.get_json(silent=True) or {}
    updated = qa_store.update_bug(bug_id, d)
    if updated is None:
        return jsonify({"error": "bug not found"}), 404
    return jsonify(updated)


@app.route("/api/qa/bug/<bug_id>/delete", methods=["POST"])
def qa_bug_delete(bug_id):
    err = _qa_require_auth()
    if err:
        return err
    if not qa_store.delete_bug(bug_id):
        return jsonify({"error": "bug not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/qa/improvement", methods=["POST"])
def qa_improvement_create():
    err = _qa_require_auth()
    if err:
        return err
    d = request.get_json(silent=True) or {}
    if not (d.get("title") or "").strip():
        return jsonify({"error": "title required"}), 400
    return jsonify(qa_store.add_improvement(d))


@app.route("/api/qa/improvement/<item_id>", methods=["POST"])
def qa_improvement_update(item_id):
    err = _qa_require_auth()
    if err:
        return err
    d = request.get_json(silent=True) or {}
    updated = qa_store.update_improvement(item_id, d)
    if updated is None:
        return jsonify({"error": "improvement not found"}), 404
    return jsonify(updated)


@app.route("/api/qa/improvement/<item_id>/delete", methods=["POST"])
def qa_improvement_delete(item_id):
    err = _qa_require_auth()
    if err:
        return err
    if not qa_store.delete_improvement(item_id):
        return jsonify({"error": "improvement not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/qa/gate")
def qa_gate():
    err = _qa_require_auth()
    if err:
        return err
    return jsonify(qa_store.compute_gate())


@app.route("/api/qa/score")
def qa_score():
    err = _qa_require_auth()
    if err:
        return err
    return jsonify(qa_store.readiness_score())


@app.route("/api/qa/version", methods=["POST"])
def qa_version():
    err = _qa_require_auth()
    if err:
        return err
    d = request.get_json(silent=True) or {}
    v = (d.get("version") or "").strip()
    if not v:
        return jsonify({"error": "version required"}), 400
    qa_store.set_version(v)
    return jsonify({"ok": True, "version": v})


@app.route("/app")
def app_home():
    # The SilentHelp app UI (ported from the Claude Design "SilentHelp App").
    return render_template("app.html", **_common())


@app.route("/today")
def today():
    metrics = behavioral.compute_metrics(behavioral.DEFAULT_TODAY)
    return render_template(
        "today.html",
        active="today",
        baseline=behavioral.BASELINE,
        today=behavioral.DEFAULT_TODAY,
        metrics=metrics,
        trend=behavioral.weekly_trend(metrics["focus_score"]),
        **_common(),
    )


@app.route("/chat")
def chat_page():
    # Keep everyone inside the real app — deep-link to its Coping Chat screen.
    # IMPORTANT: a RELATIVE 302 (Location: /app#chat) so the browser stays on
    # whatever host it's actually on (e.g. the Cloudflare URL). An absolute
    # redirect would bounce friends to 127.0.0.1 → "Not found".
    resp = redirect("/app#chat", code=302)
    resp.autocorrect_location_header = False  # Flask: don't rewrite to absolute
    resp.headers["Location"] = "/app#chat"
    return resp


@app.route("/detection")
def detection_page():
    return render_template("detection.html", active="detection", **_common())


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Coping chat turn. Generates a supportive reply AND runs the same detection
    authority used everywhere, so crisis routing is consistent. The reply is
    model text; the action is hard-coded code.
    """
    data = request.get_json(silent=True) or {}
    history = data.get("messages") or []
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "empty message"}), 400

    # Run detection (L1+L2) and the supportive reply IN PARALLEL — they're both
    # model round-trips, so this roughly halves the wait.
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_reply = ex.submit(chat.reply, [*history, {"role": "user", "content": message}])
        l1, judgment, action = _pipeline(message, record=True)
        reply = fut_reply.result()
    store.add_chat("user", message)
    store.add_chat("assistant", reply)
    return jsonify({"reply": reply, "judgment": judgment, "action": action, "l1": l1})


@app.route("/api/helper", methods=["POST"])
def api_helper():
    """
    Help-a-Friend coach. The user's FRIEND is struggling; the user forwards what
    the friend said and SilentHelp coaches the user's next reply.

    Body: {"messages": [{"role":"friend"|"user","content":...}, ...]}
    Returns: {reply, guidance, danger, escalation_reason}
    """
    data = request.get_json(silent=True) or {}
    messages = data.get("messages") or []
    if not messages:
        return jsonify({"error": "no conversation"}), 400
    # This is public/unauthenticated — an unbounded array (or huge per-message
    # content) costs a real outbound LLM call per request with no rate limit.
    # Cap both dimensions; a real Help-a-Friend conversation is nowhere near this.
    if not isinstance(messages, list) or len(messages) > 60:
        return jsonify({"error": "conversation too long"}), 400
    for m in messages:
        if isinstance(m, dict) and len(str(m.get("content", ""))) > 4000:
            return jsonify({"error": "message too long"}), 400
    return jsonify(helper.coach(messages))


@app.route("/classify", methods=["POST"])
def classify():
    """
    Take one message, run the full detection pipeline, return judgment + action.

    The endpoint is a pass-through: it never decides risk itself. If the model
    call fails, detection.classify_message() already fails SAFE to 'high', so the
    action returned here will still route to a human.
    """
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "empty message"}), 400

    l1, judgment, action = _pipeline(message)
    return jsonify({"judgment": judgment, "action": action, "l1": l1})


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """
    Layer 1 only — the fast local keyword pre-filter. Used by the live monitor
    to flag text instantly without an AI round-trip. No text is stored.
    """
    data = request.get_json(silent=True) or {}
    return jsonify(layer1.scan(data.get("text") or ""))


@app.route("/api/behavioral", methods=["POST"])
def api_behavioral():
    """Recompute L3 metrics from the dashboard's signal sliders. No text read."""
    signals = request.get_json(silent=True) or {}
    metrics = behavioral.compute_metrics(signals)
    metrics["trend"] = behavioral.weekly_trend(metrics["focus_score"])
    return jsonify(metrics)


@app.route("/api/escalation/draft", methods=["POST"])
def api_escalation_draft():
    """Build a reviewable counselor email. Drafting is NOT sending."""
    data = request.get_json(silent=True) or {}
    contact = (data.get("contact") or DEFAULT_CONTACT).strip()
    subject = "SilentHelp — I could use a check-in"
    body = (
        "Hi,\n\n"
        "I'm reaching out through SilentHelp. Some of what I've been writing "
        "lately suggests I'm going through a really hard time, and I think I "
        "could use some support.\n\n"
        "Would you have time to check in with me soon?\n\n"
        "Thank you,\n[your name]\n\n"
        "— If this is urgent, you can also reach the 988 Suicide & Crisis "
        "Lifeline (call or text 988) or the Crisis Text Line (text HOME to 741741)."
    )
    return jsonify({"contact": contact, "subject": subject, "body": body})


def _extract_email(contact: str) -> str:
    """Pull an address out of 'Name <a@b.com>' or a bare 'a@b.com'."""
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", contact or "")
    return m.group(0) if m else ""


def _smtp_send(to_addr: str, subject: str, body: str) -> bool:
    """Actually send an email via SMTP if credentials are configured in .env.
    Returns True on success. Reads SMTP_HOST/PORT/USER/PASS/FROM from the env."""
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except (TypeError, ValueError):
        port = 587  # a malformed SMTP_PORT must not crash the send path
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    sender = os.environ.get("SMTP_FROM", user or "")
    if not (user and password and to_addr):
        return False
    # subject/body are client-supplied. EmailMessage's header assignment raises
    # ValueError on an embedded \r or \n (a would-be header-injection attempt,
    # e.g. a smuggled "Bcc:" line) — strip those before building the message so
    # a malformed subject can't 500 an otherwise-legitimate send, and wrap the
    # whole build (not just the network part) in the try below so anything
    # else EmailMessage rejects fails the same safe way the rest of this
    # function already does.
    subject = (subject or "SilentHelp — a check-in").replace("\r", " ").replace("\n", " ")
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to_addr
        msg.set_content(body or "")
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls(context=ctx)
            server.login(user, password)
            server.send_message(msg)
        print(f"[escalation] SMTP email sent to {to_addr}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[escalation] SMTP send failed: {exc}")
        return False


@app.route("/api/escalation/send", methods=["POST"])
def api_escalation_send():
    """
    The user pressed send. If SMTP is configured (.env), we ACTUALLY send the
    email to the chosen recipient. Otherwise we tell the client to fall back to
    opening the user's mail app (mailto). Either way the event is recorded.
    """
    data = request.get_json(silent=True) or {}
    # The recipient is ALWAYS the account's own saved trusted contact — never a
    # client-supplied value. Trusting data.get("contact") here meant any signed-
    # up user (self-serve, no verification) could point the server's own SMTP
    # account at an arbitrary third-party address with attacker-chosen subject/
    # body: an open mail relay riding on this app's mail reputation. Changing
    # who this goes to is a Settings action, not a send-time parameter.
    contact = (store.get_settings().get("contact") or DEFAULT_CONTACT).strip()
    subject = data.get("subject") or "SilentHelp — I could use a check-in"
    body = data.get("body") or ""
    if not contact:
        return jsonify({"error": "no recipient"}), 400

    to_addr = _extract_email(contact)
    sent = _smtp_send(to_addr, subject, body)
    # Only a REAL send is a crisis-level event. A mailto fallback (or a failed
    # send) just means the note was prepared — logging it as crisis would keep
    # re-tripping the Layer-4 urgent gate and re-pop the escalation screen for
    # an email that never left.
    if sent:
        store.record_event(4, "crisis", "escalation_sent")
    else:
        store.record_event(2, "moderate", "escalation_prepared")
    return jsonify({"sent": sent, "method": "smtp" if sent else "mailto",
                    "contact": contact, "to": to_addr})


# ---------------------------------------------------------------------------
# Full-app state, settings, live screens, monitoring, data controls
# ---------------------------------------------------------------------------

@app.route("/api/state")
def api_state():
    """Everything the app needs to boot: settings, dashboard, gating, chat."""
    return jsonify({
        "settings": store.get_settings(),
        "dashboard": store.dashboard(),
        "gating": store.gating(),
        "chat": store.get_chat(),
        **_common(),
    })


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        patch = request.get_json(silent=True) or {}
        return jsonify(store.update_settings(patch))
    return jsonify(store.get_settings())


@app.route("/api/dashboard")
def api_dashboard():
    return jsonify(store.dashboard())


@app.route("/api/agent_prefs")
def api_agent_prefs():
    """Small, cheap poll target for the Mac agent — just the settings that
    change agent BEHAVIOR (not the whole settings object), so it can start/stop
    app-usage tracking without a restart when the user flips the toggle."""
    return jsonify({"track_app_usage": bool(store.get_settings().get("track_app_usage"))})


@app.route("/api/analytics")
def api_analytics():
    return jsonify(store.analytics())


@app.route("/api/findings")
def api_findings():
    return jsonify(store.findings())


@app.route("/api/behavioral/log", methods=["POST"])
def api_behavioral_log():
    """Record a real behavioral sample (Layer 3) and persist today's metrics."""
    signals = request.get_json(silent=True) or {}
    metrics = store.record_behavioral(signals)
    return jsonify(metrics)


@app.route("/api/app_usage/log", methods=["POST"])
def api_app_usage_log():
    """Record per-app foreground seconds — opt-in only. The agent is expected
    to check the toggle itself before ever calling this, but the server
    enforces it too: an old/misbehaving client can't collect this data just
    because it kept posting after the user turned tracking off."""
    if not store.get_settings().get("track_app_usage"):
        return jsonify({"ok": False, "reason": "tracking is off"}), 403
    data = request.get_json(silent=True) or {}
    apps = data.get("apps")
    if not isinstance(apps, dict):
        return jsonify({"error": "expected {\"apps\": {name: seconds}}"}), 400
    store.record_app_usage(apps)
    return jsonify({"ok": True})


@app.route("/api/wrap")
def api_wrap():
    """Monthly recap. ?year=2026&month=7 for a specific month; defaults to the
    current month (so-far, if it hasn't closed)."""
    try:
        year = int(request.args["year"]) if "year" in request.args else None
        month = int(request.args["month"]) if "month" in request.args else None
    except (ValueError, KeyError):
        return jsonify({"error": "year/month must be integers"}), 400
    if month is not None and not (1 <= month <= 12):
        return jsonify({"error": "month must be 1-12"}), 400
    return jsonify(store.monthly_wrap(year, month))


@app.route("/api/monitor", methods=["POST"])
def api_monitor():
    """
    The passive detection channel: scan text through L1+L2 (honoring toggles),
    RECORD the events for trend gating, and report whether a moment should
    surface (gentle / urgent) per Layer-4.
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "empty"}), 400
    # Anonymous callers (a friend's agent) get the full context-checked verdict
    # but we record NOTHING for them — no events, no shared-store writes. Their
    # popup decision comes from judgment.surface alone. A paired device token
    # (see _bind_user_store) counts as authed too — that's how the Mac agent
    # gets attributed on a hosted deployment, where it's never "local".
    uid = session.get("uid")
    token_uid = auth.uid_for_device_token(request.headers.get("X-Device-Token", ""))
    authed = bool(uid and auth.get_user(uid)) or bool(token_uid and auth.get_user(token_uid)) \
        or bool(_is_local_request() and _owner_uid())
    # Anonymous callers (a friend's agent) must not inherit the owner's toggles —
    # give them the default all-layers-on config, and record nothing.
    default_toggles = {"keyword": True, "semantic": True, "behavioral": True, "trend": True}
    l1, judgment, action = _pipeline(text, record=bool(authed),
                                     toggles=None if authed else default_toggles)
    gating = store.gating() if authed else {"gentle": False, "urgent": False,
                                            "streak": 0, "layers": []}
    return jsonify({"l1": l1, "judgment": judgment, "action": action,
                    "gating": gating})


@app.route("/api/gating")
def api_gating():
    return jsonify(store.gating())


@app.route("/api/chat/history")
def api_chat_history():
    return jsonify({"chat": store.get_chat()})


@app.route("/api/chat/clear", methods=["POST"])
def api_chat_clear():
    store.clear_chat()
    return jsonify({"ok": True})


# --- Chat threads (ChatGPT-style history) ---------------------------------

@app.route("/api/chat/threads")
def api_chat_threads():
    return jsonify({"threads": store.list_threads()})


@app.route("/api/chat/new", methods=["POST"])
def api_chat_new():
    """Archive the current conversation and start a fresh one."""
    store.new_thread()
    return jsonify({"ok": True, "chat": store.get_chat()})


@app.route("/api/chat/open", methods=["POST"])
def api_chat_open():
    """Reopen an archived conversation as the active one."""
    d = request.get_json(silent=True) or {}
    if not store.open_thread((d.get("id") or "").strip()):
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True, "chat": store.get_chat()})


@app.route("/api/chat/thread/delete", methods=["POST"])
def api_chat_thread_delete():
    d = request.get_json(silent=True) or {}
    if not store.delete_thread((d.get("id") or "").strip()):
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/export")
def api_export():
    payload = json.dumps(store.export(), ensure_ascii=False, indent=2)
    resp = make_response(payload)
    resp.headers["Content-Type"] = "application/json"
    resp.headers["Content-Disposition"] = "attachment; filename=silenthelp-data.json"
    return resp


@app.route("/api/wipe", methods=["POST"])
def api_wipe():
    store.wipe()
    return jsonify({"ok": True})


@app.route("/api/moments")
def api_moments():
    return jsonify({"moments": store.moments()})


@app.route("/api/status")
def api_status():
    return jsonify(store.status())


@app.route("/api/reset-baseline", methods=["POST"])
def api_reset_baseline():
    store.reset_baseline()
    return jsonify({"ok": True})


@app.route("/download/agent")
def download_agent():
    """Serve the packaged native macOS agent (built by run.sh / make-app.sh)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "SilentHelpAgent.zip")
    if not os.path.exists(path):
        return ("The Mac app hasn't been packaged yet. Run ./run.sh (or "
                "SilentHelpAgent/make-app.sh) to build it.", 404)
    return send_file(path, as_attachment=True, download_name="SilentHelpAgent.zip")


if __name__ == "__main__":
    # Local prototype only — bind to localhost.
    # 0.0.0.0 so a phone on the same Wi-Fi can reach it at http://<mac-ip>:5055.
    # (Prototype / home network only — this exposes the app to your LAN.)
    # threaded: SSE streams (/api/hq/stream) hold a connection open — without
    # threads the single dev worker would block all other requests.
    app.run(host="0.0.0.0", port=5055, debug=False, threaded=True)
