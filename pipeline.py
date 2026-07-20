import os
import sys
import time
import argparse
import logging
from datetime import datetime, timedelta, timezone
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

def run_single_trigger(target_uploads=6, interval_hours=2):
    """
    Executes 1 daily batch run:
    Fetches Twitch clips, processes them into Shorts, and uploads `target_uploads` Shorts in 1 single execution.
    Schedules each video with a minimum gap of `interval_hours` (2 hours) apart on YouTube!
    """
    now_utc = datetime.now(timezone.utc)
    print(f"\n--- Starting Scheduled Daily Batch Automation ({target_uploads} Shorts, {interval_hours}h Spacing) at {now_utc.isoformat()} ---")
    
    uploads_today = get_upload_count_today()
    logging.info(f"[*] Total uploads recorded today prior to run: {uploads_today}/{MAX_UPLOADS_PER_DAY}")
    
    if uploads_today >= MAX_UPLOADS_PER_DAY:
        logging.info(f"[!] Daily quota limit reached ({uploads_today}/{MAX_UPLOADS_PER_DAY}). Exiting gracefully.")
        return True

    videos = find_twitch_clips()
    if not videos:
        logging.warning("[-] No suitable unseen clips found on Twitch.")
        return False

    # First scheduled video releases 2 hours after batch creation time
    base_publish_time = now_utc + timedelta(hours=interval_hours)
        
    uploaded_count = 0
    for video in videos:
        if uploaded_count >= target_uploads:
            logging.info(f"[+] Target batch goal of {target_uploads} scheduled Shorts achieved for today!")
            break

        logging.info(f"\n>>> Processing Candidate [{uploaded_count + 1}/{target_uploads}]: {video['title']} (ID: {video['video_id']}) [{video['game_name']}]")
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
        
        # 4. Process into YouTube Short (9:16 vertical 1080p)
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
        
        # 6. Calculate Scheduled Publish Time (2 Hours Gap per Video)
        scheduled_time = base_publish_time + timedelta(hours=uploaded_count * interval_hours)
        
        # 7. Upload & Schedule Short on YouTube
        try:
            upload_short(processed_path, metadata, schedule_time=scheduled_time)
            uploaded_count += 1
            logging.info(f"[+] ({uploaded_count}/{target_uploads}) Successfully uploaded & scheduled Twitch clip {video['video_id']} for release at {scheduled_time.strftime('%H:%M')} UTC!")
        except Exception as e:
            logging.error(f"[!] Upload failed: {e}")
            
        mark_video_seen(video['video_id'])
        cleanup_disk()
        
        # Sleep 5 seconds between batch uploads
        time.sleep(5)

    print(f"--- Daily Scheduled Batch Trigger Finished (Total Shorts Scheduled: {uploaded_count}) ---")
    return uploaded_count > 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Twitch to YouTube Shorts Scheduled Automation Pipeline")
    parser.add_argument("--count", type=int, default=6, help="Number of Shorts to generate and schedule in one daily batch run (default: 6)")
    parser.add_argument("--gap", type=int, default=2, help="Minimum gap in hours between scheduled video releases (default: 2)")
    parser.add_argument("--loop", action="store_true", help="Run continuously in 24/7 loop mode instead of single trigger mode")
    args = parser.parse_args()

    print("🤖 Twitch to YouTube Shorts Scheduled Automation Bot Initiated 🤖")
    
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
                run_single_trigger(target_uploads=args.count, interval_hours=args.gap)
                logging.info("[*] Sleeping 24 hours until next daily batch cycle...")
                time.sleep(86400)
            except Exception as e:
                logging.error(f"[!] Pipeline crashed: {e}")
                time.sleep(300)
    else:
        logging.info(f"[*] Running daily scheduled batch mode ({args.count} Shorts, {args.gap}h gap)...")
        run_single_trigger(target_uploads=args.count, interval_hours=args.gap)
        sys.exit(0)
