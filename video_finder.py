import os
import random
from googleapiclient.discovery import build
from config import YOUTUBE_API_KEY, TARGET_NICHES, MAX_SUBS, SEEN_VIDEOS_FILE

def get_seen_videos():
    if not os.path.exists(SEEN_VIDEOS_FILE):
        return set()
    with open(SEEN_VIDEOS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f.readlines())

def mark_video_seen(video_id):
    with open(SEEN_VIDEOS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{video_id}\n")

def find_videos():
    """
    Finds recent unseen gaming videos by querying target niches.
    Iterates through niches until fresh candidates are found.
    """
    if not YOUTUBE_API_KEY:
        raise ValueError("YOUTUBE_API_KEY is missing!")
        
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
    seen_videos = get_seen_videos()
    
    niches = list(TARGET_NICHES)
    random.shuffle(niches)
    
    videos = []
    
    for niche in niches:
        print(f"[*] Searching YouTube for niche: '{niche}'...")
        try:
            search_response = youtube.search().list(
                q=niche,
                part='id,snippet',
                maxResults=50,
                type='video',
                videoDuration='medium',
                order='date'
            ).execute()
            
            for item in search_response.get('items', []):
                video_id = item['id']['videoId']
                channel_id = item['snippet']['channelId']
                title = item['snippet']['title']
                
                if video_id in seen_videos:
                    continue
                    
                # Check channel subscriber count
                try:
                    channel_response = youtube.channels().list(
                        part='statistics',
                        id=channel_id
                    ).execute()
                    
                    if channel_response.get('items'):
                        stats = channel_response['items'][0].get('statistics', {})
                        subs = int(stats.get('subscriberCount', 0))
                        if subs >= MAX_SUBS:
                            continue
                except Exception:
                    pass # If channel stats check fails, keep video as candidate
                    
                videos.append({
                    'video_id': video_id,
                    'title': title,
                    'channel_id': channel_id
                })
                
            if videos:
                # Found fresh candidate videos in this niche!
                print(f"[+] Found {len(videos)} fresh candidate videos in niche '{niche}'")
                break
                
        except Exception as e:
            print(f"[!] Search error for niche '{niche}': {e}")
            continue
            
    random.shuffle(videos)
    return videos

if __name__ == "__main__":
    vids = find_videos()
    print(f"Found {len(vids)} matching videos.")
