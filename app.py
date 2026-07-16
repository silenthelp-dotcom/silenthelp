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
import smtplib
import ssl
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage

from flask import Flask, Response, jsonify, make_response, redirect, render_template, request, send_file, session, stream_with_context
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
import hq_store
import layer1
import store

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "silenthelp-dev-secret-change-me")
# Behind Cloudflare Tunnel: trust the X-Forwarded-* headers so Flask builds
# redirects/url_for with the real public host + https (not 127.0.0.1/http).
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

DEFAULT_CONTACT = "School Counselor <counselor@school.edu>"
USERDATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "userdata")
os.makedirs(USERDATA_DIR, exist_ok=True)


def _is_local_request() -> bool:
    """True only for traffic from this Mac itself (the agent, a local browser).
    Tunnel visitors carry their real IP via X-Forwarded-For (ProxyFix)."""
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
    "/api/scan", "/classify", "/api/behavioral", "/api/monitor",
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

    if uid:
        store.set_data_file(os.path.join(USERDATA_DIR, f"user_{uid}.json"))
        return None
    store.set_data_file(None)

    # HQ (careers / team / founder admin) is shared company data, not personal
    # on-device data — always public so every visitor sees the same live site.
    if request.path.startswith("/api/hq"):
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


@app.route("/api/signup", methods=["POST"])
def api_signup():
    d = request.get_json(silent=True) or {}
    uid = auth.signup(d.get("email", ""), d.get("password", ""), d.get("name", ""))
    if not uid:
        return jsonify({"error": "That email is taken, or the details are invalid (password 4+ chars)."}), 409
    session["uid"] = uid
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
    return jsonify({"ok": True, "user": auth.get_user(uid)})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.pop("uid", None)
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


def _pipeline(message: str, record: bool = False, toggles: dict | None = None):
    """
    Graded layered detection. Honors the Settings toggles.

    `toggles` lets a caller pass explicit layer settings. When omitted we read
    the bound user's store — but anonymous callers (a friend's agent) must NOT
    inherit the Mac owner's toggles, so they pass all-on defaults instead.

    Layer 1 (your keyword database, layer1_blocks.json) produces a graded signal:
      - a standalone tier-3 crisis phrase  -> "crisis"
      - a burnout/stress/isolation root    -> "moderate"
      - nothing                            -> "none"
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
    if not semantic_on or l2_failed:
        final = l1_level
    else:
        final = l2_level

    categories = l1["categories"] or judgment.get("categories") or []
    # Popup policy for BACKGROUND monitoring (agent/OCR): interrupt only when it
    # matters. crisis/high → urgent · moderate → gentle · low → logged silently
    # (feeds trends/dashboard) · none → nothing.
    surface = ("urgent" if final in ("crisis", "high")
               else "gentle" if final == "moderate" else "none")
    judgment = {**judgment, "risk_level": final, "_l1_level": l1_level,
                "_l2_level": l2_level, "_l1_tier3": bool(l1["tier3"]),
                "surface": surface,
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
    # Front page — the Lithos hero (Claude Design "SilentHelp Hero - Lithos").
    return render_template("hero.html")


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
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    sender = os.environ.get("SMTP_FROM", user or "")
    if not (user and password and to_addr):
        return False
    msg = EmailMessage()
    msg["Subject"] = subject or "SilentHelp — a check-in"
    msg["From"] = sender
    msg["To"] = to_addr
    msg.set_content(body or "")
    try:
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
    contact = (data.get("contact") or store.get_settings().get("contact") or DEFAULT_CONTACT).strip()
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
    # popup decision comes from judgment.surface alone.
    uid = session.get("uid")
    authed = bool(uid and auth.get_user(uid)) or (_is_local_request() and _owner_uid())
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
