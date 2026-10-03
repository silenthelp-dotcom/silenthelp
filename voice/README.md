# SilentHelp voice mode: local prototype (BETA, research only)

Voice mode is off by default. It only loads on `/app?voice=1` (or `?voice=open`, which opens
the voice view straight away) and talks to this local service on `127.0.0.1:5077`. Spoken turns
go through the normal `App.send()` path, so detection and crisis handling are unchanged.

## What lives where
- This folder (in the repo): the service code (`server/`) and `start.sh` / `stop.sh`.
- `SH_VOICE_ROOT` (default `~/silenthelp-voice`, NOT in the repo): the heavy parts:
  - `.venv/`: Python env with torch, fastapi, uvicorn, soundfile, numpy and VibeVoice's requirements
  - `VibeVoice/`: a clone of https://github.com/microsoft/VibeVoice (the service imports its `demo/web/app.py`)
  - `VibeASR.cpp/`: built so that `build/bin/asr_stream_server` exists (speech-to-text)
  - `models/vibeasr/vibeasr-vae-encoder-i8_s.gguf`, `models/vibeasr/vibeasr-lm-i2_s-embed-q6_k.gguf`
  - `hf-cache/` (HF_HOME; VibeVoice-Realtime-0.5B downloads here), `logs/`, `voice.pid`

If the ASR binary or models are missing, STT reports "unavailable" and the UI falls back to typing (TTS only).

## Run
- Start: `voice/start.sh` (detached; ready in about 20 s). Use another root with `SH_VOICE_ROOT=/path voice/start.sh`.
- Stop: `voice/stop.sh`
- Health: `curl http://127.0.0.1:5077/health` · Log: `$SH_VOICE_ROOT/logs/voice.log`
- Try it: http://127.0.0.1:5055/app?voice=1#chat, then press "Voice BETA" next to Send.
- TTS: Microsoft VibeVoice-Realtime-0.5B (MPS on Apple silicon, else CPU). Voice `en-Soother_woman`;
  change it with `SH_TTS_VOICE=en-Grace_woman voice/start.sh`. Diffusion steps: `SH_TTS_STEPS` (default 4).
- STT: Microsoft VibeVoice-ASR-BitNet via VibeASR.cpp (CPU, 4 threads).
- Tests: `server/ws_test.py` (TTS latency), `server/e2e_voice.py` (Chrome with a fake mic; needs
  `$SH_VOICE_ROOT/samples/e2e_phrase_48k.wav`; set `MOCK_CHAT=1` to keep /api/chat out of it).

Microsoft notice: VibeVoice is for research and development only, and isn't meant for commercial or
real-world use without more testing. Nothing here is a safety mechanism; crisis routing stays in the app.
