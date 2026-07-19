import os
import time
import yt_dlp
from config import RAW_VIDEOS_DIR, BASE_DIR, get_ffmpeg_path

def download_video(video_id):
    """
    Downloads a public video using multi-stage client fallback endpoints 
    with cookie authentication logging & verbose diagnostics.
    """
    if not os.path.exists(RAW_VIDEOS_DIR):
        os.makedirs(RAW_VIDEOS_DIR, exist_ok=True)
        
    out_tmpl = os.path.join(RAW_VIDEOS_DIR, f"{video_id}.%(ext)s")
    
    ydl_opts_base = {
        'format': 'bestvideo[height<=1080]+bestaudio/best',
        'outtmpl': out_tmpl,
        'merge_output_format': 'mp4',
        'postprocessor_args': {
            'ffmpeg': ['-strict', 'experimental', '-c:v', 'copy', '-c:a', 'aac']
        },
        'quiet': False,
        'no_warnings': False,
        'verbose': True,
        'socket_timeout': 30,
        'retries': 10,
        'fragment_retries': 10,
        'file_access_retries': 5,
        'concurrent_fragment_downloads': 4,
        'sleep_interval': 2,
        'max_sleep_interval': 4,
    }
    
    local_ffmpeg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ffmpeg', 'bin')
    if os.path.exists(local_ffmpeg_dir):
        ydl_opts_base['ffmpeg_location'] = local_ffmpeg_dir
        
    cookies_env = os.getenv("COOKIES_PATH")
    if cookies_env and os.path.exists(cookies_env):
        cookies_path = os.path.abspath(cookies_env)
    else:
        cookies_path = os.path.join(BASE_DIR, "cookies.txt")

    has_cookies = os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 10

    print("=== COOKIES DIAGNOSTIC INFO ===")
    print("Cookie file:", cookies_path)
    print("Exists:", os.path.exists(cookies_path))
    if os.path.exists(cookies_path):
        print("Size (bytes):", os.path.getsize(cookies_path))
    print("===============================")

    stages = [
        ("Android VR & Mobile API", ['android_vr', 'android'], True),
        ("iOS & Mobile Web API", ['ios', 'mweb'], True),
        ("Standard Client", ['web', 'mweb'], True)
    ]

    for stage_name, clients, use_cookies in stages:
        print(f"\n[*] Downloading {video_id} ({stage_name})...")
        opts = dict(ydl_opts_base)
        if use_cookies and has_cookies:
            opts['cookiefile'] = cookies_path
            
        opts['extractor_args'] = {'youtube': {'player_client': clients}}
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
                base_filename = ydl.prepare_filename(info)
                final_filename = base_filename.rsplit('.', 1)[0] + '.mp4'
                if os.path.exists(final_filename):
                    print(f"[+] Download succeeded via {stage_name}!")
                    return final_filename
                elif os.path.exists(base_filename):
                    print(f"[+] Download succeeded via {stage_name}!")
                    return base_filename
        except Exception as e:
            print(f"[!] {stage_name} attempt failed: {e}")
            time.sleep(2)
            continue

    return None
