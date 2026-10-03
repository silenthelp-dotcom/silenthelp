"""Measure streaming TTS latency over the websocket exactly like the browser does."""
import asyncio, json, sys, time, urllib.parse
import numpy as np, soundfile as sf, websockets

TEXT = sys.argv[1] if len(sys.argv) > 1 else "That sounds really heavy, and I'm glad you told me. What's been the hardest part?"
OUT = sys.argv[2] if len(sys.argv) > 2 else None

async def main():
    url = "ws://127.0.0.1:5077/tts?text=" + urllib.parse.quote(TEXT)
    t0 = time.time(); first = None; pcm = []
    async with websockets.connect(url, origin="http://127.0.0.1:5055", max_size=None) as ws:
        async for msg in ws:
            if isinstance(msg, bytes):
                if first is None:
                    first = time.time() - t0
                pcm.append(np.frombuffer(msg, dtype=np.int16))
            else:
                m = json.loads(msg)
                if m.get("type") == "done":
                    print("server:", m)
    a = np.concatenate(pcm) if pcm else np.zeros(1, np.int16)
    total = time.time() - t0
    print(f"client: first_audio_ms={first*1000:.0f} total={total:.2f}s audio={len(a)/24000:.2f}s chunks={len(pcm)}")
    if OUT:
        sf.write(OUT, a, 24000, subtype="PCM_16")

asyncio.run(main())
