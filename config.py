import os
import shutil
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Keys & Auth Secrets (strip accidental newlines/whitespace)
YOUTUBE_API_KEY = (os.getenv("YOUTUBE_API_KEY") or "").strip()
GROQ_API_KEY = (os.getenv("GROQ_API_KEY") or "").strip()
TWITCH_CLIENT_ID = (os.getenv("TWITCH_CLIENT_ID") or "").strip()
TWITCH_CLIENT_SECRET = (os.getenv("TWITCH_CLIENT_SECRET") or "").strip()

# Directory Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_VIDEOS_DIR = os.path.join(DATA_DIR, "raw_videos")
CLIPS_DIR = os.path.join(DATA_DIR, "clips")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
THUMBNAILS_DIR = os.path.join(DATA_DIR, "thumbnails")

ASSETS_DIR = os.path.join(BASE_DIR, "assets")
BGM_DIR = os.path.join(ASSETS_DIR, "background_music")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")

# Persistence Files
SEEN_VIDEOS_FILE = os.path.join(DATA_DIR, "seen_videos.txt")
UPLOAD_LOG_FILE = os.path.join(DATA_DIR, "upload_log.json")
QUEUE_FILE = os.path.join(DATA_DIR, "upload_queue.json")
CLIENT_SECRETS_FILE = os.path.join(BASE_DIR, "client_secret.json")

# Limits & Requirements
MAX_UPLOADS_PER_DAY = 15

# Target Gaming Categories (Strictly GTA 5, GTA 6, Indian Bike Driving 3D, and Call of Duty ONLY)
TARGET_GAMES = [
    "Grand Theft Auto V",
    "Grand Theft Auto VI",
    "Indian Bike Driving 3D",
    "Call of Duty: Warzone",
    "Call of Duty: Modern Warfare III",
    "Call of Duty: Black Ops 6"
]

def setup_secret_files():
    """Auto-populates secret files if environment variables are provided (e.g. in GitHub Actions)."""
    token_json_env = os.getenv("YOUTUBE_TOKEN_JSON")
    token_path = os.path.join(BASE_DIR, "token.json")
    if token_json_env:
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(token_json_env)

    client_secret_env = os.getenv("YOUTUBE_CLIENT_SECRET_JSON")
    if client_secret_env:
        with open(CLIENT_SECRETS_FILE, "w", encoding="utf-8") as f:
            f.write(client_secret_env)

def get_ffmpeg_path():
    """
    Returns the path to FFmpeg executable.
    Prioritizes system PATH (works seamlessly on Linux/GitHub Actions & Windows),
    and falls back to local ffmpeg binary if present.
    """
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    
    local_win_ffmpeg = os.path.join(BASE_DIR, "ffmpeg", "bin", "ffmpeg.exe")
    if os.path.exists(local_win_ffmpeg):
        return local_win_ffmpeg
        
    return "ffmpeg"

# Initialize secrets on import if running in environment with secret env vars
setup_secret_files()
