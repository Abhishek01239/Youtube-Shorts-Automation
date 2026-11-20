"""
Final "mastering" pass for Shorts, run after captions and before upload.

What it does:
  Video
    - Guarantees exact 1080x1920 output (lanczos scaling, square pixels)
    - Deband (removes blocky colour gradients from compressed Twitch/YouTube sources)
    - Contrast-adaptive sharpening (CAS) - crisper edges without the halo look
      of a second unsharp pass
    - Keeps 60fps if the source is >= 50fps, otherwise locks to a clean 30fps
    - Optional headline (the video title) in the empty band above the gameplay
    - Tags BT.709 colour so YouTube doesn't wash out the colours
  Audio
    - High-pass at 70 Hz to drop mic rumble / desk thumps
    - Two-pass EBU R128 loudness normalisation to -14 LUFS (YouTube's playback
      target), true-peak -1.5 dB, so every Short is equally loud and never clips
    - AAC 192 kbps / 48 kHz
  Encode
    - libx264 High profile, CRF 17, high-quality settings. A higher-quality
      upload gives YouTube's own re-encode more detail to work with.

Safety: this step NEVER blocks an upload. Any failure returns the input path
unchanged and the pipeline continues with the un-enhanced video.
"""
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile

import config

TARGET_W, TARGET_H = 1080, 1920
TARGET_LUFS = -14.0
TARGET_TP = -1.5
TARGET_LRA = 11.0

_filter_cache = None


def _ffmpeg():
    return config.get_ffmpeg_path() or "ffmpeg"


def _ffprobe():
    probe = shutil.which("ffprobe")
    if probe:
        return probe
    sibling = os.path.join(os.path.dirname(_ffmpeg()), "ffprobe")
    return sibling if os.path.exists(sibling) else "ffprobe"


def _available_filters():
    """Names of the video/audio filters this ffmpeg build supports (cached)."""
    global _filter_cache
    if _filter_cache is None:
        try:
            out = subprocess.run(
                [_ffmpeg(), "-hide_banner", "-filters"],
                capture_output=True, text=True, timeout=30,
            ).stdout
            _filter_cache = {
                parts[1] for parts in (l.split() for l in out.splitlines())
                if len(parts) >= 2
            }
        except Exception:
            _filter_cache = set()
    return _filter_cache


FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts", "roboto.ttf")


def clean_headline(title, max_chars=60):
    """Strip hashtags/emojis (the font can't draw emojis) and tidy a title for on-screen use."""
    if not title:
        return ""
    text = re.sub(r"#\w+", "", title)
    text = "".join(ch for ch in text if ord(ch) < 0x2000 or 0x2010 <= ord(ch) <= 0x203A)
    text = re.sub(r"\s+", " ", text).strip(" -|:,")
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0].rstrip(" -|:,") + "..."
    return text.upper()


def _wrap(text, width=18, max_lines=3):
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".") + "..."
    return lines


def _headline_filters(headline, framing, tmpdir):
    """drawtext filters for a centred, boxed headline in the top band of the frame."""
    if not headline or not os.path.exists(FONT_PATH) or "drawtext" not in _available_filters():
        return []
    lines = _wrap(headline)
    if not lines:
        return []
    size, gap = 78, 22
    block_h = len(lines) * size + (len(lines) - 1) * gap
    # In blur framing a 16:9 clip leaves an empty band above the gameplay
    # (about 656px tall); centre the headline in it. In crop mode, sit near the top.
    top = (656 - block_h) // 2 if framing == "blur" else 170
    top = max(top, 120)  # stay clear of YouTube's top-of-screen UI
    font = FONT_PATH.replace("\\", "/").replace(":", "\\:")
    filters = []
    for i, line in enumerate(lines):
        tf = os.path.join(tmpdir, f"headline_{i}.txt")
        with open(tf, "w", encoding="utf-8") as fh:
            fh.write(line)
        tf_esc = tf.replace("\\", "/").replace(":", "\\:")
        filters.append(
            f"drawtext=fontfile='{font}':textfile='{tf_esc}':fontsize={size}:fontcolor=white"
            f":borderw=5:bordercolor=black:box=1:boxcolor=black@0.45:boxborderw=18"
            f":x=(w-text_w)/2:y={top + i * (size + gap)}"
        )
    return filters


def _probe(path):
    """Returns (fps, has_audio)."""
    out = subprocess.run(
        [_ffprobe(), "-v", "error", "-show_streams", "-of", "json", path],
        capture_output=True, text=True, timeout=60, check=True,
    ).stdout
    streams = json.loads(out).get("streams", [])
    fps = 30.0
    has_audio = False
    for s in streams:
        if s.get("codec_type") == "video":
            rate = s.get("avg_frame_rate") or s.get("r_frame_rate") or "30/1"
            try:
                num, den = rate.split("/")
                fps = float(num) / float(den) if float(den) else 30.0
            except (ValueError, ZeroDivisionError):
                fps = 30.0
        elif s.get("codec_type") == "audio":
            has_audio = True
    return fps, has_audio


def _video_filter(fps, extra=()):
    f = _available_filters()
    chain = [
        f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase:flags=lanczos",
        f"crop={TARGET_W}:{TARGET_H}",
        "setsar=1",
    ]
    if "deband" in f:
        chain.append("deband=1thr=0.015:2thr=0.015:3thr=0.015:range=16:blur=1")
    elif "gradfun" in f:
        chain.append("gradfun=strength=1.2:radius=16")
    if "cas" in f:
        chain.append("cas=strength=0.45")
    else:
        chain.append("unsharp=3:3:0.4:3:3:0.0")
    chain.extend(extra)
    chain.append(f"fps={60 if fps >= 50 else 30}")
    chain.append("format=yuv420p")
    return ",".join(chain)


def _measure_loudness(path):
    """First loudnorm pass: returns the measured stats dict, or None."""
    cmd = [
        _ffmpeg(), "-hide_banner", "-nostats", "-i", path, "-vn",
        "-af", f"highpass=f=70,loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json",
        "-f", "null", "-",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", res.stderr, re.S)
    if not match:
        return None
    stats = json.loads(match.group(0))
    # Silent clips report -inf; linear normalisation would blow up the noise floor.
    if not stats.get("input_i") or "inf" in str(stats.get("input_i")):
        return None
    return stats


def _audio_filter(stats):
    base = f"highpass=f=70,loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA={TARGET_LRA}"
    if stats:
        base += (
            f":measured_I={stats['input_i']}"
            f":measured_TP={stats['input_tp']}"
            f":measured_LRA={stats['input_lra']}"
            f":measured_thresh={stats['input_thresh']}"
            f":offset={stats['target_offset']}"
            ":linear=true"
        )
    # loudnorm internally upsamples to 192 kHz; bring it back to 48 kHz.
    return base + ",aresample=48000"


def enhance_video(input_path, output_path=None, headline=None, framing="blur"):
    """
    Masters a finished Short for upload. Returns the path of the enhanced file,
    or `input_path` unchanged if anything goes wrong.

    headline: optional title text burned into the top of the frame.
    framing:  "blur" or "crop" (matches video_processor) - decides headline position.
    """
    if not input_path or not os.path.exists(input_path):
        return input_path

    if output_path is None:
        root, _ = os.path.splitext(input_path)
        output_path = f"{root}_hq.mp4"

    tmpdir = tempfile.mkdtemp(prefix="quality_")
    try:
        fps, has_audio = _probe(input_path)
        out_fps = 60 if fps >= 50 else 30
        text_filters = _headline_filters(clean_headline(headline), framing, tmpdir)

        cmd = [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-i", input_path,
               "-vf", _video_filter(fps, text_filters)]

        if has_audio:
            stats = _measure_loudness(input_path)
            cmd += ["-af", _audio_filter(stats),
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
            logging.info(
                f"[quality] loudness in: {stats['input_i']} LUFS -> {TARGET_LUFS} LUFS"
                if stats else "[quality] loudness: single-pass (no measurable speech/music)"
            )
        else:
            cmd += ["-an"]

        cmd += [
            "-c:v", "libx264", "-preset", "slow", "-crf", "17",
            "-profile:v", "high", "-level:v", "4.2",
            "-tune", "film",
            # GOP of 2s and B-frames: what YouTube recommends for uploads
            "-g", str(out_fps * 2), "-bf", "2",
            "-maxrate", "16M", "-bufsize", "32M",
            "-colorspace", "bt709", "-color_primaries", "bt709",
            "-color_trc", "bt709", "-color_range", "tv",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            output_path,
        ]

        subprocess.run(cmd, capture_output=True, text=True, timeout=1200, check=True)

        if not os.path.exists(output_path) or os.path.getsize(output_path) < 10_000:
            raise RuntimeError("enhanced file missing or empty")

        logging.info(f"[quality] Enhanced -> {output_path} ({out_fps}fps, {TARGET_W}x{TARGET_H})")
        return output_path

    except subprocess.CalledProcessError as e:
        logging.warning(f"[quality] ffmpeg failed, uploading un-enhanced video: {(e.stderr or '')[-800:]}")
    except Exception as e:
        logging.warning(f"[quality] Enhancement skipped, uploading un-enhanced video: {e}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return input_path


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Master a Short for upload (quality pass)")
    ap.add_argument("input")
    ap.add_argument("output", nargs="?")
    ap.add_argument("--headline", default=None)
    ap.add_argument("--framing", default="blur")
    a = ap.parse_args()
    print(enhance_video(a.input, a.output, a.headline, a.framing))
