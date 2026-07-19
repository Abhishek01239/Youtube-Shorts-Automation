import os
import random
from googleapiclient.discovery import build
from config import YOUTUBE_API_KEY, TARGET_NICHES, MAX_SUBS, SEEN_VIDEOS_FILE

def get_seen_videos():
    if not os.path.exists(SEEN_VIDEOS_FILE):
        return set()
    with open(SEEN_VIDEOS_FILE, "r") as f:
        return set(line.strip() for line in f.readlines())

def mark_video_seen(video_id):
    with open(SEEN_VIDEOS_FILE, "a") as f:
        f.write(f"{video_id}\n")

def find_videos():
    """Finds recent Minecraft videos from channels with < 20K subs."""
    if not YOUTUBE_API_KEY:
        raise ValueError("YOUTUBE_API_KEY is missing!")
        
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
    seen_videos = get_seen_videos()
    
    # 1. Search for videos using a randomly selected niche
    selected_niche = random.choice(TARGET_NICHES)
    print(f"[*] Searching YouTube for niche: '{selected_niche}'...")
    
    search_response = youtube.search().list(
        q=selected_niche,
        part='id,snippet',
        maxResults=50,
        type='video',
        videoDuration='medium', # 4-20 minutes usually good for highlights
        order='date'
    ).execute()
    
    videos = []
    for item in search_response.get('items', []):
        video_id = item['id']['videoId']
        channel_id = item['snippet']['channelId']
        title = item['snippet']['title']
        
        if video_id in seen_videos:
            continue
            
        # 2. Check channel subscriber count
        channel_response = youtube.channels().list(
            part='statistics',
            id=channel_id
        ).execute()
        
        if not channel_response['items']:
            continue
            
        stats = channel_response['items'][0].get('statistics', {})
        subs = int(stats.get('subscriberCount', 0))
        
        if subs < MAX_SUBS:
            videos.append({
                'video_id': video_id,
                'title': title,
                'channel_id': channel_id,
                'subs': subs
            })
            
    # Return shuffled list to randomize processing order
    random.shuffle(videos)
    return videos

if __name__ == "__main__":
    vids = find_videos()
    print(f"Found {len(vids)} matching videos.")
