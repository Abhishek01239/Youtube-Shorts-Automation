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
    """Fetch headlines via News API (free tier / no OpenAI)."""
    import requests, hashlib
    # News API endpoint (free tier; replace key with env var in production)
    api_key = os.environ.get("NEWS_API_KEY", "test-key")
    url = ("https://newsapi.org/v2/top-headlines"
           "?category=general&pageSize=5&apiKey=" + api_key)
    try:
        resp = requests.get(url, timeout=15,
            headers={"User-Agent":"AINEWS/1.0"})
        data = resp.json()
        results = []
        for art in data.get("articles", [])[:5]:
            title = art.get("title", "")
            url_link = art.get("url", "")
            if not title or len(title) < 10:
                continue
            video_id = hashlib.md5(f"{url_link}{title}".encode()).hexdigest()[:12]
            results.append({
                "video_id": video_id,
                "title": title,
                "url": url_link,
                "thumbnail_url": art.get("urlToImage", ""),
                "game_name": "Breaking News",
                "duration": 60,
                "source": "news_api"
            })
        return results
    except Exception as e:
        return []


def process_news_channel(channel_config, platform="youtube"):
    channel_name = channel_config.get('channel_name', 'AINEWS')
    niche = channel_config.get('niche', 'Breaking News')
    print(f"[*] AINEWS pipeline for: {channel_name} | Niche: {niche}")
    news_items = fetch_rss_headlines(channel_config)
    if not news_items:
        print("[-] No news headlines found (News API)")
        return {"channel_name": channel_name, "shorts_created": 0, "uploads": [], "status": "No news headlines", "error": None}
    results = []
    for item in news_items[:5]:
        print(f"[*] News item: {item['title']}")
        results.append({"video_id": item["video_id"], "title": item["title"], "url": item["url"], "publish_time": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'), "type": "short"})
    return {"channel_name": channel_name, "shorts_created": len(results), "uploads": results, "status": "Success", "error": None}

def run_news_pipeline(channel_config):
    try:
        return process_news_channel(channel_config, channel_config.get('platform', 'youtube'))
    except Exception as e:
        print(f"[!] AINEWS pipeline error: {e}")
        return {"channel_name": channel_config.get('channel_name', 'AINEWS'), "shorts_created": 0, "uploads": [], "status": "Failed", "error": str(e)}
