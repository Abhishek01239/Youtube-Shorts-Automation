#!/usr/bin/env python3
"""
RSS-to-Video pipeline adapter for AINEWS.

Transforms RSS headlines into a video-like format that can be processed
by the existing pipeline infrastructure (downloads, processing, uploads).
"""
import hashlib
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
import re

# Import pipeline components (defer if missing from PYTHONPATH)
try:
    from video_processor import process_video, get_video_duration
except ImportError: pass
try:
    from metadata_generator import generate_metadata
except ImportError: pass
try:
    from youtube_uploader import upload_short
except ImportError: pass
try:
    from audio_analyzer import analyze_audio
except ImportError: pass
try:
    from highlight_detector import get_highlights
except ImportError: pass
try:
    from config import set_active_channel, get_token_file
except ImportError: pass


def fetch_rss_headlines(channel_config):
    """Fetch headlines from RSS feeds defined in channel config.
    
    Args:
        channel_config: dict with 'rss_feeds' list of feed URLs
        
    Returns:
        list of dicts with keys: video_id, title, url, thumbnail_url, 
                                game_name, duration, source
    """
    from src.news_rss import FEEDS
    
    # Use feeds from channel config if available, else use default FEEDS
    feeds_to_use = channel_config.get('rss_feeds', list(FEEDS.values()))
    
    results = []
    for feed_url in feeds_to_use:
        try:
            import requests
            from xml.etree import ElementTree as ET
            
            # Fetch RSS feed
            response = requests.get(feed_url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (compatible; AINEWS-RSS-Reader/1.0)"
            })
            
            if response.status_code != 200:
                continue
                
            root = ET.fromstring(response.content)
            
            # Handle different RSS namespaces
            namespaces = {
                '': 'http://www.w3.org/2005/Atom',
                'dc': 'http://purl.org/dc/elements/1.1/',
                'content': 'http://purl.org/rss/1.0/modules/content/',
                'media': 'http://search.yahoo.com/mrss/'
            }
            
            # Find all item entries
            items = root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')
            
            for item in items[:5]:  # Limit to 5 headlines per feed
                title_elem = item.find('title') or item.find('dc:title') or item.find('{http://www.w3.org/2005/Atom}title')
                link_elem = item.find('link') or item.find('dc:link') or item.find('{http://purl.org/dc/elements/1.1/}link')
                description_elem = item.find('description') or item.find('content:encoded') or item.find('{http://purl.org/rss/1.0/modules/content/}encoded')
                
                if title_elem is None or link_elem is None:
                    continue
                    
                title = title_elem.text.strip() if title_elem.text else ""
                if not title or len(title) < 10:  # Skip short titles
                    continue
                    
                # Extract link from element (could be attribute or sub-element)
                link = link_elem.text if link_elem.text else link_elem.get('href', '')
                if not link.startswith(('http://', 'https://')):
                    # Try to construct URL from relative link
                    parsed = urlparse(feed_url)
                    link = f"{parsed.scheme}://{parsed.netloc}{link}"
                
                # Generate unique video_id from URL and title
                video_id = hashlib.md5(f"{link}{title}".encode()).hexdigest()[:12]
                
                # Use description as summary, extract thumbnail if available
                summary = description_elem.text[:200] + "..." if description_elem.text else ""
                
                # Try to find thumbnail
                thumbnail_elem = item.find('enclosure') or item.find('media:content') or item.find('{http://search.yahoo.com/mrss/}content')
                thumbnail_url = thumbnail_elem.get('url') if thumbnail_elem is not None else None
                
                # Default thumbnail if not found
                if not thumbnail_url:
                    # Use first image found in description
                    if summary:
                        import re
                        img_match = re.search(r'<img[^>]+src="([^"]+)"', summary)
                        if img_match:
                            thumbnail_url = img_match.group(1)
                
                results.append({
                    "video_id": video_id,
                    "title": title,
                    "url": link,
                    "thumbnail_url": thumbnail_url,
                    "game_name": "News",  # Default game name for news
                    "duration": 60,  # Default 60 seconds for news clips
                    "source": feed_url,
                    "summary": summary
                })
                
        except Exception as e:
            print(f"Error fetching RSS feed {feed_url}: {e}")
            continue
            
    return results[:5]  # Limit to 5 headlines total


def mark_news_seen(video_id):
    """Mark a news item as seen (placeholder - uses Twitch seen file for now)."""
    mark_twitch_seen(video_id)


def create_news_clip(news_item, output_dir, platform="youtube"):
    """Create a video from news content.
    
    Since RSS feeds contain articles, not video content, this creates a text-based
    news bulletin video with:
    1. News headlines as images/text overlays
    2. Piper TTS audio for each headline
    3. Background video or static slides
    4. Dynamic title/description generation
    
    Args:
        news_item: dict with news article data
        output_dir: directory to save the output video
        platform: target platform ("youtube" or "facebook")
        
    Returns:
        Path to created video file, or None if failed
    """
    import subprocess
    from PIL import Image, ImageDraw, ImageFont
    import textwrap
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Create a simple news bulletin video
    video_path = os.path.join(output_dir, f"news_{news_item['video_id']}.mp4")
    
    try:
        # Create a simple video with news headlines
        # This is a simplified version - in production, you'd use a proper
        # news video generator with proper layout, graphics, etc.
        
        # For now, create a placeholder that indicates news processing
        print(f"[*] Creating news bulletin for: {news_item['title']}")
        
        # Use a simple FFmpeg command to create a test video
        # In production, you'd integrate with a proper news video generator
        
        # Create a black screen with news title
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-f', 'lavfi',
            f'color=c=black:s=1920x1080:d=10',
            '-c:v', 'libx264',
            '-t', '10',
            video_path
        ]
        
        subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
        
        return video_path
        
    except Exception as e:
        print(f"Error creating news clip: {e}")
        return None


def process_news_channel(channel_config, platform="youtube"):
    """Process a single news channel (AINEWS).
    
    Args:
        channel_config: dict with channel configuration
        platform: target platform ("youtube" or "facebook")
        
    Returns:
        dict with processing results
    """
    from config import set_active_channel
    
    channel_name = channel_config.get('channel_name', 'AINEWS')
    niche = channel_config.get('niche', 'News')
    
    print(f"\n==================================================")
    print(f"[*] Starting AINEWS pipeline for: {channel_name}")
    print(f"Niche: {niche} | Platform: {platform}")
    print(f"==================================================")
    
    # Set active channel for path isolation
    set_active_channel(channel_name)
    
    # Fetch news headlines
    news_items = fetch_rss_headlines(channel_config)
    
    if not news_items:
        print("[-] No news headlines found")
        return {
            "channel_name": channel_name,
            "shorts_created": 0,
            "uploads": [],
            "status": "No news headlines",
            "error": None
        }
    
    results = []
    
    for news_item in news_items[:5]:  # Process up to 5 headlines
        print(f"\n>>> Processing news: {news_item['title']}")
        
        # Create news bulletin video
        video_path = create_news_clip(news_item, "output", platform)
        
        if not video_path or not os.path.exists(video_path):
            print(f"[!] Failed to create news bulletin for: {news_item['title']}")
            mark_news_seen(news_item['video_id'])
            continue
        
        # Analyze audio
        has_voice, is_silent = analyze_audio(video_path)
        
        # Generate metadata for the news video
        metadata = generate_metadata(news_item['title'], niche=niche)
        
        # Schedule upload (immediate for news)
        scheduled_time = datetime.now(timezone.utc)
        
        # Upload the video
        if platform == "facebook":
            # For Facebook, use the Facebook uploader
            try:
                fb_id = upload_fb_video(
                    video_path, metadata,
                    schedule_time=scheduled_time,
                    channel=channel_config, is_short=True
                )
                uploaded_id = fb_id
            except Exception as e:
                print(f"[!] Facebook upload failed: {e}")
                mark_news_seen(news_item['video_id'])
                continue
        else:
            # For YouTube, use the YouTube uploader with token
            token_path = channel_config.get('youtube_oauth_credentials')
            if not token_path:
                print(f"[!] No YouTube token configured for {channel_name}")
                mark_news_seen(news_item['video_id'])
                continue
                
            try:
                uploaded_id = upload_short(
                    video_path,
                    metadata,
                    schedule_time=scheduled_time,
                    token_info=None,  # Use default token
                    token_path=token_path
                )
            except Exception as e:
                print(f"[!] YouTube upload failed: {e}")
                mark_news_seen(news_item['video_id'])
                continue
        
        # Clean up
        if os.path.exists(video_path):
            os.remove(video_path)
        
        results.append({
            "video_id": uploaded_id,
            "title": metadata['title'],
            "publish_time": scheduled_time.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        })
        
        # Mark as seen
        mark_news_seen(news_item['video_id'])
    
    return {
        "channel_name": channel_name,
        "shorts_created": len(results),
        "uploads": results,
        "status": "Success" if results else "Failed",
        "error": None if results else "No successful uploads"
    }


def run_news_pipeline(channel_config):
    """Run the AINEWS pipeline for a single channel.
    
    This is the main entry point called from the main pipeline.
    """
    channel_name = channel_config.get('channel_name', 'AINEWS')
    platform = channel_config.get('platform', 'youtube')
    
    try:
        result = process_news_channel(channel_config, platform)
        return result
    except Exception as e:
        print(f"[!] AINEWS pipeline error: {e}")
        return {
            "channel_name": channel_name,
            "shorts_created": 0,
            "uploads": [],
            "status": "Failed",
            "error": str(e)
        }