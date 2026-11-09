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
        self._n = 0

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
            with requests.get(url, stream=True, timeout=120) as d:
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
