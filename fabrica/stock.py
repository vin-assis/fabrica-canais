"""Cenas de banco de vídeo (Pexels, grátis). Guarda o crédito de cada autor para a descrição."""
import os
import random
import subprocess
from pathlib import Path

import requests

API = "https://api.pexels.com/v1/videos/search"


class Stock:
    def __init__(self, cache_dir, orientation="landscape", offline=False):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.orientation = orientation
        self.offline = offline or not (os.getenv("PEXELS_API_KEY") or os.getenv("PIXABAY_API_KEY"))
        self.used_ids = set()
        self.credits = {}
        self.photo_files = []
        self.photo_credits = []  # (arquivo, autor, licença, url) das fotos do Wikimedia Commons
        self._n = 0
        self.net = not offline

    def clips(self, query, n=2):
        """Baixa até n clipes para a busca. Sempre devolve pelo menos 1 arquivo (cartão colorido se não achar)."""
        found = []
        if not self.offline:
            if os.getenv("PIXABAY_API_KEY"):
                found = self._pixabay(query, n)
            if not found and os.getenv("PEXELS_API_KEY"):
                found = self._pexels(query, n)
        if not found:
            found = [self._placeholder(query)]
        return found

    # ---------- fotos reais do Wikimedia Commons (licença livre, com crédito) ----------
    OK_LICENSES = ("cc0", "public domain", "pd", "cc by", "cc-by")

    def photos(self, query, n=2):
        """Fotos reais do Commons viradas em clipes de 5 s com zoom lento. Pode voltar vazio."""
        if not self.net:
            return []
        out = self._photos(query, n)
        words = query.split()
        if not out and len(words) > 2:  # busca longa demais: tenta só as 2 primeiras palavras
            out = self._photos(" ".join(words[:2]), n, strict_words=query)
        return out

    @staticmethod
    def _relevant(title, query):
        """A busca do Commons é solta ('Opening Ceremony' traz Olimpíada). Exige metade das palavras no título."""
        import math
        import re
        words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 3]
        if not words:
            return True
        t = title.lower()
        return sum(w in t for w in words) >= max(1, math.ceil(len(words) / 2))

    def _photos(self, query, n, strict_words=None):
        try:
            r = requests.get("https://commons.wikimedia.org/w/api.php", timeout=30,
                             headers={"User-Agent": "fabrica-canais/1.0 (https://github.com/vin-assis/fabrica-canais)"},
                             params={"action": "query", "format": "json", "generator": "search",
                                     "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": 20,
                                     "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": 1280})
            r.raise_for_status()
            pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
        except Exception as e:  # noqa: BLE001
            print(f"  commons falhou para '{query}': {e}", flush=True)
            return []
        out, motivos = [], {"licença": 0, "pequena": 0, "download": 0, "fora do tema": 0}
        for pg in pages:
            info = (pg.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            lic = (meta.get("LicenseShortName", {}).get("value") or "").lower()
            if not lic or any(b in lic for b in ("nc", "nd", "fair use", "non-free")) or \
                    not any(lic.startswith(g) or g in lic for g in self.OK_LICENSES):
                motivos["licença"] += 1
                continue
            if not self._relevant(pg["title"], strict_words or query):
                motivos["fora do tema"] += 1
                continue
            if info.get("width", 0) < 900 or pg["title"] in self.used_ids:
                motivos["pequena"] += 1
                continue
            import html
            import re
            artist = re.sub("<[^>]+>", "", html.unescape(meta.get("Artist", {}).get("value", "") or "")).strip()[:60]
            src = info.get("thumburl") or info.get("url")
            img = self.dir / f"cm_{pg['pageid']}.jpg"
            if not self._download(src, img):
                motivos["download"] += 1
                continue
            clip = self._photo_clip(img)
            if not clip:
                continue
            self.used_ids.add(pg["title"])
            self.photo_files.append(img)
            self.photo_credits.append((pg["title"].replace("File:", ""), artist or "autor desconhecido",
                                       meta.get("LicenseShortName", {}).get("value", ""), info.get("descriptionurl", "")))
            out.append(clip)
            if len(out) >= n:
                break
        print(f"  commons '{query}': {len(pages)} achadas, {len(out)} usadas, descartes {motivos}", flush=True)
        return out

    def _photo_clip(self, img, dur=5.0):
        w, h = (1920, 1080) if self.orientation == "landscape" else (1080, 1920)
        out = img.with_suffix(f".{self.orientation}.mp4")
        if out.exists():
            return out
        frames = int(dur * 30)
        fc = (f"[0]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=30:3,eq=brightness=-0.12[bg];"
              f"[0]scale={int(w*0.94)}:{int(h*0.94)}:force_original_aspect_ratio=decrease[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2,scale={w*2}:{h*2},"
              f"zoompan=z='min(zoom+0.0006,1.10)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=30,"
              f"format=yuv420p")
        p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(img), "-filter_complex", fc,
                            "-t", f"{dur}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out)],
                           capture_output=True, text=True)
        if p.returncode != 0:
            print(f"  foto {img.name} não converteu: {p.stderr[-200:]}", flush=True)
            return None
        return out

    def _pexels(self, query, n):
        try:
            r = requests.get(API, headers={"Authorization": os.environ["PEXELS_API_KEY"]},
                             params={"query": query, "orientation": self.orientation, "per_page": 15,
                                     "size": "medium"}, timeout=30)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            print(f"  pexels falhou para '{query}': {e}")
            return []
        out = []
        videos = [v for v in r.json().get("videos", []) if v["id"] not in self.used_ids and v.get("duration", 0) >= 4]
        for v in videos[: n * 2]:
            f = self._best_file(v)
            if not f:
                continue
            path = self.dir / f"px_{v['id']}.mp4"
            if not path.exists():
                try:
                    with requests.get(f["link"], stream=True, timeout=120) as d:
                        d.raise_for_status()
                        with open(path, "wb") as fh:
                            for chunk in d.iter_content(1 << 20):
                                fh.write(chunk)
                except Exception as e:  # noqa: BLE001
                    print(f"  download falhou {v['id']}: {e}")
                    continue
            self.used_ids.add(v["id"])
            self.credits[v["user"]["name"]] = v["user"].get("url", "https://www.pexels.com")
            out.append(path)
            if len(out) >= n:
                break
        return out

    def _download(self, url, path):
        if path.exists():
            return True
        try:
            headers = {"User-Agent": "fabrica-canais/1.0 (https://github.com/vin-assis/fabrica-canais; bot de video)"}
            with requests.get(url, stream=True, timeout=120, headers=headers) as d:
                d.raise_for_status()
                with open(path, "wb") as fh:
                    for chunk in d.iter_content(1 << 20):
                        fh.write(chunk)
            return True
        except Exception as e:  # noqa: BLE001
            print(f"  download falhou {url[:60]}: {e}")
            path.unlink(missing_ok=True)
            return False

    def _pixabay(self, query, n):
        """Pixabay: vídeos grátis, 100 pedidos por minuto. Precisa baixar (não pode usar o link direto)."""
        try:
            r = requests.get("https://pixabay.com/api/videos/",
                             params={"key": os.environ["PIXABAY_API_KEY"], "q": query[:100], "per_page": 20,
                                     "safesearch": "true", "video_type": "film"}, timeout=30)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            print(f"  pixabay falhou para '{query}': {e}")
            return []
        out = []
        want_w = 1920 if self.orientation == "landscape" else 1080
        for v in r.json().get("hits", []):
            key = f"pb{v['id']}"
            if key in self.used_ids or v.get("duration", 0) < 4:
                continue
            files = [f for f in (v.get("videos") or {}).values() if f.get("url") and f.get("width")]
            ok = [f for f in files if f["width"] >= want_w * 0.66] or files
            if not ok:
                continue
            f = min(ok, key=lambda f: abs(f["width"] - want_w))
            path = self.dir / f"pb_{v['id']}.mp4"
            if not self._download(f["url"], path):
                continue
            self.used_ids.add(key)
            self.credits[v.get("user", "Pixabay")] = f"https://pixabay.com/users/{v.get('user','')}-{v.get('user_id','')}/"
            out.append(path)
            if len(out) >= n:
                break
        return out

    def _best_file(self, v):
        want_w = 1920 if self.orientation == "landscape" else 1080
        files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("width")]
        if not files:
            return None
        ok = [f for f in files if f["width"] >= want_w * 0.66]
        pool = ok or files
        return min(pool, key=lambda f: abs(f["width"] - want_w))

    def _placeholder(self, query):
        self._n += 1
        w, h = (1920, 1080) if self.orientation == "landscape" else (1080, 1920)
        hue = random.Random(query).randint(0, 359)
        path = self.dir / f"ph_{self._n}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                        "-i", f"gradients=s={w}x{h}:c0=0x1b1f2a:c1=0x3a4a6b:speed=0.02:d=8:r=30",
                        "-vf", f"hue=h={hue}", "-t", "8", "-pix_fmt", "yuv420p", "-c:v", "libx264",
                        "-preset", "ultrafast", str(path)], check=True)
        return path
