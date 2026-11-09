"""Pesquisa grátis e com fonte: artigos da Wikipédia no idioma do canal e em inglês."""
import requests

UA = {"User-Agent": "fabrica-canais/1.0 (https://github.com/vin-assis/fabrica-canais)"}


def _search(lang, query, n):
    r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", headers=UA, timeout=30, params={
        "action": "query", "list": "search", "srsearch": query, "srlimit": n, "format": "json"})
    r.raise_for_status()
    return [h["title"] for h in r.json().get("query", {}).get("search", [])]


def _extract(lang, title, max_chars):
    r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", headers=UA, timeout=30, params={
        "action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1, "titles": title, "format": "json"})
    r.raise_for_status()
    pages = r.json().get("query", {}).get("pages", {})
    for p in pages.values():
        text = p.get("extract", "")
        if text:
            url = f"https://{lang}.wikipedia.org/wiki/{p['title'].replace(' ', '_')}"
            return p["title"], text[:max_chars], url
    return None


def gather(topic, langs=("pt", "en"), per_lang=3, max_chars=9000, english_query=None):
    """Devolve (texto_do_dossie_bruto, fontes). Nunca levanta erro: sem internet, volta vazio."""
    parts, sources, seen = [], [], set()
    for lang in langs:
        q = english_query if (lang == "en" and english_query) else topic
        try:
            titles = _search(lang, q, per_lang)
        except Exception as e:  # noqa: BLE001
            print(f"  wikipédia {lang}: busca falhou ({e})", flush=True)
            continue
        for t in titles:
            try:
                got = _extract(lang, t, max_chars)
            except Exception as e:  # noqa: BLE001
                print(f"  wikipédia {lang}: '{t}' falhou ({e})", flush=True)
                continue
            if not got or got[2] in seen:
                continue
            title, text, url = got
            seen.add(url)
            parts.append(f"### Fonte: {title} ({url})\n{text}")
            sources.append({"name": f"Wikipédia: {title}", "url": url})
    print(f"  wikipédia: {len(sources)} artigos", flush=True)
    return "\n\n".join(parts), sources
