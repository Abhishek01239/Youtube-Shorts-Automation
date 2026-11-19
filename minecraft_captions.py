#!/usr/bin/env python3
"""
minecraft_captions.py
Auto-captions a video from its speech using faster-whisper and burns
Minecraft-style pixel text into the video.

Pipeline slot:
    Twitch clip -> crop/process to 9:16 -> auto captions -> upload to Shorts

CLI:
    python minecraft_captions.py in.mp4 out.mp4
"""
import argparse
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FONT_NAME = "Monocraft"
FONT_DIR = Path(__file__).parent / "fonts"
WHISPER_MODEL = "small"
WORDS_PER_CAPTION = 3
MAX_CHARS = 16
PAUSE_BREAK = 0.6
BOTTOM_MARGIN = 0.30

PALETTE = ["FFFF55", "55FFFF", "55FF55", "FF55FF", "FF5555", "FFAA00", "FFFFFF"]


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def probe_size(video):
    out = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", str(video),
    ]).stdout
    s = json.loads(out)["streams"][0]
    return int(s["width"]), int(s["height"])


def transcribe(video, language=None):
    from faster_whisper import WhisperModel

    model = WhisperModel(WHISPER_MODEL, device="auto", compute_type="auto")
    segments, _ = model.transcribe(
        str(video), word_timestamps=True, vad_filter=True, language=language
    )
    words = []
    for seg in segments:
        for w in seg.words or []:
            t = w.word.strip()
            if t:
                words.append((w.start, w.end, t))
    return words


def chunk_words(words):
    chunks, cur = [], []
    for w in words:
        if cur:
            gap = w[0] - cur[-1][1]
            text_len = len(" ".join(x[2] for x in cur + [w]))
            if len(cur) >= WORDS_PER_CAPTION or gap > PAUSE_BREAK or text_len > MAX_CHARS:
                chunks.append(cur)
                cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def color_stream():
    last = None
    while True:
        choices = [c for c in PALETTE if c != last]
        c = random.choice(choices)
        last = c
        yield c


def to_bgr(hex_rgb):
    r, g, b = hex_rgb[0:2], hex_rgb[2:4], hex_rgb[4:6]
    return f"&H{b}{g}{r}&"


def shadow_of(hex_rgb):
    r, g, b = (int(hex_rgb[i:i + 2], 16) // 4 for i in (0, 2, 4))
    return f"{r:02X}{g:02X}{b:02X}"


def ass_time(t):
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def clean(text):
    text = re.sub(r"[{}\\]", "", text)
    return text.strip(",.;:").upper()


def build_ass(chunks, width, height):
    ref = min(width, height * 9 / 16)
    size = int(ref * 0.075)
    outline = max(2, int(size * 0.06))
    shadow = max(3, int(size * 0.09))
    margin_v = int(height * BOTTOM_MARGIN)

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Default,{FONT_NAME},{size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        f"0,0,0,0,100,100,0,0,1,{outline},{shadow},2,40,40,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]

    colors = color_stream()
    for i, ch in enumerate(chunks):
        start, end = ch[0][0], ch[-1][1]
        if i + 1 < len(chunks):
            nxt = chunks[i + 1][0][0]
            if nxt - end < 0.35:
                end = nxt
            end = min(end, nxt)
        end = max(end, start + 0.3)

        col = next(colors)
        text = " ".join(clean(w[2]) for w in ch)
        tags = (
            f"{{\\c{to_bgr(col)}\\3c&H000000&\\4c{to_bgr(shadow_of(col))}"
            f"\\fscx125\\fscy125\\t(0,120,\\fscx100\\fscy100)}}"
        )
        lines.append(
            f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{tags}{text}"
        )
    return "\n".join(lines) + "\n"


def add_captions(input_path, output_path=None, language=None):
    input_path = Path(input_path).resolve()
    output_path = (
        Path(output_path).resolve()
        if output_path
        else input_path.with_name(input_path.stem + "_captioned.mp4")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    words = transcribe(input_path, language)
    if not words:
        print("[captions] no speech detected, passing video through unchanged")
        shutil.copy(input_path, output_path)
        return str(output_path)

    width, height = probe_size(input_path)
    ass = build_ass(chunk_words(words), width, height)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "captions.ass").write_text(ass, encoding="utf-8")

        fonts = tmp / "fonts"
        fonts.mkdir()
        found = [f for f in FONT_DIR.glob("*") if f.suffix.lower() in (".ttf", ".otf")]
        if not found:
            print(f"[captions] WARNING: no font in {FONT_DIR}, falling back to a system font")
        for f in found:
            shutil.copy(f, fonts / f.name)

        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-vf", "subtitles=captions.ass:fontsdir=fonts",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "copy", str(output_path),
        ]
        try:
            run(cmd, cwd=tmp)
        except subprocess.CalledProcessError as e:
            sys.stderr.write(e.stderr[-2000:])
            raise

    print(f"[captions] done -> {output_path}")
    return str(output_path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Minecraft-style auto captions")
    ap.add_argument("input")
    ap.add_argument("output", nargs="?")
    ap.add_argument("--lang", default=None)
    a = ap.parse_args()
    print(add_captions(a.input, a.output, a.lang))
