"""Narração. Padrão: vozes neurais do Microsoft Edge (edge-tts, grátis). Devolve áudio + tempo de cada palavra."""
import asyncio
import json
import subprocess
from pathlib import Path


def _probe_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


async def _edge(text, voice, rate, out_path):
    import edge_tts
    com = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words = []
    with open(out_path, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append([start, start + chunk["duration"] / 1e7, chunk["text"]])
    return words


def synth(text, voice, rate, out_path, offline=False):
    """Gera out_path (.mp3). Retorna (duração_em_s, palavras[[início, fim, texto]])."""
    out_path = Path(out_path)
    if offline:
        toks = text.split()
        dur = max(1.0, len(toks) / 2.6)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                        "-t", f"{dur:.2f}", "-c:a", "libmp3lame", "-b:a", "64k", str(out_path)], check=True)
        step = dur / len(toks)
        return dur, [[i * step, (i + 1) * step * 0.95, t] for i, t in enumerate(toks)]
    last_err = None
    fallback = {"en": ["en-US-GuyNeural", "en-US-ChristopherNeural", "en-US-AndrewNeural"],
                "pt": ["pt-BR-AntonioNeural", "pt-BR-FranciscaNeural"]}[voice[:2]]
    for v in [voice] + [f for f in fallback if f != voice]:
        for _ in range(2):
            try:
                words = asyncio.run(_edge(text, v, rate, out_path))
                if out_path.stat().st_size > 1000:
                    if v != voice:
                        print(f"  voz {voice} falhou, usando {v}", flush=True)
                    return _probe_duration(out_path), words
            except Exception as e:  # noqa: BLE001
                last_err = e
    raise RuntimeError(f"narração falhou: {last_err}")
