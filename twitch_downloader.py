import os
import re
import time
import logging
import requests
import yt_dlp
from config import RAW_VIDEOS_DIR, get_ffmpeg_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def get_direct_cdn_mp4_url(thumbnail_url):
    """
    Derives the direct Twitch CDN MP4 video URL from a clip's thumbnail_url.
    Example:
    'https://clips-media-assets2.twitch.tv/AT-cm%7C123456-preview-480x272.jpg'
    -> 'https://clips-media-assets2.twitch.tv/AT-cm%7C123456.mp4'
    """
    if not thumbnail_url:
        return None
    # Strip preview dimensions (-preview-480x272.jpg or -preview.jpg)
    mp4_url = re.sub(r"-preview(-\d+x\d+)?\.(jpg|png|jpeg)$", ".mp4", thumbnail_url)
    if mp4_url != thumbnail_url and mp4_url.endswith(".mp4"):
        return mp4_url
    return None

def download_file_http(url, out_path, retries=3):
    """Downloads an MP4 file directly via HTTP stream with retries."""
    for attempt in range(1, retries + 1):
        try:
            logging.info(f"[*] HTTP Downloading from CDN (Attempt {attempt}): {url}")
            res = requests.get(url, stream=True, timeout=30)
            res.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in res.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 100000:
                return True
        except Exception as e:
            logging.warning(f"[!] HTTP download attempt {attempt} failed: {e}")
            time.sleep(2)
    return False

def download_twitch_clip(video_data):
    """
    Downloads a Twitch clip MP4 and saves it to RAW_VIDEOS_DIR.
    video_data: dict with 'video_id', 'url', 'thumbnail_url'
    Returns absolute path to downloaded MP4 file or None on failure.
    """
    if not os.path.exists(RAW_VIDEOS_DIR):
        os.makedirs(RAW_VIDEOS_DIR, exist_ok=True)

    if isinstance(video_data, str):
        clip_id = video_data
        clip_url = f"https://clips.twitch.tv/{clip_id}"
        thumbnail_url = None
    else:
        clip_id = video_data.get("video_id")
        clip_url = video_data.get("url", f"https://clips.twitch.tv/{clip_id}")
        thumbnail_url = video_data.get("thumbnail_url")

    out_file = os.path.join(RAW_VIDEOS_DIR, f"{clip_id}.mp4")

    # Method 1: Direct Twitch CDN Fast Download
    direct_mp4 = get_direct_cdn_mp4_url(thumbnail_url)
    if direct_mp4:
        if download_file_http(direct_mp4, out_file):
            logging.info(f"[+] Successfully downloaded Twitch clip via CDN: {out_file}")
            return out_file

    # Method 2: Fallback yt-dlp Native Twitch Extractor
    logging.info(f"[*] Fallback yt-dlp downloading Twitch clip: {clip_url}")
    out_tmpl = os.path.join(RAW_VIDEOS_DIR, f"{clip_id}.%(ext)s")

    ydl_opts = {
        'format': 'best',
        'outtmpl': out_tmpl,
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
        'retries': 5,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clip_url, download=True)
            base_filename = ydl.prepare_filename(info)
            final_filename = base_filename.rsplit('.', 1)[0] + '.mp4'
            if os.path.exists(final_filename):
                logging.info(f"[+] Downloaded Twitch clip via yt-dlp: {final_filename}")
                return final_filename
            elif os.path.exists(base_filename):
                return base_filename
    except Exception as e:
        logging.error(f"[!] Error downloading Twitch clip {clip_id}: {e}")

    return None

if __name__ == "__main__":
    test_clip = {"video_id": "AwkwardImportantPloverTTours", "url": "https://clips.twitch.tv/AwkwardImportantPloverTTours"}
    res = download_twitch_clip(test_clip)
    print("Download result:", res)
