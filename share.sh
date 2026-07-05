#!/bin/bash
# Share SilentHelp publicly via a Cloudflare quick tunnel.
#   ./share.sh          -> starts everything in the background, prints the link
#   ./share.sh stop     -> stops backend + tunnel + watchdog
# The watchdog keeps the backend + tunnel alive (auto-reconnects if the tunnel
# drops) and stops your Mac from idle-sleeping while sharing.
cd "$(dirname "$0")"

if [ "$1" = "stop" ]; then
  pkill -f watchdog.sh 2>/dev/null
  pkill -f "app.py" 2>/dev/null
  pkill -f cloudflared 2>/dev/null
  pkill -f "caffeinate -im" 2>/dev/null
  echo "▸ stopped."
  exit 0
fi

PY=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
[ -x "$PY" ] || PY=python3

echo "▸ starting backend on :5055 …"
pkill -f "app.py" 2>/dev/null; sleep 1
nohup "$PY" app.py >/tmp/sh.log 2>&1 & disown
sleep 3

echo "▸ starting watchdog (keeps the tunnel alive in the background) …"
pkill -f watchdog.sh 2>/dev/null; sleep 1
rm -f /tmp/silenthelp-link.txt
nohup ./watchdog.sh >/dev/null 2>&1 & disown

for i in $(seq 1 40); do
  [ -s /tmp/silenthelp-link.txt ] && break
  sleep 1
done
echo ""
echo "──────────────────────────────────────────────"
echo "  SHARE THIS LINK:  $(cat /tmp/silenthelp-link.txt 2>/dev/null)"
echo "──────────────────────────────────────────────"
echo "Runs in the background — you can close this window."
echo "Current link anytime:  cat /tmp/silenthelp-link.txt"
echo "Stop everything:       ./share.sh stop"
