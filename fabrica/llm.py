"""Chamadas ao modelo de linguagem. Padrão: Gemini (tem plano grátis). Opcional: Claude (ANTHROPIC_API_KEY)."""
import json
import os
import re
import time

import requests

GEMINI_MODELS = [m for m in [os.getenv("GEMINI_MODEL"), "gemini-3.6-flash", "gemini-flash-latest",
                             "gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"] if m]
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")


class LLMError(RuntimeError):
    pass


def provider() -> str:
    if os.getenv("LLM_PROVIDER"):
        return os.environ["LLM_PROVIDER"]
    if os.getenv("ANTHROPIC_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        return "anthropic"
    return "gemini"


def _gemini(prompt: str, search: bool, want_json: bool, temperature: float):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise LLMError("GEMINI_API_KEY não configurada")
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 16000},
    }
    if search:
        body["tools"] = [{"google_search": {}}]
    elif want_json:
        body["generationConfig"]["responseMimeType"] = "application/json"
    errors = []
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(3):
            try:
                r = requests.post(url, params={"key": key}, json=body, timeout=(20, 420))
            except requests.RequestException as e:
                errors.append(f"{model}: {type(e).__name__}")
                print(f"  gemini {model}: {type(e).__name__}, tentando de novo", flush=True)
                continue
            if r.status_code == 200:
                pass
            elif r.status_code == 429 and "limit: 0" in r.text:
                errors.append(f"{model}: sem cota no plano grátis")
                print(f"  gemini {model}: sem cota no plano grátis, pulando", flush=True)
                break
            elif r.status_code == 429 or r.status_code >= 500:
                errors.append(f"{model}: HTTP {r.status_code}")
                print(f"  gemini {model}: HTTP {r.status_code} {r.text[:200]}", flush=True)
                time.sleep(15 * (attempt + 1))
                continue
            else:
                errors.append(f"{model}: HTTP {r.status_code} {r.text[:200]}")
                print(f"  gemini {model}: HTTP {r.status_code} {r.text[:300]}", flush=True)
                break
            data = r.json()
            cand = (data.get("candidates") or [{}])[0]
            text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
            sources = []
            for ch in cand.get("groundingMetadata", {}).get("groundingChunks", []) or []:
                web = ch.get("web") or {}
                if web.get("uri"):
                    sources.append({"name": web.get("title", ""), "url": web["uri"]})
            if not text.strip():
                errors.append(f"{model}: resposta vazia ({cand.get('finishReason')})")
                time.sleep(5)
                continue
            print(f"  gemini {model}: ok ({len(text)} caracteres)", flush=True)
            return text, sources
    raise LLMError("; ".join(errors[-6:]) or "falha no Gemini")


def _anthropic(prompt: str, search: bool, want_json: bool, temperature: float):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise LLMError("ANTHROPIC_API_KEY não configurada")
    body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 16000,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if search:
        body["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}]
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    for attempt in range(4):
        r = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=body, timeout=600)
        if r.status_code in (429, 500, 502, 503, 529):
            time.sleep(20 * (attempt + 1))
            continue
        if r.status_code != 200:
            raise LLMError(f"Claude: HTTP {r.status_code} {r.text[:500]}")
        data = r.json()
        text, sources = "", []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
                for c in block.get("citations") or []:
                    if c.get("url"):
                        sources.append({"name": c.get("title", ""), "url": c["url"]})
            elif block.get("type") == "web_search_tool_result":
                for res in block.get("content") or []:
                    if isinstance(res, dict) and res.get("url"):
                        sources.append({"name": res.get("title", ""), "url": res["url"]})
        return text, sources
    raise LLMError("Claude indisponível depois de 4 tentativas")


def ask(prompt: str, *, search: bool = False, want_json: bool = False, temperature: float = 0.7):
    """Retorna (texto, fontes). Com want_json=True, retorna (objeto, fontes)."""
    fn = _anthropic if provider() == "anthropic" else _gemini
    text, sources = fn(prompt, search, want_json, temperature)
    if want_json:
        return parse_json(text), sources
    return text, sources


def parse_json(text: str):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=0)
    text = text[start:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        end = max(text.rfind("}"), text.rfind("]"))
        return json.loads(text[: end + 1])
