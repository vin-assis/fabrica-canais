"""Cartela de número: quando a frase traz um ano, valor ou porcentagem e não há foto própria para ela,
mostra o número grande na tela em vez de repetir uma foto que já apareceu."""
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT_B = ROOT / "assets/fonts/Poppins-Bold.ttf"
FONT_R = ROOT / "assets/fonts/Poppins-Regular.ttf"

_NUM = re.compile(
    r"(?:US\$|R\$|€|£)\s?\d[\d.,]*(?:\s(?:milhões|milhão|bilhões|bilhão|trilhões|mil|thousand|million|billion)\b)?"
    r"|\d+(?:[.,]\d+)?\s?%"
    r"|\d[\d.,]*\s(?:milhões|milhão|bilhões|bilhão|trilhões|mil|million|billion)\b"
    r"(?:\s(?:de\s)?(?:dólares|reais|euros|pessoas|empregados|funcionários|dollars|people))?"
    r"|\b(?:1[5-9]|20)\d{2}\b"
    r"|\b\d{1,3}(?:\.\d{3})+\b")


def numero(frase):
    """O número mais informativo da frase (valor > porcentagem > ano), ou None."""
    achados = _NUM.findall(frase)
    if not achados:
        return None
    achados.sort(key=lambda s: (not s.strip().startswith(("US$", "R$", "€", "£")), "%" not in s, len(s) < 5))
    return achados[0].strip()


def _fit(draw, text, font_path, max_w, start):
    size = start
    while size > 30:
        f = ImageFont.truetype(str(font_path), size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 8
    return ImageFont.truetype(str(font_path), 30)


def fazer(num, rotulo, out, vertical=False):
    w, h = (1080, 1920) if vertical else (1920, 1080)
    img = Image.new("RGB", (w, h), (14, 18, 24))
    glow = Image.new("RGB", (w, h), (14, 18, 24))
    g = ImageDraw.Draw(glow)
    g.ellipse([w * 0.15, h * 0.2, w * 0.85, h * 0.8], fill=(46, 38, 20))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(220)), 0.9)
    d = ImageDraw.Draw(img)
    fn = _fit(d, num, FONT_B, w * 0.86, 300 if not vertical else 220)
    fr = _fit(d, rotulo.upper(), FONT_R, w * 0.8, 52 if not vertical else 46)
    nb = d.textbbox((0, 0), num, font=fn)
    rb = d.textbbox((0, 0), rotulo.upper(), font=fr)
    total = (nb[3] - nb[1]) + 60 + (rb[3] - rb[1])
    y0 = (h - total) / 2 - (h * 0.06 if vertical else 0)
    d.text(((w - (rb[2] - rb[0])) / 2, y0), rotulo.upper(), font=fr, fill=(170, 176, 186))
    yl = y0 + rb[3] + 26
    d.line([(w / 2 - 90, yl), (w / 2 + 90, yl)], fill=(242, 193, 78), width=5)
    d.text(((w - (nb[2] - nb[0])) / 2, yl + 40 - nb[1]), num, font=fn, fill=(242, 193, 78))
    img.save(out, quality=94)
    return Path(out)
