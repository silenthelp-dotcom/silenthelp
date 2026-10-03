"""
SilentHelp voice service (LOCAL PROTOTYPE, research use only)
=============================================================

Runs on 127.0.0.1:5077, outside the SilentHelp repo, in ~/silenthelp-voice/.venv.

  * TTS: Microsoft VibeVoice-Realtime-0.5B (streaming, English, embedded voice
    presets). Streams 24 kHz mono PCM16 over a websocket.
  * STT: Microsoft VibeVoice-ASR-BitNet via VibeASR.cpp (CPU, persistent
    asr_stream_server process). If that binary/model is missing, STT reports
    "unavailable" and the UI falls back to typing (TTS-only mode).

Endpoints
  GET  /health                -> engines, device, voice, warm timings
  POST /stt                   -> body: any WAV (browser sends 16 kHz mono PCM16)
                                 returns {"text", "ms", "audio_sec", "engine"}
  WS   /tts?text=...&voice=   -> first a JSON {"type":"meta"} text frame, then
                                 binary PCM16 frames, then {"type":"done"}.
                                 Client closing the socket = interrupt.
  POST /tts.wav               -> {"text": "..."} -> full WAV (for tests)

Microsoft's notice: VibeVoice is for research and development only; it is not
intended for commercial or real-world use without further testing. Nothing
here is a safety mechanism: crisis routing stays in the SilentHelp app.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

ROOT = Path(os.environ.get("SH_VOICE_ROOT", Path.home() / "silenthelp-voice"))
os.environ.setdefault("HF_HOME", str(ROOT / "hf-cache"))
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
sys.path.insert(0, str(ROOT / "VibeVoice" / "demo"))
sys.path.insert(0, str(ROOT / "VibeVoice"))

import torch  # noqa: E402
from fastapi import FastAPI, Request, WebSocket  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse, Response  # noqa: E402
from starlette.websockets import WebSocketDisconnect, WebSocketState  # noqa: E402

from web.app import StreamingTTSService  # noqa: E402  (VibeVoice's own demo class)

MODEL_PATH = os.environ.get("SH_TTS_MODEL", "microsoft/VibeVoice-Realtime-0.5B")
DEVICE = os.environ.get("SH_TTS_DEVICE") or ("mps" if torch.backends.mps.is_available() else "cpu")
VOICE = os.environ.get("SH_TTS_VOICE", "en-Soother_woman")
TTS_STEPS = int(os.environ.get("SH_TTS_STEPS", "4"))  # 5 = Microsoft default (RTF ~1.5 on base M4); 3 = ~1.1
CFG = float(os.environ.get("SH_TTS_CFG", "1.5"))
SR = 24_000

ASR_DIR = ROOT / "VibeASR.cpp"
ASR_BIN = ASR_DIR / "build" / "bin" / "asr_stream_server"
ASR_VAE = ROOT / "models" / "vibeasr" / "vibeasr-vae-encoder-i8_s.gguf"
ASR_LM = ROOT / "models" / "vibeasr" / "vibeasr-lm-i2_s-embed-q6_k.gguf"
ASR_THREADS = os.environ.get("SH_ASR_THREADS", "4")

ALLOWED_ORIGINS = [
    "http://127.0.0.1:5055", "http://localhost:5055",
    "http://127.0.0.1:5077", "http://localhost:5077",
]


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# --------------------------------------------------------------------------
# Text clean-up so the voice reads replies naturally (English only model)
# --------------------------------------------------------------------------
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]")


def speakable(text: str) -> str:
    t = text or ""
    t = re.sub(r"\*\*|__|`|#+ ", "", t)                 # markdown
    t = re.sub(r"^\s*[-•*]\s+", "", t, flags=re.M)      # bullets
    t = _EMOJI.sub("", t)
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("—", ", ").replace("–", ", ")
    # crisis numbers read clearly, digit by digit
    t = re.sub(r"\b988\b", "nine, eight, eight", t)
    t = re.sub(r"\b741741\b", "seven four one, seven four one", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:1200]


# --------------------------------------------------------------------------
# STT: VibeASR.cpp persistent server
# --------------------------------------------------------------------------
class VibeASR:
    engine = "VibeVoice-ASR-BitNet (VibeASR.cpp, CPU)"

    def __init__(self):
        self.proc: Optional[subprocess.Popen] = None
        self.lock = threading.Lock()
        self.error: Optional[str] = None

    def available(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        for p in (ASR_BIN, ASR_VAE, ASR_LM):
            if not p.exists():
                self.error = f"missing {p}"
                log("[stt] unavailable:", self.error)
                return
        cmd = [str(ASR_BIN), "--vae-model", str(ASR_VAE), "--lm-model", str(ASR_LM),
               "-t", ASR_THREADS, "--max-tokens", "1024", "--greedy",
               "--prompt-format", "text"]
        t0 = time.time()
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=open(ROOT / "logs" / "asr_server.stderr.log", "ab"),
                                     bufsize=0)
        ready = self.proc.stdout.readline().decode().strip()
        if ready != "---READY---":
            self.error = f"asr_stream_server did not become ready ({ready!r})"
            log("[stt]", self.error)
            self.proc.kill()
            self.proc = None
            return
        log(f"[stt] VibeASR ready in {time.time()-t0:.1f}s (threads={ASR_THREADS})")

    def transcribe_file(self, path: str) -> str:
        with self.lock:
            if not self.available():
                raise RuntimeError(self.error or "STT not running")
            self.proc.stdin.write(f"{path}\n".encode())
            self.proc.stdin.flush()
            out = []
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    break
                s = line.decode("utf-8", errors="replace")
                if s.strip() == "---END---":
                    break
                if s.startswith("[ERROR]"):
                    raise RuntimeError(s.strip())
                out.append(s)
            return clean_transcript("".join(out))


def clean_transcript(raw: str) -> str:
    """VibeVoice-ASR emits rich output (speaker / timestamps / tags). Keep words."""
    s = raw.strip()
    # JSON-ish output: [{"Start":..,"Content":".."}]
    contents = re.findall(r'"(?:Content|content|text)"\s*:\s*"((?:[^"\\]|\\.)*)"', s)
    if contents:
        s = " ".join(json.loads(f'"{c}"') for c in contents)
    s = re.sub(r"\[[^\]]*\]", " ", s)          # [Speaker 0] / [noise] / timestamps
    s = re.sub(r"<[^>]*>", " ", s)
    s = re.sub(r"^\s*(Speaker\s*\d+|\d+(\.\d+)?\s*-\s*\d+(\.\d+)?)\s*[:,]?", " ", s, flags=re.M)
    s = re.sub(r"\s+", " ", s).strip()
    # streaming server emits token-spaced text: "can 't sleep at night ."
    s = re.sub(r"(\w) (['’])(\w)", r"\1\2\3", s)
    s = re.sub(r"\s+([.,!?;:%])", r"\1", s)
    return s


def to_24k_mono_wav(data: bytes) -> tuple[str, float]:
    audio, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if sr != SR:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(int(sr), SR)
        audio = resample_poly(audio, SR // g, int(sr) // g).astype(np.float32)
    # 0.3 s of leading/trailing silence helps the model catch the first word
    pad = np.zeros(int(0.3 * SR), np.float32)
    audio = np.concatenate([pad, audio, pad])
    fd, path = tempfile.mkstemp(suffix=".wav", prefix="shv_")
    os.close(fd)
    sf.write(path, audio, SR, subtype="PCM_16")
    return path, len(audio) / SR - 0.6


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
app = FastAPI(title="SilentHelp voice (prototype)")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["*"],
                   allow_headers=["*"])

STATE: dict = {"tts": None, "stt": VibeASR(), "tts_lock": None, "current_stop": None,
               "last": {}, "tts_error": None}


@app.on_event("startup")
async def startup():
    (ROOT / "logs").mkdir(exist_ok=True)
    STATE["tts_lock"] = asyncio.Lock()

    def load_tts():
        try:
            os.environ["VOICE_PRESET"] = VOICE
            t0 = time.time()
            svc = StreamingTTSService(model_path=MODEL_PATH, device=DEVICE, inference_steps=TTS_STEPS)
            svc.load()
            log(f"[tts] VibeVoice-Realtime loaded on {svc.device} in {time.time()-t0:.1f}s, voice={svc.default_voice_key}")
            # warm-up (first MPS run compiles kernels)
            t0 = time.time()
            for warm in ("Hi.", "I'm here with you. Take your time, there's no rush."):
                for _ in svc.stream(warm, cfg_scale=CFG, voice_key=VOICE):
                    pass
            log(f"[tts] warm-up {time.time()-t0:.2f}s")
            STATE["tts"] = svc
        except Exception as e:  # degrade: STT-only / text-only
            STATE["tts_error"] = f"{type(e).__name__}: {e}"
            log("[tts] FAILED:", STATE["tts_error"])

    await asyncio.gather(asyncio.to_thread(load_tts), asyncio.to_thread(STATE["stt"].start))
    log("[startup] voice service ready")


@app.get("/health")
def health():
    tts = STATE["tts"]
    stt: VibeASR = STATE["stt"]
    return {
        "ok": True,
        "tts": {"ready": tts is not None, "engine": "VibeVoice-Realtime-0.5B",
                "device": getattr(tts, "device", None), "voice": VOICE,
                "error": STATE["tts_error"]},
        "stt": {"ready": stt.available(), "engine": stt.engine, "error": stt.error},
        "last": STATE["last"],
        "notice": "Research prototype (Microsoft VibeVoice). Not for real-world use without further testing.",
    }


@app.get("/voices")
def voices():
    tts = STATE["tts"]
    return {"voices": sorted(tts.voice_presets) if tts else [], "default": VOICE}


@app.post("/stt")
async def stt(request: Request):
    stt: VibeASR = STATE["stt"]
    if not stt.available():
        return JSONResponse({"error": "stt_unavailable", "detail": stt.error}, status_code=503)
    body = await request.body()
    if not body or len(body) > 20 * 1024 * 1024:
        return JSONResponse({"error": "bad_audio"}, status_code=400)
    t0 = time.time()
    path, dur = await asyncio.to_thread(to_24k_mono_wav, body)
    try:
        text = await asyncio.to_thread(stt.transcribe_file, path)
    finally:
        try:
            os.remove(path)  # audio never kept on disk
        except OSError:
            pass
    ms = int((time.time() - t0) * 1000)
    STATE["last"]["stt"] = {"ms": ms, "audio_sec": round(dur, 2), "rtf": round(ms / 1000 / max(dur, 0.01), 2)}
    log(f"[stt] {dur:.2f}s audio -> {ms} ms : {text!r}")
    return {"text": text, "ms": ms, "audio_sec": round(dur, 2), "engine": stt.engine}


@app.websocket("/tts")
async def tts_ws(ws: WebSocket):
    origin = ws.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        log(f"[tts] reject origin={origin!r}")
        await ws.close(code=1008)
        return
    await ws.accept()
    svc = STATE["tts"]
    if svc is None:
        await ws.send_text(json.dumps({"type": "error", "error": "tts_unavailable",
                                       "detail": STATE["tts_error"]}))
        await ws.close()
        return
    text = speakable(ws.query_params.get("text", ""))
    voice = ws.query_params.get("voice") or VOICE
    if not text:
        log("[tts] empty text after speakable — closing")
        await ws.close()
        return

    # A new utterance interrupts whatever is still being generated.
    if STATE["current_stop"] is not None:
        STATE["current_stop"].set()
    stop = threading.Event()
    user_stop = {"v": False}
    async with STATE["tts_lock"]:
        STATE["current_stop"] = stop
        t0 = time.time()
        first_ms = None
        samples = 0
        rtf_hint = (STATE["last"].get("tts") or {}).get("rtf") or 1.4
        await ws.send_text(json.dumps({"type": "meta", "sample_rate": SR, "voice": voice,
                                       "rtf_hint": rtf_hint}))
        it = svc.stream(text, cfg_scale=CFG, voice_key=voice, stop_event=stop)
        sentinel = object()

        async def watch_client():
            # Detect client 'stop' messages / disconnects while generating.
            try:
                while True:
                    msg = await ws.receive()
                    if msg.get("type") == "websocket.disconnect" or msg.get("text") == "stop":
                        user_stop["v"] = True
                        stop.set()
                        return
            except Exception:
                stop.set()

        watcher = asyncio.create_task(watch_client())
        try:
            while not stop.is_set() and ws.client_state == WebSocketState.CONNECTED:
                chunk = await asyncio.to_thread(next, it, sentinel)
                if chunk is sentinel:
                    break
                if first_ms is None:
                    first_ms = int((time.time() - t0) * 1000)
                samples += chunk.size
                await ws.send_bytes(svc.chunk_to_pcm16(chunk))
            gen_s = time.time() - t0
            audio_s = samples / SR
            stats = {"first_audio_ms": first_ms, "gen_sec": round(gen_s, 2),
                     "audio_sec": round(audio_s, 2), "rtf": round(gen_s / max(audio_s, 0.01), 2),
                     "interrupted": user_stop["v"]}
            STATE["last"]["tts"] = stats
            log(f"[tts] {len(text)} chars: {stats}")
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.send_text(json.dumps({"type": "done", **stats}))
        except (WebSocketDisconnect, RuntimeError):
            stop.set()
        finally:
            stop.set()
            try:
                it.close()
            except Exception:
                pass
            watcher.cancel()
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.close()
            except Exception:
                pass


@app.post("/warm")
async def warm():
    """Called by the UI the moment the user stops talking: MPS clocks down after
    ~30 s idle (first audio ~570 ms cold vs ~150 ms warm), so run a tiny
    throwaway synthesis while STT + the chat reply are in flight.
    Real /tts utterances interrupt this via current_stop."""
    svc = STATE["tts"]
    lock = STATE["tts_lock"]
    if svc is None or lock.locked():
        return {"warmed": False}

    async def _go():
        stop = threading.Event()
        async with lock:
            # A real speak may have already signaled an interrupt before we got the lock.
            if STATE["current_stop"] is not None and STATE["current_stop"].is_set():
                return
            STATE["current_stop"] = stop
            try:
                def run():
                    for _ in svc.stream("Okay.", cfg_scale=CFG, voice_key=VOICE, stop_event=stop):
                        if stop.is_set():
                            break
                await asyncio.to_thread(run)
            finally:
                if STATE.get("current_stop") is stop:
                    STATE["current_stop"] = None
    asyncio.create_task(_go())
    return {"warmed": True}


@app.post("/tts.wav")
async def tts_wav(request: Request):
    svc = STATE["tts"]
    if svc is None:
        return JSONResponse({"error": "tts_unavailable"}, status_code=503)
    data = await request.json()
    text = speakable(data.get("text", ""))
    voice = data.get("voice") or VOICE

    def run():
        t0 = time.time()
        first = None
        chunks = []
        for c in svc.stream(text, cfg_scale=CFG, voice_key=voice):
            if first is None:
                first = time.time() - t0
            chunks.append(c)
        return chunks, first, time.time() - t0

    async with STATE["tts_lock"]:
        chunks, first, total = await asyncio.to_thread(run)
    audio = np.concatenate(chunks) if chunks else np.zeros(1, np.float32)
    buf = io.BytesIO()
    sf.write(buf, np.clip(audio, -1, 1), SR, format="WAV", subtype="PCM_16")
    dur = len(audio) / SR
    stats = {"first_audio_ms": int((first or 0) * 1000), "gen_sec": round(total, 2),
             "audio_sec": round(dur, 2), "rtf": round(total / max(dur, 0.01), 2)}
    STATE["last"]["tts"] = stats
    log(f"[tts.wav] {stats}")
    return Response(buf.getvalue(), media_type="audio/wav",
                    headers={"X-TTS-Stats": json.dumps(stats)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("SH_VOICE_PORT", "5077")),
                log_level="warning")
