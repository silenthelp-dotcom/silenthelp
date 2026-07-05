#!/bin/bash
# SilentHelp background watchdog: keeps backend + Cloudflare quick tunnel alive.
# Started by share.sh (or directly: nohup ./watchdog.sh & ). Writes the current
# public link to /tmp/silenthelp-link.txt
cd "$(dirname "$0")"
PY=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
[ -x "$PY" ] || PY=python3
CF="$HOME/.silenthelp-bin/cloudflared"

start_tunnel(){
  pkill -f cloudflared 2>/dev/null; sleep 1
  : > /tmp/cf-tunnel.log
  nohup "$CF" tunnel --url http://localhost:5055 >/tmp/cf-tunnel.log 2>&1 & disown
  for i in $(seq 1 30); do
    URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cf-tunnel.log | head -1)
    [ -n "$URL" ] && grep -q "Registered tunnel connection" /tmp/cf-tunnel.log && break
    sleep 1
  done
  echo "$URL/app" > /tmp/silenthelp-link.txt
  echo "$(date '+%F %T') tunnel up: $URL/app" >> /tmp/silenthelp-watchdog.log
}

# keep the Mac from idle-sleeping while we're sharing (display can still sleep)
pgrep -f "caffeinate -im" >/dev/null || { nohup caffeinate -im >/dev/null 2>&1 & disown; }

while true; do
  if ! pgrep -f "app.py" >/dev/null; then
    echo "$(date '+%F %T') backend restart" >> /tmp/silenthelp-watchdog.log
    nohup "$PY" app.py >/tmp/sh.log 2>&1 & disown; sleep 3
  fi
  if ! pgrep -f "cloudflared tunnel" >/dev/null || tail -8 /tmp/cf-tunnel.log 2>/dev/null | grep -q "Retrying connection"; then
    echo "$(date '+%F %T') tunnel reconnect" >> /tmp/silenthelp-watchdog.log
    start_tunnel
  fi
  sleep 20
done
