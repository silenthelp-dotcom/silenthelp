#!/bin/zsh
# Stop the SilentHelp voice prototype (and its VibeASR child process).
ROOT="${SH_VOICE_ROOT:-$HOME/silenthelp-voice}"
if [ -f "$ROOT/voice.pid" ]; then
  PID=$(cat "$ROOT/voice.pid")
  pkill -P "$PID" 2>/dev/null
  kill "$PID" 2>/dev/null && echo "stopped PID $PID" || echo "not running"
  rm -f "$ROOT/voice.pid"
else
  echo "no pid file"
fi
pkill -f "VibeASR.cpp/build/bin/asr_stream_server" 2>/dev/null || true
