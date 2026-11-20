"""
Smart editing helpers for Shorts:

  transcribe_for_short()  one Whisper pass on the raw clip; words are re-timed to
                          the Short's timeline so captions reuse them (no 2nd pass)
  score_clip()            AI clip picker: Groq rates how watchable a clip is (1-10)
  find_hype_moments()     loudest spikes (screams, explosions, kills) for punch-ins
  zoom_expressions()      ffmpeg expressions for a quick zoom + shake at those moments
  detect_facecam()        finds a streamer facecam so the Short can use a split layout

Every helper fails open: on any error it returns a neutral value and the pipeline
carries on exactly as before.
"""
import logging
import os
import subprocess

import numpy as np

import config

# Bundled (OpenCV 5 no longer ships this file in cv2.data). MIT-style Intel licence
# is in the file header.
_FACE_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "assets", "models", "haarcascade_frontalface_default.xml")

# Must match the speed-up applied in video_processor.process_video().
SPEED = 1.2


def short_window(start, end):
    """(start, raw_duration) that process_video() cuts for a Short."""
    return start, min(max(end - start, 15.0), 45.0)


# ----------------------------------------------------------------------------
# Transcript (shared by the AI picker and the captions)
# ----------------------------------------------------------------------------
def transcribe_for_short(video_path, start, raw_dur, language=None):
    """
    Returns (words_on_short_timeline, plain_text). Words are (start, end, text)
    tuples, already shifted and sped up to match the processed Short.
    Returns (None, "") if transcription fails, so captions transcribe themselves.
    """
    try:
        from minecraft_captions import transcribe
        raw_words = transcribe(video_path, language)
    except Exception as e:
        logging.warning(f"[smart] Transcription failed, captions will retry on their own: {e}")
        return None, ""

    words = []
    for ws, we, text in raw_words:
        if ws < start or ws >= start + raw_dur:
            continue
        words.append(((ws - start) / SPEED, (min(we, start + raw_dur) - start) / SPEED, text))
    return words, " ".join(w[2] for w in words)


# ----------------------------------------------------------------------------
# AI clip picker
# ----------------------------------------------------------------------------
def score_clip(title, transcript, game="", views=None, niche="gaming"):
    """
    Asks Groq to rate a clip 1-10 for how well it would do as a Short.
    Returns (score, reason) or (None, reason) if scoring isn't possible.
    """
    if not config.GROQ_API_KEY:
        return None, "GROQ_API_KEY missing"
    try:
        from groq import Groq
        from metadata_generator import _available_chat_models, _extract_json

        transcript = (transcript or "").strip()[:1500] or "(no speech: gameplay audio only)"
        prompt = f"""You pick clips for a YouTube Shorts channel about "{niche}".
Rate this Twitch clip from 1 to 10 for how likely viewers are to watch it to the end.

Clip title: "{title}"
Game: {game or "unknown"}
Twitch views: {views if views is not None else "unknown"}
Transcript of the clip:
\"\"\"{transcript}\"\"\"

High scores: a clear funny, shocking, skilful or emotional moment; a strong reaction;
a payoff a viewer can follow without context.
Low scores: dead air, menus/loading, inside jokes that need context, mostly talking
about nothing, ads/sponsor reads, or anything unsafe for a general audience.
A clip with no speech can still score high if the title suggests an exciting play.

Reply with JSON only: {{"score": <1-10 integer>, "reason": "<one short sentence>"}}"""

        client = Groq(api_key=config.GROQ_API_KEY)
        for model in _available_chat_models(client)[:3]:
            try:
                resp = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=model, temperature=0.2,
                )
                obj = _extract_json(resp.choices[0].message.content)
                if obj and "score" in obj:
                    score = max(1, min(10, int(round(float(obj["score"])))))
                    return score, str(obj.get("reason", ""))[:200]
            except Exception as e:
                logging.info(f"[smart] Groq model {model} failed for scoring: {e}")
    except Exception as e:
        logging.warning(f"[smart] Clip scoring unavailable: {e}")
    return None, "scoring failed"


# ----------------------------------------------------------------------------
# Zoom punch-ins
# ----------------------------------------------------------------------------
def find_hype_moments(video_path, start, raw_dur, max_peaks=4, min_gap=2.5):
    """
    Finds the loudest sudden spikes in the clip's audio.
    Returns times (seconds) on the Short's sped-up timeline.
    """
    try:
        sr = 8000
        raw = subprocess.run(
            [config.get_ffmpeg_path(), "-v", "error", "-ss", str(start), "-t", str(raw_dur),
             "-i", video_path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
            capture_output=True, timeout=120, check=True,
        ).stdout
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        hop = int(sr * 0.05)  # 50 ms windows
        n = len(audio) // hop
        if n < 40:
            return []
        rms = np.sqrt(np.mean(audio[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-10)
        db = 20 * np.log10(rms)
        db = np.convolve(db, np.ones(3) / 3, mode="same")

        median, p95 = np.median(db), np.percentile(db, 95)
        if p95 - median < 6 or p95 < -45:   # flat/quiet audio: nothing stands out
            return []
        threshold = max(median + 8, p95 - 1.5)
        # "Sudden" = louder than the preceding ~1s by a clear margin
        prev = np.array([db[max(0, i - 20):i].mean() if i else db[0] for i in range(n)])
        cands = [i for i in range(1, n - 1)
                 if db[i] >= threshold and db[i] >= db[i - 1] and db[i] >= db[i + 1]
                 and db[i] - prev[i] >= 5]
        cands.sort(key=lambda i: db[i], reverse=True)

        dur_out = raw_dur / SPEED
        picked = []
        for i in cands:
            # Hit the zoom on the START of the sound, not its loudest point.
            j = i
            while j > 0 and i - j < 10 and db[j - 1] > prev[i] + 3:
                j -= 1
            t = j * 0.05 / SPEED
            if t < 0.4 or t > dur_out - 0.7:
                continue
            if all(abs(t - p) >= min_gap for p in picked):
                picked.append(t)
            if len(picked) >= max_peaks:
                break
        return sorted(round(p, 2) for p in picked)
    except Exception as e:
        logging.warning(f"[smart] Hype detection skipped: {e}")
        return []


def zoom_expressions(peaks, strength=0.14, shake_px=12):
    """
    ffmpeg expressions (scale w/h with eval=frame, crop x/y) giving a fast punch-in
    (60 ms attack, 550 ms ease-out) with a small shake at each peak, on a
    1080x1920 frame. Returns None when there are no peaks.
    """
    if not peaks:
        return None
    attack, length = 0.06, 0.55
    pulses = [
        f"between(t,{p:.2f},{p + length:.2f})*min((t-{p:.2f})/{attack},1)*(1-(t-{p:.2f})/{length})"
        for p in peaks
    ]
    P = "(" + "+".join(pulses) + ")"
    zoom = f"(1+{strength}*{P})"
    return {
        "w": f"trunc(1080*{zoom}/2)*2",
        "h": f"trunc(1920*{zoom}/2)*2",
        "x": f"(in_w-1080)/2+{shake_px}*sin(t*73)*{P}",
        "y": f"(in_h-1920)/2+{shake_px}*cos(t*61)*{P}",
    }


# ----------------------------------------------------------------------------
# Facecam detection
# ----------------------------------------------------------------------------
def detect_facecam(video_path, start, raw_dur, samples=10):
    """
    Looks for a streamer facecam: a small face that stays in the same spot across
    the clip. Returns a crop box (x, y, w, h) in source pixels sized for the
    1080x640 top panel of the split layout, or None.
    """
    try:
        import cv2
    except ImportError:
        return None
    try:
        cascade = cv2.CascadeClassifier(_FACE_MODEL)
        if cascade.empty():
            logging.warning("[smart] Face model could not be loaded; skipping facecam detection.")
            return None
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
        W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if W <= 0 or H <= 0 or W / H < 1.3:   # only for landscape sources
            cap.release()
            return None

        found = []
        for k in range(samples):
            t = start + raw_dur * (k + 0.5) / samples
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.equalizeHist(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
            faces = cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=6,
                minSize=(int(W * 0.03), int(W * 0.03)), maxSize=(int(W * 0.25), int(W * 0.25)),
            )
            for (x, y, w, h) in faces:
                found.append((x + w / 2, y + h / 2, w))
        cap.release()

        if len(found) < samples * 0.5:
            return None
        # The facecam is the face that keeps turning up in the same place.
        best = []
        for cx, cy, w in found:
            group = [f for f in found if abs(f[0] - cx) < w * 0.6 and abs(f[1] - cy) < w * 0.6]
            if len(group) > len(best):
                best = group
        if len(best) < samples * 0.5:
            return None
        cx = float(np.median([f[0] for f in best]))
        cy = float(np.median([f[1] for f in best]))
        fw = float(np.median([f[2] for f in best]))
        # Facecams sit near an edge/corner; a face in the middle is probably gameplay.
        if W * 0.3 < cx < W * 0.7 and H * 0.3 < cy < H * 0.7:
            return None

        aspect = 1080 / 640
        bw = min(fw * 3.6, W)
        bh = bw / aspect
        if bh > H:
            bh, bw = H, H * aspect
        x = int(min(max(cx - bw / 2, 0), W - bw))
        y = int(min(max(cy - bh * 0.45, 0), H - bh))
        box = (x, y, int(bw) // 2 * 2, int(bh) // 2 * 2)
        logging.info(f"[smart] Facecam found at {box} in {W}x{H} source")
        return box
    except Exception as e:
        logging.warning(f"[smart] Facecam detection skipped: {e}")
        return None
