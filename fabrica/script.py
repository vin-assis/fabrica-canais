"""Pauta, pesquisa, roteiro e revisão. Tudo em JSON para o resto do motor consumir."""
import json
from pathlib import Path

from . import llm

ROOT = Path(__file__).resolve().parent.parent
WPM = {"pt": 155, "en": 150}


def _lang(ch):
    return "pt" if ch["idioma"].lower().startswith("pt") else "en"


def _lang_name(ch):
    return "português do Brasil" if _lang(ch) == "pt" else "American English"


def pick_topic(ch_id, ch, history):
    """Primeiro usa a fila manual (config/topics/<canal>.txt); se acabar, pede ideias ao modelo."""
    used = {h["topic"].strip().lower() for h in history}
    fila = ROOT / "config" / "topics" / f"{ch_id}.txt"
    if fila.exists():
        for line in fila.read_text(encoding="utf-8").splitlines():
            t = line.strip()
            if t and not t.startswith("#") and t.lower() not in used:
                return t, "fila manual"
    recent = [h["topic"] for h in history[-60:]]
    prompt = f"""Você é o estrategista de conteúdo de um canal do YouTube.
Nicho: {ch['nicho']}
Público: {ch['publico']}
Idioma do canal: {_lang_name(ch)}

Já publicados (não repetir nem fazer variação próxima):
{json.dumps(recent, ensure_ascii=False)}

Liste 12 temas para o próximo vídeo longo (8 a 11 minutos). Critérios, nesta ordem:
1. Alguém pesquisaria isso no YouTube ou clicaria vendo o título (curiosidade real, não inventada).
2. Perene: continua interessante daqui a 2 anos.
3. Dá para contar com fatos verificáveis e fontes públicas.
4. Dá para ilustrar com imagens de banco de vídeo (pessoas, lugares, objetos, cidades), sem precisar de imagens de pessoas famosas específicas.
Evite temas de saúde com conselho médico, política partidária, tragédias recentes e pessoas vivas acusadas de crimes.

Responda só com JSON: {{"temas": [{{"tema": "...", "por_que": "..."}}]}} com o tema escrito no idioma do canal, do melhor para o pior."""
    data, _ = llm.ask(prompt, want_json=True, temperature=0.9)
    for item in data.get("temas", []):
        t = item.get("tema", "").strip()
        if t and t.lower() not in used:
            return t, item.get("por_que", "")
    raise RuntimeError("o modelo não sugeriu nenhum tema novo")


def research(topic, ch):
    prompt = f"""Pesquise na web e escreva um dossiê factual sobre: "{topic}".
Para cada fato, inclua número, data, lugar ou nome concreto quando existir, e diga de onde veio.
Separe em: contexto, linha do tempo, números, viradas da história, curiosidades pouco conhecidas,
mitos comuns (e o que é verdade), e o que ainda é incerto ou disputado.
Não invente nada: se não achar, escreva "não encontrado". Escreva em {_lang_name(ch)}."""
    try:
        notes, sources = llm.ask(prompt, search=True, temperature=0.2)
        return notes, sources, True
    except llm.LLMError as e:
        notes, sources = llm.ask(prompt.replace("Pesquise na web e escreva", "Escreva"), temperature=0.2)
        return notes + f"\n\n[AVISO: pesquisa na web falhou: {e}]", sources, False


def write_script(topic, ch, notes, sources):
    lang = _lang(ch)
    minutes = (ch["duracao_min"] + ch["duracao_max"]) / 2
    words = int(minutes * WPM[lang])
    n_shorts = int(ch.get("shorts_por_video", 3))
    prompt = f"""Você é roteirista de um canal de documentários curtos no YouTube.
Canal: {ch['nome']} | Nicho: {ch['nicho']}
Público: {ch['publico']}
Tom: {ch['tom']}
Idioma de TODO o texto falado e dos títulos: {_lang_name(ch)}.

Tema: {topic}

DOSSIÊ (use só fatos que estão aqui; o que não estiver aqui, não afirme):
{notes[:30000]}

Escreva o roteiro narrado com cerca de {words} palavras no total, dividido em 9 a 13 blocos.
Regras de roteiro:
- Abertura (bloco 1, até 45 palavras): comece pelo fato mais surpreendente, faça uma promessa clara do que a pessoa vai descobrir. Nada de "Olá, pessoal", nada de "neste vídeo".
- Cada bloco termina puxando o próximo (pergunta aberta, virada, "mas tem um detalhe").
- Números por extenso quando curtos ("dois bilhões"), datas claras. Frases curtas, fáceis de ouvir.
- Um ponto de vista próprio e uma lição prática para o público no final (isso é o que torna o vídeo original).
- Último bloco: conclusão + convite natural para comentar uma pergunta específica. Sem pedir like de forma genérica.
- Nunca afirme algo que o dossiê marcou como incerto sem dizer que é incerto.

Para cada bloco, dê de 2 a 4 buscas de imagens de banco de vídeo EM INGLÊS (2 a 4 palavras, coisas filmáveis: "coffee beans roasting", "busy street sao paulo", "old factory workers"). Nada de nomes de pessoas famosas ou logotipos.

Escreva também {n_shorts} roteiros de Shorts independentes (cada um com 165 a 200 palavras, para dar entre 61 e 80 segundos): gancho forte na primeira frase, um único fato ou história, final que manda para o vídeo completo.

Responda só com JSON neste formato:
{{
 "titulos": ["5 opções de título, até 65 caracteres, curiosidade sem mentira"],
 "titulo": "o melhor dos 5",
 "texto_thumbnail": "2 a 4 palavras em MAIÚSCULAS, diferente do título",
 "busca_thumbnail": "busca em inglês para a imagem de fundo da thumbnail",
 "descricao": "2 parágrafos para a descrição do YouTube, com palavras-chave naturais",
 "tags": ["15 a 20 tags"],
 "blocos": [{{"titulo_capitulo": "curto", "narracao": "texto falado", "buscas": ["..."]}}],
 "shorts": [{{"titulo": "até 60 caracteres", "narracao": "texto falado", "buscas": ["..."], "legenda": "texto para Instagram/TikTok com 3 a 5 hashtags"}}],
 "afirmacoes_para_checar": ["as 5 afirmações mais arriscadas do roteiro, para o revisor humano conferir"]
}}"""
    data, _ = llm.ask(prompt, want_json=True, temperature=0.75)
    data["fontes"] = _dedupe_sources(sources)
    return data


def review(script, notes, ch):
    texto = "\n\n".join(b["narracao"] for b in script["blocos"])
    prompt = f"""Você é checador de fatos. Compare o ROTEIRO com o DOSSIÊ.
Liste cada afirmação do roteiro que NÃO está apoiada no dossiê, ou que exagera o que o dossiê diz.
Para cada uma, proponha a correção mínima (no mesmo idioma do roteiro).
Também dê uma nota de 0 a 10 para: gancho dos primeiros 15 segundos, clareza, originalidade (tem opinião/lição própria?).

DOSSIÊ:
{notes[:25000]}

ROTEIRO:
{texto}

Responda só com JSON: {{"problemas": [{{"trecho": "...", "problema": "...", "correcao": "..."}}], "notas": {{"gancho": 0, "clareza": 0, "originalidade": 0}}, "veredito": "ok" ou "corrigir"}}"""
    data, _ = llm.ask(prompt, want_json=True, temperature=0.1)
    fixes = 0
    for p in data.get("problemas", []):
        trecho, corr = p.get("trecho", ""), p.get("correcao", "")
        if not trecho or not corr:
            continue
        for b in script["blocos"]:
            if trecho in b["narracao"]:
                b["narracao"] = b["narracao"].replace(trecho, corr)
                fixes += 1
                break
    data["correcoes_aplicadas"] = fixes
    return data


def _dedupe_sources(sources):
    seen, out = set(), []
    for s in sources:
        u = s.get("url", "")
        if u and u not in seen:
            seen.add(u)
            out.append(s)
    return out[:15]


def offline_script(topic, ch):
    """Roteiro falso só para testar a montagem sem internet."""
    lang = _lang(ch)
    frase = ("Esta é uma frase de teste para medir o tempo da narração e das legendas. " if lang == "pt"
             else "This is a test sentence used to measure narration timing and captions. ")
    blocos = [{"titulo_capitulo": f"Parte {i+1}", "narracao": frase * 4, "buscas": ["city timelapse", "coffee beans"]}
              for i in range(4)]
    return {
        "titulos": [topic] * 5, "titulo": topic, "texto_thumbnail": "TESTE DE FÁBRICA",
        "busca_thumbnail": "coffee cup", "descricao": "Descrição de teste.", "tags": ["teste"],
        "blocos": blocos,
        "shorts": [{"titulo": f"Short {i+1}", "narracao": frase * 3, "buscas": ["ocean waves"], "legenda": "teste #teste"}
                   for i in range(2)],
        "afirmacoes_para_checar": ["(modo offline)"], "fontes": [],
    }
