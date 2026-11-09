"""Roda a fábrica para um canal: pauta -> pesquisa -> roteiro -> revisão -> voz -> cenas -> montagem -> checagem.

Uso:
  python -m fabrica.main --canal pt
  python -m fabrica.main --canal en --tema "The origin of the fork"
  python -m fabrica.main --canal pt --offline      # teste sem internet (sem IA, sem voz real, cenas coloridas)
"""
import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import yaml

from . import render, script, stock, thumb, tts

ROOT = Path(__file__).resolve().parent.parent
LONG = (1920, 1080)
VERT = (1080, 1920)


def log(msg):
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def load_history(ch_id):
    p = ROOT / "state" / f"history_{ch_id}.json"
    return json.loads(p.read_text()) if p.exists() else []


def save_history(ch_id, hist):
    p = ROOT / "state" / f"history_{ch_id}.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(hist, ensure_ascii=False, indent=1))


def chapters(blocks, starts):
    if len(blocks) < 3:
        return ""
    out = []
    for b, s in zip(blocks, starts):
        s = int(s) if out else 0
        if out and s - out[-1][0] < 12:
            continue
        out.append((s, b.get("titulo_capitulo", "").strip() or "..."))
    return "\n".join(f"{s // 60}:{s % 60:02d} {t}" for s, t in out) if len(out) >= 3 else ""


def make_video(blocks, ch, work, size, name, offline, vertical=False, hook=None, seed=0):
    """Narra blocos, busca cenas, monta. Retorna (caminho, duração, inícios dos blocos, créditos)."""
    work.mkdir(parents=True, exist_ok=True)
    st = stock.Stock(ROOT / ".cache" / "stock", "portrait" if vertical else "landscape", offline)
    audio_parts, all_words = [], []
    seg_words = []
    for i, b in enumerate(blocks):
        mp3 = work / f"{name}_n{i:02d}.mp3"
        _, words = tts.synth(b["narracao"], ch["voz"], ch.get("velocidade_voz", "+0%"), mp3, offline)
        audio_parts.append(mp3)
        seg_words.append(words)
    narration = work / f"{name}_narracao.wav"
    starts, total = render.join_audio(audio_parts, narration)
    for s, words in zip(starts, seg_words):
        all_words += [[w0 + s, w1 + s, t] for w0, w1, t in words]
    seg_dur = [(starts[i + 1] if i + 1 < len(starts) else total) - starts[i] for i in range(len(starts))]
    seg_clips = []
    for b in blocks:
        clips = []
        for q in (b.get("buscas") or ["abstract background"])[:4]:
            clips += st.clips(q, n=2)
        seg_clips.append(clips)
    track = render.build_track(seg_dur, seg_clips, size, work / f"{name}_trilha.mp4", seed=seed)
    subs = render.write_ass(all_words, work / f"{name}.ass", size, vertical=vertical, hook=hook)
    out = work / f"{name}.mp4"
    render.final_mix(track, narration, subs, out, music_dir=ROOT / "assets" / "music", total=total)
    return out, total, starts, st.credits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--canal", required=True)
    ap.add_argument("--tema")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--sem-shorts", action="store_true")
    ap.add_argument("--saida", default=str(ROOT / "dist"))
    a = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config" / "channels.yaml").read_text(encoding="utf-8"))["canais"]
    if a.canal not in cfg:
        sys.exit(f"canal '{a.canal}' não existe em config/channels.yaml")
    ch = cfg[a.canal]
    out_dir = Path(a.saida) / a.canal
    if out_dir.exists():
        shutil.rmtree(out_dir)
    work = out_dir / "_work"
    work.mkdir(parents=True)
    hist = load_history(a.canal)
    report = {"canal": a.canal, "nome": ch["nome"], "gerado_em": dt.datetime.now(dt.timezone.utc).isoformat(),
              "offline": a.offline, "checagens": []}

    # 1. pauta, pesquisa, roteiro, revisão
    if a.offline:
        topic, why = a.tema or "Teste offline da fábrica", "teste"
        sc, rev, pesquisou = script.offline_script(topic, ch), {"problemas": [], "notas": {}}, False
    else:
        topic, why = (a.tema, "tema escolhido por você") if a.tema else script.pick_topic(a.canal, ch, hist)
        log(f"tema: {topic}")
        notes, sources, pesquisou = script.research(topic, ch)
        (work / "dossie.md").write_text(notes, encoding="utf-8")
        log(f"pesquisa: {len(notes)} caracteres, {len(sources)} fontes")
        sc = script.write_script(topic, ch, notes, sources)
        log(f"roteiro: {sum(len(b['narracao'].split()) for b in sc['blocos'])} palavras, {len(sc['blocos'])} blocos")
        rev = script.review(sc, notes, ch)
        log(f"revisão: {len(rev.get('problemas', []))} problemas, {rev.get('correcoes_aplicadas', 0)} corrigidos")
    report.update(tema=topic, motivo_tema=why, pesquisa_web=pesquisou, revisao=rev)
    (out_dir / "roteiro.json").write_text(json.dumps(sc, ensure_ascii=False, indent=1), encoding="utf-8")

    # 2. vídeo longo
    log("montando vídeo longo...")
    video, total, starts, credits = make_video(sc["blocos"], ch, work, LONG, "video", a.offline, seed=len(hist))
    shutil.move(str(video), out_dir / "video.mp4")
    lufs, peak = render.loudness(out_dir / "video.mp4")
    log(f"vídeo longo: {total/60:.1f} min, {lufs} LUFS")

    # 3. thumbnails
    thumbs = []
    for i, t in enumerate([0.18, 0.42, 0.66]):
        frame = render.grab_frame(work / "video_trilha.mp4", total * t, work / f"frame_{i}.jpg")
        thumbs.append(thumb.make(frame, sc.get("texto_thumbnail") or sc["titulo"], out_dir / f"thumb_{i+1}.jpg", i))

    # 4. shorts
    shorts_meta = []
    if not a.sem_shorts:
        for i, s in enumerate(sc.get("shorts", [])[: int(ch.get("shorts_por_video", 3))]):
            log(f"short {i+1}...")
            v, d, _, cr = make_video([s], ch, work, VERT, f"short_{i+1}", a.offline, vertical=True,
                                     hook=s.get("titulo"), seed=i + 7)
            shutil.move(str(v), out_dir / f"short_{i+1}.mp4")
            credits.update(cr)
            shorts_meta.append({"arquivo": f"short_{i+1}.mp4", "titulo": s["titulo"], "duracao_s": round(d, 1),
                                "legenda": s.get("legenda", "")})

    # 5. descrição final
    pt = ch["idioma"].startswith("pt")
    cap = chapters(sc["blocos"], starts)
    fontes = "\n".join(f"- {f.get('name') or f['url']}: {f['url']}" for f in sc.get("fontes", []))
    cred = ", ".join(sorted(credits)) if credits else ""
    desc = sc.get("descricao", "").strip()
    if cap:
        desc += ("\n\nCapítulos:\n" if pt else "\n\nChapters:\n") + cap
    if fontes:
        desc += ("\n\nFontes:\n" if pt else "\n\nSources:\n") + fontes
    if cred:
        desc += ("\n\nImagens: Pixabay e Pexels (" if pt else "\n\nFootage: Pixabay and Pexels (") + cred + ")"
    desc += ("\n\nNarração com voz sintética. Roteiro pesquisado e revisado pela equipe do canal."
             if pt else "\n\nNarrated with a synthetic voice. Script researched and reviewed by the channel team.")
    desc += "\n\n" + " ".join(ch.get("hashtags", []))

    # 6. checagem automática
    words = sum(len(b["narracao"].split()) for b in sc["blocos"])
    chk = report["checagens"]

    def check(nome, ok, detalhe):
        chk.append({"item": nome, "ok": bool(ok), "detalhe": detalhe})

    check("Duração", ch["duracao_min"] * 60 * 0.85 <= total <= ch["duracao_max"] * 60 * 1.15 or a.offline,
          f"{total/60:.1f} min (alvo {ch['duracao_min']}-{ch['duracao_max']})")
    check("Volume", lufs is not None and -16 <= lufs <= -12, f"{lufs} LUFS, pico {peak} dBTP")
    check("Narração", words > 0, f"{words} palavras")
    check("Pesquisa na web", pesquisou or a.offline, f"{len(sc.get('fontes', []))} fontes")
    check("Título", 0 < len(sc["titulo"]) <= 70, f"{len(sc['titulo'])} caracteres")
    check("Tags", len(",".join(sc.get("tags", []))) <= 480, f"{len(sc.get('tags', []))} tags")
    check("Capítulos", bool(cap), "ok" if cap else "sem capítulos")
    check("Shorts", a.sem_shorts or all(61 <= s["duracao_s"] <= 180 for s in shorts_meta) or a.offline,
          ", ".join(f"{s['duracao_s']}s" for s in shorts_meta) or "nenhum")
    probs = len(rev.get("problemas", [])) - rev.get("correcoes_aplicadas", 0)
    check("Fatos sem apoio", probs <= 0, f"{max(probs, 0)} trecho(s) para conferir")

    meta = {
        "canal": a.canal, "nome_canal": ch["nome"], "tema": topic,
        "titulo": sc["titulo"], "titulos_alternativos": sc.get("titulos", []),
        "descricao": desc, "tags": sc.get("tags", [])[:20], "categoria_youtube": ch.get("categoria_youtube", "EDUCATION"),
        "video": "video.mp4", "duracao_s": round(total, 1), "thumbnails": [p.name for p in thumbs],
        "shorts": shorts_meta, "afirmacoes_para_checar": sc.get("afirmacoes_para_checar", []),
        "checagem_ok": all(c["ok"] for c in chk), "aprovado": False,
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    write_report(out_dir / "relatorio.md", report, meta, sc)
    shutil.rmtree(work, ignore_errors=True)

    if not a.offline:
        hist.append({"topic": topic, "titulo": sc["titulo"], "data": dt.date.today().isoformat()})
        save_history(a.canal, hist)
    log(f"pronto: {out_dir}")
    print(json.dumps({c["item"]: c["ok"] for c in chk}, ensure_ascii=False))


def write_report(path, report, meta, sc):
    L = [f"# {meta['titulo']}", "", f"Canal: {meta['nome_canal']}  |  Tema: {meta['tema']}  |  "
         f"Duração: {meta['duracao_s']/60:.1f} min", "", "## Checagem automática", ""]
    for c in report["checagens"]:
        L.append(f"- {'OK' if c['ok'] else 'ATENÇÃO'} · {c['item']}: {c['detalhe']}")
    L += ["", "## Confira antes de aprovar", ""]
    L += [f"- {x}" for x in meta["afirmacoes_para_checar"]] or ["- nada marcado"]
    probs = report.get("revisao", {}).get("problemas", [])
    if probs:
        L += ["", "## Trechos apontados pelo checador", ""]
        L += [f"- \"{p.get('trecho','')[:140]}\" → {p.get('problema','')}" for p in probs]
    notas = report.get("revisao", {}).get("notas", {})
    if notas:
        L += ["", "## Notas do revisor (0 a 10)", "", " · ".join(f"{k}: {v}" for k, v in notas.items())]
    L += ["", "## Títulos alternativos", ""] + [f"- {t}" for t in meta["titulos_alternativos"]]
    L += ["", "## Shorts", ""] + [f"- {s['titulo']} ({s['duracao_s']}s)" for s in meta["shorts"]]
    L += ["", "## Roteiro", ""]
    for b in sc["blocos"]:
        L += [f"### {b.get('titulo_capitulo','')}", "", b["narracao"], ""]
    Path(path).write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
