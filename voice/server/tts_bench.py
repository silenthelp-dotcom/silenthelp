import os, sys, time
from pathlib import Path
ROOT = Path(os.environ.get("SH_VOICE_ROOT", Path.home() / "silenthelp-voice"))
os.environ.setdefault("HF_HOME", str(ROOT / "hf-cache"))
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
sys.path.insert(0, str(ROOT / "VibeVoice" / "demo")); sys.path.insert(0, str(ROOT / "VibeVoice"))
import numpy as np, soundfile as sf, torch
from web.app import StreamingTTSService
dev = sys.argv[1] if len(sys.argv) > 1 else "mps"
voices = sys.argv[2].split(",") if len(sys.argv) > 2 else ["en-Soother_woman"]
text = ("That sounds really heavy, and I'm glad you told me. You don't have to figure it all out tonight. "
        "What's been weighing on you the most?")
t0 = time.time()
svc = StreamingTTSService(model_path="microsoft/VibeVoice-Realtime-0.5B", device=dev, inference_steps=int(os.environ.get("STEPS","5")))
os.environ["VOICE_PRESET"] = voices[0]
svc.load(); print(f"LOAD {dev} {time.time()-t0:.1f}s", flush=True)
for _ in svc.stream("Hi there.", voice_key=voices[0]): pass
for v in voices:
    for run in range(2):
        t0 = time.time(); first = None; chunks = []
        for c in svc.stream(text, voice_key=v):
            if first is None: first = time.time() - t0
            chunks.append(c)
        tot = time.time() - t0; a = np.concatenate(chunks); dur = len(a) / 24000
        print(f"RESULT dev={dev} voice={v} run={run} first_chunk_ms={first*1000:.0f} gen={tot:.2f}s audio={dur:.2f}s rtf={tot/dur:.2f}", flush=True)
    sf.write(str(ROOT / "samples" / f"sample_{v}_{dev}.wav"), np.clip(a, -1, 1), 24000, subtype="PCM_16")
