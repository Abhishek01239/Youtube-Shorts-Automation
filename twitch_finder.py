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
    """Append clips whose id is not yet seen."""
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
            "duration": clip.get("duration", 30),
            "broadcaster_name": clip.get("broadcaster_name"),
            "broadcaster_login": clip.get("_broadcaster_login"),
        })


def resolve_streamers(logins, headers):
    """Resolves Twitch usernames to {id: login}. Unknown names are logged and skipped."""
    clean = sorted({l.strip().lstrip("@").lower() for l in logins if l and l.strip()})
    found = {}
    for i in range(0, len(clean), 100):
        batch = clean[i:i + 100]
        try:
            res = requests.get("https://api.twitch.tv/helix/users", headers=headers,
                               params=[("login", l) for l in batch], timeout=10)
            res.raise_for_status()
            for u in res.json().get("data", []):
                found[u["id"]] = u["login"]
        except Exception as e:
            logging.error(f"[!] Could not resolve Twitch streamers {batch}: {e}")
    missing = set(clean) - set(found.values())
    if missing:
        logging.warning(f"[!] Twitch streamers not found, skipping: {', '.join(sorted(missing))}")
    return found


def find_twitch_clips(target_games=None, allowed_streamers=None, days=7):
    """
    Finds fresh clips of the target games, ONLY from streamers on the channel's
    `allowed_streamers` list (streamers who gave permission to clip, plus your own
    channel). Clips from anyone else are never picked up. An empty list means no
    clips: the channel uploads nothing until streamers are added.
    """
    if not allowed_streamers:
        logging.warning("[!] No allowed_streamers configured for this channel: skipping Twitch clips. "
                        "Add streamers who gave you permission (or your own channel) to "
                        "source_configuration.allowed_streamers in channels.json.")
        return []

    token = get_twitch_access_token()
    if not token:
        logging.error("Failed to authenticate with Twitch API.")
        return []

    client_id = (config.TWITCH_CLIENT_ID or "").strip()
    headers = {"Client-ID": client_id, "Authorization": f"Bearer {token}"}

    games = list(target_games) if target_games is not None else list(config.TARGET_GAMES)
    game_ids = {}
    for game_name in games:
        gid = get_game_id(game_name, headers)
        if gid:
            game_ids[gid] = game_name
    if not game_ids:
        logging.error(f"[!] None of the target games were found on Twitch: {games}")
        return []

    streamers = resolve_streamers(allowed_streamers, headers)
    seen = get_seen_videos()
    started_at = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidates = []

    for broadcaster_id, login in streamers.items():
        logging.info(f"[*] Checking @{login} for clips of {', '.join(game_ids.values())}...")
        cursor = None
        try:
            for _ in range(3):  # up to 300 most-viewed clips from the window
                params = {"broadcaster_id": broadcaster_id, "first": 100, "started_at": started_at}
                if cursor:
                    params["after"] = cursor
                res = requests.get("https://api.twitch.tv/helix/clips", headers=headers, params=params, timeout=10)
                res.raise_for_status()
                data = res.json()
                for clip in data.get("data", []):
                    game_name = game_ids.get(clip.get("game_id"))
                    if game_name:
                        clip["_broadcaster_login"] = login
                        _collect_unseen([clip], seen, candidates, game_name)
                cursor = data.get("pagination", {}).get("cursor")
                if not cursor:
                    break
        except Exception as e:
            logging.error(f"[!] Error fetching clips for @{login}: {e}")

    logging.info(f"[+] Found {len(candidates)} unseen clips from {len(streamers)} allowed streamer(s)")
    random.shuffle(candidates)
    return candidates

if __name__ == "__main__":
    clips = find_twitch_clips()
    print(f"Found {len(clips)} candidate clips.")
