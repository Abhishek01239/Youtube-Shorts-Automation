import os
import shutil
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Keys
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

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
MAX_SUBS = 500000
MAX_UPLOADS_PER_DAY = 15

# Expanded Target Gaming Niches
TARGET_NICHES = [
    "GTA 5 gameplay no commentary",
    "GTA 6 leaks gameplay no commentary",
    "Indian Bike Driving 3D gameplay",
    "Minecraft survival gameplay no commentary",
    "Minecraft parkour gameplay",
    "Roblox gameplay no commentary",
    "Fortnite gameplay no commentary",
    "BeamNG drive car crash gameplay",
    "Subway Surfers gameplay no commentary",
    "PUBG Mobile gameplay no commentary",
    "Need For Speed gameplay no commentary"
]
MAX_VIDEO_DURATION_MINS = 30 

def setup_secret_files():
    """Auto-populates secret files if environment variables are provided (e.g. in GitHub Actions)."""
    token_json_env = os.getenv("YOUTUBE_TOKEN_JSON")
    token_path = os.path.join(BASE_DIR, "token.json")
    if token_json_env and not os.path.exists(token_path):
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(token_json_env)

    client_secret_env = os.getenv("YOUTUBE_CLIENT_SECRET_JSON")
    if client_secret_env and not os.path.exists(CLIENT_SECRETS_FILE):
        with open(CLIENT_SECRETS_FILE, "w", encoding="utf-8") as f:
            f.write(client_secret_env)

    cookies_txt_env = os.getenv("COOKIES_TXT")
    cookies_path = os.path.join(BASE_DIR, "cookies.txt")
    if cookies_txt_env and not os.path.exists(cookies_path):
        with open(cookies_path, "w", encoding="utf-8") as f:
            f.write(cookies_txt_env)

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
