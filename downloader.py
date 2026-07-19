import os
import yt_dlp
from config import RAW_VIDEOS_DIR, get_ffmpeg_path

def download_video(video_id):
    """Downloads a public video in best quality up to 1080p/4K with mobile player client fallbacks."""
    if not os.path.exists(RAW_VIDEOS_DIR):
        os.makedirs(RAW_VIDEOS_DIR, exist_ok=True)
        
    out_tmpl = os.path.join(RAW_VIDEOS_DIR, f"{video_id}.%(ext)s")
    
    ydl_opts_base = {
        'format': 'bestvideo[height<=1080]+bestaudio/best',
        'outtmpl': out_tmpl,
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'mweb']
            }
        }
    }
    
    local_ffmpeg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ffmpeg', 'bin')
    if os.path.exists(local_ffmpeg_dir):
        ydl_opts_base['ffmpeg_location'] = local_ffmpeg_dir
        
    # Attempt 1: iOS & Android Mobile Clients (bypasses cloud IP bot detection)
    print(f"[*] Downloading {video_id} (Attempt 1: Mobile player clients)...")
    try:
        with yt_dlp.YoutubeDL(ydl_opts_base) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
            base_filename = ydl.prepare_filename(info)
            final_filename = base_filename.rsplit('.', 1)[0] + '.mp4'
            if os.path.exists(final_filename):
                return final_filename
            elif os.path.exists(base_filename):
                return base_filename
    except Exception as e:
        print(f"[!] Attempt 1 failed for {video_id}: {e}")

    # Attempt 2: TV & Web Embedded fallback
    opts_fallback = dict(ydl_opts_base)
    opts_fallback['extractor_args'] = {
        'youtube': {
            'player_client': ['tv', 'web_embedded']
        }
    }
    print(f"[*] Downloading {video_id} (Attempt 2: TV & Web fallback)...")
    try:
        with yt_dlp.YoutubeDL(opts_fallback) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
            base_filename = ydl.prepare_filename(info)
            final_filename = base_filename.rsplit('.', 1)[0] + '.mp4'
            if os.path.exists(final_filename):
                return final_filename
            elif os.path.exists(base_filename):
                return base_filename
    except Exception as e:
        print(f"[!] Attempt 2 failed for {video_id}: {e}")

    # Attempt 3: Try cookies if cookies.txt is provided and valid
    cookies_path = 'cookies.txt'
    if os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 10:
        opts_cookies = dict(ydl_opts_base)
        opts_cookies.pop('extractor_args', None)
        opts_cookies['cookiefile'] = cookies_path
        print(f"[*] Downloading {video_id} (Attempt 3: with cookies)...")
        try:
            with yt_dlp.YoutubeDL(opts_cookies) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
                base_filename = ydl.prepare_filename(info)
                final_filename = base_filename.rsplit('.', 1)[0] + '.mp4'
                if os.path.exists(final_filename):
                    return final_filename
                elif os.path.exists(base_filename):
                    return base_filename
        except Exception as e:
            print(f"[!] Attempt 3 failed for {video_id}: {e}")

    return None
