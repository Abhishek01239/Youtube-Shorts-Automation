import os
import yt_dlp
from config import RAW_VIDEOS_DIR, get_ffmpeg_path

def download_video(video_id):
    """Downloads a video in best quality up to 4K."""
    if not os.path.exists(RAW_VIDEOS_DIR):
        os.makedirs(RAW_VIDEOS_DIR, exist_ok=True)
        
    out_tmpl = os.path.join(RAW_VIDEOS_DIR, f"{video_id}.%(ext)s")
    
    ydl_opts = {
        'format': 'bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': out_tmpl,
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'mweb', 'tv']
            }
        },
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
    }
    
    cookies_path = 'cookies.txt'
    if os.path.exists(cookies_path):
        try:
            with open(cookies_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            # Only use cookie file if it contains actual login/session cookies
            if any(k in content for k in ['SID', 'LOGIN_INFO', '__Secure-3PAPISID', '__Secure-1PAPISID']):
                ydl_opts['cookiefile'] = cookies_path
        except Exception:
            pass

    # If local ffmpeg dir exists, specify it, otherwise yt-dlp uses system ffmpeg
    local_ffmpeg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ffmpeg', 'bin')
    if os.path.exists(local_ffmpeg_dir):
        ydl_opts['ffmpeg_location'] = local_ffmpeg_dir
    
    print(f"[*] Downloading {video_id} in up to 4K...")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
            base_filename = ydl.prepare_filename(info)
            final_filename = base_filename.rsplit('.', 1)[0] + '.mp4'
            
            if os.path.exists(final_filename):
                return final_filename
            elif os.path.exists(base_filename):
                return base_filename
            return None
    except Exception as e:
        print(f"[!] Error downloading {video_id}: {e}")
        return None
