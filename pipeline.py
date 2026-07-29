import os
import sys
import time
import json
import argparse
import logging
from datetime import datetime, timezone, timedelta
import config
from twitch_finder import find_twitch_clips, mark_video_seen as mark_twitch_seen
from twitch_downloader import download_twitch_clip
from video_finder import find_videos, find_playlist_videos, mark_video_seen as mark_youtube_seen
from downloader import download_video
from audio_analyzer import analyze_audio
from highlight_detector import get_highlights
from video_processor import process_video
from metadata_generator import generate_metadata
from youtube_uploader import upload_short, get_upload_count_today
from notifier import notify_report


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def cleanup_disk():
    """Cleans up temporary downloaded and processed video files to preserve storage."""
    logging.info("[*] Cleaning up temporary video files...")
    raw_dir = config.get_raw_videos_dir()
    processed_dir = config.get_processed_dir()
    for folder in [raw_dir, processed_dir]:
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

def run_channel_pipeline(channel, default_count=6, default_gap=2):
    channel_name = channel["channel_name"]
    niche = channel.get("niche", "gaming")
    shorts_per_run = channel.get("shorts_per_run", default_count)
    
    # Resolve schedule
    schedule_config = channel.get("upload_schedule", {})
    interval_hours = schedule_config.get("interval_hours", default_gap)
    
    # Set the active channel in config to isolate paths
    config.set_active_channel(channel_name)
    
    # 1. Handle credentials setup
    creds_config = channel.get("youtube_oauth_credentials")
    token_info = None
    token_path = None
    
    if isinstance(creds_config, dict):
        # Inline token content: Write it to the channel's dynamic token file path if not already present
        token_path = config.get_token_file()
        if not os.path.exists(token_path):
            parent_dir = os.path.dirname(os.path.abspath(token_path))
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(token_path, "w", encoding="utf-8") as f:
                json.dump(creds_config, f, indent=4)
        token_info = creds_config
    elif isinstance(creds_config, str):
        # A filepath to the token
        token_path = creds_config
    else:
        # Fallback to default
        token_path = config.get_token_file()
        
    logging.info(f"\n==================================================")
    logging.info(f"[*] Starting Pipeline for Channel: {channel_name}")
    logging.info(f"Niche: {niche} | Target: {shorts_per_run} Shorts | Interval: {interval_hours}h")
    logging.info(f"==================================================")
    
    # 2. Check upload quota today
    uploads_today = get_upload_count_today()
    logging.info(f"[*] Total uploads recorded today prior to run for '{channel_name}': {uploads_today}/{config.MAX_UPLOADS_PER_DAY}")
    if uploads_today >= config.MAX_UPLOADS_PER_DAY:
        logging.info(f"[!] Daily quota limit reached ({uploads_today}/{config.MAX_UPLOADS_PER_DAY}). Skipping upload phase.")
        return {
            "channel_name": channel_name,
            "shorts_created": 0,
            "uploads": [],
            "status": "Skipped (Quota reached)",
            "error": None
        }
        
    # 3. Sourcing videos
    source_config = channel.get("source_configuration", {})
    source_type = source_config.get("source_type", "twitch").lower()
    
    videos = []
    if source_type == "twitch":
        target_games = source_config.get("target_games")
        videos = find_twitch_clips(target_games=target_games)
    elif source_type == "youtube_search" or source_type == "youtube_api":
        query = source_config.get("query", niche)
        max_subs = source_config.get("max_subs", 100000)
        videos = find_videos(niche_query=query, max_subs=max_subs)
    elif source_type == "youtube_playlist":
        playlist_id = source_config.get("playlist_id")
        if playlist_id:
            videos = find_playlist_videos(playlist_id=playlist_id)
        else:
            raise ValueError(f"Playlist ID is missing in source_configuration for channel {channel_name}")
    else:
        raise ValueError(f"Unsupported source_type: {source_type}")
        
    if not videos:
        logging.warning(f"[-] No suitable unseen videos/clips found for channel {channel_name}.")
        return {
            "channel_name": channel_name,
            "shorts_created": 0,
            "uploads": [],
            "status": "No candidate videos",
            "error": None
        }

    now_utc = datetime.now(timezone.utc)
    base_publish_time = now_utc + timedelta(hours=interval_hours)
    
    uploaded_count = 0
    uploads_info = []
    upload_error = None
    
    for video in videos:
        if uploaded_count >= shorts_per_run:
            logging.info(f"[+] Target run goal of {shorts_per_run} scheduled Shorts achieved for {channel_name}!")
            break
            
        logging.info(f"\n>>> Processing Candidate [{uploaded_count + 1}/{shorts_per_run}]: {video['title']} (ID: {video['video_id']})")
        time.sleep(2)
        
        # 1. Download Video
        video_path = None
        if source_type == "twitch":
            video_path = download_twitch_clip(video)
        else:
            video_path = download_video(video['video_id'])
            
        if not video_path or not os.path.exists(video_path):
            logging.error(f"[!] Downloading video failed for ID: {video['video_id']}")
            if source_type == "twitch":
                mark_twitch_seen(video['video_id'])
            else:
                mark_youtube_seen(video['video_id'])
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
            if source_type == "twitch":
                mark_twitch_seen(video['video_id'])
            else:
                mark_youtube_seen(video['video_id'])
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
            if source_type == "twitch":
                mark_twitch_seen(video['video_id'])
            else:
                mark_youtube_seen(video['video_id'])
            cleanup_disk()
            continue
            
        # 5. Metadata Generation (Pass the dynamic Niche parameter!)
        metadata = generate_metadata(video['title'], niche=niche)
        
        # 6. Calculate Scheduled Publish Time
        scheduled_time = base_publish_time + timedelta(hours=uploaded_count * interval_hours)
        
        # 7. Upload & Schedule Short on YouTube
        try:
            uploaded_video_id = upload_short(
                processed_path, 
                metadata, 
                schedule_time=scheduled_time,
                token_info=token_info,
                token_path=token_path
            )
            uploaded_count += 1
            logging.info(f"[+] ({uploaded_count}/{shorts_per_run}) Successfully uploaded & scheduled clip {video['video_id']} for release at {scheduled_time.strftime('%H:%M')} UTC!")
            uploads_info.append({
                "video_id": uploaded_video_id,
                "title": metadata['title'],
                "publish_time": scheduled_time.strftime('%Y-%m-%dT%H:%M:%S.000Z')
            })
            if source_type == "twitch":
                mark_twitch_seen(video['video_id'])
            else:
                mark_youtube_seen(video['video_id'])
        except Exception as e:
            logging.error(f"[!] Upload failed for video {video['video_id']}: {e}")
            upload_error = str(e)
            cleanup_disk()
            
            # Detect credentials, OAuth, or connection-related exceptions
            err_str = str(e).lower()
            is_auth_error = any(kw in err_str for kw in ["invalid_grant", "credentials", "token", "unauthorized", "auth"])
            is_network_error = any(kw in err_str for kw in ["transport", "connection", "socket", "timeout"])
            
            if is_auth_error or is_network_error:
                logging.error("[!] Authentication or network error detected. Aborting channel pipeline loop.")
                break
                
            # For other transient or video-specific errors, mark seen and continue
            if source_type == "twitch":
                mark_twitch_seen(video['video_id'])
            else:
                mark_youtube_seen(video['video_id'])
            continue
            
        cleanup_disk()
        
        time.sleep(5)
        
    status = "Success"
    if upload_error:
        if uploaded_count > 0:
            status = "Partial Success"
        else:
            status = "Failed"
            
    return {
        "channel_name": channel_name,
        "shorts_created": uploaded_count,
        "uploads": uploads_info,
        "status": status,
        "error": upload_error
    }

def print_report(report):
    print("\n" + "=" * 60)
    print("                 AUTOMATION BATCH RUN REPORT")
    print("=" * 60)
    for r in report:
        print(f"Channel Name:   {r['channel_name']}")
        print(f"Status:         {r['status']}")
        print(f"Shorts Created: {r['shorts_created']}")
        if r['uploads']:
            print("Scheduled Uploads:")
            for u in r['uploads']:
                print(f"  - [{u['video_id']}] {u['title']} (Publish: {u['publish_time']})")
        if r['error']:
            print(f"Error:          {r['error']}")
        print("-" * 60)
    print("=" * 60 + "\n")

def save_report(report):
    report_dir = os.path.join(config.DATA_DIR, "reports")
    os.makedirs(report_dir, exist_ok=True)
    report_file = os.path.join(report_dir, f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    latest_report_file = os.path.join(config.DATA_DIR, "latest_run_report.json")
    
    report_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": report
    }
    
    for fpath in [report_file, latest_report_file]:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=4)
            
    logging.info(f"[+] Run report saved to {latest_report_file}")

def run_multi_channel(channels_file="channels.json", default_count=6, default_gap=2):
    if not os.path.exists(channels_file):
        logging.error(f"Channels configuration file '{channels_file}' does not exist.")
        sys.exit(1)
        
    with open(channels_file, "r", encoding="utf-8") as f:
        try:
            channels = json.load(f)
        except Exception as e:
            logging.error(f"Failed to parse channels configuration file: {e}")
            sys.exit(1)
            
    if not isinstance(channels, list):
        logging.error("Channels configuration must be a JSON array of channel objects.")
        sys.exit(1)
        
    logging.info(f"[*] Loaded {len(channels)} channel configurations from '{channels_file}'.")
    
    report = []
    
    for channel in channels:
        channel_name = channel.get("channel_name", "Unknown Channel")
        try:
            res = run_channel_pipeline(channel, default_count=default_count, default_gap=default_gap)
            report.append(res)
        except Exception as e:
            logging.error(f"[!] Pipeline failed for channel '{channel_name}': {e}", exc_info=True)
            report.append({
                "channel_name": channel_name,
                "shorts_created": 0,
                "uploads": [],
                "status": "Failed",
                "error": str(e)
            })
            
    print_report(report)
    save_report(report)
    
    # Send execution summary notification
    try:
        notify_report(report)
    except Exception as e:
        logging.error(f"[!] Failed to execute notification flow: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Channel YouTube Shorts Scheduled Automation Pipeline")
    parser.add_argument("--channels", type=str, default="channels.json", help="Path to channels.json configuration file")
    parser.add_argument("--count", type=int, default=6, help="Default number of Shorts to generate and schedule in one daily batch run (default: 6)")
    parser.add_argument("--gap", type=int, default=2, help="Default minimum gap in hours between scheduled video releases (default: 2)")
    parser.add_argument("--loop", action="store_true", help="Run continuously in 24/7 loop mode instead of single trigger mode")
    args = parser.parse_args()

    print("[Bot] Multi-Channel YouTube Shorts Scheduled Automation Bot Initiated [Bot]")
    
    if args.loop:
        logging.info("[*] Running in continuous loop mode...")
        while True:
            try:
                run_multi_channel(channels_file=args.channels, default_count=args.count, default_gap=args.gap)
                logging.info("[*] Sleeping 24 hours until next daily batch cycle...")
                time.sleep(86400)
            except Exception as e:
                logging.error(f"[!] Pipeline crashed: {e}")
                time.sleep(300)
    else:
        logging.info(f"[*] Running multi-channel scheduled batch mode...")
        run_multi_channel(channels_file=args.channels, default_count=args.count, default_gap=args.gap)
        sys.exit(0)
