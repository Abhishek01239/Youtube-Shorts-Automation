import os
import subprocess
from config import get_ffmpeg_path

def get_video_duration(video_path):
    """Probes the video file using ffprobe to retrieve duration in seconds."""
    try:
        ffmpeg_path = get_ffmpeg_path()
        # Resolve ffprobe path by replacing ffmpeg with ffprobe
        if "ffmpeg.exe" in ffmpeg_path:
            ffprobe_path = ffmpeg_path.replace("ffmpeg.exe", "ffprobe.exe")
        elif "ffmpeg" in ffmpeg_path:
            ffprobe_path = ffmpeg_path.replace("ffmpeg", "ffprobe")
        else:
            ffprobe_path = "ffprobe"
            
        cmd = [
            ffprobe_path, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", video_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[!] Error getting video duration: {e}")
        return 0.0

def get_highlights(video_path, num_clips=1):
    """
    Bypasses complex audio energy and scene detection.
    Always cuts a reliable segment from the video to guarantee successful processing.
    """
    print("[*] Detecting highlights (Simplified Cut logic)...")
    duration = get_video_duration(video_path)
    
    if duration <= 0:
        # Default fallback if duration could not be determined
        print("[!] Could not determine video duration. Using fallback range.")
        return [{"start": 10.0, "end": 45.0, "duration": 35.0}]
        
    print(f"[+] Video duration detected: {duration:.1f}s")
    
    # Target clip duration of 35 seconds (leads to a ~29.1s Short after 1.2x speedup)
    target_clip_dur = 35.0
    
    if duration <= 45.0:
        # For short clips (already under 45s), use the full clip
        start_time = 0.0
        end_time = duration
        clip_dur = duration
    else:
        # For longer videos, cut a 35s segment from the middle
        start_time = (duration - target_clip_dur) / 2.0
        end_time = start_time + target_clip_dur
        clip_dur = target_clip_dur
        
    return [{
        "start": start_time,
        "end": end_time,
        "duration": clip_dur
    }]
