"""Olho e pincel: o Gemini confere se cada imagem combina com a frase narrada e, onde faltar, gera uma imagem.

- conferir(): usa um modelo leve (grátis, 15 por minuto). Descarta cenas fora do assunto.
- gerar(): usa o modelo de imagem do Gemini (precisa de cobrança ativa no projeto). Cerca de US$ 0,04 por imagem.
"""
import base64
import json
import os
import subprocess
import time
from pathlib import Path

import requests

from . import llm

VISION_MODELS = [m for m in [os.getenv("GEMINI_VISION_MODEL"), "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"] if m]
IMAGE_MODELS = [m for m in [os.getenv("GEMINI_IMAGE_MODEL"), "gemini-nano-banana-2.1", "gemini-3.1-flash-lite-image",
                            "gemini-3.1-flash-image"] if m]
_MIN_GAP = 60.0 / float(os.getenv("VISION_RPM", "14"))
_last = [0.0]
_disabled = {"vision": False, "image": False}


def _key():
    return os.environ.get("GEMINI_API_KEY")


def _wait():
    gap = time.time() - _last[0]
    if gap < _MIN_GAP:
        time.sleep(_MIN_GAP - gap)
    _last[0] = time.time()


def frame_of(video, out, t=1.2):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=512:-2", "-q:v", "4", str(out)], check=False)
    return Path(out) if Path(out).exists() else None


def conferir(image_path, narracao, assunto):
    """Nota de 0 a 10 para o quanto a imagem mostra o que a frase diz. None se não deu para conferir."""
    if _disabled["vision"] or not _key():
        return None
    img = Path(image_path)
    if img.suffix.lower() not in (".jpg", ".jpeg", ".png"):
        img = frame_of(img, img.with_suffix(".check.jpg"))
        if not img:
            return None
    else:
        small = img.with_suffix(".small.jpg")
        if not small.exists():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(img), "-vf", "scale=512:-2", "-q:v", "4",
                            str(small)], check=False)
        img = small if small.exists() else img
    b64 = base64.b64encode(img.read_bytes()).decode()
    prompt = (f'Assunto do vídeo: "{assunto}". Frase narrada neste momento: "{narracao[:600]}".\n'
              "Dê uma nota de 0 a 10 para o quanto ESTA imagem mostra algo diretamente ligado à frase ou ao assunto "
              "(o objeto, o lugar, a época ou a ação citados). Paisagem, objeto ou pessoa sem relação = 0 a 3. "
              "Genérico mas coerente (ex.: dinheiro numa frase sobre lucro) = 5 a 6. Mostra o que é citado = 8 a 10. "
              'Responda só JSON: {"nota": 0, "mostra": "o que a imagem mostra em 5 palavras"}')
    body = {"contents": [{"role": "user", "parts": [{"inlineData": {"mimeType": "image/jpeg", "data": b64}},
                                                    {"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": 200}}
    for model in VISION_MODELS:
        for attempt in range(3):
            _wait()
            try:
                r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                  params={"key": _key()}, json=body, timeout=60)
            except requests.RequestException:
                continue
            if r.status_code == 200:
                try:
                    parts = r.json()["candidates"][0]["content"]["parts"]
                    data = llm.parse_json("".join(p.get("text", "") for p in parts))
                    return float(data.get("nota", 0))
                except Exception:  # noqa: BLE001
                    return None
            if r.status_code == 429 and attempt < 2:
                time.sleep(20)
                continue
            if r.status_code in (400, 404):
                break
            if r.status_code == 429:
                break
    print("  conferência de imagens indisponível agora; seguindo sem filtro", flush=True)
    _disabled["vision"] = True
    return None


def gerar(prompt, out_path, vertical=False):
    """Gera uma imagem com IA. Devolve o caminho ou None (sem cobrança ativa, sem cota, erro)."""
    if _disabled["image"] or not _key() or os.getenv("IMAGENS_IA", "1") == "0":
        return None
    ratio = "9:16" if vertical else "16:9"
    full = (f"{prompt}. Photorealistic documentary photograph, natural light, realistic details, "
            f"no text, no captions, no watermark, no logos.")
    body = {"contents": [{"role": "user", "parts": [{"text": full}]}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": ratio,
                                                                                   "imageSize": "1K"}}}
    errors = []
    for model in IMAGE_MODELS:
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                              params={"key": _key()}, json=body, timeout=180)
        except requests.RequestException as e:
            errors.append(f"{model}: {type(e).__name__}")
            continue
        if r.status_code != 200:
            errors.append(f"{model}: HTTP {r.status_code} {r.text[:160]}")
            if r.status_code == 400 and "imageSize" in r.text:
                body["generationConfig"]["imageConfig"].pop("imageSize", None)
            continue
        try:
            for p in r.json()["candidates"][0]["content"]["parts"]:
                inline = p.get("inlineData") or p.get("inline_data")
                if inline and inline.get("data"):
                    Path(out_path).write_bytes(base64.b64decode(inline["data"]))
                    return Path(out_path)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{model}: resposta sem imagem ({e})")
    print(f"  geração de imagem indisponível: {'; '.join(errors)[:400]}", flush=True)
    _disabled["image"] = True
    return None


def resumo():
    return json.dumps(_disabled)
