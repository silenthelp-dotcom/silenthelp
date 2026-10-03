"""End-to-end browser test of /app?voice=1 using Chrome with a fake microphone.

Turn 1 (REAL): fake mic plays a benign phrase -> VibeASR -> real /api/chat -> VibeVoice reply.
Turn 2 (MOCKED crisis): /api/chat and /api/scan are intercepted in the browser (nothing reaches
the server) to verify the 988 / 741741 resources appear on screen in voice mode.
"""
import json, os, sys, time
from playwright.sync_api import sync_playwright

ROOT = os.environ.get("SH_VOICE_ROOT", os.path.expanduser("~/silenthelp-voice"))
WAV = os.path.join(ROOT, "samples", "e2e_phrase_48k.wav")
OUT = os.path.join(ROOT, "samples")
URL = "http://127.0.0.1:5055/app?voice=1#chat"

def main():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True, args=[
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-audio-capture={WAV}", "--autoplay-policy=no-user-gesture-required"])
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, permissions=["microphone"])
        page = ctx.new_page()
        logs = []
        page.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
        page.on("pageerror", lambda e: logs.append(f"PAGEERROR: {e}"))
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_selector("#shv-btn", timeout=20000)
        time.sleep(1.5)
        page.screenshot(path=f"{OUT}/ui_chat_with_voice_button.png")
        # --- Turn 1: real pipeline (set MOCK_CHAT=1 to keep /api/chat out of it and not add to chat history)
        if os.environ.get("MOCK_CHAT") == "1":
            benign = {"reply": "Thanks for telling me about your day. What part of it is still on your mind?",
                      "judgment": {"risk_level": "none"}, "action": {"risk_level": "none"}, "l1": {}}
            page.route("**/api/chat", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(benign)))
            print("(turn 1 /api/chat mocked)")
        page.click("#shv-btn")
        page.wait_for_function("document.getElementById('shv-meta').textContent.includes('VibeVoice')", timeout=15000)
        page.uncheck("#shv-auto")                     # don't loop the fake mic into a 2nd turn
        t0 = time.time()
        page.click("#shv-mic")
        page.wait_for_function("document.getElementById('shv-live').textContent.startsWith('You:')", timeout=60000)
        t_stt = time.time() - t0
        print("TRANSCRIPT:", page.inner_text("#shv-live"))
        page.wait_for_function("document.getElementById('shv-reply').textContent.length > 0", timeout=60000)
        t_reply = time.time() - t0
        print("REPLY:", page.inner_text("#shv-reply"))
        page.wait_for_function("window.SHVoice.state.t.firstAudio > 0", timeout=60000)
        t_audio = time.time() - t0
        time.sleep(1.2)
        page.screenshot(path=f"{OUT}/ui_voice_speaking.png")
        page.wait_for_function("window.SHVoice.state.state === 'idle'", timeout=120000)
        print("TIMINGS(s from mic tap): transcript=%.2f reply_text=%.2f first_audio=%.2f" % (t_stt, t_reply, t_audio))
        print("APP-TIMINGS(ms):", json.dumps(page.evaluate("window.SHVoice.state.t")))
        # --- Turn 2: mocked crisis verdict (no server call)
        mock = {"reply": "I'm really sorry you're carrying this. Please reach out right now: call or text 988, or text HOME to 741741.",
                "judgment": {"risk_level": "crisis", "categories": ["crisis"]},
                "action": {"risk_level": "crisis", "action": "show_crisis_resources", "route_to_human": True, "dismissible": False,
                           "resources": [{"name": "988 Suicide & Crisis Lifeline", "contact": "Call or text 988", "available": "24/7"},
                                         {"name": "Crisis Text Line", "contact": "Text HOME to 741741", "available": "24/7"}]},
                "l1": {}}
        page.unroute("**/api/chat")
        page.route("**/api/chat", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(mock)))
        page.route("**/api/scan", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"level": 0})))
        page.evaluate("window.SHVoice.turn('[mocked test turn]')")
        page.wait_for_function("document.getElementById('shv-crisis').classList.contains('on')", timeout=15000)
        urgent = page.evaluate("getComputedStyle(document.getElementById('popup-urgent')).display")
        ov = page.evaluate("getComputedStyle(document.getElementById('shv-overlay')).display")
        top = page.evaluate("(document.elementFromPoint(720,450)||{}).closest && !!document.elementFromPoint(720,450).closest('#popup-urgent')")
        print("CRISIS: overlay card on=True | urgent popup display:", urgent, "| voice overlay display while urgent open:", ov, "| urgent popup is topmost:", top)
        time.sleep(1.5)
        page.screenshot(path=f"{OUT}/ui_voice_crisis_with_popup.png")
        page.evaluate("App.closePopup()")
        time.sleep(0.6)
        print("after closing urgent popup, voice overlay display:", page.evaluate("getComputedStyle(document.getElementById('shv-overlay')).display"))
        page.screenshot(path=f"{OUT}/ui_voice_crisis_overlay.png")
        page.evaluate("window.SHVoice.close()")
        errs = [l for l in logs if "error" in l.lower()]
        print("CONSOLE errors:", errs[:10])
        b.close()

main()
