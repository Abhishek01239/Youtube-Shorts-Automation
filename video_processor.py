import os
import random
import ffmpeg
from config import PROCESSED_DIR, BGM_DIR, FONTS_DIR, get_ffmpeg_path

def get_random_bgm():
    if not os.path.exists(BGM_DIR): return None
    files = [f for f in os.listdir(BGM_DIR) if f.endswith('.mp3')]
    if not files: return None
    return os.path.join(BGM_DIR, random.choice(files))

def get_font_path():
    if not os.path.exists(FONTS_DIR): return None
    files = [f for f in os.listdir(FONTS_DIR) if f.endswith('.ttf')]
    if not files: return None
    return os.path.join(FONTS_DIR, files[0])

def process_video(video_path, start, end, output_filename, mute_original=False):
    """
    Processes a landscape gameplay video into a high-quality YouTube Short.
    Guarantees strict duration <= 45s for YouTube Shorts compliance.
    """
    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR, exist_ok=True)
        
    out_path = os.path.join(PROCESSED_DIR, output_filename)
    
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
        ffmpeg_cmd = get_ffmpeg_path()
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
