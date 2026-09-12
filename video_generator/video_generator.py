
#!/usr/bin/env python3
"""
AINEWS Video Generator — creates 9:16 MP4 Short from news inputs.
Uses ONLY: Python + Pillow (optional) + FFmpeg + existing inputs.
No paid AI video APIs (OpenAI, Sora, Veo, etc.).
"""
import os, sys
sys.path.insert(0, '.')
from .scene_builder import build_all_scenes
from .renderer import render_video

def generate_video(
    title="Breaking News",
    script="",
    image_path="",
    source="News",
    source_url="",
    narration_path="",
    subtitles_path=""
):
    news_item = {
        "title": title,
        "description": script,
        "source": source,
        "url": source_url,
        "thumbnail_url": image_path,
        "video_id": "short_video"
    }
    scenes = build_all_scenes(news_item)
    # Render (placeholder for full pipeline; real use creates output for upload)
    output = render_video(scenes, narration_path, subtitles_path, "output/news_short.mp4", duration_target=30)
    # Verify file exists
    import os
    video_path = os.path.join("data/processed", f"news_{news_item['video_id']}.mp4")
    # Fallback: if renderer didn't create file, create via create_news_clip logic
    if not os.path.exists(output) and not os.path.exists(video_path):
        from src.news_clip_builder import create_news_clip
        video_path = create_news_clip(news_item, "data/processed", platform="youtube")
        if video_path and os.path.exists(video_path):
            output = video_path
    if os.path.exists(output) or (video_path and os.path.exists(video_path)):
        final_path = output if os.path.exists(output) else video_path
        print(f"VIDEO GENERATED SUCCESSFULLY: {final_path}")
        return final_path
    else:
        print("VIDEO GENERATION FAILED: no output file produced")
        return None

if __name__ == "__main__":
    # Example usage (pipeline calls generate_video() programmatically)
    result = generate_video(
        title="Example News",
        script="This is a breaking news story.",
        image_path="",
        source="Example News",
        source_url="",
        narration_path="",
        subtitles_path=""
    )
    print(f"Result: {result}")
