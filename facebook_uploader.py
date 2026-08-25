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
    Because Facebook's simple /videos upload rejects large files
    (HTTP 413 "Request Entity Too Large"), long-form videos use the
    RESUMABLE (chunked) upload endpoint, which has a much higher limit.
  - Shorts / vertical clips: small files, so the simple /videos upload is
    fine. Facebook does NOT support scheduling Reels via the Graph API,
    so they are published immediately (published=true).
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

# Above this size we switch to the resumable (chunked) upload endpoint,
# which avoids Facebook's 413 "Request Entity Too Large" on big files.
RESUMABLE_THRESHOLD = 80 * 1024 * 1024  # 80 MB
CHUNK_SIZE = 4 * 1024 * 1024            # 4 MB per chunk (FB allows up to 8 MB)


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


def _raise_for_error(resp, params_hint=""):
    """Turn a non-200 Graph response into an actionable Exception."""
    data = resp.json() if resp.content else {}
    if resp.status_code == 200 and "id" in data:
        return data["id"]
    err = data.get("error", {}) if isinstance(data, dict) else {}
    code = err.get("code")
    subcode = err.get("error_subcode")
    if code == 190 and subcode == 463:
        raise Exception(
            "Facebook token EXPIRED (code 190/subcode 463). The FACEBOOK_PAGE_ACCESS_TOKEN "
            "secret holds a short-lived token. Regenerate a LONG-LIVED Page Access Token "
            "(~60 days) and update the GitHub secret 'FACEBOOK_PAGE_ACCESS_TOKEN'."
        )
    if code == 190:
        raise Exception(
            "Facebook token invalid (code 190). Check FACEBOOK_PAGE_ACCESS_TOKEN / FACEBOOK_PAGE_ID."
        )
    raise Exception(f"Facebook API {resp.status_code}: {data}")


def _post_video_simple(page_id, access_token, video_path, title, description,
                       is_short, schedule_time=None):
    """Simple /videos upload (best for small files: shorts/reels)."""
    params = {
        "access_token": access_token,
        "title": title[:255],
        "description": description,
        "published": "false" if (schedule_time and not is_short) else "true",
    }
    if schedule_time and not is_short:
        params["scheduled_publish_time"] = str(int(schedule_time.timestamp()))
    if is_short:
        params["video_reels_publish"] = "true"

    url = f"{GRAPH_BASE}/{page_id}/videos"
    with open(video_path, "rb") as f:
        files = {"source": (os.path.basename(video_path), f, "video/mp4")}
        resp = requests.post(url, data=params, files=files, timeout=900)
    return _raise_for_error(resp)


def _post_video_resumable(page_id, access_token, video_path, title, description,
                          is_short, schedule_time=None):
    """
    Resumable (chunked) upload for LARGE files (compilation videos).

    Steps (Facebook Graph resumable video upload):
      1. POST /{page}/videos?upload_phase=start&access_token=...  -> {upload_session_id, video_id, ...}
      2. POST /{page}/videos?upload_phase=transfer&upload_session_id=...&start_offset=0
         with the file chunk as multipart 'video_file_chunk'  -> {start_offset, end_offset}
      3. Repeat transfer until end_offset == file_size
      4. POST /{page}/videos?upload_phase=finish&upload_session_id=...&title=...&description=...
         [&published=false&scheduled_publish_time=...]  -> {success: true}
    """
    file_size = os.path.getsize(video_path)

    # 1. start
    start = requests.post(
        f"{GRAPH_BASE}/{page_id}/videos",
        data={"access_token": access_token, "upload_phase": "start"},
        timeout=120,
    )
    start_data = start.json() if start.content else {}
    if start.status_code != 200 or "upload_session_id" not in start_data:
        raise Exception(f"Facebook resumable START failed: {start_data}")
    session_id = start_data["upload_session_id"]

    # 2. transfer chunks
    offset = 0
    with open(video_path, "rb") as f:
        while offset < file_size:
            f.seek(offset)
            chunk = f.read(CHUNK_SIZE)
            transfer = requests.post(
                f"{GRAPH_BASE}/{page_id}/videos",
                data={
                    "access_token": access_token,
                    "upload_phase": "transfer",
                    "upload_session_id": session_id,
                    "start_offset": str(offset),
                },
                files={"video_file_chunk": ("chunk", chunk, "application/octet-stream")},
                timeout=900,
            )
            tdata = transfer.json() if transfer.content else {}
            if transfer.status_code != 200 or "end_offset" not in tdata:
                raise Exception(f"Facebook resumable TRANSFER failed at offset {offset}: {tdata}")
            offset = int(tdata["end_offset"])

    # 3. finish
    finish_params = {
        "access_token": access_token,
        "upload_phase": "finish",
        "upload_session_id": session_id,
        "title": title[:255],
        "description": description,
        "published": "false" if (schedule_time and not is_short) else "true",
    }
    if schedule_time and not is_short:
        finish_params["scheduled_publish_time"] = str(int(schedule_time.timestamp()))
    finish = requests.post(
        f"{GRAPH_BASE}/{page_id}/videos",
        data=finish_params,
        timeout=300,
    )
    fdata = finish.json() if finish.content else {}
    if finish.status_code != 200 or not fdata.get("success"):
        # If finish gives a video_id anyway, treat as success.
        if "video_id" in fdata:
            return fdata["video_id"]
        raise Exception(f"Facebook resumable FINISH failed: {fdata}")
    return fdata.get("video_id") or session_id


def _post_video(page_id, access_token, video_path, title, description,
                is_short, schedule_time=None):
    """Pick upload strategy by file size; fall back simple->resumable on 413."""
    file_size = os.path.getsize(video_path)
    if file_size > RESUMABLE_THRESHOLD:
        try:
            return _post_video_resumable(page_id, access_token, video_path,
                                          title, description, is_short, schedule_time)
        except Exception as e:
            if "413" in str(e):
                # Already resumable but still too large? nothing more we can do.
                raise
            # Non-413 resumable error: try the simple endpoint as a last resort.
            logging.warning(f"[!] Facebook resumable upload failed ({e}); trying simple upload...")
            return _post_video_simple(page_id, access_token, video_path,
                                      title, description, is_short, schedule_time)
    # Small file: simple upload, upgrade to resumable if we hit 413.
    try:
        return _post_video_simple(page_id, access_token, video_path,
                                  title, description, is_short, schedule_time)
    except Exception as e:
        if "413" in str(e) or "Request Entity Too Large" in str(e):
            logging.warning("[!] Facebook simple upload 413 (file too large); switching to resumable...")
            return _post_video_resumable(page_id, access_token, video_path,
                                         title, description, is_short, schedule_time)
        raise


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

    # Strip any "#shorts"/"#Shorts" from incoming hashtags too (FB has no such tag).
    def _clean_tags(t):
        return " ".join(w for w in t.split() if w.lower() != "#shorts")

    description = metadata.get("description", "")
    if isinstance(metadata.get("hashtags"), list):
        description += "\n\n" + _clean_tags(" ".join(metadata["hashtags"]))
    elif isinstance(metadata.get("hashtags"), str):
        description += "\n\n" + _clean_tags(metadata["hashtags"])
    # Facebook has no #shorts tag convention; use neutral gaming tags.
    description += "\n\n#gaming #minecraft #reels" if is_short else "\n\n#gaming #minecraft"

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
