#!/bin/zsh
# Start the SilentHelp voice prototype (VibeVoice TTS + VibeASR STT) on 127.0.0.1:5077,
# fully detached (own session, survives the terminal closing).
# SH_VOICE_ROOT = folder holding .venv/, VibeVoice/, VibeASR.cpp/, models/, hf-cache/
# (default ~/silenthelp-voice). The service code itself runs from this repo folder.
HERE="$(cd "$(dirname "$0")" && pwd)"
export SH_VOICE_ROOT="${SH_VOICE_ROOT:-$HOME/silenthelp-voice}"
ROOT="$SH_VOICE_ROOT"
cd "$ROOT" || { echo "SH_VOICE_ROOT not found: $ROOT (see voice/README.md)"; exit 1; }
mkdir -p logs
if [ -f voice.pid ] && kill -0 "$(cat voice.pid)" 2>/dev/null; then
  echo "already running (PID $(cat voice.pid))"; exit 0
fi
export HF_HOME="$ROOT/hf-cache" PYTORCH_ENABLE_MPS_FALLBACK=1 TOKENIZERS_PARALLELISM=false
export SH_TTS_VOICE="${SH_TTS_VOICE:-en-Soother_woman}"
export SH_VOICE_SERVICE="$HERE/server/voice_service.py"
"$ROOT/.venv/bin/python" - <<'PY'
import os, subprocess
root = os.environ["SH_VOICE_ROOT"]
log = open(os.path.join(root, "logs", "voice.log"), "ab")
p = subprocess.Popen([os.path.join(root, ".venv/bin/python"), os.environ["SH_VOICE_SERVICE"]],
                     stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                     start_new_session=True, cwd=root)
open(os.path.join(root, "voice.pid"), "w").write(str(p.pid))
PY
echo "started PID $(cat voice.pid); log: $ROOT/logs/voice.log; health: http://127.0.0.1:5077/health (ready after ~20 s)"
