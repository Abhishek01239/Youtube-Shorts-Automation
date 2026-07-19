import os
import subprocess
import logging
from config import get_ffmpeg_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def crop_facecam(video_path, corner):
    """
    Crops out the detected streamer facecam box using FFmpeg while keeping gameplay centered.
    corner: 'top-left', 'top-right', 'bottom-left', or 'bottom-right'
    Returns path to cropped video or None if cropping fails.
    """
    if not corner:
        logging.info("[*] No facecam corner specified. Returning original video.")
        return video_path

    if not os.path.exists(video_path):
        logging.error(f"[!] Video file not found for facecam cropping: {video_path}")
        return None

    out_path = video_path.rsplit('.', 1)[0] + "_nocam.mp4"
    logging.info(f"[*] Removing facecam ({corner}) from video: {os.path.basename(video_path)}")

    # FFmpeg crop filters according to corner location
    # iw = input width, ih = input height
    crop_filters = {
        "top-left": "crop=iw*0.82:ih:iw*0.18:0",      # Slice off top-left 18%
        "top-right": "crop=iw*0.82:ih:0:0",            # Slice off top-right 18%
        "bottom-left": "crop=iw*0.82:ih*0.82:iw*0.18:0", # Slice off bottom-left
        "bottom-right": "crop=iw*0.82:ih*0.82:0:0"     # Slice off bottom-right
    }

    filter_str = crop_filters.get(corner, "crop=iw*0.82:ih:0:0")
    ffmpeg_cmd = get_ffmpeg_path()

    cmd = [
        ffmpeg_cmd, "-y",
        "-i", video_path,
        "-vf", filter_str,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "copy",
        out_path
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            logging.info(f"[+] Facecam successfully removed! Saved cropped video: {out_path}")
            return out_path
        else:
            logging.error(f"[!] FFmpeg crop failed: {res.stderr}")
            return None
    except Exception as e:
        logging.error(f"[!] Error cropping facecam: {e}")
        return None

if __name__ == "__main__":
    import sys
    test_file = sys.argv[1] if len(sys.argv) > 1 else "data/raw_videos/test.mp4"
    res = crop_facecam(test_file, "top-left")
    print("FACE CROP RESULT:", res)
