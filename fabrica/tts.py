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


def _speech_spans(path, min_sil=0.42):
    """Trechos com fala, separados por silêncios de pelo menos min_sil segundos (as pausas de fim de frase)."""
    import re
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", f"silencedetect=n=-40dB:d={min_sil}",
                        "-f", "null", "-"], capture_output=True, text=True)
    total = _probe_duration(path)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", p.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", p.stderr)]
    spans, cur = [], 0.0
    for s0, e0 in zip(starts, ends + [total] * (len(starts) - len(ends))):
        if s0 - cur > 0.15:
            spans.append([cur, s0])
        cur = e0
    if total - cur > 0.15:
        spans.append([cur, total])
    return spans or [[0.0, total]]


def align(text, audio_path):
    """Tempo de cada palavra a partir do próprio áudio: cada frase cai num trecho de fala (entre pausas),
    e dentro da frase as palavras dividem o tempo pelo tamanho. Não depende dos tempos do serviço de voz."""
    import re
    sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", text.strip()) if s.strip()]
    spans = _speech_spans(audio_path)
    if len(spans) != len(sentences):
        # junta ou divide para casar: distribui frases pelo tempo de fala proporcional ao tamanho, e encaixa nas pausas
        speech = sum(e - s for s, e in spans)
        chars = [len(s) for s in sentences]
        total_c = sum(chars) or 1
        bounds = [s for s, _ in spans[1:]]
        mapped, acc, t_lin = [], 0, 0.0
        def lin_to_abs(t):
            for s, e in spans:
                if t <= e - s:
                    return s + t
                t -= e - s
            return spans[-1][1]
        prev = spans[0][0]
        for i, c in enumerate(chars):
            acc += c
            end = lin_to_abs(speech * acc / total_c)
            if i < len(chars) - 1 and bounds:
                near = min(bounds, key=lambda b: abs(b - end))
                if abs(near - end) < 1.2 and near > prev:
                    end = near
            mapped.append([prev, end])
            prev = end
        spans = mapped
    words = []
    for sent, (s0, e0) in zip(sentences, spans):
        toks = sent.split()
        weights = [len(t) + 2 for t in toks]
        tot = sum(weights) or 1
        t = s0
        for tok, w in zip(toks, weights):
            d = (e0 - s0) * w / tot
            words.append([t, t + d * 0.95, tok])
            t += d
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
                    # mp3 do serviço às vezes vem com quadros quebrados: regrava limpo antes de usar
                    clean = out_path.with_suffix(".clean.wav")
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-err_detect", "ignore_err", "-i", str(out_path),
                                    "-ar", "24000", "-ac", "1", str(clean)], check=True)
                    clean.replace(out_path.with_suffix(".wav"))
                    wav = out_path.with_suffix(".wav")
                    try:
                        words = align(text, wav)
                    except Exception as e:  # noqa: BLE001
                        print(f"  alinhamento falhou ({e}); usando tempos do serviço", flush=True)
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-c:a", "libmp3lame", "-b:a",
                                    "128k", str(out_path)], check=True)
                    return _probe_duration(out_path), words
            except Exception as e:  # noqa: BLE001
                last_err = e
    raise RuntimeError(f"narração falhou: {last_err}")
