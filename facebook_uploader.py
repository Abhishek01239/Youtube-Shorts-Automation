"""
Facebook Page video uploader (Graph API).

Mirrors youtube_uploader.py: uploads the SAME processed short / long-form
video to a Facebook Page instead of YouTube. Used when a channel in
channels.json has "platform": "facebook".

Auth model (kept simple, free-tier, no extra deps beyond `requests`):
  - A long-lived Facebook **Page Access Token** is provided via the
    FACEBOOK_PAGE_ACCESS_TOKEN secret (GitHub Actions) or env var.
  - The target Page ID is provided via FACEBOOK_PAGE_ID.
  - Alternatively a per-channel "facebook" block can name custom
    env-var keys (see channels.json).

Behaviour:
  - Long-form videos: uploaded with scheduled_publish_time (matches the
    channel's interval-based schedule, just like YouTube publishAt).
  - Shorts / vertical clips: Facebook does NOT support scheduling Reels via
    the Graph API, so they are published immediately (published=true).
  - If scheduling fails, it transparently falls back to immediate publish
    so the video is never lost.
  - All failures raise; the caller (pipeline.py) treats Facebook uploads as
    BEST-EFFORT (never aborts the channel run).
"""
import os
import logging
import requests

# Graph API version. If you get a "Unsupported version" / 403, bump this
# (e.g. v20.0, v21.0). Overridable via FACEBOOK_GRAPH_VERSION env var.
GRAPH_VERSION = os.getenv("FACEBOOK_GRAPH_VERSION", "v19.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


def get_fb_credentials(channel):
    """Return (page_id, access_token) or (None, None) if FB is not configured."""
    fb_cfg = (channel or {}).get("facebook")
    if isinstance(fb_cfg, dict):
        page_id = (
            fb_cfg.get("page_id")
            or os.getenv(fb_cfg.get("page_id_env", "FACEBOOK_PAGE_ID"))
        )
        token = os.getenv(fb_cfg.get("access_token_env", "FACEBOOK_PAGE_ACCESS_TOKEN"))
    else:
        # Fall back to global env vars
        page_id = os.getenv("FACEBOOK_PAGE_ID")
        token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")

    page_id = (page_id or "").strip()
    token = (token or "").strip()
    if not page_id or not token:
        return None, None
    return page_id, token


def _post_video(page_id, access_token, video_path, title, description,
                is_short, schedule_time=None):
    """Core Graph upload. Returns the created post/video id."""
    params = {
        "access_token": access_token,
        "title": title[:255],
        "description": description,
        # For videos we honour the schedule; for shorts (Reels) FB can't
        # schedule, so publish immediately.
        "published": "false" if (schedule_time and not is_short) else "true",
    }
    if schedule_time and not is_short:
        params["scheduled_publish_time"] = str(int(schedule_time.timestamp()))
    if is_short:
        # Mark vertical clips as Reels where the API supports it (non-fatal).
        params["video_reels_publish"] = "true"

    url = f"{GRAPH_BASE}/{page_id}/videos"
    with open(video_path, "rb") as f:
        files = {"source": (os.path.basename(video_path), f, "video/mp4")}
        resp = requests.post(url, data=params, files=files, timeout=900)
    data = resp.json() if resp.content else {}
    if resp.status_code != 200 or "id" not in data:
        raise Exception(f"Facebook API {resp.status_code}: {data}")
    return data["id"]


def upload_fb_video(video_path, metadata, schedule_time=None,
                    channel=None, is_short=True):
    """
    Upload a processed video to a Facebook Page.

    Mirrors youtube_uploader.upload_short / upload_video signatures so the
    pipeline can swap the destination based on channel["platform"].
    Returns the Facebook post/video id.
    """
    if not os.path.exists(video_path):
        raise Exception(f"Facebook upload: file not found: {video_path}")

    page_id, token = get_fb_credentials(channel)
    if not page_id or not token:
        raise Exception(
            "Facebook credentials not configured. Set FACEBOOK_PAGE_ID and "
            "FACEBOOK_PAGE_ACCESS_TOKEN (GitHub secrets or env vars)."
        )

    raw_title = metadata.get("title", "Gaming Highlight")
    # Facebook has no "#shorts" convention; strip it for cleanliness.
    title = raw_title.replace("#shorts", "").replace("#Shorts", "").strip() or "Gaming Highlight"

    description = metadata.get("description", "")
    if isinstance(metadata.get("hashtags"), list):
        description += "\n\n" + " ".join(metadata["hashtags"])
    elif isinstance(metadata.get("hashtags"), str):
        description += "\n\n" + metadata["hashtags"]
    description += "\n\n#gaming #minecraft #shorts" if is_short else "\n\n#gaming #minecraft"

    kind = "Short/Reel" if is_short else "video"
    logging.info(f"[*] Uploading {video_path} to Facebook Page {page_id} ({kind})...")

    try:
        post_id = _post_video(page_id, token, video_path, title, description,
                              is_short, schedule_time)
        if schedule_time and not is_short:
            logging.info(f"[+] Facebook video scheduled (post id {post_id}) for {schedule_time.strftime('%Y-%m-%d %H:%M')} UTC")
        else:
            logging.info(f"[+] Facebook {kind} published (post id {post_id})")
        return post_id
    except Exception as e:
        # Reels can't be scheduled; if a scheduled *video* call failed for a
        # scheduling reason, retry immediately so the content still goes out.
        if schedule_time and not is_short:
            logging.warning(f"[!] Facebook scheduled upload failed ({e}); retrying as immediate publish...")
            return _post_video(page_id, token, video_path, title, description,
                               is_short, None)
        raise
