#!/bin/bash
# SilentHelp — start everything: backend + native background agent.
#
#   ./run.sh
#
# Then grant Accessibility permission to "SilentHelp Agent" when macOS asks
# (System Settings ▸ Privacy & Security ▸ Accessibility), quit the agent from
# its 🟢 SH menu-bar icon, and run ./run.sh again. After that it reads the
# focused text field of whatever app you're in (Messages, Notes…) and pops up.

set -e
cd "$(dirname "$0")"

PY=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
[ -x "$PY" ] || PY=python3

echo "▸ Starting backend on http://127.0.0.1:5055 …"
pkill -f "app.py" 2>/dev/null || true
sleep 1
"$PY" app.py > /tmp/silenthelp.log 2>&1 &
sleep 2
if curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:5055/ | grep -q 200; then
  echo "  ✓ backend up"
else
  echo "  ✗ backend failed — see /tmp/silenthelp.log"; exit 1
fi

DEST="/Applications"; [ -w "$DEST" ] || { DEST="$HOME/Applications"; mkdir -p "$DEST"; }

# IMPORTANT: do NOT rebuild if it's already installed. Rebuilding changes the
# app's code hash and macOS drops the Accessibility grant. Pass --rebuild to
# force a fresh build (you'll have to re-grant permission afterward).
if [ "$1" = "--rebuild" ] || [ ! -d "$DEST/SilentHelpAgent.app" ]; then
  echo "▸ Building the background agent …"
  ( cd SilentHelpAgent && ./make-app.sh > /tmp/silenthelp-agent-build.log 2>&1 ) \
    && echo "  ✓ agent built" || { echo "  ✗ build failed — see /tmp/silenthelp-agent-build.log"; exit 1; }
  pkill -f "SilentHelpAgent" 2>/dev/null || true; sleep 1
  rm -rf "$DEST/SilentHelpAgent.app"
  ditto SilentHelpAgent/SilentHelpAgent.app "$DEST/SilentHelpAgent.app"   # preserves signature
  [ "$1" = "--rebuild" ] && tccutil reset Accessibility com.silenthelp.agent 2>/dev/null || true
else
  echo "▸ Agent already installed — launching it (run with --rebuild to force a fresh build)."
fi

echo "▸ Launching agent from $DEST (look for 🟢 SH in the menu bar) …"
open "$DEST/SilentHelpAgent.app"

echo "▸ Opening the app front page …"
open http://127.0.0.1:5055/

cat <<'NOTE'

──────────────────────────────────────────────────────────────
NEXT (first run only):
  1. macOS will ask for Accessibility permission. Grant it to
     "SilentHelp Agent" in System Settings ▸ Privacy & Security
     ▸ Accessibility.
  2. Quit the agent (🟢 SH menu-bar icon ▸ Quit) and run ./run.sh again.
  3. Open Messages/Notes and type something like:
        "i'm so done, i wanna unalive myself tonight"
     → a popup appears within ~1.5s, and the app surfaces the
       matching gentle/urgent screen.

Backend log:  /tmp/silenthelp.log
──────────────────────────────────────────────────────────────
NOTE
