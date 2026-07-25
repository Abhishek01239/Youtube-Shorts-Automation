import os
import random
from googleapiclient.discovery import build
import config

def get_seen_videos():
    seen_file = config.get_seen_videos_file()
    if not os.path.exists(seen_file):
        return set()
    with open(seen_file, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f.readlines() if line.strip())

def mark_video_seen(video_id):
    seen_file = config.get_seen_videos_file()
    parent_dir = os.path.dirname(os.path.abspath(seen_file))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    with open(seen_file, "a", encoding="utf-8") as f:
        f.write(f"{video_id}\n")

def find_videos(niche_query=None, max_subs=None):
    """
    Finds recent unseen gaming videos by querying target niches.
    Iterates through niches until fresh candidates are found.
    """
    api_key = config.YOUTUBE_API_KEY
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY is missing!")
        
    youtube = build('youtube', 'v3', developerKey=api_key)
    seen_videos = get_seen_videos()
    
    if niche_query:
        niches = [niche_query] if isinstance(niche_query, str) else list(niche_query)
    else:
        niches = list(config.TARGET_NICHES)
        
    random.shuffle(niches)
    
    limit_subs = max_subs if max_subs is not None else config.MAX_SUBS
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
                video_id = item['id'].get('videoId')
                if not video_id:
                    continue
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
                        if subs >= limit_subs:
                            continue
                except Exception:
                    pass # If channel stats check fails, keep video as candidate
                    
                videos.append({
                    'video_id': video_id,
                    'title': title,
                    'channel_id': channel_id
                })
                
            if videos:
                print(f"[+] Found {len(videos)} fresh candidate videos in niche '{niche}'")
                break
                
        except Exception as e:
            print(f"[!] Search error for niche '{niche}': {e}")
            continue
            
    random.shuffle(videos)
    return videos

def find_playlist_videos(playlist_id):
    """
    Retrieves recent videos from a specified YouTube playlist.
    """
    api_key = config.YOUTUBE_API_KEY
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY is missing!")
        
    youtube = build('youtube', 'v3', developerKey=api_key)
    seen_videos = get_seen_videos()
    videos = []
    
    print(f"[*] Fetching videos from YouTube Playlist: '{playlist_id}'...")
    try:
        response = youtube.playlistItems().list(
            playlistId=playlist_id,
            part='snippet',
            maxResults=50
        ).execute()
        
        for item in response.get('items', []):
            snippet = item.get('snippet', {})
            res_id = snippet.get('resourceId', {})
            video_id = res_id.get('videoId')
            title = snippet.get('title', 'Playlist Video')
            
            if video_id and video_id not in seen_videos:
                videos.append({
                    'video_id': video_id,
                    'title': title
                })
        print(f"[+] Found {len(videos)} unseen videos in playlist '{playlist_id}'")
    except Exception as e:
        print(f"[!] Error fetching playlist items: {e}")
        
    random.shuffle(videos)
    return videos

if __name__ == "__main__":
    vids = find_videos()
    print(f"Found {len(vids)} matching videos.")
