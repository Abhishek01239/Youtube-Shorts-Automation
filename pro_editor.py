#!/usr/bin/env python3
"""
pro_editor.py
Edits a raw clip into a finished vertical Short, like a pro editor would:

  - Framing: wide gameplay is zoomed in over a blurred, darkened copy of itself;
    vertical clips fill the screen.
  - Word-by-word captions: 2-3 bold words at a time, the spoken word pops in yellow.
  - Hook title for the first 3 seconds, optional permanent credit (e.g. twitch.tv/name).
  - Punch-in zoom + synthesized bass impact on the clip's most exciting second
    (audio spikes + on-screen motion + hype words).
  - Color grade + sharpening, loudness normalized to -14 LUFS, progress bar.

CLI:
    python pro_editor.py in.mp4 out.mp4 [--title "Hook text"] [--credit "twitch.tv/name"]
                                        [--layout blur|fill] [--no-captions]
"""
import argparse
import json
import math
import re
import statistics
import subprocess
import tempfile
from pathlib import Path

W, H = 1080, 1920
FONT_DIR = Path(__file__).parent / "assets" / "fonts"
FONT_NAME = "Roboto"
WHISPER_MODEL = "small"

HYPE = [
    (r"\b(oh my god|omg|oh my gosh)\b", 3), (r"\b(let'?s go+|lets go+|lfg)\b", 3),
    (r"\b(no way|no shot|are you serious|are you kidding)\b", 3), (r"\b(what the (hell|heck|fuck)|wtf)\b", 3),
    (r"\b(holy (shit|crap|moly)|bro what|yo+)\b", 2.5), (r"\b(clip (it|that)|clipped)\b", 4),
    (r"\b(insane|crazy|unbelievable|nuts|wild|clutch|massive|huge)\b", 2),
    (r"\b(run|go go|drive|get in|shoot|cops?|police|chase|explod\w*|crash\w*)\b", 1),
    (r"\b(ha(ha)+|lmao|lol)\b", 2), (r"\b(no+ ?no+|nooo+|wait wait|help)\b", 2), (r"!", 0.5),
]


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


# ---------- analysis ----------

def probe(path):
    data = json.loads(run(["ffprobe", "-v", "error", "-show_entries",
                           "stream=codec_type,width,height:format=duration", "-of", "json", str(path)]).stdout)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if not video:
        raise ValueError("clip has no video stream")
    return {"width": int(video["width"]), "height": int(video["height"]),
            "duration": float(data["format"].get("duration") or 0),
            "has_audio": any(s["codec_type"] == "audio" for s in data["streams"])}


def loudness_per_second(path):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
                          "aresample=8000,asetnsamples=n=8000,astats=metadata=1:reset=1,"
                          "ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file=-",
                          "-f", "null", "-"], capture_output=True, text=True).stdout
    return [-100.0 if v == "-inf" else max(-100.0, float(v))
            for v in re.findall(r"RMS_level=(-?[\d.]+|-inf)", out)]


def motion_per_second(path, seconds):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-an", "-vf",
                          "fps=4,scale=160:-2,format=gray,tblend=all_mode=difference,signalstats,"
                          "metadata=mode=print:key=lavfi.signalstats.YAVG:file=-",
                          "-f", "null", "-"], capture_output=True, text=True).stdout
    total, count, t = [0.0] * seconds, [0] * seconds, 0.0
    for line in out.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            t = float(m.group(1))
        m = re.search(r"YAVG=([\d.]+)", line)
        if m and int(t) < seconds:
            total[int(t)] += float(m.group(1))
            count[int(t)] += 1
    return [s / c if c else 0.0 for s, c in zip(total, count)]


def relative_spikes(values, radius=30):
    """How unusual each second is vs the surrounding minute, scaled so steady wobble stays near 0."""
    if not values:
        return []
    raw = [v - statistics.median(values[max(0, i - radius):i + radius + 1]) for i, v in enumerate(values)]
    ordered = sorted(values)
    value_range = ordered[-1] - ordered[int((len(ordered) - 1) * 0.05)]
    spread = max(statistics.median(abs(r) for r in raw), 0.08 * value_range) or 1
    return [min(max(0.0, r) / spread, 6) for r in raw]


def hype_score(text):
    return sum(len(re.findall(p, text, re.I)) * w for p, w in HYPE)


def excitement_curve(loudness, motion, words):
    n = max(len(loudness), len(motion))
    if not n:
        return []
    loud = (loudness + [loudness[-1] if loudness else -30.0] * n)[:n]
    audio = relative_spikes(loud)
    jumps = relative_spikes([0.0] + [max(0.0, loud[i] - loud[i - 1]) for i in range(1, n)], 15)
    mot = relative_spikes((motion + [0.0] * n)[:n])
    speech = [0.0] * n
    for w in words:
        for t in range(int(w["start"]), min(n - 1, int(w["end"])) + 1):
            speech[t] += hype_score(w["word"])
    score = [audio[i] + 0.6 * jumps[i] + 0.7 * mot[i] + 0.9 * min(speech[i] / 3, 6) for i in range(n)]
    return [sum(score[max(0, i - 2):i + 3]) / len(score[max(0, i - 2):i + 3]) for i in range(n)]


def peak_from_curve(curve):
    """Most exciting second, ignoring the very first and last second; None if nothing stands out."""
    if len(curve) < 4:
        return None
    i = max(range(1, len(curve) - 1), key=lambda k: curve[k])
    return i + 0.5 if curve[i] > 0.5 else None


def transcribe_words(path):
    from faster_whisper import WhisperModel
    model = WhisperModel(WHISPER_MODEL, device="auto", compute_type="auto")
    segments, _ = model.transcribe(str(path), word_timestamps=True, vad_filter=True)
    return [{"word": w.word.strip(), "start": w.start, "end": w.end}
            for seg in segments for w in (seg.words or []) if w.word.strip()]


# ---------- captions ----------

def chunk_words(words, max_words=3, max_chars=14):
    chunks, cur = [], []
    for w in words:
        if cur:
            chars = sum(len(x["word"]) + 1 for x in cur) + len(w["word"])
            if (len(cur) >= max_words or chars > max_chars or w["start"] - cur[-1]["end"] > 0.6
                    or re.search(r"[.!?,]$", cur[-1]["word"])):
                chunks.append(cur)
                cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def ass_time(t):
    cs = max(0, round(t * 100))
    return f"{cs // 360000}:{cs % 360000 // 6000:02d}:{cs % 6000 // 100:02d}.{cs % 100:02d}"


def ass_text(s):
    s = re.sub(r"\{[^}]*\}", "", s)
    s = re.sub(r"[\\{}]", "", s)
    s = re.sub(r"[^\w\s.,!?'\"&%$#@+=:;()/-]", "", s)  # drop emoji the font can't draw
    return re.sub(r"\s+", " ", s).strip()


YELLOW, WHITE = "&H0000E5FF&", "&H00FFFFFF&"


def build_ass(duration, words, hook=None, credit=None):
    lines = []
    for chunk in chunk_words(words):
        chunk_end = min(duration, chunk[-1]["end"] + 0.15)
        for i, w in enumerate(chunk):
            start = w["start"]
            end = chunk[i + 1]["start"] if i < len(chunk) - 1 else chunk_end
            if end <= start:
                continue
            text = " ".join(
                f"{{\\c{YELLOW}\\fscx112\\fscy112}}{ass_text(x['word']).upper()}{{\\c{WHITE}\\fscx100\\fscy100}}"
                if j == i else ass_text(x["word"]).upper() for j, x in enumerate(chunk))
            pop = "{\\fscx70\\fscy70\\t(0,90,\\fscx100\\fscy100)}" if i == 0 else ""
            lines.append(f"Dialogue: 1,{ass_time(start)},{ass_time(end)},Caption,,0,0,0,,{pop}{text}")
    if hook and ass_text(hook):
        lines.append(f"Dialogue: 2,{ass_time(0)},{ass_time(min(3, duration))},Hook,,0,0,0,,"
                     f"{{\\fad(120,250)\\fscx85\\fscy85\\t(0,120,\\fscx100\\fscy100)}}{ass_text(hook)}")
    if credit and ass_text(credit):
        lines.append(f"Dialogue: 0,{ass_time(0)},{ass_time(duration)},Credit,,0,0,0,,{ass_text(credit)}")
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{FONT_NAME},86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,1,0,1,7,3,2,60,60,450,1
Style: Hook,{FONT_NAME},64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,3,18,0,8,80,80,300,1
Style: Credit,{FONT_NAME},38,&H00FFFFFF,&H00FFFFFF,&H00000000,&H8C000000,-1,0,0,0,100,100,0,0,3,10,0,8,60,60,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(lines) + "\n"


# ---------- render ----------

def build_filter(info, peak, ass_name, layout=None):
    layout = layout or ("blur" if info["width"] / info["height"] > 1.2 else "fill")
    z = "1" if peak is None else f"(1+0.14*exp(-pow((t-{peak:.2f})/0.45,2)))"
    grade = "eq=contrast=1.07:saturation=1.2:brightness=0.01,unsharp=5:5:0.7"
    v = []
    if layout == "blur":
        fg_h = 860
        v += ["[0:v]split=2[bgsrc][fgsrc]",
              f"[bgsrc]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:3,eq=brightness=-0.12:saturation=1.1[bg]",
              f"[fgsrc]scale=w='trunc({fg_h}*{z}*iw/ih/2)*2':h='trunc({fg_h}*{z}/2)*2':eval=frame,crop='min(iw,{W})':{fg_h},{grade}[fg]",
              "[bg][fg]overlay=(W-w)/2:(H-h)/2-80,setsar=1[framed]"]
    else:
        v += [f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"scale=w='trunc({W}*{z}/2)*2':h=-2:eval=frame,crop={W}:{H},{grade},setsar=1[framed]"]
    dur = f"{max(0.1, info['duration']):.2f}"
    v += [f"color=c=0xFFE500:s={W}x14:r=30[bar]",
          f"[framed][bar]overlay=x='-w+w*t/{dur}':y=H-14:shortest=1:eval=frame[barred]",
          f"[barred]subtitles={ass_name}:fontsdir=fonts,format=yuv420p[vout]"]
    src = ("[0:a]aformat=sample_rates=48000:channel_layouts=stereo" if info["has_audio"]
           else f"anullsrc=r=48000:cl=stereo,atrim=duration={dur}")
    if peak is not None:
        delay = max(0, round((peak - 0.05) * 1000))
        a = [f"aevalsrc='0.9*sin(2*PI*(38+70*exp(-9*t))*t)*exp(-5*t)':s=48000:d=0.7,"
             f"aformat=channel_layouts=stereo,adelay={delay}|{delay}[hit]",
             f"{src}[main]",
             "[main][hit]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]"]
    else:
        a = [f"{src},loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]"]
    return ";".join(v + a), layout


def pro_edit(src, dst, title=None, credit=None, layout=None, captions=True, words=None):
    src, dst = Path(src).resolve(), Path(dst).resolve()
    info = probe(src)
    if words is None:
        words = []
        if captions and info["has_audio"]:
            try:
                words = transcribe_words(src)
            except Exception as e:
                print(f"[pro_editor] captions skipped: {e}")
    loud = loudness_per_second(src) if info["has_audio"] else []
    motion = motion_per_second(src, max(len(loud), math.ceil(info["duration"])))
    peak = peak_from_curve(excitement_curve(loud, motion, words))
    hook = re.sub(r"#\S+", "", title or "").strip()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "captions.ass").write_text(
            build_ass(info["duration"], words, hook if 0 < len(hook) <= 70 else None, credit), encoding="utf-8")
        fonts = tmp / "fonts"
        fonts.mkdir()
        for f in FONT_DIR.glob("*.ttf"):
            (fonts / f.name).write_bytes(f.read_bytes())
        graph, used_layout = build_filter(info, peak, "captions.ass", layout)
        subprocess.run(["ffmpeg", "-y", "-i", str(src), "-filter_complex", graph, "-map", "[vout]", "-map", "[aout]",
                        "-t", f"{info['duration']:.3f}", "-r", "30", "-c:v", "libx264", "-preset", "medium",
                        "-crf", "20", "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                        "-movflags", "+faststart", str(dst)], check=True, capture_output=True, text=True, cwd=tmp)
    print(f"[pro_editor] {dst.name}: {used_layout} layout, {len(words)} caption words, "
          f"punch-in {'at %.1fs' % peak if peak is not None else 'skipped'}")
    return dst


def main():
    ap = argparse.ArgumentParser(description="Pro-edit a clip into a vertical Short")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--title", help="hook text shown for the first 3 seconds")
    ap.add_argument("--credit", help="permanent credit, e.g. twitch.tv/streamer")
    ap.add_argument("--layout", choices=["blur", "fill"])
    ap.add_argument("--no-captions", action="store_true")
    a = ap.parse_args()
    pro_edit(a.input, a.output, a.title, a.credit, a.layout, captions=not a.no_captions)


if __name__ == "__main__":
    main()
