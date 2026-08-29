import os
import random
import shutil
import subprocess
import ffmpeg
import config

def get_random_bgm():
    if not os.path.exists(config.BGM_DIR): return None
    files = [f for f in os.listdir(config.BGM_DIR) if f.endswith('.mp3')]
    if not files: return None
    return os.path.join(config.BGM_DIR, random.choice(files))

def get_font_path():
    if not os.path.exists(config.FONTS_DIR): return None
    files = [f for f in os.listdir(config.FONTS_DIR) if f.endswith('.ttf')]
    if not files: return None
    return os.path.join(config.FONTS_DIR, files[0])

def process_video(video_path, start, end, output_filename, mute_original=False):
    """
    Processes a landscape gameplay video into a high-quality YouTube Short.
    Guarantees strict duration <= 45s for YouTube Shorts compliance.
    """
    processed_dir = config.get_processed_dir()
    if not os.path.exists(processed_dir):
        os.makedirs(processed_dir, exist_ok=True)
        
    out_path = os.path.join(processed_dir, output_filename)
    
    # Cap raw clip duration to 45s max (speedup 1.2x produces ~37s Short)
    clip_duration = min(max(end - start, 15.0), 45.0)
    print(f"[*] Processing Short clip ({start:.1f}s -> {start+clip_duration:.1f}s, target duration: {clip_duration/1.2:.1f}s)")
    
    stream = ffmpeg.input(video_path, ss=start, t=clip_duration)
    video = stream.video
    audio = stream.audio
    
    # 1. Scale down to 1920 height
    v = video.filter("scale", -1, 1920, flags="lanczos")
    
    # 2. Crop center to 9:16 (1080x1920)
    v = v.filter("crop", w=1080, h=1920, x="(in_w-1080)/2", y=0)
    
    # 3. Speed up video to 1.2x
    v = v.filter("setpts", "0.833333*PTS")
    
    # 4. Light denoise
    v = v.filter("hqdn3d", 1.0, 1.0, 3.0, 3.0)
    
    # 5. Color balance
    v = v.filter("colorbalance", rs=0.18, gs=0.18, bs=0.18)
    
    # 6. HDR-style curve
    v = v.filter("curves", m="0/0 0.25/0.20 0.5/0.55 0.75/0.83 1/1")
    
    # 7. Sharpen
    v = v.filter("unsharp", 5, 5, 1.2, 5, 5, 0.0)
    
    # ENCODER SETTINGS (Optimized for speed & multi-threading)
    kwargs = {
        "vcodec": "libx264",
        "acodec": "aac",
        "preset": "fast",
        "crf": 20,
        "pix_fmt": "yuv420p",
        "movflags": "+faststart",
        "strict": "experimental",
        "loglevel": "error",
        "threads": 0,
        "shortest": None  # Crucial: cut output at shortest stream (video length)
    }
    
    bgm_path = get_random_bgm()
    if mute_original:
        if bgm_path:
            bgm = (
                ffmpeg
                .input(bgm_path)
                .audio
                .filter("atrim", duration=clip_duration)
                .filter("volume", 0.8)
            )
            out = ffmpeg.output(v, bgm, out_path, **kwargs)
        else:
            out = ffmpeg.output(v, out_path, an=None, **kwargs)
    else:
        audio = audio.filter("atempo", 1.2)
        if bgm_path:
            bgm = (
                ffmpeg
                .input(bgm_path)
                .audio
                .filter("atrim", duration=clip_duration)
                .filter("volume", 0.15)
            )
            audio = ffmpeg.filter([audio, bgm], "amix", inputs=2, duration="first")
            
        out = ffmpeg.output(v, audio, out_path, **kwargs)
        
    try:
        ffmpeg_cmd = config.get_ffmpeg_path()
        out.run(overwrite_output=True, cmd=ffmpeg_cmd)
        print(f"[+] YouTube Short saved: {out_path}")
        return out_path
    except ffmpeg.Error as e:
        print("\n========== FFMPEG ERROR ==========")
        if e.stderr:
            print(e.stderr.decode())
        else:
            print(str(e))
        print("==================================\n")
        return None


def get_video_duration(video_path):
    """
    Returns the actual duration (seconds, float) of a rendered video file using
    ffprobe. Returns 0.0 if ffprobe is unavailable or the file can't be probed.
    Used to HARD-VERIFY a minimum length requirement before upload (e.g. every
    Facebook video must be > 3 minutes).
    """
    if not video_path or not os.path.exists(video_path):
        return 0.0
    probe = shutil.which("ffprobe") or os.path.join(
        os.path.dirname(config.get_ffmpeg_path()), "ffprobe"
    )
    if not probe or not os.path.exists(probe):
        # ffprobe missing — fall back to a best-effort estimate via ffmpeg
        probe = config.get_ffmpeg_path()
    try:
        result = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60
        )
        out = result.stdout.decode().strip()
        if out:
            return float(out)
    except (subprocess.SubprocessError, ValueError, OSError):
        pass
    return 0.0


def process_compilation_video(clip_segments, output_filename, max_duration=2400, min_duration=1200, use_bgm=False):
    """
    Builds a long-form video (16:9 1080p) by stitching several clip segments
    together into a single file. Each segment receives the same color / denoise /
    sharpen grade as the Shorts processor, and the ORIGINAL clip audio is kept
    exactly as-is (no background music) unless use_bgm=True. Output is capped at
    max_duration seconds (default 40 min = 2400s) and the pipeline enforces a
    minimum length of min_duration seconds (default 20 min = 1200s).

    clip_segments: list of (video_path, start, end) tuples.
    Returns absolute path to the final MP4 or None on failure.
    """
    processed_dir = config.get_processed_dir()
    os.makedirs(processed_dir, exist_ok=True)

    ffmpeg_cmd = config.get_ffmpeg_path()
    base = os.path.splitext(output_filename)[0]
    part_paths = []
    list_path = os.path.join(processed_dir, f"{base}_concat.txt")
    merged_path = os.path.join(processed_dir, f"{base}_merged.mp4")
    out_path = os.path.join(processed_dir, output_filename)

    try:
        # Step A: grade & normalize each segment into uniform 16:9 1080p parts
        for i, (video_path, start, end) in enumerate(clip_segments):
            dur = min(max(end - start, 5.0), 90.0)
            part_path = os.path.join(processed_dir, f"{base}_part{i}.mp4")

            stream = ffmpeg.input(video_path, ss=start, t=dur)
            v = (
                stream.video
                .filter("scale", 1920, 1080, force_original_aspect_ratio="decrease")
                .filter("pad", 1920, 1080, "(ow-iw)/2", "(oh-ih)/2")
                .filter("hqdn3d", 1.0, 1.0, 3.0, 3.0)
                .filter("colorbalance", rs=0.18, gs=0.18, bs=0.18)
                .filter("curves", m="0/0 0.25/0.20 0.5/0.55 0.75/0.83 1/1")
                .filter("unsharp", 5, 5, 1.2, 5, 5, 0.0)
            )

            # Try with original audio (normalized params so concat can stream-copy)
            has_audio = False
            try:
                a = stream.audio.filter(
                    "aformat",
                    sample_fmts="fltp", sample_rates=44100, channel_layouts="stereo"
                )
                has_audio = True
            except (AttributeError, ffmpeg.Error):
                pass

            if has_audio:
                try:
                    part = ffmpeg.output(
                        v, a, part_path,
                        vcodec="libx264", acodec="aac", preset="fast", crf=18,
                        pix_fmt="yuv420p", movflags="+faststart",
                        strict="experimental", loglevel="error", threads=0
                    )
                    part.run(overwrite_output=True, cmd=ffmpeg_cmd)
                except ffmpeg.Error:
                    has_audio = False

            if not has_audio:
                part = ffmpeg.output(
                    v, part_path,
                    vcodec="libx264", preset="fast", crf=18,
                    pix_fmt="yuv420p", movflags="+faststart",
                    loglevel="error", threads=0
                )
                part.run(overwrite_output=True, cmd=ffmpeg_cmd)

            part_paths.append(part_path)

        if len(part_paths) < 1:
            return None

        # Step B: concatenate parts (identical encoding params -> stream copy)
        with open(list_path, "w", encoding="utf-8") as f:
            for p in part_paths:
                escaped = p.replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        concat_in = ffmpeg.input(list_path, f="concat", safe=0)
        try:
            concat_in.output(merged_path, c="copy", loglevel="error").run(
                overwrite_output=True, cmd=ffmpeg_cmd
            )
        except ffmpeg.Error:
            concat_in.output(
                merged_path, vcodec="libx264", acodec="aac", preset="fast", crf=18,
                pix_fmt="yuv420p", loglevel="error", threads=0
            ).run(overwrite_output=True, cmd=ffmpeg_cmd)

        # Step C: keep the ORIGINAL audio as-is (no background music) unless
        # use_bgm is requested.
        if use_bgm:
            bgm_path = get_random_bgm()
            if bgm_path:
                merged = ffmpeg.input(merged_path)
                bgm = (
                    ffmpeg.input(bgm_path).audio
                    .filter("atrim", duration=max_duration)
                    .filter("volume", 0.15)
                )
                mixed = ffmpeg.filter([merged.audio, bgm], "amix", inputs=2, duration="first")
                ffmpeg.output(
                    merged.video, mixed, out_path,
                    vcodec="copy", acodec="aac", preset="fast", t=max_duration,
                    movflags="+faststart", loglevel="error", threads=0
                ).run(overwrite_output=True, cmd=ffmpeg_cmd)
            else:
                os.replace(merged_path, out_path)
        else:
            # No BGM: trim to max_duration and copy the original audio verbatim.
            merged = ffmpeg.input(merged_path)
            ffmpeg.output(
                merged.video, merged.audio, out_path,
                vcodec="copy", acodec="copy", t=max_duration,
                movflags="+faststart", loglevel="error", threads=0
            ).run(overwrite_output=True, cmd=ffmpeg_cmd)

        if os.path.exists(out_path) and os.path.getsize(out_path) > 100000:
            print(f"[+] Long-form video saved: {out_path}")
            return out_path
        return None

    except ffmpeg.Error as e:
        print("\n========== FFMPEG ERROR (compilation) ==========")
        if e.stderr:
            print(e.stderr.decode())
        else:
            print(str(e))
        print("===============================================\n")
        return None

    finally:
        # Always clean up intermediates (raw/processed dirs are wiped later too)
        for p in part_paths + [list_path, merged_path]:
            try:
                if os.path.exists(p):
                    os.unlink(p)
            except Exception:
                pass
