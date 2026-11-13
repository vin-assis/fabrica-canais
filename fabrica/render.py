"""Montagem com ffmpeg: cenas cortadas no tempo da narração, legendas queimadas, música opcional, volume -14 LUFS."""
import json
import random
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"
GAP = 0.35  # respiro entre blocos, em segundos


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou: {' '.join(map(str, cmd[:6]))}...\n{p.stderr[-1500:]}")
    return p


def duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)]).stdout
    return float(json.loads(out)["format"]["duration"])


def join_audio(parts, out):
    """parts: lista de mp3. Junta com respiro GAP entre eles. Retorna lista de inícios de cada parte."""
    out = Path(out)
    work = out.parent
    sil = work / "gap.wav"
    run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(GAP), str(sil)])
    lst = work / "audio_list.txt"
    starts, t, lines = [], 0.0, []
    for i, p in enumerate(parts):
        wav = work / f"a_{i:02d}.wav"
        run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-ar", "24000", "-ac", "1", str(wav)])
        starts.append(t)
        t += duration(wav)
        lines.append(f"file '{wav.name}'")
        if i < len(parts) - 1:
            lines.append(f"file '{sil.name}'")
            t += GAP
    lst.write_text("\n".join(lines))
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:a", "pcm_s16le", str(out)])
    return starts, duration(out)


def build_track(seg_durations, seg_clips, size, out, seed=0):
    """Cria a trilha de vídeo (sem som) com a duração exata de cada bloco."""
    w, h = size
    out = Path(out)
    work = out.parent / (out.stem + "_pieces")
    work.mkdir(exist_ok=True)
    rnd = random.Random(seed)
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=30,setsar=1,"
          f"eq=saturation=1.05:contrast=1.03,format=yuv420p")
    pieces, k = [], 0
    for si, (need, clips) in enumerate(zip(seg_durations, seg_clips)):
        filled, ci, last = 0.0, 0, None
        while need - filled > 0.05:
            clip = clips[ci % len(clips)]
            ci += 1
            if clip == last and len(clips) > 1:  # nunca a mesma cena duas vezes seguidas
                clip = clips[ci % len(clips)]
                ci += 1
            last = clip
            cd = duration(clip)
            piece = min(rnd.uniform(3.2, 5.5), need - filled, cd)
            if need - filled - piece < 1.0:  # evita sobrar pedacinho
                piece = min(need - filled, cd)
            start = rnd.uniform(0, max(0.0, cd - piece - 0.1))
            p = work / f"p_{k:04d}.mp4"
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}", "-i", str(clip), "-t", f"{piece:.3f}",
                 "-an", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(p)])
            pieces.append(p)
            filled += piece
            k += 1
    lst = work / "list.txt"
    lst.write_text("\n".join(f"file '{p.name}'" for p in pieces))
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
    return out


def _ts(t):
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(s):
    return s.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def write_ass(words, out, size, vertical=False, hook=None):
    """Legendas em blocos de até 4 palavras, grandes e com contorno (estilo dos canais que retêm)."""
    w, h = size
    fs = 130 if vertical else 100
    margin_v = int(h * 0.30) if vertical else 70
    hook_fs = 96 if vertical else 80
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Poppins,{fs},&H00FFFFFF,&H0000E5FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{9 if vertical else 7},3,2,60,60,{margin_v},1
Style: Hook,Poppins,{hook_fs},&H0000E5FF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,3,14,0,8,70,70,{int(h*0.12)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    if hook:
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(3.2)},Hook,,0,0,0,,{_esc(hook.upper())}")
    chunk = []
    for i, (s, e, t) in enumerate(words):
        chunk.append((s, e, t))
        nxt = words[i + 1][0] if i + 1 < len(words) else None
        end_sentence = t.rstrip().endswith((".", "!", "?", ":", ";", ","))
        if len(chunk) >= 4 or end_sentence or nxt is None or (nxt - e) > 0.6:
            start, end = chunk[0][0], chunk[-1][1]
            if nxt is not None:
                end = min(max(end, start + 0.4), nxt)
            text = " ".join(c[2] for c in chunk)
            if vertical:
                text = text.upper()
            lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{_esc(text)}")
            chunk = []
    Path(out).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return out


def final_mix(video, narration, subs, out, music_dir=None, total=None):
    """Junta vídeo + narração + legenda + música de fundo e normaliza o volume. Se o loudnorm falhar, usa ganho simples."""
    try:
        # volume em duas passadas e linear: sem o "bombeamento" que o loudnorm de uma passada causa na voz
        p = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(narration), "-af",
                            "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True)
        m = json.loads(p.stderr[p.stderr.rindex("{"):p.stderr.rindex("}") + 1])
        norm = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
                f"linear=true")
        return _final_mix(video, narration, subs, out, music_dir, total, norm=norm)
    except RuntimeError as e:
        print(f"  loudnorm falhou, usando ganho simples ({str(e)[-120:]})", flush=True)
        return _final_mix(video, narration, subs, out, music_dir, total, norm="volume=2.0,alimiter=limit=0.89")


def _final_mix(video, narration, subs, out, music_dir, total, norm):
    music = sorted(Path(music_dir).glob("*.mp3")) if music_dir and Path(music_dir).exists() else []
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(narration)]
    subs_f = str(subs).replace(":", "\\:")
    vf = f"[0:v]ass={subs_f}:fontsdir={FONTS}[v]"
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(random.choice(music))]
        af = ("[2:a]aresample=48000,volume=0.10,afade=t=in:d=2[m];[1:a]aresample=48000[n];"
              f"[n][m]amix=inputs=2:duration=first:dropout_transition=0,{norm}[a]")
    else:
        af = f"[1:a]aresample=48000,aformat=sample_fmts=fltp,{norm}[a]"
    cmd += ["-filter_complex", f"{vf};{af}", "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart"]
    if total:
        cmd += ["-t", f"{total:.3f}"]
    cmd.append(str(out))
    run(cmd)
    return out


def loudness(path):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    lufs, peak = None, None
    for line in p.stderr.splitlines()[-30:]:
        line = line.strip()
        if line.startswith("I:"):
            lufs = float(line.split()[1])
        elif line.startswith("Peak:"):
            peak = float(line.split()[1])
    return lufs, peak


def grab_frame(video, t, out):
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out)])
    return out
