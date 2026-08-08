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

# Notification Configuration
NOTIFICATION_PROVIDER = (os.getenv("NOTIFICATION_PROVIDER") or "TELEGRAM").upper().strip()
TWILIO_ACCOUNT_SID = (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
TWILIO_AUTH_TOKEN = (os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
TWILIO_FROM_NUMBER = (os.getenv("TWILIO_FROM_NUMBER") or "").strip()
USER_PHONE_NUMBER = (os.getenv("USER_PHONE_NUMBER") or "").strip()
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()


# Directory Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

ACTIVE_CHANNEL_NAME = None

def set_active_channel(channel_name):
    global ACTIVE_CHANNEL_NAME
    ACTIVE_CHANNEL_NAME = channel_name

def get_channel_dir():
    if ACTIVE_CHANNEL_NAME:
        sanitized = "".join([c if c.isalnum() else "_" for c in ACTIVE_CHANNEL_NAME])
        path = os.path.join(DATA_DIR, "channels", sanitized)
        os.makedirs(path, exist_ok=True)
        return path
    return DATA_DIR

def get_raw_videos_dir():
    d = os.path.join(get_channel_dir(), "raw_videos")
    os.makedirs(d, exist_ok=True)
    return d

def get_clips_dir():
    d = os.path.join(get_channel_dir(), "clips")
    os.makedirs(d, exist_ok=True)
    return d

def get_processed_dir():
    d = os.path.join(get_channel_dir(), "processed")
    os.makedirs(d, exist_ok=True)
    return d

def get_thumbnails_dir():
    d = os.path.join(get_channel_dir(), "thumbnails")
    os.makedirs(d, exist_ok=True)
    return d

def get_seen_videos_file():
    return os.path.join(get_channel_dir(), "seen_videos.txt")

def get_upload_log_file():
    return os.path.join(get_channel_dir(), "upload_log.json")

def get_queue_file():
    return os.path.join(get_channel_dir(), "upload_queue.json")

def get_token_file():
    return os.path.join(get_channel_dir(), "token.json")

CLIENT_SECRETS_FILE = os.path.join(BASE_DIR, "client_secret.json")

# Default fallbacks
TARGET_NICHES = ["gaming"]
MAX_SUBS = 100000

def __getattr__(name):
    if name == "RAW_VIDEOS_DIR":
        return get_raw_videos_dir()
    if name == "PROCESSED_DIR":
        return get_processed_dir()
    if name == "CLIPS_DIR":
        return get_clips_dir()
    if name == "THUMBNAILS_DIR":
        return get_thumbnails_dir()
    if name == "SEEN_VIDEOS_FILE":
        return get_seen_videos_file()
    if name == "UPLOAD_LOG_FILE":
        return get_upload_log_file()
    if name == "QUEUE_FILE":
        return get_queue_file()
    raise AttributeError(f"module {__name__} has no attribute {name}")

ASSETS_DIR = os.path.join(BASE_DIR, "assets")
BGM_DIR = os.path.join(ASSETS_DIR, "background_music")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")

# Limits & Requirements
# 6 Shorts + 3 long-form videos per channel per day (2 channels = 18 max),
# plus headroom for manual/dispatch runs.
MAX_UPLOADS_PER_DAY = 24

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

    # Resolve channels.json path to map uppercase env keys to exact case-sensitive channel names
    channels_file = "channels.json"
    import sys
    if "--channels" in sys.argv:
        try:
            idx = sys.argv.index("--channels")
            if idx + 1 < len(sys.argv):
                channels_file = sys.argv[idx + 1]
        except Exception:
            pass

    channel_name_map = {}
    if os.path.exists(channels_file):
        try:
            import json
            with open(channels_file, "r", encoding="utf-8") as f:
                channels_data = json.load(f)
                if isinstance(channels_data, list):
                    for ch in channels_data:
                        name = ch.get("channel_name")
                        if name:
                            channel_name_map[name.upper()] = name
        except Exception as e:
            print(f"[!] Error loading channels configuration in setup_secret_files: {e}")

    # Support channel-specific tokens from environment variables on GitHub Actions
    for key, value in os.environ.items():
        if key.startswith("YOUTUBE_TOKEN_JSON_"):
            token_val = (value or "").strip()
            if not token_val:
                print(f"[!] Warning: Environment variable {key} is empty. Skipping writing to token file.")
                continue
            channel_name = key[len("YOUTUBE_TOKEN_JSON_"):]
            actual_channel_name = channel_name_map.get(channel_name.upper(), channel_name)
            sanitized = "".join([c if c.isalnum() else "_" for c in actual_channel_name])
            path = os.path.join(DATA_DIR, "channels", sanitized, "token.json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(token_val)

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
