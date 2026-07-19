import os
import subprocess
import librosa
import numpy as np
from scenedetect import detect, ContentDetector
from config import get_ffmpeg_path

def get_highlights(video_path, num_clips=5):
    """
    Uses scenedetect to segment the video and audio energy (librosa) 
    to score segments, extracting the most exciting 15-59s moments.
    """
    print("[*] Detecting highlights...")
    scenes = detect(video_path, ContentDetector())
    
    if not scenes:
        # Fallback if no cuts detected
        return [{"start": 10, "end": 45, "duration": 35}]

    # Extract full audio to compute RMS energy
    wav_path = video_path.rsplit('.', 1)[0] + "_full.wav"
    ffmpeg_path = get_ffmpeg_path()
    subprocess.run([
        ffmpeg_path, "-y", "-i", video_path, 
        "-ac", "1", "-ar", "16000", wav_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    try:
        y, sr_lib = librosa.load(wav_path, sr=16000)
        rms = librosa.feature.rms(y=y)[0]
        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr_lib)
    except Exception as e:
        print(f"[!] Error loading audio for highlight detection: {e}")
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass
        return []

    scored_scenes = []
    
    for scene in scenes:
        start_time = scene[0].get_seconds()
        end_time = scene[1].get_seconds()
        duration = end_time - start_time
        
        if duration < 10:
            continue
            
        clip_end = min(start_time + 59, end_time)
        clip_dur = clip_end - start_time
        
        if clip_dur < 15:
            continue
            
        start_idx = np.searchsorted(times, start_time)
        end_idx = np.searchsorted(times, clip_end)
        
        if start_idx >= end_idx:
            continue
            
        energy = np.mean(rms[start_idx:end_idx])
        
        scored_scenes.append({
            "start": start_time,
            "end": clip_end,
            "duration": clip_dur,
            "energy": energy
        })
        
    if os.path.exists(wav_path):
        try:
            os.remove(wav_path)
        except Exception:
            pass
        
    # Sort by highest energy
    scored_scenes.sort(key=lambda x: x["energy"], reverse=True)
    
    return scored_scenes[:num_clips]
