import os
import sys
import time
import argparse
from datetime import datetime, timedelta
from config import RAW_VIDEOS_DIR, PROCESSED_DIR, MAX_UPLOADS_PER_DAY
from video_finder import find_videos, mark_video_seen
from downloader import download_video
from audio_analyzer import analyze_audio
from highlight_detector import get_highlights
from video_processor import process_video
from metadata_generator import generate_metadata
from youtube_uploader import upload_short, get_upload_count_today, get_authenticated_service

def cleanup_disk():
    """Cleans up temporary downloaded and processed video files to preserve storage."""
    print("[*] Cleaning up temporary video files...")
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
                    print(f"Failed to delete {file_path}: {e}")

def run_single_trigger():
    """
    Executes 1 trigger cycle:
    1. Finds candidate video
    2. Downloads & analyzes audio
    3. Detects highlight & renders Short
    4. Uploads 1 video to YouTube
    5. Cleans up disk space and exits cleanly
    """
    print(f"\n--- Starting Scheduled Action Trigger at {datetime.utcnow().isoformat()} UTC ---")
    
    uploads_today = get_upload_count_today()
    print(f"[*] Total uploads recorded today: {uploads_today}/{MAX_UPLOADS_PER_DAY}")
    
    if uploads_today >= MAX_UPLOADS_PER_DAY:
        print(f"[!] Daily quota limit reached ({uploads_today}/{MAX_UPLOADS_PER_DAY}). Exiting gracefully.")
        return True

    videos = find_videos()
    if not videos:
        print("[-] No suitable unseen videos found in target niches.")
        return False
        
    uploaded = False
    for video in videos:
        print(f"\n>>> Processing Candidate: {video['title']} (ID: {video['video_id']})")
        time.sleep(3) # Human-like throttle delay to prevent IP rate-limiting
        
        # 1. Download
        video_path = download_video(video['video_id'])
        if not video_path:
            mark_video_seen(video['video_id'])
            continue
            
        # 2. Analyze Audio
        has_voice, is_silent = analyze_audio(video_path)
        mute_audio = False
        if has_voice:
            print("[!] Voice detected. Original audio will be muted.")
            mute_audio = True
        elif is_silent:
            print("[!] Audio is silent. BGM will be added.")
            mute_audio = True
        else:
            print("[+] Clear game audio found. Preserving game audio with BGM.")
            
        # 3. Highlight Detection
        highlights = get_highlights(video_path, num_clips=1)
        if not highlights:
            print("[-] No exciting highlights found.")
            mark_video_seen(video['video_id'])
            cleanup_disk()
            continue
            
        scene = highlights[0]
        
        # 4. Process Short
        out_filename = f"short_{video['video_id']}.mp4"
        processed_path = process_video(
            video_path, 
            scene['start'], 
            scene['end'], 
            out_filename, 
            mute_original=mute_audio
        )
        
        if not processed_path or not os.path.exists(processed_path):
            print("[!] Processing failed.")
            mark_video_seen(video['video_id'])
            cleanup_disk()
            continue
            
        # 5. Metadata Generation
        metadata = generate_metadata(video['title'])
        
        # 6. Upload to YouTube
        try:
            upload_short(processed_path, metadata)
            print(f"[+] Successfully uploaded video {video['video_id']} to YouTube!")
            uploaded = True
        except Exception as e:
            print(f"[!] Upload failed: {e}")
            
        mark_video_seen(video['video_id'])
        cleanup_disk()
        
        if uploaded:
            # Uploaded 1 video for this scheduled trigger run! Exit trigger loop.
            break

    print(f"--- Trigger Execution Finished (Uploaded: {uploaded}) ---")
    return uploaded

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YouTube Shorts Automation Pipeline")
    parser.add_argument("--loop", action="store_true", help="Run continuously in 24/7 loop mode instead of single trigger mode")
    args = parser.parse_args()

    print("🤖 YouTube Shorts Automation Bot Initiated 🤖")
    
    # Authenticate YouTube service
    print("[*] Verifying YouTube Credentials...")
    try:
        get_authenticated_service()
        print("[+] YouTube Authentication Successful!")
    except Exception as e:
        print(f"[!] Authentication failed: {e}")
        sys.exit(1)

    if args.loop:
        print("[*] Running in continuous loop mode...")
        while True:
            try:
                run_single_trigger()
                print("[*] Sleeping 3 hours until next cycle...")
                time.sleep(10800) # 3 hours
            except Exception as e:
                print(f"[!] Pipeline crashed: {e}")
                time.sleep(300)
    else:
        # Single-run mode for GitHub Actions trigger
        print("[*] Running single trigger mode (1 video upload per trigger execution)...")
        run_single_trigger()
        sys.exit(0)
