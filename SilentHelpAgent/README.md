# SilentHelp Agent (native macOS background monitor)

The real thing: a menu-bar app that runs in the background, reads the **focused
text field of whatever app you're in** (via the macOS Accessibility API), sends
it to your SilentHelp backend, and **pops up** when a crisis phrase fires or the
backend routes to a human.

The agent is the *eyes*. The Python backend is the *brain*. Run both.

## Run it

1. **Start the backend** (in one terminal):
   ```
   cd ~/silenthelp-detection
   python3 app.py          # http://127.0.0.1:5055
   ```

2. **Build + launch the agent** (in another terminal):
   ```
   cd ~/silenthelp-detection/SilentHelpAgent
   ./make-app.sh
   open SilentHelpAgent.app
   ```
   A 🟢 SH icon appears in the menu bar.

3. **Grant Accessibility permission** when prompted:
   System Settings ▸ Privacy & Security ▸ Accessibility ▸ enable *SilentHelp Agent*.
   Then **quit and relaunch** the app (menu-bar ▸ Quit, then `open SilentHelpAgent.app`).
   Icon turns 🟢 when it's monitoring.

4. **Test it**: open **Messages** (or Notes) and type something concerning, e.g.
   `i'm so done, i wanna unalive myself tonight`. Within ~1.5s a popup appears.

## How it works
- Polls the system-wide focused element every 1.5s, reads its text (`AXValue`).
- `POST /api/scan` (Layer 1, instant) → tier-3 crisis phrase ⇒ immediate popup.
- Otherwise, if L1 matched, `POST /classify` (Layer 2 semantic) ⇒ popup if it
  routes to a human.
- 90s cooldown after a popup; ignores text under 8 chars; never stores text.

## Honest limits (prototype)
- **Native apps** (Messages, Notes, Mail, Safari fields) expose text well.
  **Electron apps (Discord, Slack)** are inconsistent — their accessibility tree
  often doesn't surface the compose field. That's an app-by-app reality of AX,
  not a bug here.
- Reads only the **currently focused** field, not full-screen history. Full
  on-screen reading would use ScreenCaptureKit + OCR (heavier, more invasive).
- Behavioral (L3) and trend gating (L4) are not yet wired into the agent — this
  build covers L1+L2 content detection + popup. L3/L4 come next.
- Requires the backend running on localhost:5055.

## Config
Edit `Sources/SilentHelpAgent/main.swift` → `enum Config` (backend URL, poll
interval, min length, cooldown), then re-run `./make-app.sh`.
