import os
import shutil
import subprocess
import requests
import hashlib
from pathlib import Path

PIPER_VOICES_DIR = Path(__file__).parent / "data" / "piper_voices"
PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)

# Default voice: en_US-lessac-medium (natural, clear, good for news)
DEFAULT_VOICE = "en_US-lessac-medium"
DEFAULT_VOICE_URL = f"https://github.com/rhasspy/piper/releases/download/v1.3.0/{DEFAULT_VOICE}.onnx"
DEFAULT_VOICE_CONFIG_URL = f"https://github.com/rhasspy/piper/releases/download/v1.3.0/{DEFAULT_VOICE}.onnx.json"

EXPECTED_SHA256 = {
    f"{DEFAULT_VOICE}.onnx": "a3b5d5c9c4a8f3e2d1b4c5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6",
}

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def download_piper_voice(voice_name=DEFAULT_VOICE, force=False):
    """Download Piper voice model and config if not present."""
    model_path = PIPER_VOICES_DIR / f"{voice_name}.onnx"
    config_path = PIPER_VOICES_DIR / f"{voice_name}.onnx.json"
    
    if model_path.exists() and config_path.exists() and not force:
        return str(model_path), str(config_path)
    
    print(f"[*] Downloading Piper voice: {voice_name}...")
    
    # Download model
    model_url = f"https://github.com/rhasspy/piper/releases/download/v1.3.0/{voice_name}.onnx"
    config_url = f"https://github.com/rhasspy/piper/releases/download/v1.3.0/{voice_name}.onnx.json"
    
    try:
        # Download model
        print(f"[*] Fetching {model_url}...")
        resp = requests.get(model_url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(model_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"[+] Model saved: {model_path} ({model_path.stat().st_size / 1024 / 1024:.1f} MB)")
        
        # Download config
        print(f"[*] Fetching {config_url}...")
        resp = requests.get(config_url, timeout=30)
        resp.raise_for_status()
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(resp.text)
        print(f"[+] Config saved: {config_path}")
        
        return str(model_path), str(config_path)
        
    except Exception as e:
        print(f"[!] Failed to download Piper voice: {e}")
        # Cleanup partial downloads
        for p in [model_path, config_path]:
            if p.exists():
                p.unlink()
        raise


def get_piper_voice_path(voice_name=DEFAULT_VOICE):
    """Get path to Piper voice model, downloading if needed."""
    model_path, config_path = download_piper_voice(voice_name)
    return model_path, config_path


def synthesize_piper(text, output_path, voice_name=DEFAULT_VOICE, speed=1.0):
    """Synthesize speech using Piper TTS (local, no API key needed)."""
    model_path, config_path = get_piper_voice_path(voice_name)
    
    # Find piper binary
    piper_bin = None
    for p in [
        "piper",
        str(Path.home() / ".local" / "bin" / "piper"),
        "/usr/local/bin/piper",
        "C:/piper/piper.exe",
    ]:
        if shutil.which(p) or Path(p).exists():
            piper_bin = p
            break
    
    if not piper_bin:
        # Try pipx/uv installed
        try:
            import piper
            piper_bin = "piper"
        except ImportError:
            pass
    
    if not piper_bin:
        raise RuntimeError("Piper binary not found. Install with: pip install piper-tts")
    
    cmd = [
        piper_bin,
        "--model", model_path,
        "--config", config_path,
        "--output_file", output_path,
    ]
    
    if speed != 1.0:
        cmd.extend(["--length_scale", str(1.0 / speed)])
    
    print(f"[*] Synthesizing with Piper: '{text[:60]}...'")
    result = subprocess.run(cmd, input=text.encode(), capture_output=True, timeout=120)
    
    if result.returncode != 0:
        raise RuntimeError(f"Piper synthesis failed: {result.stderr.decode()}")
    
    if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
        raise RuntimeError("Piper produced empty/invalid output")
    
    print(f"[+] Speech synthesized: {output_path} ({os.path.getsize(output_path) / 1024:.1f} KB)")
    return output_path


if __name__ == "__main__":
    import sys
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "This is a test of the Piper text to speech system."
    out = PIPER_VOICES_DIR.parent / "test_piper.wav"
    synthesize_piper(text, str(out))