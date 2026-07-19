import os
import random
import requests
import logging
from config import TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, TARGET_GAMES, SEEN_VIDEOS_FILE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

_TWITCH_TOKEN = None

def get_twitch_access_token():
    """
    Obtains an App Access Token using Twitch Client ID and Client Secret.
    """
    global _TWITCH_TOKEN
    if _TWITCH_TOKEN:
        return _TWITCH_TOKEN

    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        logging.error("TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET environment variable is missing!")
        raise ValueError("TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET must be set in environment variables.")

    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials"
    }

    try:
        response = requests.post(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        _TWITCH_TOKEN = data.get("access_token")
        logging.info("[+] Twitch OAuth Authentication Successful!")
        return _TWITCH_TOKEN
    except Exception as e:
        logging.error(f"[!] Twitch Auth Error: {e}")
        return None

def get_seen_videos():
    """Reads seen video/clip IDs from the persistence file."""
    if not os.path.exists(SEEN_VIDEOS_FILE):
        return set()
    with open(SEEN_VIDEOS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f.readlines() if line.strip())

def mark_video_seen(video_id):
    """Appends a clip ID to the seen videos file."""
    with open(SEEN_VIDEOS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{video_id}\n")

def get_game_id(game_name, headers):
    """Resolves a Twitch game name to its Helix game ID."""
    url = f"https://api.twitch.tv/helix/games?name={game_name}"
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        data = res.json().get("data", [])
        if data:
            return data[0]["id"]
    except Exception as e:
        logging.warning(f"[!] Could not resolve game ID for '{game_name}': {e}")
    return None

def find_twitch_clips():
    """
    Queries Twitch Helix API for top trending clips across target game categories.
    Iterates through games until fresh unseen candidate clips are found.
    """
    token = get_twitch_access_token()
    if not token:
        logging.error("Failed to authenticate with Twitch API.")
        return []

    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

    seen = get_seen_videos()
    games = list(TARGET_GAMES)
    random.shuffle(games)

    candidates = []

    for game_name in games:
        logging.info(f"[*] Searching Twitch for category: '{game_name}'...")
        game_id = get_game_id(game_name, headers)
        if not game_id:
            continue

        url = f"https://api.twitch.tv/helix/clips?game_id={game_id}&first=50"
        try:
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            clips = res.json().get("data", [])

            for clip in clips:
                clip_id = clip.get("id")
                if not clip_id or clip_id in seen:
                    continue

                candidates.append({
                    "video_id": clip_id,
                    "title": clip.get("title", f"{game_name} Twitch Clip"),
                    "url": clip.get("url"),
                    "thumbnail_url": clip.get("thumbnail_url"),
                    "game_name": game_name,
                    "duration": clip.get("duration", 30)
                })

            if candidates:
                logging.info(f"[+] Found {len(candidates)} unseen candidate clips in '{game_name}'")
                break

        except Exception as e:
            logging.error(f"[!] Error fetching clips for game '{game_name}': {e}")
            continue

    random.shuffle(candidates)
    return candidates

if __name__ == "__main__":
    clips = find_twitch_clips()
    print(f"Found {len(clips)} candidate clips.")
