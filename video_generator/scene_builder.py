
import os, tempfile

def build_scene(title, description, source, image_path=None):
    """Build a single scene description dict."""
    return {
        "title": title,
        "subtitle": description[:200] if description else "Breaking News",
        "source": source,
        "image_path": image_path,
        "duration": 7
    }

def build_all_scenes(news_item):
    scenes = [
        build_scene("HOOK", news_item.get("title", ""), news_item.get("source", ""), news_item.get("thumbnail_url", "")),
        build_scene("WHAT HAPPENED", "Key information from news source.", news_item.get("source", ""), news_item.get("thumbnail_url", "")),
        build_scene("KEY INFO", "Details and important points.", news_item.get("source", ""), news_item.get("thumbnail_url", "")),
        build_scene("WHY IT MATTERS", "Impact and significance.", news_item.get("source", ""), news_item.get("thumbnail_url", "")),
        build_scene("SOURCE", f"Source: {news_item.get('source', '')}", "", news_item.get("thumbnail_url", ""))
    ]
    return scenes
