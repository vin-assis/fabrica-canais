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


def _sentences(text):
    """Frases para narrar uma a uma. Pedaços muito curtos vão junto com a frase seguinte."""
    import re
    parts = [x.strip() for x in re.split(r"(?<=[.!?…])\s+", text.strip()) if x.strip()]
    out = []
    for x in parts:
        if out and len(out[-1].split()) < 3:
            out[-1] = out[-1] + " " + x
        else:
            out.append(x)
    return out or [text.strip()]


async def _edge_bytes(text, voice, rate):
    import edge_tts
    com = edge_tts.Communicate(text, voice, rate=rate)
    data = bytearray()
    async for chunk in com.stream():
        if chunk["type"] == "audio":
            data += chunk["data"]
    return bytes(data)


def _read_wav(path):
    import wave
    import numpy as np
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def _write_wav(path, x, sr=24000):
    import wave
    import numpy as np
    y = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(y.tobytes())


def tem_corte(x, sr=24000):
    """Procura sinal de áudio picotado: som que começa 'no meio' (forte de uma vez) logo depois de silêncio total.
    Medido em relação ao pico da própria frase, então não depende do volume."""
    import numpy as np
    a = np.abs(x)
    n = sr // 50  # 20 ms
    if len(a) < sr // 10:
        return False
    peak = a.max() or 1.0
    prev = np.convolve(a, np.ones(n) / n, "full")[:len(a)]
    abrupt = np.where((a[n:] > 0.3 * peak) & (prev[n - 1:-1] < 0.004 * peak))[0]
    return len(abrupt) > 0


def _one(sentence, voice, rate, tmp):
    """Narra uma frase e só aceita se o mp3 decodificar sem erro e sem corte. Devolve o áudio limpo ou None."""
    mp3, wav, cut = tmp.with_suffix(".mp3"), tmp.with_suffix(".wav"), tmp.with_suffix(".cut.wav")
    data = asyncio.run(_edge_bytes(sentence, voice, rate))
    if len(data) < 800:
        raise RuntimeError("sem áudio")
    mp3.write_bytes(data)
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-ar", "24000", "-ac", "1", str(wav)],
                       capture_output=True, text=True)
    quebrado = p.returncode != 0 or bool(p.stderr.strip())
    if quebrado:  # mp3 com quadro quebrado: guarda uma versão remendada só como último recurso
        print(f"    mp3 com defeito: {p.stderr.strip()[:120]}", flush=True)
        subprocess.run(["ffmpeg", "-v", "quiet", "-y", "-err_detect", "ignore_err", "-i", str(mp3), "-ar", "24000",
                        "-ac", "1", str(wav)], check=True)
    corte = quebrado or tem_corte(_read_wav(wav))  # testa antes de aparar, com o silêncio original em volta
    # tira só o excesso de silêncio das pontas, com folga para não comer o começo suave da palavra
    x = _aparar(_read_wav(wav))
    if corte:
        _one.suspeito = x  # guarda: se nenhuma tentativa vier limpa, usa a última
        return None
    return x


def _aparar(x, sr=24000, antes=0.07, depois=0.12):
    """Corta o silêncio longo do começo e do fim, mas deixa 70 ms antes do primeiro som e 120 ms depois
    do último (o ataque e a cauda da voz ficam inteiros). Rampa curta só nas pontas do silêncio."""
    import numpy as np
    a = np.abs(x)
    som = np.where(a > 0.0015)[0]
    if len(som) == 0:
        return x
    i0 = max(0, som[0] - int(antes * sr))
    i1 = min(len(x), som[-1] + int(depois * sr))
    y = x[i0:i1].copy()
    n = min(len(y) // 4, int(0.03 * sr))
    if n > 0:
        y[-n:] *= np.linspace(1, 0, n)
    return y


PAUSA = {".": 0.26, "!": 0.3, "?": 0.32, "…": 0.32, ":": 0.16, ";": 0.16}  # somadas às folgas de 70+120 ms


def synth(text, voice, rate, out_path, offline=False):
    """Gera out_path (.mp3) narrando frase por frase.
    Retorna (duração_em_s, palavras[[início, fim, texto]], frases[[início, fim, texto]])."""
    import numpy as np
    out_path = Path(out_path)
    sents = _sentences(text)
    if offline:
        toks = text.split()
        dur = max(1.0, len(toks) / 2.6)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                        "-t", f"{dur:.2f}", "-c:a", "libmp3lame", "-b:a", "64k", str(out_path)], check=True)
        step = dur / len(toks)
        words = [[i * step, (i + 1) * step * 0.95, t] for i, t in enumerate(toks)]
        frases, k = [], 0
        for s in sents:
            n = len(s.split())
            frases.append([k * step, (k + n) * step, s])
            k += n
        return dur, words, frases
    fallback = {"en": ["en-US-GuyNeural", "en-US-ChristopherNeural", "en-US-AndrewNeural"],
                "pt": ["pt-BR-AntonioNeural", "pt-BR-FranciscaNeural"]}[voice[:2]]
    tmpdir = out_path.parent / (out_path.stem + "_frases")
    tmpdir.mkdir(exist_ok=True)
    last_err = None
    for v in [voice] + [f for f in fallback if f != voice]:
        pieces, ok = [], True
        for i, s in enumerate(sents):
            x = None
            for attempt in range(4):
                try:
                    x = _one(s, v, rate, tmpdir / f"f{i:03d}_{attempt}")
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    x = None
                if x is not None:
                    break
                if attempt == 1:
                    print(f"  frase {i+1} veio com defeito, pedindo de novo", flush=True)
            if x is None and getattr(_one, "suspeito", None) is not None:
                print(f"  frase {i+1}: usando versão com possível defeito (nenhuma veio limpa)", flush=True)
                x = _one.suspeito
            _one.suspeito = None
            if x is None:
                ok = False
                break
            pieces.append(x)
        if not ok:
            if pieces:  # a voz funcionou mas uma frase nunca veio limpa
                print(f"  frase sem versão limpa: {sents[len(pieces)][:60]}", flush=True)
            continue
        if v != voice:
            print(f"  voz {voice} falhou, usando {v}", flush=True)
        sr, audio, frases, words, t = 24000, [], [], [], 0.0
        for i, (s, x) in enumerate(zip(sents, pieces)):
            d = len(x) / sr
            frases.append([t, t + d, s])
            toks = s.split()
            weights = [len(tok) + 2 for tok in toks]
            tot = sum(weights) or 1
            tw = t
            for tok, wgt in zip(toks, weights):
                dw = d * wgt / tot
                words.append([tw, tw + dw * 0.95, tok])
                tw += dw
            audio.append(x)
            t += d
            if i < len(sents) - 1:
                gap = PAUSA.get(s.rstrip()[-1:], 0.14)
                audio.append(np.zeros(int(gap * sr), dtype=np.float32))
                t += gap
        wav = out_path.with_suffix(".wav")
        _write_wav(wav, np.concatenate(audio), sr)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "192k",
                        str(out_path)], check=True)
        return t, words, frases
    raise RuntimeError(f"narração falhou: {last_err}")
