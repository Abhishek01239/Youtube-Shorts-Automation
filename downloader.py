import os
import yt_dlp
from config import RAW_VIDEOS_DIR, get_ffmpeg_path

def download_video(video_id):
    """Downloads a public video in best quality up to 1080p with AAC audio stream conversion & retry logic."""
    if not os.path.exists(RAW_VIDEOS_DIR):
        os.makedirs(RAW_VIDEOS_DIR, exist_ok=True)
        
    out_tmpl = os.path.join(RAW_VIDEOS_DIR, f"{video_id}.%(ext)s")
    
    ydl_opts = {
        'format': 'bestvideo[height<=1080][vcodec!=none]+bestaudio[acodec!=none]/bestvideo[height<=1080]+bestaudio/best[ext=mp4]/best',
        'outtmpl': out_tmpl,
        'merge_output_format': 'mp4',
        'postprocessor_args': {
            'ffmpeg': ['-c:v', 'copy', '-c:a', 'aac']
        },
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
        'retries': 10,
        'fragment_retries': 10,
        'file_access_retries': 5,
        'concurrent_fragment_downloads': 4,
    }
    
    local_ffmpeg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ffmpeg', 'bin')
    if os.path.exists(local_ffmpeg_dir):
        ydl_opts['ffmpeg_location'] = local_ffmpeg_dir
        
    print(f"[*] Downloading {video_id}...")
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
