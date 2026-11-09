"""Thumbnails 1280x720: imagem de fundo + texto grande com contorno. Gera 3 opções para você escolher."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT_CANDIDATES = [ROOT / "assets/fonts/Anton-Regular.ttf", ROOT / "assets/fonts/Poppins-Bold.ttf"]
PALETTES = [("#FFE100", "#000000"), ("#FFFFFF", "#000000"), ("#FF3B30", "#FFFFFF")]


def _font(size):
    for f in FONT_CANDIDATES:
        if f.exists():
            return ImageFont.truetype(str(f), size)
    return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        test = (cur + " " + wd).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def make(bg_path, text, out, variant=0):
    W, H = 1280, 720
    img = Image.open(bg_path).convert("RGB")
    r = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * r) + 1, int(img.height * r) + 1))
    left = (img.width - W) // 2
    img = img.crop((left, (img.height - H) // 2, left + W, (img.height - H) // 2 + H))
    img = ImageEnhance.Contrast(img).enhance(1.25)
    img = ImageEnhance.Color(img).enhance(1.3)
    shade = Image.new("L", (W, H))
    sd = ImageDraw.Draw(shade)
    for x in range(W):
        sd.line([(x, 0), (x, H)], fill=int(190 * max(0, 1 - x / (W * 0.75))))
    dark = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.composite(dark, img, shade.filter(ImageFilter.GaussianBlur(8)))
    d = ImageDraw.Draw(img)
    fill, stroke = PALETTES[variant % len(PALETTES)]
    text = text.upper()
    size = 150
    while size > 60:
        font = _font(size)
        lines = _wrap(d, text, font, W * 0.62)
        line_h = size * 1.05
        if len(lines) * line_h <= H * 0.78 and len(lines) <= 3:
            break
        size -= 8
    y = (H - len(lines) * line_h) / 2
    for ln in lines:
        d.text((60, y), ln, font=font, fill=fill, stroke_width=max(4, size // 14), stroke_fill=stroke)
        y += line_h
    img.save(out, quality=92)
    return out
