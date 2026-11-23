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


def _small(image_path):
    img = Path(image_path)
    if img.suffix.lower() not in (".jpg", ".jpeg", ".png"):
        return frame_of(img, img.with_suffix(".check.jpg"))
    small = img.with_suffix(".small.jpg")
    if not small.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(img), "-vf", "scale=512:-2", "-q:v", "4",
                        str(small)], check=False)
    return small if small.exists() else img


def _ask(img, prompt):
    b64 = base64.b64encode(img.read_bytes()).decode()
    body = {"contents": [{"role": "user", "parts": [{"inlineData": {"mimeType": "image/jpeg", "data": b64}},
                                                    {"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": 300}}
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
                    return llm.parse_json("".join(p.get("text", "") for p in parts))
                except Exception:  # noqa: BLE001
                    return None
            if r.status_code == 429 and attempt < 2:
                time.sleep(20)
                continue
            break
    print("  conferência de imagens indisponível agora; seguindo sem filtro", flush=True)
    _disabled["vision"] = True
    return None


def avaliar(image_path, frases, assunto):
    """Olha a imagem e diz (nota 0-10, índice da frase que ela ilustra melhor). (None, None) se não deu."""
    if _disabled["vision"] or not _key():
        return None, None
    img = _small(image_path)
    if not img:
        return None, None
    lista = "\n".join(f"{i}: {f[:220]}" for i, f in enumerate(frases))
    prompt = (f'Assunto do vídeo: "{assunto}". Frases narradas neste trecho, numeradas:\n{lista}\n\n'
              "Esta imagem vai aparecer na tela enquanto UMA dessas frases é dita. Escolha a frase que ela ilustra "
              "melhor e dê nota de 0 a 10 para o quanto ela mostra ESPECIFICAMENTE o que a frase cita "
              "(a empresa, o produto, o objeto, a pessoa, o lugar, a época ou o fato).\n"
              "- Mostra exatamente o que é citado (ex.: câmera Kodak antiga numa frase sobre a câmera de 1888) = 8 a 10.\n"
              "- Relacionado ao assunto mas não ao que a frase diz (ex.: prédio da Kodak numa frase sobre falência) = 6 a 7.\n"
              "- Imagem de banco genérica (pessoa qualquer, natureza, praia, laboratório, escritório, câmera de "
              "outra marca atual) = no máximo 4.\n"
              "- Logotipo, faixa, cartaz ou texto de outra coisa, ou sem relação = 0 a 2.\n"
              "- Droga, planta de maconha, arma, sangue, nudez ou rosto de celebridade sem ligação direta com a frase = 0.\n"
              'Se aparecer uma pessoa famosa reconhecível (político, atleta, artista), escreva o nome dela em "famoso"; '
              'senão deixe "".\n'
              'Responda só JSON: {"frase": 0, "nota": 0, "famoso": "", "mostra": "o que a imagem mostra em até 6 palavras"}')
    data = _ask(img, prompt)
    if isinstance(data, list):  # às vezes o modelo devolve [ {...} ]
        data = next((d for d in data if isinstance(d, dict)), None)
    if not isinstance(data, dict):
        return None, None
    try:
        fi = int(data.get("frase", 0))
    except (TypeError, ValueError):
        fi = 0
    try:
        nota = float(data.get("nota", 0))
    except (TypeError, ValueError):
        return None, None
    famoso = str(data.get("famoso") or "").strip().lower()
    if famoso:
        texto = " ".join(frases).lower() + " " + assunto.lower()
        partes = [p for p in famoso.replace("-", " ").split() if len(p) > 3]
        if not any(p in texto for p in partes):
            nota = 0.0  # rosto famoso que a narração não cita
    return nota, max(0, min(len(frases) - 1, fi))


def conferir(image_path, narracao, assunto):
    """Compatibilidade: nota de 0 a 10 contra o trecho inteiro."""
    nota, _ = avaliar(image_path, [narracao[:600]], assunto)
    return nota


def gerar(prompt, out_path, vertical=False):
    """Gera uma imagem com IA. Devolve o caminho ou None (sem cobrança ativa, sem cota, erro)."""
    if _disabled["image"] or not _key() or os.getenv("IMAGENS_IA", "1") == "0":
        return None
    ratio = "9:16" if vertical else "16:9"
    full = (f"{prompt}. Editorial digital illustration in a painterly documentary style, muted period colors, "
            f"clearly a drawing and not a photograph. Generic anonymous people only, never a real or famous person. "
            f"Absolutely no written words, letters, numbers, signs, posters, newspapers or labels anywhere in the image; "
            f"no watermark, no logos, no brand names.")
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
