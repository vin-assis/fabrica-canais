"""Vozes do Cresci, Ferrou! com o TTS do Gemini.

Cada fala é gerada separada, com a voz do personagem. Depois o áudio é transcrito de volta
(faster-whisper) e comparado palavra por palavra com o texto. Se faltar palavra, gera de novo.
Se nenhuma tentativa passar, a fala fica marcada como REPROVADA no relatório (nunca entra em silêncio).

Uso:
  python -m fabrica.vozes teste            -> audição: o mesmo trecho com vários pares de voz
  python -m fabrica.vozes episodio ep1     -> episódio inteiro (roteiros/cresci_ep1.json)
"""
import base64
import difflib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import wave
from pathlib import Path

import requests

MODELOS = [m for m in [os.getenv("GEMINI_TTS_MODEL"), "gemini-3.8-flash-tts",
                       "gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"] if m]
RATE = 24000
PAUSA = 0.35  # segundos entre falas

ESTILO = {
    "LEO": "Fale em português do Brasil, sotaque paulista neutro. Voz de um rapaz de 22 anos, "
           "animado, impulsivo, meio atrapalhado, com timing de comédia.",
    "TATI": "Fale em português do Brasil, sotaque paulista neutro. Voz de uma mulher de 27 anos, "
            "segura, calma, explica com leve ironia e simpatia, sem tom de professora.",
}

PARES_TESTE = [
    {"LEO": "Puck", "TATI": "Leda"},
    {"LEO": "Fenrir", "TATI": "Aoede"},
    {"LEO": "Achird", "TATI": "Sulafat"},
]

TRECHO_TESTE = [
    ["LEO", "Eu paguei. Eu PAGUEI. Como é que a fatura ficou maior?"],
    ["TATI", "Deixa eu adivinhar. Pagou o mínimo."],
    ["LEO", "Era uma opção da fatura!"],
    ["TATI", "Era uma opção de empréstimo. Tudo o que você não paga da fatura vira crédito rotativo, "
             "e o rotativo é o empréstimo mais caro do país."],
    ["LEO", "Quatrocentos por cento? Isso nem existe."],
    ["TATI", "Existe, e você está pagando."],
]


class TTSErro(Exception):
    pass


def _gera(texto, voz, estilo):
    key = os.environ["GEMINI_API_KEY"]
    body = {
        "contents": [{"parts": [{"text":
            "### NOTAS DE DIREÇÃO (não ler em voz alta)\n"
            f"{estilo}\n\n"
            "### TRANSCRIÇÃO (ler só isto, exatamente como está)\n"
            f"{texto}"}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}},
        },
    }
    erros = []
    for modelo in MODELOS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
        for tentativa in range(3):
            try:
                r = requests.post(url, params={"key": key}, json=body, timeout=(20, 180))
            except requests.RequestException as e:
                erros.append(f"{modelo}: {type(e).__name__}")
                continue
            if r.status_code == 200:
                parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                for p in parts:
                    if "inlineData" in p:
                        return base64.b64decode(p["inlineData"]["data"]), modelo
                erros.append(f"{modelo}: resposta sem áudio")
                break
            if r.status_code in (429, 500, 502, 503) and "limit: 0" not in r.text:
                time.sleep(10 * (tentativa + 1))
                continue
            erros.append(f"{modelo}: HTTP {r.status_code} {r.text[:200]}")
            break
    raise TTSErro("; ".join(erros))


def _salva_wav(pcm, path):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)


_whisper = None


def _transcreve(path):
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel(os.getenv("WHISPER_MODEL", "small"), device="cpu", compute_type="int8")
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    segs, _ = _whisper.transcribe(audio, language="pt", beam_size=5, vad_filter=False)
    return " ".join(s.text for s in segs)


def _norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9]+", t)


def confere(texto, ouvido):
    """Nota de 0 a 1 e lista de palavras do texto que não apareceram no áudio."""
    a, b = _norm(texto), _norm(ouvido)
    sm = difflib.SequenceMatcher(None, a, b)
    faltando = []
    for op, i1, i2, _, _ in sm.get_opcodes():
        if op in ("delete", "replace"):
            faltando += a[i1:i2]
    return round(sm.ratio(), 3), faltando


def _apara(pcm):
    """Tira silêncio do começo e do fim (com folga de 60 ms), sem encostar na fala."""
    import numpy as np
    x = np.frombuffer(pcm, dtype=np.int16)
    if not len(x):
        return pcm
    env = np.abs(x.astype(np.int32))
    lim = max(300, int(env.max() * 0.02))
    idx = np.where(env > lim)[0]
    if not len(idx):
        return pcm
    folga = int(0.06 * RATE)
    return x[max(0, idx[0] - folga): min(len(x), idx[-1] + folga)].tobytes()


def fala(texto, voz, personagem, out, tentativas=4, nota_min=0.9):
    melhor = None
    for n in range(tentativas):
        pcm, modelo = _gera(texto, voz, ESTILO[personagem])
        pcm = _apara(pcm)
        _salva_wav(pcm, out)
        ouvido = _transcreve(out)
        nota, faltando = confere(texto, ouvido)
        res = {"texto": texto, "ouvido": ouvido.strip(), "nota": nota, "faltando": faltando,
               "tentativa": n + 1, "modelo": modelo, "dur": round(len(pcm) / 2 / RATE, 2)}
        print(f"  [{personagem}/{voz}] t{n+1} nota {nota} faltando {faltando}", flush=True)
        if melhor is None or nota > melhor[0]["nota"]:
            melhor = (res, pcm)
        if nota >= nota_min and not faltando:
            res["ok"] = True
            return res, pcm
    res, pcm = melhor
    _salva_wav(pcm, out)
    res["ok"] = False
    return res, pcm


def monta(falas, vozes, pasta, nome):
    pasta.mkdir(parents=True, exist_ok=True)
    pcm_total, t, relatorio = b"", 0.0, []
    silencio = b"\x00\x00" * int(PAUSA * RATE)
    for i, (pers, texto) in enumerate(falas):
        res, pcm = fala(texto, vozes[pers], pers, pasta / f"{nome}_{i:03d}.wav")
        res.update({"i": i, "personagem": pers, "voz": vozes[pers], "inicio": round(t, 2)})
        relatorio.append(res)
        pcm_total += pcm + silencio
        t += len(pcm) / 2 / RATE + PAUSA
    wav = pasta / f"{nome}.wav"
    _salva_wav(pcm_total, wav)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-af", "loudnorm=I=-16:TP=-1.5",
                    "-b:a", "160k", str(pasta / f"{nome}.mp3")], check=True)
    (pasta / f"{nome}.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=1))
    reprov = [r for r in relatorio if not r["ok"]]
    print(f"{nome}: {len(relatorio)} falas, {len(reprov)} reprovadas, {t:.1f} s", flush=True)
    return relatorio


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "teste"
    out = Path("vozes")
    if modo == "teste":
        for k, par in enumerate(PARES_TESTE, 1):
            monta(TRECHO_TESTE, par, out, f"par{k}_leo-{par['LEO']}_tati-{par['TATI']}")
    else:
        ep = json.loads(Path(f"roteiros/cresci_{sys.argv[2]}.json").read_text())
        monta(ep["falas"], ep["vozes"], out, f"cresci_{sys.argv[2]}")
    for f in out.glob("*_[0-9][0-9][0-9].wav"):
        f.unlink()


if __name__ == "__main__":
    main()
