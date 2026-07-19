import os
import sys
import time
import argparse
import logging
from datetime import datetime
from config import RAW_VIDEOS_DIR, PROCESSED_DIR, MAX_UPLOADS_PER_DAY
from twitch_finder import find_twitch_clips, mark_video_seen
from twitch_downloader import download_twitch_clip
from audio_analyzer import analyze_audio
from highlight_detector import get_highlights
from video_processor import process_video
from metadata_generator import generate_metadata
from youtube_uploader import upload_short, get_upload_count_today, get_authenticated_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def cleanup_disk():
    """Cleans up temporary downloaded and processed video files to preserve storage."""
    logging.info("[*] Cleaning up temporary video files...")
    for folder in [RAW_VIDEOS_DIR, PROCESSED_DIR]:
        if os.path.exists(folder):
            for filename in os.listdir(folder):
                if filename.startswith('.'): 
                    continue
                file_path = os.path.join(folder, filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    logging.warning(f"Failed to delete {file_path}: {e}")

def run_single_trigger():
    """
    Executes 1 scheduled trigger cycle:
    1. Searches Twitch API for trending clips in game categories.
    2. Downloads candidate clip MP4 into RAW_VIDEOS_DIR.
    3. Analyzes audio for voice/silence.
    4. Detects highlights & renders 9:16 vertical 1080p Short (< 45s).
    5. Generates AI metadata & uploads Short to YouTube.
    6. Cleans up temporary disk files and exits cleanly.
    """
    print(f"\n--- Starting Scheduled Action Trigger at {datetime.utcnow().isoformat()} UTC ---")
    
    uploads_today = get_upload_count_today()
    logging.info(f"[*] Total uploads recorded today: {uploads_today}/{MAX_UPLOADS_PER_DAY}")
    
    if uploads_today >= MAX_UPLOADS_PER_DAY:
        logging.info(f"[!] Daily quota limit reached ({uploads_today}/{MAX_UPLOADS_PER_DAY}). Exiting gracefully.")
        return True

    videos = find_twitch_clips()
    if not videos:
        logging.warning("[-] No suitable unseen clips found on Twitch.")
        return False
        
    uploaded = False
    for video in videos:
        logging.info(f"\n>>> Processing Candidate: {video['title']} (ID: {video['video_id']}) [{video['game_name']}]")
        time.sleep(2)
        
        # 1. Download Twitch Clip
        video_path = download_twitch_clip(video)
        if not video_path:
            mark_video_seen(video['video_id'])
            continue
            
        # 2. Analyze Audio
        has_voice, is_silent = analyze_audio(video_path)
        mute_audio = False
        if has_voice:
            logging.info("[!] Voice detected. Original audio will be muted.")
            mute_audio = True
        elif is_silent:
            logging.info("[!] Audio is silent. BGM will be added.")
            mute_audio = True
        else:
            logging.info("[+] Clear game audio found. Preserving game audio with BGM.")
            
        # 3. Highlight Detection
        highlights = get_highlights(video_path, num_clips=1)
        if not highlights:
            logging.info("[-] No exciting highlights found.")
            mark_video_seen(video['video_id'])
            cleanup_disk()
            continue
            
        scene = highlights[0]
        
        # 4. Process into YouTube Short
        out_filename = f"short_{video['video_id']}.mp4"
        processed_path = process_video(
            video_path, 
            scene['start'], 
            scene['end'], 
            out_filename, 
            mute_original=mute_audio
        )
        
        if not processed_path or not os.path.exists(processed_path):
            logging.error("[!] Video processing failed.")
            mark_video_seen(video['video_id'])
            cleanup_disk()
            continue
            
        # 5. Metadata Generation
        metadata = generate_metadata(video['title'])
        
        # 6. Upload Short to YouTube
        try:
            upload_short(processed_path, metadata)
            logging.info(f"[+] Successfully uploaded Twitch clip {video['video_id']} to YouTube Shorts!")
            uploaded = True
        except Exception as e:
            logging.error(f"[!] Upload failed: {e}")
            
        mark_video_seen(video['video_id'])
        cleanup_disk()
        
        if uploaded:
            break

    print(f"--- Trigger Execution Finished (Uploaded: {uploaded}) ---")
    return uploaded

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Twitch to YouTube Shorts Automation Pipeline")
    parser.add_argument("--loop", action="store_true", help="Run continuously in 24/7 loop mode instead of single trigger mode")
    args = parser.parse_args()

    print("🤖 Twitch to YouTube Shorts Automation Bot Initiated 🤖")
    
    # Authenticate YouTube service for uploading
    logging.info("[*] Verifying YouTube Uploader Credentials...")
    try:
        get_authenticated_service()
        logging.info("[+] YouTube Authentication Successful!")
    except Exception as e:
        logging.error(f"[!] YouTube Authentication failed: {e}")
        sys.exit(1)

    if args.loop:
        logging.info("[*] Running in continuous loop mode...")
        while True:
            try:
                run_single_trigger()
                logging.info("[*] Sleeping 3 hours until next cycle...")
                time.sleep(10800)
            except Exception as e:
                logging.error(f"[!] Pipeline crashed: {e}")
                time.sleep(300)
    else:
        logging.info("[*] Running single trigger mode (1 Short upload per trigger execution)...")
        run_single_trigger()
        sys.exit(0)
