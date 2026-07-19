import os
import subprocess
import librosa
import numpy as np
import speech_recognition as sr
from config import get_ffmpeg_path

def analyze_audio(video_path):
    """
    Analyzes audio for human voice AND overall silence.
    Returns: (has_voice: bool, is_silent: bool)
    """
    print("[*] Analyzing audio for human voice and overall sound levels...")
    wav_path = video_path.rsplit('.', 1)[0] + "_sample.wav"
    
    try:
        # 1. Extract first 60 seconds of audio for quick analysis
        ffmpeg_path = get_ffmpeg_path()
        cmd = [
            ffmpeg_path, "-y", "-i", video_path, 
            "-t", "60", "-ac", "1", "-ar", "16000", wav_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if not os.path.exists(wav_path):
            # If FFmpeg failed to make a WAV, the video has no audio track
            return False, True

        # 2. Spectral Analysis (librosa)
        y, sr_lib = librosa.load(wav_path, sr=16000)
        
        # Check for absolute silence
        rms = librosa.feature.rms(y=y)
        mean_rms = np.mean(rms)
        
        # 0.005 is a very low threshold. If below this, video is basically mute.
        is_silent = mean_rms < 0.005
        
        if is_silent:
            print("[+] Audio is completely silent (no game sounds or voice).")
            return False, True
            
        # Continue with Voice Detection
        S = np.abs(librosa.stft(y))
        
        # Vocal frequency band is roughly 300Hz - 3000Hz
        freqs = librosa.fft_frequencies(sr=sr_lib)
        vocal_band = np.where((freqs > 300) & (freqs < 3000))[0]
        vocal_energy = np.sum(S[vocal_band, :])
        total_energy = np.sum(S)
        
        vocal_ratio = vocal_energy / (total_energy + 1e-6)
        
        # 3. Speech Recognition Check
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            try:
                text = recognizer.recognize_google(audio_data)
                if len(text.strip()) > 0:
                    print(f"[-] Voice detected via Speech Recognition: '{text}'")
                    return True, False
            except sr.UnknownValueError:
                pass # No recognizable speech
            except sr.RequestError:
                pass # API error, fallback to spectral
                
        # Spectral fallback if API fails or is ambiguous
        if vocal_ratio > 0.65:
            print(f"[-] Voice detected via Spectral Analysis (Ratio: {vocal_ratio:.2f})")
            return True, False
            
        print("[+] Good game sounds found. No human voice detected.")
        return False, False
        
    except Exception as e:
        print(f"[!] Audio analysis error: {e}")
        return True, False
    finally:
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass
