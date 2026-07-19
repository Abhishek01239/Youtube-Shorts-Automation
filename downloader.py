import os
import yt_dlp
from config import RAW_VIDEOS_DIR, get_ffmpeg_path

def download_video(video_id):
    """Downloads a video with extractor player_client fallbacks to bypass YouTube bot detection."""
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
                'player_client': ['android', 'ios', 'mweb']
            }
        }
    }
    
    local_ffmpeg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ffmpeg', 'bin')
    if os.path.exists(local_ffmpeg_dir):
        ydl_opts_base['ffmpeg_location'] = local_ffmpeg_dir
        
    # Attempt 1: Mobile player_client API without cookies (bypasses bot check on cloud IP)
    print(f"[*] Downloading {video_id} (Attempt 1: mobile player clients)...")
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
        print(f"[!] Mobile client attempt failed: {e}. Trying cookies...")

    # Attempt 2: Try with cookies if cookies.txt exists
    cookies_path = 'cookies.txt'
    if os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 10:
        opts_with_cookies = dict(ydl_opts_base)
        opts_with_cookies['cookiefile'] = cookies_path
        print(f"[*] Downloading {video_id} (Attempt 2: with cookies)...")
        try:
            with yt_dlp.YoutubeDL(opts_with_cookies) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
                base_filename = ydl.prepare_filename(info)
                final_filename = base_filename.rsplit('.', 1)[0] + '.mp4'
                if os.path.exists(final_filename):
                    return final_filename
                elif os.path.exists(base_filename):
                    return base_filename
        except Exception as e:
            print(f"[!] Cookie attempt failed: {e}")

    return None
