"""
Moment finder: picks the best 15-45 s segment of a stream clip for a Short.

Twitch clips are usually ~60 s and the moment people clipped is often at the very
end, so a fixed "middle 35 s" cut regularly loses it. This module instead:

  1. Builds an EXCITEMENT CURVE on a 0.5 s grid from three signals
       audio   - loudness above the clip's own baseline + sudden rises (screams, blasts)
       motion  - how much the picture changes (fights, explosions, fast action)
       speech  - talking speed, hype words ("no way", "let's go", "what"), laughter,
                 shouting (ALL-CAPS / "!!" in the transcript)
  2. Scores every candidate window (20-45 s): average + peak excitement, the peak
     landing in the back half (setup -> payoff), no dead air at the start, a short
     reaction tail after the peak.
  3. Asks Groq (one call, also used by the AI clip picker) to read the
     timestamped transcript and name the self-contained segment with a hook and a
     payoff; its pick wins when the signals agree it's a strong window.
  4. Snaps both ends to sentence boundaries so speech is never cut mid-word.

Everything fails open: if a signal can't be computed it is left out, and if
nothing works the old middle cut is used.
"""
import logging
import re
import subprocess

import numpy as np

import config

STEP = 0.5            # seconds per excitement sample
MIN_LEN, MAX_LEN = 15.0, 45.0
WINDOW_LENGTHS = (20.0, 25.0, 30.0, 35.0, 40.0, 45.0)

HYPE_WORDS = {
    "no", "way", "what", "wait", "bro", "dude", "omg", "god", "yo", "yes", "lets",
    "let's", "go", "dead", "insane", "crazy", "holy", "wow", "oh", "run", "help",
    "clutch", "nooo", "noooo", "yooo", "bruh", "wtf", "lol", "lmao", "why", "how",
}
LAUGH = re.compile(r"\b(ha){2,}|\b(he){2,}|\blol\b|\blmao\b", re.I)


# ----------------------------------------------------------------------------
# Signals
# ----------------------------------------------------------------------------
def _normalise(x):
    """Scale to 0..1 using the clip's own 10th-95th percentile range."""
    if x is None or len(x) == 0:
        return None
    lo, hi = np.percentile(x, 10), np.percentile(x, 95)
    if hi - lo < 1e-6:
        return np.zeros_like(x, dtype=float)
    return np.clip((x - lo) / (hi - lo), 0, 1)


def _audio_curve(video_path, n):
    sr = 8000
    raw = subprocess.run(
        [config.get_ffmpeg_path(), "-v", "error", "-i", video_path, "-vn",
         "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
        capture_output=True, timeout=180, check=True,
    ).stdout
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    hop = int(sr * STEP)
    m = min(n, len(audio) // hop)
    if m < 4:
        return None
    rms = np.sqrt(np.mean(audio[: m * hop].reshape(m, hop) ** 2, axis=1) + 1e-10)
    db = 20 * np.log10(rms)
    level = db - np.median(db)                       # loudness vs this clip's baseline
    rise = np.maximum(0, np.diff(db, prepend=db[0]))  # sudden jumps
    curve = 0.7 * _normalise(level) + 0.3 * _normalise(rise)
    return np.pad(curve, (0, n - m))


def _motion_curve(video_path, n):
    """Mean absolute frame difference at 2 fps on a tiny greyscale copy."""
    w, h = 64, 36
    raw = subprocess.run(
        [config.get_ffmpeg_path(), "-v", "error", "-i", video_path, "-an",
         "-vf", f"fps={1 / STEP},scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
        capture_output=True, timeout=180, check=True,
    ).stdout
    frames = np.frombuffer(raw, dtype=np.uint8)
    m = min(n, len(frames) // (w * h))
    if m < 4:
        return None
    frames = frames[: m * w * h].reshape(m, h, w).astype(np.float32)
    diff = np.abs(np.diff(frames, axis=0, prepend=frames[:1])).mean(axis=(1, 2))
    return np.pad(_normalise(diff), (0, n - m))


def _speech_curve(words, n):
    if not words:
        return None
    rate = np.zeros(n)
    hype = np.zeros(n)
    for ws, we, text in words:
        i = int(ws / STEP)
        if i >= n:
            continue
        rate[i] += 1
        clean = re.sub(r"[^a-z']", "", text.lower())
        if clean in HYPE_WORDS:
            hype[i] += 1
        if LAUGH.search(text):
            hype[i] += 2
        if (text.isupper() and len(clean) > 1) or "!" in text:
            hype[i] += 1.5
    k = np.ones(4) / 4                       # spread over ~2 s
    rate = np.convolve(rate, k, mode="same")
    hype = np.convolve(hype, k, mode="same")
    return 0.4 * _normalise(rate) + 0.6 * _normalise(hype)


def excitement_curve(video_path, duration, words=None, signal_weights=None):
    """0..1 excitement per 0.5 s step, from whichever signals are available.
    signal_weights: optional (audio, motion, speech) weights, e.g. chosen by the
    RL bandit; defaults to the hand-tuned (0.45, 0.25, 0.30)."""
    n = max(1, int(duration / STEP))
    w_audio, w_motion, w_speech = signal_weights or (0.45, 0.25, 0.30)
    parts, weights = [], []
    for name, fn, wt in (
        ("audio", lambda: _audio_curve(video_path, n), w_audio),
        ("motion", lambda: _motion_curve(video_path, n), w_motion),
        ("speech", lambda: _speech_curve(words, n), w_speech),
    ):
        try:
            c = fn()
            if c is not None and np.any(c):
                parts.append(c[:n] * wt)
                weights.append(wt)
        except Exception as e:
            logging.info(f"[moment] {name} signal unavailable: {e}")
    if not parts:
        return None
    curve = np.sum(parts, axis=0) / sum(weights)
    return np.convolve(curve, np.ones(3) / 3, mode="same")


# ----------------------------------------------------------------------------
# Window scoring
# ----------------------------------------------------------------------------
def _window_score(curve, s, e):
    i, j = int(s / STEP), max(int(s / STEP) + 1, int(e / STEP))
    seg = curve[i:j]
    if len(seg) == 0:
        return -1.0
    peak_idx = int(np.argmax(seg))
    peak_pos = peak_idx / max(1, len(seg) - 1)
    score = seg.mean() + 0.6 * seg.max() + 0.25 * np.sort(seg)[-max(1, len(seg) // 5):].mean()
    # Setup -> payoff: the biggest moment should land about two-thirds in...
    score += 0.2 * max(-0.5, 1 - abs(peak_pos - 0.68) / 0.3)
    # ...with a short reaction tail after it, not cut off on the peak.
    if (len(seg) - 1 - peak_idx) * STEP < 1.5:
        score -= 0.15
    # Don't open on dead air, and don't trail off into a long dull tail.
    if seg[: int(2 / STEP)].mean() < 0.12:
        score -= 0.1
    tail = seg[peak_idx + int(4 / STEP):]
    if len(tail) >= int(3 / STEP) and tail.mean() < 0.15:
        score -= 0.04 * len(tail) * STEP / 3
    return float(score + 0.002 * (e - s))   # tiny nudge towards fuller windows


def best_signal_window(curve, duration, lengths=None):
    best = (-1.0, 0.0, min(duration, 35.0))
    candidates = [l for l in (lengths or ()) if l <= duration] or WINDOW_LENGTHS
    for length in candidates:
        if length > duration:
            continue
        s = 0.0
        while s + length <= duration + 1e-6:
            sc = _window_score(curve, s, s + length)
            if sc > best[0]:
                best = (sc, s, s + length)
            s += STEP
    return best


def _snap(words, start, end, duration):
    """Move cuts to pauses between sentences: start on a word that follows a gap,
    end just after a word (plus a short reaction tail)."""
    if not words:
        return start, end
    # Start: latest word start at or slightly before `start` that follows a 0.35 s gap.
    starts = [ws for k, (ws, we, t) in enumerate(words)
              if start - 2.5 <= ws <= start + 0.5 and (k == 0 or ws - words[k - 1][1] >= 0.35)]
    if starts:
        start = max(0.0, min(starts, key=lambda x: abs(x - start)) - 0.25)
    else:
        inside = [w for w in words if w[0] < start < w[1]]   # don't start mid-word
        if inside:
            start = max(0.0, inside[0][0] - 0.25)
    # End: finish the word/sentence running at `end`, then hold 0.6 s.
    running = [w for w in words if w[0] < end <= w[1] + 0.3]
    if running:
        end = running[-1][1]
    later = [w for w in words if end < w[0] <= end + 2.0]
    for k, w in enumerate(later):            # finish the sentence if it ends soon
        nxt = later[k + 1][0] if k + 1 < len(later) else None
        if nxt is None or nxt - w[1] >= 0.35:
            end = w[1]
            break
    end = min(duration, end + 0.6)
    if end - start > MAX_LEN:
        end = start + MAX_LEN
    if end - start < MIN_LEN:
        end = min(duration, start + MIN_LEN)
        start = max(0.0, end - MIN_LEN)
    return round(start, 2), round(end, 2)


# ----------------------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------------------
def find_best_moment(video_path, duration, words=None, ai_window=None,
                     signal_weights=None, lengths=None):
    """
    Returns {"start", "end", "method", "peak"} for the best 15-45 s segment.
    ai_window: optional (start, end) suggested by Groq from the transcript.
    signal_weights / lengths: optional RL-bandit choices (see rl/bandit.py) for
    how to weigh audio/motion/speech and which window lengths to consider.
    """
    fallback_len = min(duration, 35.0)
    fallback = {"start": round((duration - fallback_len) / 2, 2),
                "end": round((duration + fallback_len) / 2, 2), "method": "middle", "peak": None}
    if duration <= 0:
        return fallback
    if duration <= 22:
        return {"start": 0.0, "end": round(duration, 2), "method": "whole clip", "peak": None}

    curve = excitement_curve(video_path, duration, words, signal_weights)
    if curve is None:
        return fallback
    peak = round(float(np.argmax(curve)) * STEP, 1)
    sig_score, s, e = best_signal_window(curve, duration, lengths)
    method = "signals"

    if ai_window:
        a_s, a_e = ai_window
        a_s, a_e = max(0.0, float(a_s)), min(duration, float(a_e))
        lo, hi = MIN_LEN - 3, MAX_LEN + 3
        if lengths:   # respect the bandit's clip-length choice (with some slack)
            lo, hi = max(lo, min(lengths) - 5), min(hi, max(lengths) + 5)
        if lo <= a_e - a_s <= hi:
            a_e = min(a_e, a_s + MAX_LEN)
            ai_score = _window_score(curve, a_s, max(a_e, a_s + MIN_LEN))
            # Trust the AI's story sense unless the signals say the window is dull.
            if ai_score >= 0.75 * sig_score:
                s, e, method = a_s, max(a_e, a_s + MIN_LEN), "AI + signals"

    s, e = _snap(words, s, e, duration)
    return {"start": s, "end": e, "method": method, "peak": peak}


def timestamped_transcript(words, max_chars=2500):
    """'[12.4] text ...' lines, one per sentence-ish chunk, for the LLM."""
    if not words:
        return ""
    lines, cur, cur_start = [], [], None
    for k, (ws, we, t) in enumerate(words):
        if cur_start is None:
            cur_start = ws
        cur.append(t)
        gap = words[k + 1][0] - we if k + 1 < len(words) else 99
        if gap >= 0.6 or len(cur) >= 14 or t.endswith((".", "?", "!")):
            lines.append(f"[{cur_start:.1f}-{we:.1f}] {' '.join(cur)}")
            cur, cur_start = [], None
    out = "\n".join(lines)
    return out[:max_chars]
