import os
import random
import time
import requests
import logging
from datetime import datetime, timezone, timedelta
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Max number of seen clip IDs we remember per channel. The Twitch "trending"
# clips endpoint only returns a few hundred clips, so an ever-growing seen
# list eventually covers the ENTIRE pool and find_twitch_clips returns [] forever
# (this is what left ExampleGamingChannel with "No candidate videos"). Capping it
# lets old clips rotate back into the candidate pool.
MAX_SEEN = 500

_TWITCH_TOKEN = None

def get_twitch_access_token():
    """
    Obtains an App Access Token using Twitch Client ID and Client Secret.
    Automatically strips accidental trailing newlines or whitespace.
    """
    global _TWITCH_TOKEN
    if _TWITCH_TOKEN:
        return _TWITCH_TOKEN

    client_id = (config.TWITCH_CLIENT_ID or "").strip()
    client_secret = (config.TWITCH_CLIENT_SECRET or "").strip()

    if not client_id or not client_secret:
        logging.error("TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET environment variable is missing!")
        raise ValueError("TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET must be set in environment variables.")

    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": client_id,
        "client_secret": client_secret,
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
    seen_file = config.get_seen_videos_file()
    if not os.path.exists(seen_file):
        return set()
    with open(seen_file, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f.readlines() if line.strip())

def mark_video_seen(video_id):
    """Appends a clip ID to the seen videos file (capped to MAX_SEEN entries)."""
    seen_file = config.get_seen_videos_file()
    parent_dir = os.path.dirname(os.path.abspath(seen_file))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    # Cap the file so old clips rotate back into the candidate pool.
    existing = []
    if os.path.exists(seen_file):
        with open(seen_file, "r", encoding="utf-8") as f:
            existing = [l.strip() for l in f.readlines() if l.strip()]
    if video_id in existing:
        return
    existing.append(video_id)
    if len(existing) > MAX_SEEN:
        existing = existing[-MAX_SEEN:]
    with open(seen_file, "w", encoding="utf-8") as f:
        f.write("\n".join(existing) + "\n")

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

def _collect_unseen(clips, seen, candidates, game_name):
    """Append clips whose id is not yet seen (helper for both query modes)."""
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


def find_twitch_clips(target_games=None):
    """
    Queries Twitch Helix API for fresh clips across target game categories.

    Fix for "No candidate videos" exhaustion: the default clips endpoint only
    returns the CURRENT top ~hundred trending clips, so once a channel's
    seen-list covers that pool it returns [] forever. We now ALSO query a
    RECENCY window (clips created in the last N days) and paginate further,
    so there is always fresh content to upload.
    """
    token = get_twitch_access_token()
    if not token:
        logging.error("Failed to authenticate with Twitch API.")
        return []

    client_id = (config.TWITCH_CLIENT_ID or "").strip()
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}"
    }

    seen = get_seen_videos()
    games = list(target_games) if target_games is not None else list(config.TARGET_GAMES)
    random.shuffle(games)

    candidates = []

    # Walk back through recent time windows to find fresh, unseen clips.
    # Twitch's Get Clips API requires RFC3339 UTC timestamps WITHOUT fractional
    # seconds (e.g. 2026-08-24T21:55:36Z) and each window must stay small, so
    # we step back in 2h increments across the last ~2 days. The trailing
    # (None, None) keeps the original plain-trending behaviour as a fallback.
    now = datetime.now(timezone.utc)
    windows = []
    for h in range(0, 48, 2):  # 2h steps, ~2 days back
        end = now - timedelta(hours=h)
        start = end - timedelta(hours=2)
        windows.append((start, end))
    windows.append((None, None))

    for game_name in games:
        logging.info(f"[*] Searching Twitch for category: '{game_name}'...")
        game_id = get_game_id(game_name, headers)
        if not game_id:
            continue

        for (start, end) in windows:
            if candidates:
                break
            try:
                cursor = None
                for page in range(4):  # up to 4 pages (400 clips) per window
                    query_url = f"https://api.twitch.tv/helix/clips?game_id={game_id}&first=100"
                    if start is not None:
                        # RFC3339 UTC, seconds precision, 'Z' suffix (no frac/offset)
                        fmt = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                        query_url += f"&started_at={fmt(start)}&ended_at={fmt(end)}"
                    if cursor:
                        query_url += f"&after={cursor}"
                    res = requests.get(query_url, headers=headers, timeout=10)
                    res.raise_for_status()
                    res_data = res.json()
                    clips = res_data.get("data", [])
                    _collect_unseen(clips, seen, candidates, game_name)
                    cursor = res_data.get("pagination", {}).get("cursor")
                    if not cursor or len(clips) < 100:
                        break
                if candidates:
                    logging.info(f"[+] Found {len(candidates)} unseen candidate clips in '{game_name}' (recency window)")
                    break
            except Exception as e:
                logging.error(f"[!] Error fetching clips for game '{game_name}': {e}")
                continue

        if candidates:
            break

    random.shuffle(candidates)
    return candidates

if __name__ == "__main__":
    clips = find_twitch_clips()
    print(f"Found {len(clips)} candidate clips.")
